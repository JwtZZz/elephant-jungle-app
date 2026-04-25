import re

from providers import embed_texts, generate_answer, generate_general_answer
from store import insert_chunks, insert_document, search_chunks


DEFAULT_TOP_K = 5
FALLBACK_SCORE_THRESHOLD = 0.35
RAG_PREFIX = "已经查询到最新更新的知识库内容整理："
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


def is_heading(line: str) -> bool:
    if not line:
        return False
    if line.startswith(("#", "##", "###")):
        return True
    if re.match(r"^(\d+(\.\d+)*|[IVXLC]+)[\).\s-]+", line):
        return True
    if len(line) <= 90 and line.endswith(":"):
        return True
    words = line.split()
    if 1 <= len(words) <= 12 and len(line) <= 90 and line == line.title():
        return True
    return False


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


def split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
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


def structure_blocks(text: str) -> list[tuple[str, str]]:
    lines = normalize_document_text(text).split("\n")
    blocks: list[tuple[str, str]] = []
    current_lines: list[str] = []
    current_kind = "paragraph"
    pending_heading: str | None = None

    def flush() -> None:
        nonlocal current_lines, current_kind, pending_heading
        if not current_lines:
            return
        body = "\n".join(current_lines).strip()
        if pending_heading:
            body = f"{pending_heading}\n{body}"
            pending_heading = None
        if body:
            blocks.append((current_kind, body))
        current_lines = []
        current_kind = "paragraph"

    for line in lines:
        if not line:
            flush()
            continue

        if is_heading(line):
            flush()
            pending_heading = line
            continue

        kind = "paragraph"
        if is_table_row(line):
            kind = "table"
        elif is_list_item(line):
            kind = "list"

        if current_lines and kind != current_kind:
            flush()

        current_kind = kind
        current_lines.append(line)

    flush()
    return blocks


def chunk_text(
    text: str,
    *,
    source_type: str | None = None,
    url: str | None = None,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    if overlap < 0:
        raise ValueError("overlap must be non-negative")

    blocks = structure_blocks(text)
    if not blocks:
        return []

    base_chunk_size = detect_chunk_size(source_type=source_type, url=url)
    chunks: list[str] = []

    for kind, block in blocks:
        if kind == "table":
            chunks.extend(split_table_block(block, TABLE_CHUNK_SIZE))
            continue
        chunks.extend(split_long_text(block, base_chunk_size, overlap))

    return [chunk.strip() for chunk in chunks if chunk.strip()]


def append_hit_score(answer: str, score: float) -> str:
    safe_score = max(0.0, score)
    return f"{answer}\n\n命中分数：{safe_score:.3f}"


def prepend_rag_prefix(answer: str) -> str:
    clean = answer.strip()
    if clean.startswith(RAG_PREFIX):
        return clean
    return f"{RAG_PREFIX}\n\n{clean}"


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
    chunks = chunk_text(content, source_type=source_type, url=url)
    if not chunks:
        return {"document_id": doc_id, "chunks": 0}
    embeddings = embed_texts(chunks)
    count = insert_chunks(document_id=doc_id, chunks=chunks, embeddings=embeddings)
    return {
        "document_id": doc_id,
        "chunks": count,
        "title": title,
        "url": url,
        "source": source,
        "published_at": published_at,
        "doc_type": doc_type,
    }


def search(query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    query_vector = embed_texts([query])[0]
    return search_chunks(query_embedding=query_vector, top_k=top_k)


def chat(query: str, top_k: int = DEFAULT_TOP_K, use_rag: bool = True) -> dict:
    if not use_rag:
        answer = generate_general_answer(query=query)
        return {"answer": answer, "contexts": [], "sources": [], "mode": "general"}

    hits = search(query=query, top_k=top_k)
    contexts = [h["content"] for h in hits]
    top_score = hits[0]["score"] if hits else -1.0
    sources = build_sources(hits)

    if top_score < FALLBACK_SCORE_THRESHOLD:
        answer = append_hit_score(generate_general_answer(query=query), top_score)
        return {"answer": answer, "contexts": hits, "sources": sources, "mode": "general"}

    answer = prepend_rag_prefix(generate_answer(query=query, contexts=contexts))
    answer = append_hit_score(answer, top_score)
    return {"answer": answer, "contexts": hits, "sources": sources, "mode": "rag"}
