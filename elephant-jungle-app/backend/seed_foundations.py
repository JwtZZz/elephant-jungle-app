import re
from pathlib import Path

from dotenv import load_dotenv

from providers import validate_provider_env
from rag import ingest_document
from store import get_chroma_collection, get_conn, init_db, sync_chroma_index


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def parse_md_file(path: Path) -> dict | None:
    """Parse a .md file with YAML frontmatter. Returns dict for ingest_document()."""
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        print(f"  [skip] {path.name}: no frontmatter found")
        return None

    frontmatter_text = m.group(1)
    content = m.group(2).strip()

    # Parse simple key: value frontmatter
    metadata: dict[str, str] = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            metadata[key] = value

    if not content:
        print(f"  [skip] {path.name}: empty content")
        return None

    return {
        "source": metadata.get("source", "Elephant Jungle Seed"),
        "title": metadata.get("title", path.stem),
        "url": metadata.get("url", f"seed://knowledge/{path.stem}"),
        "published_at": metadata.get("published_at"),
        "doc_type": metadata.get("doc_type"),
        "project": metadata.get("project"),
        "category": metadata.get("category"),
        "region": metadata.get("region"),
        "source_type": metadata.get("source_type"),
        "language": metadata.get("language"),
        "summary": metadata.get("summary"),
        "content": content,
    }


def document_exists(url: str, title: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM documents
            WHERE url = ? OR (title = ? AND source = 'Elephant Jungle Seed')
            LIMIT 1
            """,
            (url, title),
        ).fetchone()
    return row is not None


def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    validate_provider_env()
    init_db()

    with get_conn() as conn:
        seed_doc_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM documents WHERE source = 'Elephant Jungle Seed'"
            ).fetchall()
        ]
        if seed_doc_ids:
            placeholders = ",".join("?" for _ in seed_doc_ids)
            conn.execute(
                f"DELETE FROM chunks WHERE document_id IN ({placeholders})",
                seed_doc_ids,
            )
        removed = conn.execute(
            "DELETE FROM documents WHERE source = 'Elephant Jungle Seed'"
        ).rowcount
        conn.commit()
    print(f"  old seed documents removed: {removed}")

    try:
        get_chroma_collection().delete(where={"source": "Elephant Jungle Seed"})
    except Exception:
        pass

    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not md_files:
        print("No .md files found in knowledge/")
        return

    inserted = 0
    skipped = 0

    for md_path in md_files:
        print(f"Processing: {md_path.name}")
        item = parse_md_file(md_path)
        if item is None:
            skipped += 1
            continue

        if document_exists(item["url"], item["title"]):
            print(f"  [skip] already exists: {item['title']}")
            skipped += 1
            continue

        result = ingest_document(**item)
        print(f"  [ok] id={result['document_id']} chunks={result['chunks']} title={result['title']}")
        inserted += 1

    sync_chroma_index()
    print(f"\ndone: inserted={inserted} skipped={skipped} total_files={len(md_files)}")


if __name__ == "__main__":
    main()
