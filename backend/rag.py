import json
import re

from providers import embed_texts, generate_answer, generate_general_answer
from providers import _chat_completion_raw
from store import insert_chunks, insert_document, search_chunks

from agent_tools import TOOL_DEFINITIONS, AGENT_SYSTEM_PROMPT, execute_tool


DEFAULT_TOP_K = 5
FALLBACK_SCORE_THRESHOLD = 0.35
WEB_CHUNK_SIZE = 900
PDF_CHUNK_SIZE = 1100
TABLE_CHUNK_SIZE = 1400
CHUNK_OVERLAP = 120


def normalize_document_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    normalized_lines: list[str] = []
    previous_blank = False

    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        is_blank = not line
        if is_blank:
            if not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue
        previous_blank = False
        normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()


def is_list_item(line: str) -> bool:
    return bool(re.match(r"^([-*•]|\d+[\.\)]|[a-zA-Z][\.\)])\s+", line))


def is_table_row(line: str) -> bool:
    if "|" in line:
        return True
    return bool(re.search(r"\S\s{2,}\S", line))


def detect_chunk_size(source_type: str | None, url: str | None) -> int:
    if source_type in {"file", "pdf"}:
        return PDF_CHUNK_SIZE
    if url and url.lower().endswith(".pdf"):
        return PDF_CHUNK_SIZE
    return WEB_CHUNK_SIZE


def parse_heading_level(line: str) -> int:
    """Return heading level 1-6 for markdown #-style headings, 0 otherwise."""
    m = re.match(r"^(#{1,6})\s+(.+)", line)
    if m:
        return len(m.group(1))
    return 0


