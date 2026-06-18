"""tbot — simulated trading bot with 2-agent pipeline (Analyst + Execution)."""

import json
import os
import re

from agent_tools import execute_tool
from providers import _chat_completion_raw, _chat_completion_stream
from store import (
    close_tbot_position,
    create_tbot_order,
    create_tbot_position,
    get_or_create_tbot_account,
    get_tbot_orders,
    get_tbot_position_by_symbol,
    get_tbot_positions,
    update_tbot_account_balance,
    update_tbot_position,
)

_ANALYST_PROMPT = """你是一个加密货币交易分析师。你的任务是分析市场数据并输出交易信号。

请严格按以下 JSON 格式输出，不要输出其他内容：

{"asset": "币种(SOL/BTC/ETH等)", "direction": "long", "entry_price": 当前市价, "target_price": 目标价, "stop_loss": 止损价, "confidence": 0.8, "position_size_pct": 30, "reasoning": "中文分析理由"}

规则：
- direction 只能是 "long"（做多）或 "hold"（观望）
- 没有明确交易机会时 direction="hold" confidence=0
- entry_price 用当前市场价
- position_size_pct 范围 1-100
- 用中文写 reasoning
- 只输出 JSON，不要加 markdown 标记
"""

_EXECUTION_PROMPT = """你是一个交易执行代理。你的任务是审查分析师信号并执行模拟交易。

风控规则：
- 单笔交易不超过账户总资产的 50%
- 不使用杠杆
- 已有同币种仓位时，不允许重复开仓
- 做多时止损价必须低于入场价
- 做空时止损价必须高于入场价
- confidence < 0.3 的信号直接拒绝

请根据信号和当前持仓状况，决定是否执行交易。
如果执行，返回给用户的自然语言消息要包含：交易对、方向、数量、价格、金额。
如果不执行，说明原因。
"""

_PORTFOLIO_PROMPT = """你是一个交易助手。用户正在查询他们的模拟交易账户信息。
请用自然的中文向用户汇报他们的账户状况。
"""


def _emit(on_event, etype, message):
    if on_event:
        on_event(etype, message)


def _format_market_data() -> str:
    """Fetch top coins via MCP and format as text for the analyst."""
    try:
        raw = execute_tool("get_market_coins", {})
        # get_market_coins returns formatted text, pass through directly
        return raw[:3000] if raw else "无数据"
    except Exception as e:
        return f"获取行情失败: {e}"


def _parse_coin_price(data: str, symbol: str) -> float | None:
    """Extract a coin's price from the market data text."""
    symbol = symbol.upper()
    for line in data.split("\n"):
        # Match: "7. Solana (SOL): 价格 $85.3000, ..."
        m = re.search(rf"\(\w+\):\s*价格\s*\$?([\d,]+\.?\d*)", line)
        if not m:
            continue
        # Check if this line's symbol matches
        sym_m = re.search(r"\((\w+)\)", line)
        if sym_m and sym_m.group(1).upper() == symbol:
            return float(m.group(1).replace(",", ""))
    return None


def _format_portfolio(account: dict, positions: list[dict]) -> str:
    lines = [f"账户余额: ${account['balance_usdt']:.2f} USDT"]
    lines.append(f"累计盈亏: ${account['total_pnl']:.2f}")
    if positions:
        lines.append("")
        lines.append("【当前持仓】")
        for p in positions:
            lines.append(f"  {p['asset_symbol']}: {p['quantity']} @ ${p['entry_price']}")
    else:
        lines.append("\n当前无持仓。")
    return "\n".join(lines)


def _parse_signal(text: str) -> dict | None:
    """Extract JSON block from LLM response."""
    text = text.strip()
    # Try direct JSON parse
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # Try to find ```json ... ``` block
    if "```json" in text:
        block = text.split("```json")[1].split("```")[0].strip()
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            pass
    # Try to find { ... } anywhere
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def analyst_agent(query: str, account: dict, positions: list[dict], provider: str | None = None, on_event=None) -> dict:
    """Analyst agent: fetches market data and produces a trading signal."""
    market_data = _format_market_data()
    portfolio = _format_portfolio(account, positions)

    messages = [
        {"role": "system", "content": _ANALYST_PROMPT},
        {"role": "user", "content": f"用户问题: {query}\n\n{market_data}\n\n{portfolio}\n\n请输出 JSON 交易信号。"},
    ]
    try:
        # Stream tokens while collecting full response for signal parsing
        full = ""
        for token in _chat_completion_stream(messages, temperature=0.3, provider=provider):
            full += token
            if on_event:
                on_event("token", {"text": token})
        content = full.strip()
        signal = _parse_signal(content)
        if signal:
            return {"signal": signal, "raw_analysis": content}
        return {"signal": None, "raw_analysis": content}
    except Exception as e:
        return {"signal": None, "raw_analysis": f"分析师错误: {e}"}


