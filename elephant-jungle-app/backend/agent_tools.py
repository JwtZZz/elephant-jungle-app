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
    "get_news_headlines",
    "get_news_by_topic",
})
_WORK_TOOLS = frozenset({"create_work_task"})


def _format_news_items(items: list[dict]) -> str:
    """Format news items as LLM-friendly text."""
    if not items:
        return "暂无相关新闻。"
    lines = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "")
        source = item.get("source", "")
        summary = item.get("summary", "")[:200]
        link = item.get("link", "")
        lines.append(f"{i}. [{source}] {title}")
        if summary:
            lines.append(f"   {summary}")
        if link:
            lines.append(f"   {link}")
    return "\n".join(lines)


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
    {
        "type": "function",
        "function": {
            "name": "create_work_task",
            "description": "创建一个定时发送或价格触发的邮件通知任务。当用户说“每天X点发我价格”、“每30分钟报告”、“凌晨2点半发BTC价格”、“当SUI跌破1美元通知我”等时，使用此工具在后端直接创建任务并开始运行。用户未指定邮箱时使用登录邮箱。",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_type": {
                        "type": "string",
                        "description": "任务类型：cron_email（定时报告，按固定时间发送价格邮件）或 price_threshold_email（价格触发，当价格达到条件时发送邮件）",
                        "enum": ["cron_email", "price_threshold_email"],
                    },
                    "asset_symbol": {
                        "type": "string",
                        "description": "监控的币种符号，如 BTC、ETH、SUI、SOL。必填。",
                    },
                    "operator": {
                        "type": "string",
                        "description": "触发条件：below（跌破/低于）或 above（涨破/高于）。仅 price_threshold_email 类型必填。",
                    },
                    "threshold_value": {
                        "type": "number",
                        "description": "触发价格阈值，单位 USD。仅 price_threshold_email 类型必填。",
                    },
                    "cron_expression": {
                        "type": "string",
                        "description": "定时 cron 表达式，例如：0 9 * * *（每天9点）、0 * * * *（每小时）、30 18 * * *（每天18:30UTC=北京时间凌晨2:30）、*/30 * * * *（每30分钟）。仅 cron_email 类型必填。",
                    },
                    "recipient_email": {
                        "type": "string",
                        "description": "接收通知的邮箱地址。用户明确说了邮箱就用用户的，否则用登录邮箱。必填。",
                    },
                },
                "required": ["workflow_type", "asset_symbol", "recipient_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_headlines",
            "description": "获取最新的加密货币新闻头条（多源聚合，含 Reddit 热门讨论）。无需参数，返回按时间排序的最新新闻列表。",
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
            "name": "get_news_by_topic",
            "description": "按主题搜索加密货币新闻，适合用户问特定币种或赛道的最新新闻。传入主题词如 bitcoin、ethereum、solana、defi、比特币、以太坊等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "主题词，如 bitcoin、ethereum、solana、defi、比特币、以太坊等。必填。",
                    },
                },
                "required": ["topic"],
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
7. get_news_headlines — 获取多源聚合的加密货币头条新闻（RSS + Reddit）
8. get_news_by_topic — 按主题搜索最新加密货币新闻

【知识库工具】— 回答概念性、原理性问题用这个：
9. search_knowledge_base — 搜索内部知识库，查找区块链/加密货币的技术文档和概念解释

【任务创建工具】— 创建定时/触发通知任务用这个：
10. create_work_task — 创建定时邮件报告或价格触发邮件通知。用户说"每天X点发我"、"每小时报告"、"凌晨X点半发价格"、"跌破X通知我"等时，用此工具创建。注意时间转换：北京时间=UTC+8，凌晨2:30北京=30 18 * * *，早上9点=0 1 * * *，晚上8点=0 12 * * *。

选择原则：
- 用户问"多少钱"、"行情"、"涨了没"等实时信息 → 调对应的实时数据工具
- **用户问"最近怎么样"、"今天发生了什么"、"最新动态"、"近期"、"本周"等时间敏感问题 → 先用 get_news_by_topic 搜索相关币种的最新新闻，同时调 get_market_coins 获取价格行情，两者结合回答**
- 用户问特定币种的全面分析 → 同时调 get_market_coins（价格）+ get_news_by_topic（新闻）+ 如有必要 get_okx_detail（技术面）
- 用户问"什么是"、"是什么意思"、"怎么理解"、"原理"、"是谁"、"作者"等知识性或身份识别问题 → 调 search_knowledge_base
- 当你被问到"作者是谁"、"这个网页是谁"等身份识别问题时，不要拒绝回答，而是立即搜索知识库
- 用户问分析、对比、前景、推荐类问题（如"哪个更好"、"有前景"、"值得买"）→ 先调 get_market_coins 获取实时行情，再基于数据回答
- 不确定的问题或可能存在于内部知识库中的信息 → 优先调 search_knowledge_base 试试
- 用户打招呼或闲聊 → 直接回答，不调工具

