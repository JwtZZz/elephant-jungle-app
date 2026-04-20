import json
from pathlib import Path

from dotenv import load_dotenv

from providers import validate_provider_env
from rag import ingest_document
from store import get_conn, init_db, sync_chroma_index


BASE_DIR = Path(__file__).resolve().parent
SEED_PATH = BASE_DIR / "seeds" / "web3_foundations.json"


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

    items = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    inserted = 0
    skipped = 0

    for item in items:
        if document_exists(item["url"], item["title"]):
            skipped += 1
            continue

        ingest_document(**item)
        inserted += 1

    sync_chroma_index()
    print(f"inserted={inserted} skipped={skipped} total={len(items)}")


if __name__ == "__main__":
    main()