def execution_agent(
    signal: dict | None,
    raw_analysis: str,
    account: dict,
    positions: list[dict],
    provider: str | None = None,
    on_event=None,
) -> str:
    """Execution agent: reviews signal and executes simulated trade."""
    signal_json = json.dumps(signal, ensure_ascii=False) if signal else "无明确信号"
    portfolio = _format_portfolio(account, positions)

    user_content = f"分析师信号:\n{signal_json}\n\n分析师原始分析:\n{raw_analysis}\n\n{portfolio}\n\n请根据以上信息决定是否执行交易。"

    messages = [
        {"role": "system", "content": _EXECUTION_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        full = ""
        for token in _chat_completion_stream(messages, temperature=0.2, provider=provider):
            full += token
            if on_event:
                on_event("token", {"text": token})
        return full.strip()
    except Exception as e:
        return f"执行错误: {e}"


def _portfolio_query_handler(account: dict, positions: list[dict], orders: list[dict], provider: str | None = None) -> str:
    """Handle portfolio-related queries."""
    portfolio = _format_portfolio(account, positions)

    orders_text = ""
    if orders:
        orders_text = "\n【最近交易】\n"
        for o in orders[:5]:
            orders_text += f"  {o['side']} {o['asset_symbol']} {o['quantity']} @ ${o['price']} ({o['created_at']})\n"

    messages = [
        {"role": "system", "content": _PORTFOLIO_PROMPT},
        {"role": "user", "content": f"{portfolio}\n{orders_text}\n请用中文向用户汇报。"},
    ]
    try:
        resp = _chat_completion_raw(messages, temperature=0.2, provider=provider)
        return (resp.get("content") or "").strip()
    except Exception as e:
        return f"查询失败: {e}"


def _get_coin_price(symbol: str) -> float | None:
    """Get current price of a coin via MCP."""
    try:
        raw = execute_tool("get_market_coins", {})
        return _parse_coin_price(raw, symbol)
    except Exception:
        pass
    return None


def _parse_explicit_trade(query: str) -> dict | None:
    """Detect explicit buy/sell commands like '买入0.1BTC' / '帮我卖ETH'."""
    q = query.strip()
    # Buy patterns
    buy_m = re.search(r"(?:买入|帮我买|买)\s*(\d+\.?\d*)\s*(?:个)?\s*([A-Za-z]+)", q)
    if buy_m:
        return {"side": "buy", "quantity": float(buy_m.group(1)), "asset": buy_m.group(2).upper()}
    buy_m = re.search(r"(?:买入|帮我买|买)\s*([A-Za-z]+)", q)
    if buy_m:
        return {"side": "buy", "asset": buy_m.group(1).upper()}

    # Sell patterns
    sell_m = re.search(r"(?:卖出|帮我卖|卖)\s*(\d+\.?\d*)\s*(?:个)?\s*([A-Za-z]+)", q)
    if sell_m:
        return {"side": "sell", "quantity": float(sell_m.group(1)), "asset": sell_m.group(2).upper()}
    sell_m = re.search(r"(?:卖出|帮我卖|卖)\s*([A-Za-z]+)", q)
    if sell_m:
        return {"side": "sell", "asset": sell_m.group(1).upper()}

    return None


def _execute_buy(asset: str, quantity: float | None, account: dict, positions: list[dict], provider: str | None = None) -> str:
    """Execute a buy order for a specific asset."""
    price = _get_coin_price(asset)
    if not price:
        return f"❌ 无法获取 {asset} 的当前价格，请稍后重试。"

    # Check existing position
    existing = get_tbot_position_by_symbol(account["id"], asset)
    if existing:
        return f"⚠️ 已有 {asset} 持仓 ({existing['quantity']} @ ${existing['entry_price']})，请先卖出再重新买入。"

    # Determine quantity
    if quantity is None:
        max_trade = account["balance_usdt"] * 0.5
        quantity = max_trade / price

    total_usdt = quantity * price
    if total_usdt > account["balance_usdt"]:
        return f"❌ 余额不足。需要 ${total_usdt:.2f} USDT，账户余额 ${account['balance_usdt']:.2f} USDT。"

    if total_usdt < 1:
        return f"❌ 交易金额太小（${total_usdt:.2f}），最低 $1。"

    # Execute
    update_tbot_account_balance(account["id"], -total_usdt)
    create_tbot_position(account["id"], asset, quantity, price)
    create_tbot_order(account["id"], asset, "buy", quantity, price, total_usdt, reasoning="用户手动买入")

    return (
        f"✅ 买入成功!\n"
        f"   币种: {asset}\n"
        f"   数量: {quantity:.4f}\n"
        f"   价格: ${price:.2f}\n"
        f"   金额: ${total_usdt:.2f} USDT\n"
        f"   余额: ${account['balance_usdt'] - total_usdt:.2f} USDT"
    )


def _execute_sell(asset: str, quantity: float | None, account: dict, positions: list[dict], provider: str | None = None) -> str:
    """Execute a sell order for a specific asset."""
    existing = get_tbot_position_by_symbol(account["id"], asset)
    if not existing:
        return f"⚠️ 没有 {asset} 持仓可卖。"

    price = _get_coin_price(asset)
    if not price:
        return f"❌ 无法获取 {asset} 的当前价格。"

    sell_qty = quantity if quantity else existing["quantity"]
    if sell_qty > existing["quantity"]:
        return f"⚠️ 持仓不足。当前 {asset} 持仓 {existing['quantity']}，请求卖出 {sell_qty}。"

    total_usdt = sell_qty * price
    ratio = sell_qty / existing["quantity"]
    entry_cost = existing["entry_price"] * sell_qty

    if sell_qty >= existing["quantity"]:
        close_tbot_position(existing["id"])
    else:
        update_tbot_position(existing["id"], existing["quantity"] - sell_qty)

    update_tbot_account_balance(account["id"], total_usdt)
    create_tbot_order(account["id"], asset, "sell", sell_qty, price, total_usdt, reasoning="用户手动卖出")

    pnl = total_usdt - entry_cost
    return (
        f"✅ 卖出成功!\n"
        f"   币种: {asset}\n"
        f"   数量: {sell_qty:.4f}\n"
        f"   价格: ${price:.2f}\n"
        f"   金额: ${total_usdt:.2f} USDT\n"
        f"   盈亏: ${pnl:.2f}"
    )


def _is_portfolio_query(query: str) -> bool:
    """Detect portfolio-related queries."""
    q = query.lower()
    keywords = ["持仓", "仓位", "账户", "余额", "赚了多少", "亏了多少", "portfolio", "pnl", "盈亏", "收益"]
    return any(kw in q for kw in keywords)


def _execute_trade(signal: dict, account: dict, positions: list[dict]) -> str:
    """Execute a simulated trade based on the signal. Returns execution description."""
    asset = signal.get("asset", "").upper()
    direction = signal.get("direction", "hold")
    entry_price = signal.get("entry_price")
    confidence = signal.get("confidence", 0)
    position_pct = signal.get("position_size_pct", 30)
    reasoning = signal.get("reasoning", "")

    if direction == "hold" or confidence < 0.3:
        return None  # No trade

    if not asset or not entry_price:
        return None

    # Check existing position
    existing = get_tbot_position_by_symbol(account["id"], asset)
    if existing:
        # Already have position in this asset - skip re-entry
        return f"已有 {asset} 持仓 (${existing['entry_price']})，跳过重复开仓。"

    # Calculate trade size
    max_trade = account["balance_usdt"] * 0.5  # At most 50% of balance
    trade_usdt = min(account["balance_usdt"] * (position_pct / 100), max_trade)
    if trade_usdt < 1:
        return None  # Too small

    quantity = trade_usdt / entry_price

    if direction == "long":
        # Buy: deduct balance, create position
        update_tbot_account_balance(account["id"], -trade_usdt)
        create_tbot_position(account["id"], asset, quantity, entry_price)
        create_tbot_order(
            account["id"], asset, "buy", quantity, entry_price, trade_usdt,
            reasoning=reasoning, signal_json=json.dumps(signal, ensure_ascii=False),
        )
        target = signal.get("target_price", "N/A")
        stop = signal.get("stop_loss", "N/A")
        return (
            f"✅ 执行买入: {quantity:.4f} {asset} @ ${entry_price}\n"
            f"   金额: ${trade_usdt:.2f} USDT\n"
            f"   目标价: ${target} | 止损价: ${stop}\n"
            f"   置信度: {confidence:.0%}"
        )

    elif direction == "short" and existing:
        # Sell (close position)
        update_tbot_account_balance(account["id"], trade_usdt)
        close_tbot_position(existing["id"])
        create_tbot_order(
            account["id"], asset, "sell", quantity, entry_price, trade_usdt,
            reasoning=reasoning, signal_json=json.dumps(signal, ensure_ascii=False),
        )
        pnl = (entry_price - existing["entry_price"]) * existing["quantity"]
        return (
            f"✅ 执行卖出: {quantity:.4f} {asset} @ ${entry_price}\n"
            f"   金额: ${trade_usdt:.2f} USDT\n"
            f"   盈亏: ${pnl:.2f}"
        )

    return None


def tbot_chat(
    query: str,
    user: dict | None,
    on_event=None,
    provider: str | None = None,
) -> dict:
    """Full tbot pipeline: analyst → execution → answer."""
    if not user:
        return {"answer": "请先登录后再使用模拟交易功能。", "mode": "tbot"}

    _emit(on_event, "status", "正在初始化交易账户...")

    account = get_or_create_tbot_account(user["id"])
    positions = get_tbot_positions(account["id"])
    orders = get_tbot_orders(account["id"])

    # Portfolio query: skip analyst, just show portfolio
    if _is_portfolio_query(query):
        _emit(on_event, "status", "正在查询账户信息...")
        answer = _portfolio_query_handler(account, positions, orders, provider=provider)
        return {"answer": answer, "mode": "tbot"}

    # Explicit trade command (e.g. "买入0.1BTC"): skip analyst, execute directly
    trade_cmd = _parse_explicit_trade(query)
    if trade_cmd:
        _emit(on_event, "status", f"正在执行{trade_cmd['side']}订单...")
        if trade_cmd["side"] == "buy":
            answer = _execute_buy(trade_cmd["asset"], trade_cmd.get("quantity"), account, positions, provider=provider)
        else:
            answer = _execute_sell(trade_cmd["asset"], trade_cmd.get("quantity"), account, positions, provider=provider)
        return {"answer": answer, "mode": "tbot"}

    # Step 1: Analyst — for analytical queries like "BTC现在能买吗"
    _emit(on_event, "status", "正在分析市场数据...")
    result = analyst_agent(query, account, positions, provider=provider, on_event=on_event)
    signal = result["signal"]

    # Step 2: Execution
    _emit(on_event, "status", "正在执行交易策略...")

    execution_text = None
    if signal:
        execution_text = _execute_trade(signal, account, positions)

    if execution_text:
        # Trade executed
        full_answer = f"【分析师信号】\n{signal.get('reasoning', '')}\n\n【执行结果】\n{execution_text}"
    elif signal and signal.get("direction") != "hold":
        # Signal says trade but execution skipped
        full_answer = (signal.get("reasoning", result.get("raw_analysis", ""))
                      + "\n\n" + execution_text)
    else:
        # No trade signal — use execution agent for explanation
        execution_text = execution_agent(
            signal, result.get("raw_analysis", ""), account, positions, provider=provider, on_event=on_event
        )
        full_answer = execution_text

    return {"answer": full_answer, "mode": "tbot"}

def get_tbot_account_data(user_id: int) -> dict:
    """Return structured account data for the frontend UI."""
    account = get_or_create_tbot_account(user_id)
    positions = get_tbot_positions(account["id"])
    orders = get_tbot_orders(account["id"], limit=50)
    return {
        "account": {
            "balance_usdt": account["balance_usdt"],
            "total_pnl": account["total_pnl"],
            "position_count": len(positions),
        },
        "positions": [
            {
                "asset_symbol": p["asset_symbol"],
                "quantity": p["quantity"],
                "entry_price": p["entry_price"],
                "current_value_usdt": round(p["quantity"] * p["entry_price"], 2),
            }
            for p in positions
        ],
        "orders": [
            {
                "id": o["id"],
                "asset_symbol": o["asset_symbol"],
                "side": o["side"],
                "quantity": o["quantity"],
                "price": o["price"],
                "total_usdt": o["total_usdt"],
                "reasoning": o["reasoning"],
                "created_at": o["created_at"],
            }
            for o in orders
        ],
    }
