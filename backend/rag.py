import re

from providers import embed_texts, generate_answer, generate_general_answer
from store import insert_chunks, insert_document, search_chunks


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


def split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    sentences = re.split(r"(?<=[.!?。！？])\s*", text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            overlap_text = current[-overlap:].strip()
            current = f"{overlap_text} {sentence}".strip() if overlap_text else sentence
        else:
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
                    results.append({"text": sub_chunk, "heading_path": heading_path})

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
    embeddings = embed_texts(chunk_texts)
    count = insert_chunks(
        document_id=doc_id,
        chunks=chunk_texts,
        embeddings=embeddings,
        heading_paths=heading_paths,
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


def chat(query: str, top_k: int = DEFAULT_TOP_K, use_rag: bool = True) -> dict:
    if not use_rag:
        answer = generate_general_answer(query=query)
        return {"answer": answer, "contexts": [], "sources": [], "mode": "general"}

    lang = _detect_query_language(query)
    hits = search(query=query, top_k=top_k, language=lang)
    top_score = hits[0]["score"] if hits else -1.0
    sources = build_sources(hits)

    if top_score < FALLBACK_SCORE_THRESHOLD:
        answer = generate_general_answer(query=query)
        answer = f"{answer}\n\n命中分数：{top_score:.3f}"
        return {"answer": answer, "contexts": hits, "sources": sources, "mode": "general"}

    context_text = _build_context(hits)
    answer = generate_answer(query=query, contexts=[context_text])
    answer = f"{answer}\n\n命中分数：{top_score:.3f}"
    return {"answer": answer, "contexts": hits, "sources": sources, "mode": "rag"}
