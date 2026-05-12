"""Tool definitions and executors for the chat agent.

All data-fetching logic lives in :mod:`mcp_server` so the same functions
are available to both the chat agent and external MCP clients.

Real-time price tools route through the MCP protocol (subprocess + JSON-RPC)
for clean separation.  The knowledge base tool uses a direct import path.
"""

import json
import os
import subprocess
import threading

# Direct import for the knowledge base tool only
from mcp_server import search_knowledge_base

# ---------------------------------------------------------------------------
# MCP client — runs mcp_server.py as a subprocess, communicates via JSON-RPC
# ---------------------------------------------------------------------------

_MCP_LOCK = threading.Lock()
_MCP_PROC: subprocess.Popen | None = None
_MCP_REQ_ID = 0

_PRICE_TOOLS = frozenset({
    "get_market_coins",
    "get_okx_detail",
    "get_meme_trending",
    "get_market_briefs",
    "get_market_timeline",
    "get_whale_feed",
})


def _ensure_mcp():
    """Lazy-start the MCP subprocess and run the initialize handshake."""
    global _MCP_PROC
    if _MCP_PROC is not None:
        return
    with _MCP_LOCK:
        if _MCP_PROC is not None:
            return
        _start_mcp()


def _start_mcp():
    global _MCP_PROC, _MCP_REQ_ID
    _MCP_REQ_ID = 0

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    venv_mcp = os.path.join(backend_dir, "venv", "bin", "mcp")
    server = os.path.join(backend_dir, "mcp_server.py")

    _MCP_PROC = subprocess.Popen(
        [venv_mcp, "run", server],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=backend_dir,
    )

    # Initialize handshake
    _mcp_send({
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "elephant-jungle-agent", "version": "1.0"},
        },
    })
    _mcp_recv()  # consume initialize result

    _mcp_send({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    })


def _next_id() -> int:
    global _MCP_REQ_ID
    _MCP_REQ_ID += 1
    return _MCP_REQ_ID


def _mcp_send(obj: dict):
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    if _MCP_PROC and _MCP_PROC.stdin:
        _MCP_PROC.stdin.write(line.encode("utf-8"))
        _MCP_PROC.stdin.flush()


def _mcp_recv() -> dict:
    """Read one JSON-RPC response (may span multiple lines if pretty-printed)."""
    if not (_MCP_PROC and _MCP_PROC.stdout):
        return {}
    buffer = ""
    decoder = json.JSONDecoder()
    while True:
        line = _MCP_PROC.stdout.readline()
        if not line:
            break
        buffer += line.decode("utf-8")
        try:
            obj, _ = decoder.raw_decode(buffer)
            return obj
        except json.JSONDecodeError:
            continue  # need more lines
    return {}


def _mcp_call(tool_name: str, arguments: dict | None = None) -> str:
    """Call a tool via MCP JSON-RPC and return the text content."""
    for _ in range(2):  # one retry on crash
        try:
            _ensure_mcp()
            _mcp_send({
                "jsonrpc": "2.0",
                "id": _next_id(),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}},
            })
            resp = _mcp_recv()
            if "result" in resp:
                content = resp["result"].get("content", [])
                texts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                return "\n".join(texts)
            err = resp.get("error", {})
            return f"错误: {err.get('message', 'MCP 调用失败')}"
        except Exception as exc:
            # Kill and retry once
            _kill_mcp()
            if _ == 1:
                return f"错误: MCP 服务异常 — {exc}"
    return "错误: MCP 服务不可用"


