from providers import embed_texts, generate_answer, generate_general_answer
from store import insert_chunks, insert_document, search_chunks


CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
DEFAULT_TOP_K = 5
FALLBACK_SCORE_THRESHOLD = 0.35


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be larger than overlap")

    chunks: list[str] = []
    step = chunk_size - overlap
    i = 0
    while i < len(clean):
        chunks.append(clean[i : i + chunk_size])
        i += step
    return chunks


def append_hit_score(answer: str, score: float) -> str:
    safe_score = max(0.0, score)
    return f"{answer}\n\n命中分数：{safe_score:.3f}"


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
    chunks = chunk_text(content)
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


def chat(query: str, top_k: int = DEFAULT_TOP_K) -> dict:
    hits = search(query=query, top_k=top_k)
    contexts = [h["content"] for h in hits]
    top_score = hits[0]["score"] if hits else -1.0
    sources = build_sources(hits)

    if top_score < FALLBACK_SCORE_THRESHOLD:
        answer = append_hit_score(generate_general_answer(query=query), top_score)
        return {"answer": answer, "contexts": hits, "sources": sources, "mode": "general"}

    answer = append_hit_score(generate_answer(query=query, contexts=contexts), top_score)
    return {"answer": answer, "contexts": hits, "sources": sources, "mode": "rag"}
