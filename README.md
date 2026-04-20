# Elephant Jungle

This project now runs in a single, simple way:

- `frontend/` contains the live static chat UI.
- `backend/` contains the FastAPI + RAG backend.
- `pixexport/` contains the sprite assets used by the UI.

## Run

### Backend

```powershell
cd "D:\elephant jungle\backend"
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```powershell
cd "D:\elephant jungle"
python -m http.server 5500
```

Open:

- `http://127.0.0.1:5500/frontend/index.html`

## Structure

- `backend/.env` stores local API keys and is not committed.
- `backend/rag.db` stores local metadata and is not committed.
- `backend/chroma/` stores the local vector index and is not committed.

## Notes

- The old Vite/React scaffold was removed to keep the workspace lighter and easier to run.
- If you want a React frontend later, we can add it back cleanly instead of keeping two frontends in parallel.
