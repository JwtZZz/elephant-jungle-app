"""Elephant Jungle MCP Server — crypto market data tools for MCP hosts.

Exposes real-time cryptocurrency market data (prices, order books, meme tokens,
news, whale transfers) via the Model Context Protocol.

Usage:
    # stdio transport (Claude Desktop):
    mcp run mcp_server.py

    # SSE transport (web app):
    python mcp_server.py

Requires the FastAPI backend (uvicorn main:app) to be running.
Backend URL defaults to http://127.0.0.1:8000; override via API_BASE_URL env var.
"""

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

mcp = FastMCP(
    "Elephant Jungle",
    dependencies=["httpx"],
)


def _api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{API_BASE}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


def _api_post(path: str, json_body: dict) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(f"{API_BASE}{path}", json=json_body)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Pure data functions (importable by agent_tools.py, used by MCP tools below)
# ---------------------------------------------------------------------------


def get_market_coins() -> list[dict]:
    """Get top 100 cryptocurrencies by market cap with real-time prices."""
    data = _api_get("/market/coins")
    return data.get("coins", [])


def get_okx_detail(symbol: str, interval: str = "15m") -> dict:
    """Get OKX order book and K-line data for a trading pair."""
    return _api_get("/market/okx-detail", params={"symbol": symbol, "interval": interval})


def get_meme_trending() -> list[dict]:
    """Get trending Solana meme tokens with prices and volume."""
    data = _api_get("/meme/trending")
    return data.get("tokens", [])


def get_market_briefs() -> dict:
    """Get latest crypto news and social media highlights."""
    return _api_get("/market/briefs")


def get_market_timeline(symbol: str, name: str = "", language: str = "zh") -> list[dict]:
    """Get news timeline for a specific cryptocurrency."""
    data = _api_get("/market/timeline", params={"symbol": symbol, "name": name, "language": language})
    return data.get("items", [])


def get_whale_feed(limit: int = 24) -> list[dict]:
    """Get large whale/institution transfer activity across chains."""
    limit = max(8, min(24, limit))
    data = _api_get("/whales/feed", params={"limit": limit})
    return data.get("items", [])


def search_knowledge_base(query: str, top_k: int = 5) -> list[dict]:
    """Search the internal RAG knowledge base."""
    if not query:
        return []
    data = _api_post("/search", {"query": query, "top_k": top_k})
    return data.get("hits", data.get("results", []))


# ---------------------------------------------------------------------------
# MCP tool wrappers
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_market_coins",
    description="获取按市值排名前 100 的加密货币实时数据，包括价格、24小时涨跌幅、市值等。"
)
def mcp_get_market_coins() -> list[dict]:
    return get_market_coins()


@mcp.tool(
    name="get_okx_detail",
    description="获取 OKX 交易所某个交易对的实时行情，包括最新价、24小时最高最低价、K线数据和买卖盘深度。"
)
def mcp_get_okx_detail(symbol: str, interval: str = "15m") -> dict:
    return get_okx_detail(symbol=symbol, interval=interval)


@mcp.tool(
    name="get_meme_trending",
    description="获取 Solana 链上当前最热门的 meme 代币列表，包括价格、交易量和涨幅。"
)
def mcp_get_meme_trending() -> list[dict]:
    return get_meme_trending()


@mcp.tool(
    name="get_market_briefs",
    description="获取最新的加密货币新闻快讯和社交媒体热点摘要。"
)
def mcp_get_market_briefs() -> dict:
    return get_market_briefs()


@mcp.tool(
    name="get_market_timeline",
    description="获取某个加密货币（如 BTC、ETH、SOL）的最新相关新闻时间线。"
)
def mcp_get_market_timeline(symbol: str, name: str = "", language: str = "zh") -> list[dict]:
    return get_market_timeline(symbol=symbol, name=name, language=language)


@mcp.tool(
    name="get_whale_feed",
    description="获取大额机构/鲸鱼转账动态，包括 BTC、ETH、SOL 等链上的大额资金流向。"
)
def mcp_get_whale_feed(limit: int = 24) -> list[dict]:
    return get_whale_feed(limit=limit)


# ---------------------------------------------------------------------------
# Entrypoint (SSE mode)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="sse")
