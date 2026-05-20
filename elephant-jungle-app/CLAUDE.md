# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Elephant Jungle is a full-stack crypto intelligence platform with an AI agent that answers both real-time market data and knowledge-based questions through a unified chat interface.

## Tech Stack

- **Frontend**: React 18 + Vite (vanilla JSX)
- **Backend**: Python FastAPI
- **Vector DB**: ChromaDB (cosine similarity)
- **SQL DB**: SQLite (via `store.py`)
- **Cache**: Redis
- **Queue**: RabbitMQ (document ingestion)
- **LLM Providers**: DashScope (primary), BigModel, NVIDIA, MiniMax
- **MCP**: `mcp` CLI (FastMCP) for JSON-RPC over stdio subprocess communication
- **Embedding**: DashScope text-embedding-v4

## Architecture

```
frontend/  →  Chat UI (React + Vite)
backend/   →  FastAPI server with RAG + Agent system
pixexport/ →  Sprite assets for UI

### Agent Data Flow

Price queries → Intent classifier → Agent LLM → Tool call → MCP subprocess (JSON-RPC/stdio) → mcp_server.py → Backend API → CoinGecko/OKX/DexScreener/Arkham
Knowledge queries → Intent classifier → Agent LLM → Direct import → search_knowledge_base() → ChromaDB RAG
```

### Key Backend Files

| File | Responsibility |
|---|---|
| `main.py` | FastAPI routes, market data fetching (CoinGecko, OKX, DexScreener, Arkham), caching |
| `rag.py` | RAG pipeline (chunking, search, context assembly), agent chat loop, memory summary |
| `agent_tools.py` | Tool definitions (7 tools) and executors for the AI agent |
| `providers.py` | LLM provider abstraction (DashScope, BigModel, NVIDIA, MiniMax) |
| `store.py` | SQLite + ChromaDB data layer (documents, chunks, users, chat history) |
| `auth.py` | JWT + email verification code auth |
| `cache_store.py` | Redis cache wrapper with fallback |
| `task_broker.py` | RabbitMQ ingestion worker |
| `mcp_server.py` | MCP server (6 price tools) — used by agent_tools.py via MCP subprocess |

## Common Commands

```bash
# Backend
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm run dev

# Ingest a document into knowledge base
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "manual", "content": "...", "title": "..."}'

# Search knowledge base
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "bitcoin", "top_k": 5}'

# MCP server (stdio mode, for testing)
cd backend && source venv/bin/activate && echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | mcp run mcp_server.py
```

## Agent System

The agent uses OpenAI-compatible function calling with 7 tools.
**Routing**: Price tools (1-6) are executed via MCP protocol (subprocess + JSON-RPC).
The knowledge-base tool (7) uses a direct import path (no MCP).

1. `get_market_coins` — Top 100 crypto prices (via MCP → CoinGecko + OKX)
2. `get_okx_detail` — OKX order book & K-lines (via MCP)
3. `get_market_briefs` — Google News RSS crypto news (via MCP)
4. `get_market_timeline` — Per-coin news timeline (via MCP)
5. `get_meme_trending` — Solana meme tokens (via MCP → DexScreener)
6. `get_whale_feed` — Large whale transfers (via MCP → Arkham API + seed data)
7. `search_knowledge_base` — Internal RAG knowledge base (direct import, ChromaDB)

Agent flow: LLM → tool_calls → execute_tool() → MCP subprocess / direct import → LLM → final answer (max 6 turns). Before the first LLM call, agent_chat() proactively pre-searches the knowledge base (skipped for market intent).

## RAG Pipeline

- **Chunking**: Markdown-aware (heading hierarchy → paragraphs → sentences → character window fallback). Default chunk size: 900 chars (web), 1100 (PDF), 1400 (tables). Overlap: 120 chars at sentence boundaries.
- **Embedding**: DashScope text-embedding-v4
- **Search**: ChromaDB cosine similarity, top_k=5 default, fallback threshold at score 0.35
- **Generation**: Uses retrieved chunks as context, answers in Chinese with source citations

## Memory System

- **Short-term**: Last 6 chat turns loaded from SQLite `chat_messages` table
- **Long-term**: LLM-generated memory summary stored in `users.memory_summary` column, updated after each agent turn via `update_memory_summary()`
- **No tests** exist in this project yet.

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. Required variables for each provider:

- **DashScope** (primary): `DASHSCOPE_API_KEY`, `ALI_CHAT_MODEL`, `ALI_EMBEDDING_MODEL`
- **BigModel** (alternative): `BIGMODEL_API_KEY`, `BIGMODEL_MODEL`, `BIGMODEL_CHAT_URL`
- **NVIDIA**: `NVIDIA_API_KEY`, `NVIDIA_MODEL`, `NVIDIA_CHAT_URL`
- **MiniMax**: `MINIMAX_API_KEY`, `MINIMAX_MODEL`, `MINIMAX_CHAT_URL`
- **Redis** (optional): `REDIS_URL`
- **RabbitMQ** (optional): `RABBITMQ_URL`
- **Auth**: `RESEND_API_KEY` (email verification), `JWT_SECRET` (auto-generated if empty)
- **Arkham**: `ARKHAM_API_KEY` (whale transfers)

## Agent Skills (`.agents/skills/`)

This project has downloaded skills from mattpocock/skills in `.agents/skills/`. These skills define how I should behave for specific tasks — invoke them by name (e.g., `/tdd`, `/caveman`, `/diagnose`) when the task matches. Key skills:

| Skill | When to use |
|---|---|
| `/tdd` | Writing new code — red-green-refactor, one vertical slice at a time |
| `/caveman` | Ultra-terse communication mode (drop articles/filler) |
| `/diagnose` | Debugging hard bugs or performance regressions |
| `/prototype` | Building throwaway prototypes to answer design questions |
| `/grill-me` | / `/grill-with-docs` | Interviewing user to clarify requirements |
| `/to-prd` | Synthesizing context into a Product Requirements Document |
| `/to-issues` | Breaking a plan into independently grabbable issues |
| `/handoff` | Compacting session context for another agent to pick up |
| `/zoom-out` | Getting a high-level map of unfamiliar code areas |
| `/improve-codebase-architecture` | Surfacing architectural friction and deepening opportunities |
| `/triage` | Managing issues through the triage state machine |
| `/write-a-skill` | Creating new agent skills |
| `/setup-matt-pocock-skills` | Scaffolding per-repo configuration for engineering skills |

These are invoked on-demand. I do NOT apply all of them at once.

## Key Design Decisions

- API keys must NEVER be committed. Use `.env` files and `.gitignore`.
- Provider switching via `CHAT_PROVIDER` env var (dashscope / bigmodel / nvidia / minimax).
- All market data is cached with Redis + in-memory fallback with configurable TTLs.
- Price tools are routed through MCP protocol (subprocess + JSON-RPC via `mcp run mcp_server.py`). Knowledge base tool uses direct import (`from mcp_server import search_knowledge_base`). Routing happens in `execute_tool()` based on the `_PRICE_TOOLS` frozenset.
- MCP subprocess: lazy-started via `_ensure_mcp()`, threadsafe with `_MCP_LOCK`. Initialized with JSON-RPC initialize handshake. On crash, retries once. Stderr redirected to DEVNULL to avoid pipe buffer deadlock.
- MCP responses may contain multiple text content items (FastMCP serializes each list element separately). `_parse_json_objects()` handles this by parsing concatenated JSON objects with `json.JSONDecoder.raw_decode()`.
- LLM `_chat_completion_raw()` supports tool calling; `_chat_completion()` does not — use the raw variant when tool_calls or non-standard response shapes are needed.
