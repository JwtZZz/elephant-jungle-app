# Minimal RAG Backend

## 1) Install

```bash
pip install -r requirements.txt
```

## 2) Configure

Copy `.env.example` to `.env` and set:

- `DASHSCOPE_API_KEY`
- `MINIMAX_API_KEY`

Service startup auto-loads `backend/.env`.
Optional model/url overrides are in `.env.example`.
Local secrets and local data are intentionally not committed:

- `backend/.env`
- `backend/rag.db`
- `backend/chroma/`

## 3) Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 4) APIs

- `POST /ingest`
  - body:
```json
{
  "source":"CoinDesk",
  "title":"Bitcoin ETF update",
  "url":"https://example.com/article",
  "published_at":"2026-04-19T09:00:00Z",
  "doc_type":"news",
  "project":"Bitcoin",
  "category":"etf",
  "region":"US",
  "source_type":"media",
  "language":"en",
  "summary":"Short optional summary",
  "content":"your document text"
}
```

- `POST /search`
  - body:
```json
{"query":"what is ...","top_k":5}
```

- `POST /chat`
  - body:
```json
{"query":"ask with rag","top_k":5}
```

`/chat` now prefers RAG results and falls back to general chat when retrieval confidence is low.
Embeddings are now indexed in Chroma, while SQLite keeps document and chunk metadata.
Search and chat results now also include source metadata so the frontend can show links and publication info.

## 5) Seed Fixed Web3 Knowledge

The project includes a small fixed Web3 knowledge seed set for concepts like Bitcoin, Ethereum, stablecoins, ETFs, Layer 2, DeFi, and wallet custody.

Run:

```bash
python seed_foundations.py
```