def _kill_mcp():
    global _MCP_PROC
    with _MCP_LOCK:
        if _MCP_PROC:
            try:
                _MCP_PROC.kill()
                _MCP_PROC.wait(timeout=3)
            except Exception:
                pass
            _MCP_PROC = None


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI-compatible function calling)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_coins",
            "description": "获取按市值排名前 100 的加密货币实时数据，包括价格、24小时涨跌幅、市值等。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_briefs",
            "description": "获取最新的加密货币新闻快讯和社交媒体摘要，涵盖比特币、以太坊等主要币种。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_okx_detail",
            "description": "获取某个交易对在 OKX 交易所的详细信息，包括实时行情、K线数据和买卖盘深度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "交易对符号，如 BTC、ETH、SOL。必填。",
                    },
                    "interval": {
                        "type": "string",
                        "description": "K线周期：1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_timeline",
            "description": "获取某个加密货币的最新相关新闻时间线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "币种符号，如 BTC、ETH、SOL。必填。",
                    },
                    "name": {
                        "type": "string",
                        "description": "币种全名（可选），如 Bitcoin、Ethereum",
                    },
                    "language": {
                        "type": "string",
                        "description": "语言：en 英文, zh 中文",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_meme_trending",
            "description": "获取 Solana 链上当前最热门的 meme 代币列表，包括价格、交易量和涨幅。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_whale_feed",
            "description": "获取大额机构/鲸鱼转账动态，包括 BTC、ETH、SOL 等链上的大额资金流向。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数量，最多 24",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "搜索内部知识库，查找技术文档、概念解释、用户资料、作者信息等。当你需要回答原理性、知识性或身份识别问题时（比如什么是比特币，什么是DeFi，这是什么项目，作者是谁，谁写的等），使用此工具。不要用它查实时价格或新闻。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，用中文描述你要找的知识点",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """你是一个专业的加密货币助手。你可以使用以下工具获取信息：

【实时数据工具】— 查价格、行情、新闻用这几个：
1. get_market_coins — 获取 Top 100 加密货币的实时行情（价格、涨跌幅、市值）
2. get_okx_detail — 获取 OKX 交易所某个交易对的详细行情（K线、深度）
3. get_market_briefs — 获取最新加密货币新闻快讯和社交媒体热点
4. get_market_timeline — 获取某个币种的最新新闻时间线
5. get_meme_trending — 获取 Solana 热门 meme 代币
6. get_whale_feed — 获取大额鲸鱼/机构资金流向

【知识库工具】— 回答概念性、原理性问题用这个：
7. search_knowledge_base — 搜索内部知识库，查找区块链/加密货币的技术文档和概念解释

选择原则：
- 用户问"多少钱"、"行情"、"涨了没"等实时信息 → 调对应的实时数据工具
- 用户问"什么是"、"是什么意思"、"怎么理解"、"原理"、"是谁"、"作者"等知识性或身份识别问题 → 调 search_knowledge_base
- 当你被问到"作者是谁"、"这个网页是谁"等身份识别问题时，不要拒绝回答，而是立即搜索知识库
- 不确定的问题或可能存在于内部知识库中的信息 → 优先调 search_knowledge_base 试试
- 用户打招呼或闲聊 → 直接回答，不调工具

每次回答时，基于工具返回的真实数据说话，不要编造数据。
用自然的中文回答，像一个专业的分析师在跟朋友聊天。
不要使用 Markdown 标题、粗体或列表格式，除非用户明确要求。"""


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return a text result for the LLM.

    Price-related tools route through the MCP protocol.
    The knowledge-base tool uses a direct import path.
    """
    if name in _PRICE_TOOLS:
        return _execute_via_mcp(name, args)
    if name == "search_knowledge_base":
        return _execute_search_kb(args)
    return f"错误：未知工具 {name}"


def _parse_json_objects(text: str) -> list:
    """Parse a string of zero or more concatenated JSON objects (no outer array)."""
    decoder = json.JSONDecoder()
    objects = []
    idx = 0
    text = text.strip()
    while idx < len(text):
        try:
            obj, end = decoder.raw_decode(text, idx)
            objects.append(obj)
            idx = end
            while idx < len(text) and text[idx] in " \t\n\r,":
                idx += 1
        except json.JSONDecodeError:
            break
    return objects


def _execute_via_mcp(name: str, args: dict) -> str:
    """Call a price tool via MCP protocol, then format for LLM."""
    try:
        raw = _mcp_call(name, args)
        if not raw:
            return "暂无数据。"

        if name == "get_market_coins":
            coins = _parse_json_objects(raw) if isinstance(raw, str) else raw
            if not coins:
                return "暂无行情数据。"
            top = coins[:20]
            lines = ["按市值排名前 20 加密货币行情："]
            for i, c in enumerate(top, 1):
                change = c.get("change", 0)
                sign = "+" if change >= 0 else ""
                lines.append(
                    f"{i}. {c['name']} ({c['symbol']}): "
                    f"价格 {c['price']}, "
                    f"24h {sign}{change:.2f}%, "
                    f"市值 {c['cap']}"
                )
            return "\n".join(lines)

        elif name == "get_market_briefs":
            import json
            data = json.loads(raw) if isinstance(raw, str) else raw
            parts = []
            social = data.get("social", [])
            news = data.get("news", [])
            if social:
                parts.append("【社交热点】：")
                for item in social[:5]:
                    parts.append(f"  · {item.get('title', '')}")
            if news:
                parts.append("【新闻快讯】：")
                for item in news[:5]:
                    parts.append(f"  · {item.get('title', '')}")
            if not parts:
                return "暂无快讯数据。"
            return "\n".join(parts)

        elif name == "get_okx_detail":
            import json
            data = json.loads(raw) if isinstance(raw, str) else raw
            ticker = data.get("ticker", {})
            candles = data.get("candles", [])
            ob = data.get("orderbook", {})
            symbol = args.get("symbol", "").upper()
            interval = args.get("interval", "15m")
            lines = [
                f"=== OKX {symbol} 实时行情 ===",
                f"最新价: ${ticker.get('last', 0):,.2f}",
                f"24h 开盘: ${ticker.get('open24h', 0):,.2f}",
                f"24h 最高: ${ticker.get('high24h', 0):,.2f}",
                f"24h 最低: ${ticker.get('low24h', 0):,.2f}",
                f"24h 成交量: {ticker.get('vol24h', 0):,.2f}",
            ]
            if candles:
                latest = candles[-1]
                lines.append(
                    f"最近 {interval} K线: "
                    f"开 ${latest['open']:,.2f} 高 ${latest['high']:,.2f} "
                    f"低 ${latest['low']:,.2f} 收 ${latest['close']:,.2f}"
                )
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if bids and asks:
                lines.append(f"买一: ${bids[0]['price']:,.2f} (量 {bids[0]['size']})")
                lines.append(f"卖一: ${asks[0]['price']:,.2f} (量 {asks[0]['size']})")
            return "\n".join(lines)

        elif name == "get_market_timeline":
            items = _parse_json_objects(raw) if isinstance(raw, str) else raw
            symbol = args.get("symbol", "").upper()
            if not items:
                return f"{symbol} 暂无最新新闻。"
            lines = [f"=== {symbol} 最新新闻 ==="]
            for item in items[:8]:
                lines.append(f"  · {item.get('title', '')}")
            return "\n".join(lines)

        elif name == "get_meme_trending":
            tokens = _parse_json_objects(raw) if isinstance(raw, str) else raw
            if not tokens:
                return "暂无热门 meme 代币数据。"
            lines = ["=== Solana 热门 Meme 代币 ==="]
            for t in tokens[:10]:
                change = t.get("change24h", 0)
                sign = "+" if change >= 0 else ""
                lines.append(
                    f"  · {t.get('symbol', '?')}: "
                    f"价格 {t.get('price', '--')}, "
                    f"24h {sign}{change}%, "
                    f"交易量 {t.get('volume24h', '--')}"
                )
            return "\n".join(lines)

        elif name == "get_whale_feed":
            items = _parse_json_objects(raw) if isinstance(raw, str) else raw
            if not items:
                return "暂无大额转账数据。"
            lines = ["=== 大额鲸鱼转账动态 ==="]
            for item in items[:15]:
                direction = "→ 流入" if item.get("direction") == "inflow" else "← 流出"
                lines.append(
                    f"  · {item['chain']} {direction}: "
                    f"{item['from']} → {item['to']}: "
                    f"{item['amount']} ({item['usd']})"
                )
            return "\n".join(lines)

        else:
            return raw

    except Exception as e:
        return f"调用工具 {name} 时出错: {str(e)}"


def _execute_search_kb(args: dict) -> str:
    """Search knowledge base via direct import (no MCP)."""
    try:
        query = args.get("query", "")
        if not query:
            return "请提供搜索关键词。"
        hits = search_knowledge_base(query=query, top_k=5)
        if not hits:
            return f"知识库中未找到与「{query}」相关的内容。"
        lines = [f"知识库搜索结果（共 {len(hits)} 条）："]
        for i, hit in enumerate(hits, 1):
            title = hit.get("title", hit.get("source", "未知来源"))
            content = hit.get("content", hit.get("text", ""))
            source = hit.get("source", "")
            snippet = content[:300] if len(content) > 300 else content
            lines.append(f"\n[{i}] {title}")
            if source:
                lines.append(f"来源: {source}")
            lines.append(f"{snippet}")
        return "\n".join(lines)
    except Exception as e:
        return f"搜索知识库时出错: {str(e)}"