def _extract_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving delimiters."""
    parts = re.split(r"(?<=[.!?。！？])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _sentence_overlap(text: str, target_chars: int = 120) -> str:
    """Take the last ~target_chars worth of complete sentences as overlap."""
    sentences = _extract_sentences(text)
    overlap = ""
    for s in reversed(sentences):
        s = s.strip()
        if not s:
            continue
        candidate = f"{s} {overlap}".strip() if overlap else s
        if len(candidate) > target_chars and overlap:
            break
        overlap = candidate
    return overlap


def split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Four-layer priority splitting: paragraph → sentence → character window.

    1. Entire text fits → single chunk.
    2. Split by paragraph (blank line) — each paragraph stays intact if possible.
    3. Long paragraphs split by sentence boundaries.
    4. Single sentence exceeds chunk_size → character-window fallback.

    Overlap is always at sentence level (not fixed character count).
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    # Layer 2: paragraph boundaries
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) <= chunk_size:
            chunks.append(para)
            continue

        # Layer 3: sentence boundaries
        sentences = _extract_sentences(para)
        current = ""

        for sentence in sentences:
            if not sentence:
                continue

            candidate = f"{current} {sentence}".strip() if current else sentence

            if len(candidate) <= chunk_size:
                current = candidate
                continue

            if current:
                chunks.append(current)
                # Sentence-level overlap
                current = f"{_sentence_overlap(current, overlap)} {sentence}".strip()
            else:
                # Layer 4: character-window fallback for overlong sentence
                step = max(1, chunk_size - overlap)
                for i in range(0, len(sentence), step):
                    piece = sentence[i : i + chunk_size].strip()
                    if piece:
                        chunks.append(piece)
                current = ""

        if current:
            chunks.append(current)

    return chunks


def split_table_block(block: str, chunk_size: int) -> list[str]:
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    if not lines:
        return []

    chunks: list[str] = []
    current = lines[0]

    for row in lines[1:]:
        candidate = f"{current}\n{row}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        chunks.append(current)
        current = f"{lines[0]}\n{row}" if len(lines) > 1 else row

    if current:
        chunks.append(current)

    return chunks


def _classify_block(lines: list[str]) -> str:
    """Classify a block of lines as table, list, or paragraph."""
    for line in lines:
        if is_table_row(line):
            return "table"
        if is_list_item(line):
            return "list"
    return "paragraph"


def _chunk_block(block_text: str, kind: str, chunk_size: int, overlap: int) -> list[str]:
    if kind == "table":
        return split_table_block(block_text, TABLE_CHUNK_SIZE)
    return split_long_text(block_text, chunk_size, overlap)


def chunk_text(
    text: str,
    *,
    source_type: str | None = None,
    url: str | None = None,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """Split text into chunks, each with a heading_path for context.

    Returns list of dicts: {"text": str, "heading_path": str}
    Heading boundaries (# ## ###) are used as primary chunk boundaries.
    Within a section, tables and lists are detected and split separately.
    """
    if overlap < 0:
        raise ValueError("overlap must be non-negative")

    base_chunk_size = detect_chunk_size(source_type=source_type, url=url)
    lines = normalize_document_text(text).split("\n")

    # Build sections from heading hierarchy
    sections: list[tuple[str, str]] = []  # (heading_path, section_text)
    heading_stack: list[str] = []
    section_lines: list[str] = []

    def flush_section() -> None:
        nonlocal section_lines
        if not section_lines:
            return
        path = " > ".join(heading_stack) if heading_stack else ""
        body = "\n".join(section_lines).strip()
        if body:
            sections.append((path, body))
        section_lines = []

    for line in lines:
        level = parse_heading_level(line) if line else 0
        if level > 0:
            flush_section()
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_text = re.sub(r"^#+\s+", "", line).strip()
            heading_stack.append(heading_text)
            section_lines = [line]
        else:
            section_lines.append(line)

    flush_section()

    if not sections:
        return []

    # Within each section, detect block types and split
    results: list[dict] = []
    BLANK_RE = re.compile(r"^\s*$")

    for heading_path, section_text in sections:
        section_lines = section_text.split("\n")
        blocks: list[tuple[str, str]] = []  # (kind, text)
        current_kind = "paragraph"
        current_lines: list[str] = []
        pending_heading: str | None = None

        for line in section_lines:
            if not line.strip():
                if current_lines:
                    if pending_heading:
                        blocks.append(
                            (current_kind, f"{pending_heading}\n" + "\n".join(current_lines).strip())
                        )
                        pending_heading = None
                    else:
                        blocks.append((current_kind, "\n".join(current_lines).strip()))
                    current_lines = []
                current_kind = "paragraph"
                continue

            sub_level = parse_heading_level(line)
            if sub_level > 0:
                if current_lines:
                    body = "\n".join(current_lines).strip()
                    if pending_heading:
                        body = f"{pending_heading}\n{body}"
                    if body:
                        blocks.append((current_kind, body))
                    pending_heading = None
                    current_lines = []
                pending_heading = line
                current_kind = "paragraph"
                continue

            kind = _classify_block([line])
            if current_lines and kind != current_kind:
                body = "\n".join(current_lines).strip()
                if pending_heading:
                    body = f"{pending_heading}\n{body}"
                    pending_heading = None
                if body:
                    blocks.append((current_kind, body))
                current_lines = []
            current_kind = kind
            current_lines.append(line)

        if current_lines:
            body = "\n".join(current_lines).strip()
            if pending_heading:
                body = f"{pending_heading}\n{body}"
            if body:
                blocks.append((current_kind, body))

        for kind, block_text in blocks:
            for sub_chunk in _chunk_block(block_text, kind, base_chunk_size, overlap):
                sub_chunk = sub_chunk.strip()
                if sub_chunk:
                    results.append({
                        "text": sub_chunk,
                        "heading_path": heading_path,
                        "chunk_type": kind,
                    })

    return results


def build_sources(hits: list[dict]) -> list[dict]:
    seen_document_ids: set[int] = set()
    sources: list[dict] = []
    for hit in hits:
        document_id = int(hit["document_id"])
        if document_id in seen_document_ids:
            continue
        seen_document_ids.add(document_id)
        sources.append(
            {
                "document_id": document_id,
                "source": hit.get("source", ""),
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "published_at": hit.get("published_at", ""),
                "doc_type": hit.get("doc_type", ""),
                "project": hit.get("project", ""),
                "category": hit.get("category", ""),
                "region": hit.get("region", ""),
                "score": hit.get("score", 0.0),
            }
        )
    return sources


def ingest_document(
    *,
    source: str,
    content: str,
    title: str | None = None,
    url: str | None = None,
    published_at: str | None = None,
    doc_type: str | None = None,
    project: str | None = None,
    category: str | None = None,
    region: str | None = None,
    source_type: str | None = None,
    language: str | None = None,
    summary: str | None = None,
) -> dict:
    doc_id = insert_document(
        source=source,
        content=content,
        title=title,
        url=url,
        published_at=published_at,
        doc_type=doc_type,
        project=project,
        category=category,
        region=region,
        source_type=source_type,
        language=language,
        summary=summary,
    )
    chunk_dicts = chunk_text(content, source_type=source_type, url=url)
    if not chunk_dicts:
        return {"document_id": doc_id, "chunks": 0}

    chunk_texts = [c["text"] for c in chunk_dicts]
    heading_paths = [c["heading_path"] for c in chunk_dicts]
    chunk_types = [c.get("chunk_type", "paragraph") for c in chunk_dicts]
    embeddings = embed_texts(chunk_texts)
    count = insert_chunks(
        document_id=doc_id,
        chunks=chunk_texts,
        embeddings=embeddings,
        heading_paths=heading_paths,
        chunk_types=chunk_types,
    )
    return {
        "document_id": doc_id,
        "chunks": count,
        "title": title,
        "url": url,
        "source": source,
        "published_at": published_at,
        "doc_type": doc_type,
    }


def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    language: str | None = None,
) -> list[dict]:
    query_vector = embed_texts([query])[0]
    return search_chunks(query_embedding=query_vector, top_k=top_k)


def _detect_query_language(query: str) -> str | None:
    """Return 'zh' if query contains Chinese, 'en' if mostly ASCII, else None."""
    zh_chars = len(re.findall(r"[一-鿿]", query))
    if zh_chars >= 2:
        return "zh"
    if zh_chars == 0 and len(query) > 0:
        return "en"
    return None


def _build_context(hits: list[dict]) -> str:
    """Build RAG context string with heading paths and source info."""
    parts: list[str] = []
    for i, h in enumerate(hits):
        heading = h.get("heading_path", "")
        title = h.get("title", "") or ""
        heading_info = f" > {heading}" if heading else ""
        header = f"[{i + 1}] {title}{heading_info}"
        parts.append(f"{header}\n{h['content']}")
    return "\n\n".join(parts)


def chat(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    use_rag: bool = True,
    provider: str | None = None,
) -> dict:
    if not use_rag:
        answer = generate_general_answer(query=query, provider=provider)
        return {"answer": answer, "contexts": [], "sources": [], "mode": "general"}

    lang = _detect_query_language(query)
    hits = search(query=query, top_k=top_k, language=lang)
    top_score = hits[0]["score"] if hits else -1.0
    sources = build_sources(hits)

    if top_score < FALLBACK_SCORE_THRESHOLD:
        answer = generate_general_answer(query=query, provider=provider)
        answer = f"{answer}\n\n命中分数：{top_score:.3f}"
        return {"answer": answer, "contexts": hits, "sources": sources, "mode": "general"}

    context_text = _build_context(hits)
    answer = generate_answer(query=query, contexts=[context_text], provider=provider)
    answer = f"{answer}\n\n命中分数：{top_score:.3f}"
    return {"answer": answer, "contexts": hits, "sources": sources, "mode": "rag"}


MAX_AGENT_TURNS = 6


MAX_HISTORY_TURNS = 6

MEMORY_SUMMARIZER_PROMPT = (
    "你是一个记忆管理器。根据旧的记忆摘要和最新的对话，提炼更新后的记忆摘要。\n"
    "摘要应包含用户的兴趣、偏好、关注的话题、问过的币种等关键信息。\n"
    "只输出事实，不要评价。按条目组织，保持简洁，不超过200字。"
)


def update_memory_summary(
    old_summary: str,
    query: str,
    answer: str,
    provider: str | None = None,
) -> str:
    """Merge old memory summary with the latest Q&A turn into a new summary."""
    messages = [
        {"role": "system", "content": MEMORY_SUMMARIZER_PROMPT},
        {
            "role": "user",
            "content": (
                f"旧摘要：\n{old_summary if old_summary else '（无）'}\n\n"
                f"最新对话：\n用户：{query}\n助手：{answer}\n\n"
                f"更新后的摘要："
            ),
        },
    ]
    try:
        result = _chat_completion_raw(messages, temperature=0.1, provider=provider)
        return (result.get("content") or "").strip() or old_summary
    except Exception:
        return old_summary


TOOL_NAMES_ZH = {
    "get_market_coins": "查询市场行情",
    "get_okx_detail": "查询OKX盘口",
    "get_market_briefs": "查询快讯",
    "get_market_timeline": "查询新闻",
    "get_meme_trending": "查询Meme币",
    "get_whale_feed": "查询鲸鱼转账",
    "search_knowledge_base": "搜索知识库",
}


def agent_chat(
    query: str,
    history_messages: list[dict] | None = None,
    memory_summary: str | None = None,
    intent: str | None = None,
    on_event: callable = None,
    provider: str | None = None,
) -> dict:
    """Chat with tool-calling ability (market-data agent).

    Args:
        query: The current user query.
        history_messages: Optional previous {"role", "content"} pairs
                          for multi-turn context.
        memory_summary: Optional persistent memory summary to inject into context.
        intent: Optional intent hint from intent classifier. Skips KB
                pre-search when "market".
        on_event: Optional callback(event_type, message) for streaming status updates.
    """
    _emit = lambda t, m: on_event(t, m) if on_event else None

    system_content = AGENT_SYSTEM_PROMPT
    if memory_summary:
        system_content += f"\n\n【对话记忆】\n{memory_summary}"

    # Pre-search knowledge base for non-market intents so the LLM
    # doesn't need to decide to call search_knowledge_base.
    kb_context: str | None = None
    if intent != "market" and provider != "ollama":
        _emit("status", "正在搜索知识库...")
        try:
            hits = search(query, top_k=3)
            if hits and hits[0]["score"] >= FALLBACK_SCORE_THRESHOLD:
                kb_context = _build_context(hits)
        except Exception:
            pass

    messages: list[dict] = [
        {"role": "system", "content": system_content},
    ]
    if history_messages:
        messages.extend(history_messages)
    if kb_context:
        messages.append({
            "role": "user",
            "content": (
                f"以下是与问题可能相关的知识库内容（来自内部知识库搜索）：\n"
                f"{kb_context}\n\n"
                f"请基于这些信息回答，如果需要更多数据可以调用工具。\n\n"
                f"用户问题：{query}"
            ),
        })
    else:
        messages.append({"role": "user", "content": query})

    for turn in range(MAX_AGENT_TURNS):
        _emit("status", "正在思考下一步操作...")
        message = _chat_completion_raw(messages, tools=TOOL_DEFINITIONS, provider=provider)
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            _emit("status", "正在生成回答...")
            content = message.get("content", "") or ""
            return {"answer": content.strip(), "mode": "agent"}

        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}

            zh_name = TOOL_NAMES_ZH.get(func_name, func_name)
            _emit("tool_call", f"正在{zh_name}...")
            tool_result = execute_tool(func_name, func_args)
            _emit("tool_result", f"{zh_name}完成")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

    return {"answer": "抱歉，处理您的请求时超出了最大轮数，请重新提问。", "mode": "agent"}
