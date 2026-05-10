# Elephant Jungle 🐘🌴

> AI-powered cryptocurrency intelligence platform / AI 驱动的加密货币智能平台

---

## English

### Overview

Elephant Jungle is a full-stack crypto intelligence platform featuring an AI agent that can answer both **real-time market data** and **knowledge-based questions** through a unified chat interface.

### Architecture

```
frontend/  →  Chat UI (React + Vite)
backend/   →  FastAPI server with RAG + Agent system
pixexport/ →  Sprite assets for UI
```

### Key Features

- **AI Agent** — Tool-calling agent that queries real-time market data (prices, OKX depth, meme tokens, whale transfers) via LLM function calling
- **RAG Knowledge Base** — ChromaDB vector store + SQLite, with Markdown-aware chunking (headings → paragraphs → sentences), for blockchain/crypto documentation
- **Multi-turn Memory** — Conversational context with short-term (recent 6 turns) and long-term (persistent memory summary) layers
- **Multi-Provider LLM Support** — DashScope, BigModel (GLM-4-Flash), NVIDIA, MiniMax with unified function calling
- **Authentication** — Email verification code login with JWT

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite |
| Backend | Python, FastAPI |
| Vector DB | ChromaDB |
| SQL DB | SQLite |
| Cache | Redis |
| Queue | RabbitMQ |
| Embedding | DashScope text-embedding-v4 |
| LLM | GLM-4-Flash (primary) |

### Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm install
npm run dev
```

### API Endpoints

| Endpoint | Description |
|---|---|
| `POST /chat` | Chat with agent or RAG mode |
| `POST /ingest` | Ingest documents into knowledge base |
| `POST /search` | Search knowledge base |
| `GET /market/coins` | Top 100 crypto prices |
| `GET /market/okx-detail` | OKX order book & K-line |
| `GET /market/briefs` | Latest crypto news |
| `POST /ocr/image` | OCR for image text extraction |

### Project Status

Active development. The knowledge base is seeded with official blockchain documentation (Bitcoin, Ethereum, Solana, Uniswap, Aave, Chainlink).

---

## 中文

### 概述

Elephant Jungle 是一个全栈加密货币智能平台，内置 AI Agent，通过统一聊天界面同时支持**实时行情查询**和**知识问答**。

### 架构

```
frontend/  →  聊天界面 (React + Vite)
backend/   →  FastAPI 服务端，集成 RAG + Agent 系统
pixexport/ →  UI 精灵素材
```

### 核心功能

- **AI Agent** — 通过 LLM Function Calling 调用实时市场数据工具（价格、OKX 深度盘口、Meme 代币、鲸鱼转账）
- **RAG 知识库** — ChromaDB 向量库 + SQLite，支持 Markdown 感知分块（标题 → 段落 → 句子），已导入区块链/加密货币官方文档
- **多轮记忆** — 短期记忆（最近 6 轮）+ 长期记忆（持久化摘要），实现上下文连贯对话
- **多 LLM 支持** — 通义千问、智谱 GLM-4-Flash、NVIDIA、MiniMax，统一 Function Calling 接口
- **用户认证** — 邮箱验证码登录 + JWT

### 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React, Vite |
| 后端 | Python, FastAPI |
| 向量库 | ChromaDB |
| 关系库 | SQLite |
| 缓存 | Redis |
| 队列 | RabbitMQ |
| 向量模型 | DashScope text-embedding-v4 |
| 语言模型 | GLM-4-Flash（主） |

### 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填写你的 API Key
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm install
npm run dev
```

### 主要 API

| 接口 | 功能 |
|---|---|
| `POST /chat` | 对话（Agent 模式或 RAG 模式） |
| `POST /ingest` | 导入文档到知识库 |
| `POST /search` | 搜索知识库 |
| `GET /market/coins` | Top 100 加密货币行情 |
| `GET /market/okx-detail` | OKX 盘口深度 & K 线 |
| `GET /market/briefs` | 最新加密货币快讯 |
| `POST /ocr/image` | 图片文字识别 |

### 项目状态

持续开发中。知识库已导入主流区块链官方文档（Bitcoin、Ethereum、Solana、Uniswap、Aave、Chainlink）。
