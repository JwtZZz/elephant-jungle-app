import json
import sqlite3
from pathlib import Path
from typing import Iterable

import chromadb


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "rag.db"
CHROMA_DIR = BASE_DIR / "chroma"
CHROMA_COLLECTION = "rag_chunks"
DOCUMENT_COLUMNS = {
    "title": "TEXT",
    "url": "TEXT",
    "published_at": "TEXT",
    "doc_type": "TEXT",
    "project": "TEXT",
    "category": "TEXT",
    "region": "TEXT",
    "source_type": "TEXT",
    "language": "TEXT",
    "summary": "TEXT",
}
CHUNK_COLUMNS = {
    "chunk_index": "INTEGER NOT NULL DEFAULT 0",
}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_chroma_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT,
                url TEXT,
                published_at TEXT,
                doc_type TEXT,
                project TEXT,
                category TEXT,
                region TEXT,
                source_type TEXT,
                language TEXT,
                summary TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )
        ensure_columns(conn, "documents", DOCUMENT_COLUMNS)
        ensure_columns(conn, "chunks", CHUNK_COLUMNS)


def insert_document(
    source: str,
    content: str,
    *,
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
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO documents(
                source, title, url, published_at, doc_type, project, category,
                region, source_type, language, summary, content
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                title,
                url,
                published_at,
                doc_type,
                project,
                category,
                region,
                source_type,
                language,
                summary,
                content,
            ),
        )
        return int(cur.lastrowid)


def get_document(document_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, source, title, url, published_at, doc_type, project, category,
                   region, source_type, language, summary, content, created_at
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"document {document_id} not found")
    return dict(row)


def build_chunk_metadata(document: dict, chunk_index: int) -> dict:
    metadata = {
        "document_id": int(document["id"]),
        "chunk_index": int(chunk_index),
        "source": document.get("source") or "",
        "title": document.get("title") or "",
        "url": document.get("url") or "",
        "published_at": document.get("published_at") or "",
        "doc_type": document.get("doc_type") or "",
        "project": document.get("project") or "",
        "category": document.get("category") or "",
        "region": document.get("region") or "",
        "source_type": document.get("source_type") or "",
        "language": document.get("language") or "",
    }
    return metadata


def insert_chunks(document_id: int, chunks: Iterable[str], embeddings: Iterable[list[float]]) -> int:
    chunk_list = list(chunks)
    embedding_list = list(embeddings)
    document = get_document(document_id)
    payload = [
        (document_id, index, chunk, json.dumps(embedding, ensure_ascii=False))
        for index, (chunk, embedding) in enumerate(zip(chunk_list, embedding_list))
    ]
    with get_conn() as conn:
        before_id = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM chunks").fetchone()["max_id"]
        conn.executemany(
            "INSERT INTO chunks(document_id, chunk_index, content, embedding_json) VALUES(?, ?, ?, ?)",
            payload,
        )
    chunk_ids = [str(before_id + index + 1) for index in range(len(payload))]
    chunk_metadatas = [build_chunk_metadata(document, index) for index in range(len(chunk_list))]
    collection = get_chroma_collection()
    collection.upsert(
        ids=chunk_ids,
        documents=chunk_list,
        embeddings=embedding_list,
        metadatas=chunk_metadatas,
    )
    return len(payload)


def load_all_chunks() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id,
                   c.document_id,
                   c.chunk_index,
                   c.content,
                   c.embedding_json,
                   d.source,
                   d.title,
                   d.url,
                   d.published_at,
                   d.doc_type,
                   d.project,
                   d.category,
                   d.region,
                   d.source_type,
                   d.language
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            ORDER BY c.id ASC
            """
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "document_id": int(row["document_id"]),
            "chunk_index": int(row["chunk_index"]),
            "content": row["content"],
            "embedding": json.loads(row["embedding_json"]),
            "metadata": {
                "document_id": int(row["document_id"]),
                "chunk_index": int(row["chunk_index"]),
                "source": row["source"] or "",
                "title": row["title"] or "",
                "url": row["url"] or "",
                "published_at": row["published_at"] or "",
                "doc_type": row["doc_type"] or "",
                "project": row["project"] or "",
                "category": row["category"] or "",
                "region": row["region"] or "",
                "source_type": row["source_type"] or "",
                "language": row["language"] or "",
            },
        }
        for row in rows
    ]


def sync_chroma_index() -> int:
    chunks = load_all_chunks()
    if not chunks:
        return 0

    collection = get_chroma_collection()
    collection.upsert(
        ids=[str(chunk["id"]) for chunk in chunks],
        documents=[chunk["content"] for chunk in chunks],
        embeddings=[chunk["embedding"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
    )
    return len(chunks)


def search_chunks(query_embedding: list[float], top_k: int) -> list[dict]:
    collection = get_chroma_collection()
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(1, top_k),
    )

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    hits = []
    for chunk_id, content, distance, metadata in zip(ids, documents, distances, metadatas):
        distance_value = float(distance) if distance is not None else 1.0
        score = max(0.0, 1.0 - distance_value)
        safe_metadata = metadata or {}
        hits.append(
            {
                "chunk_id": int(chunk_id),
                "document_id": int(safe_metadata.get("document_id", 0)),
                "chunk_index": int(safe_metadata.get("chunk_index", 0)),
                "content": content,
                "score": score,
                "distance": distance_value,
                "source": safe_metadata.get("source", ""),
                "title": safe_metadata.get("title", ""),
                "url": safe_metadata.get("url", ""),
                "published_at": safe_metadata.get("published_at", ""),
                "doc_type": safe_metadata.get("doc_type", ""),
                "project": safe_metadata.get("project", ""),
                "category": safe_metadata.get("category", ""),
                "region": safe_metadata.get("region", ""),
                "source_type": safe_metadata.get("source_type", ""),
                "language": safe_metadata.get("language", ""),
            }
        )
    return hits