每次回答时，基于工具返回的真实数据说话，不要编造数据。
用自然的中文回答，像一个专业的分析师在跟朋友聊天。
不要使用 Markdown 标题、粗体或列表格式，除非用户明确要求。"""


def execute_tool(name: str, args: dict, user: dict | None = None) -> str:
    """Execute a tool and return a text result for the LLM.

    Price-related tools route through the MCP protocol.
    The knowledge-base tool uses a direct import path.
    Work task tools require user context.
    """
    if name in _PRICE_TOOLS:
        return _execute_via_mcp(name, args)
    if name == "search_knowledge_base":
        return _execute_search_kb(args)
    if name == "create_work_task":
        return _execute_create_work_task(args, user)
    return f"错误：未知工具 {name}"


def _execute_create_work_task(args: dict, user: dict | None) -> str:
    """Create a work task (cron or threshold) directly from agent tool call."""
    if user is None:
        return "❌ 请先登录后再创建任务。"

    from store import create_work_task
    import time

    workflow_type = args.get("workflow_type", "price_threshold_email")
    asset_symbol = args.get("asset_symbol", "").upper().strip()
    recipient_email = (args.get("recipient_email") or "").strip() or user.get("email", "")
    operator = (args.get("operator") or "").strip()
    threshold_value = float(args.get("threshold_value", 0))
    cron_expression = (args.get("cron_expression") or "").strip()

    if not asset_symbol:
        return "❌ 请指定币种符号，如 BTC、ETH。"
    if not recipient_email:
        return "❌ 请提供接收通知的邮箱地址。"

    is_cron = workflow_type == "cron_email"

    if is_cron and not cron_expression:
        return "❌ 定时任务需要提供 cron 表达式，例如：0 9 * * *（每天9点）。"
    if not is_cron and not operator:
        return "❌ 价格触发任务需要设置方向（below=跌破 或 above=涨破）。"

    if is_cron:
        title = f"Scheduled: {asset_symbol} ({cron_expression})"
        email_subject = f"Scheduled Report: {asset_symbol}"
    else:
        op_label = "below" if operator == "below" else "above"
        title = f"Alert: {asset_symbol} {op_label} {threshold_value:.4f} USD".replace(".0000", "")
        email_subject = title

    try:
        task = create_work_task(
            user_id=user["id"],
            user_email=user["email"],
            workflow_type=workflow_type,
            title=title,
            status="active",
            asset_symbol=asset_symbol,
            operator=operator if not is_cron else "",
            threshold_value=threshold_value if not is_cron else 0,
            threshold_currency="USD",
            recipient_email=recipient_email,
            email_subject=email_subject,
            email_template_payload={},
            cron_expression=cron_expression if is_cron else "",
            next_check_at=int(time.time()),
        )

        if is_cron:
            return (
                f"✅ 已创建定时报告任务！\n"
                f"币种：{asset_symbol}\n"
                f"计划：{cron_expression}\n"
                f"接收邮箱：{recipient_email}\n"
                f"任务将按计划自动运行并向你发送邮件。"
            )
        else:
            op_zh = "跌破" if operator == "below" else "涨破"
            return (
                f"✅ 已创建价格触发任务！\n"
                f"条件：当 {asset_symbol} {op_zh} {threshold_value} USD\n"
                f"接收邮箱：{recipient_email}\n"
                f"达到条件时将自动发送通知邮件。"
            )
    except Exception as e:
        return f"❌ 创建任务失败：{str(e)}"


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
            lines = [f"按市值排名 Top {len(coins)} 加密货币行情："]
            for i, c in enumerate(coins, 1):
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

        elif name == "get_news_headlines":
            import json
            items = json.loads(raw) if isinstance(raw, str) else raw
            return _format_news_items(items)

        elif name == "get_news_by_topic":
            import json
            items = json.loads(raw) if isinstance(raw, str) else raw
            return _format_news_items(items)

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
