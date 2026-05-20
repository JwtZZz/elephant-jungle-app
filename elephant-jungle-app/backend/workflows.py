from __future__ import annotations

import datetime
import json
import re
import time
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, StateGraph

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / ".env")

from providers import _chat_completion_raw


WORKFLOW_PRICE_THRESHOLD_EMAIL = "price_threshold_email"

ASSET_STOPWORDS = {
    "WHEN", "EMAIL", "MAIL", "SEND", "PRICE", "USD", "USDT", "IF", "THE", "THEN",
    "WORK", "ALERT", "BELOW", "ABOVE", "UNDER", "OVER",
}

CN_ASSET_MAP = {
    "比特币": "BTC", "以太坊": "ETH", "索拉纳": "SOL",
    "币安币": "BNB", "瑞波": "XRP", "狗狗币": "DOGE", "艾达币": "ADA",
    "波卡": "DOT", "马蹄": "MATIC", "matic": "MATIC",
}


class AuthoringState(TypedDict, total=False):
    language: str
    user_email: str
    message: str
    draft_task: dict
    missing_fields: list[str]
    status: str
    assistant_message: str
    needs_confirmation: bool


class ExecutionState(TypedDict, total=False):
    task: dict
    price_payload: dict
    triggered: bool
    error: str


@dataclass
class WorkGraphResult:
    status: str
    assistant_message: str
    draft_task: dict
    missing_fields: list[str]
    needs_confirmation: bool


def _language_copy(language: str) -> dict:
    if (language or "en").startswith("zh"):
        return {
            "missing_asset": "我还不知道要监控哪个币。请直接告诉我币种符号，比如 SUI、BTC、ETH。",
            "missing_operator": "我还需要知道方向：是涨破还是跌破？比如“跌破 1 美元”或者“涨破 2 美元”。",
            "missing_threshold": "我还需要阈值价格，比如 1 美元、0.8 美元或 2.5 USD。",
            "summary": "我理解成这个任务：当 {asset} {operator_label} {threshold} {currency} 时，向 {recipient} 发送提醒邮件。确认创建吗？",
            "operator_below": "跌破",
            "operator_above": "涨破",
            "not_email": "第一版 Work 目前只支持价格触发邮件任务。你可以直接说：当 SUI 跌破 1 美元就给我发邮件。",
        }
    return {
        "missing_asset": "I still need the asset symbol. Tell me something like SUI, BTC, or ETH.",
        "missing_operator": "I still need the direction. For example: below 1 USD or above 2 USD.",
        "missing_threshold": "I still need the threshold price, for example 1 USD or 0.8 USD.",
        "summary": "I understand the task as: when {asset} goes {operator_label} {threshold} {currency}, send an alert email to {recipient}. Confirm to create it?",
        "operator_below": "below",
        "operator_above": "above",
        "not_email": "The first Work version only supports price-triggered email tasks. Try something like: email me when SUI drops below 1 USD.",
    }


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_asset(text: str) -> str | None:
    if not text:
        return None
    # Chinese coin names take priority
    for cn_name, symbol in CN_ASSET_MAP.items():
        if cn_name in text:
            return symbol
    # Latin-letter ticker symbols
    matches = re.findall(r"\b[A-Za-z][A-Za-z0-9]{1,9}\b", text)
    for match in matches:
        normalized = match.upper()
        if normalized in ASSET_STOPWORDS:
            continue
        if normalized.startswith("HTTP"):
            continue
        return normalized
    return None


def _extract_operator(text: str) -> str | None:
    normalized = (text or "").lower()
    if any(word in normalized for word in ("跌破", "低于", "under", "below", "drops below", "fall below")):
        return "below"
    if any(word in normalized for word in ("涨破", "高于", "above", "over", "break above", "goes above")):
        return "above"
    return None


def _extract_threshold(text: str) -> float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)", text or "")
    for match in matches:
        try:
            return float(match)
        except Exception:
            continue
    return None


def _extract_currency(text: str) -> str:
    normalized = (text or "").lower()
    if any(token in normalized for token in ("美元", "usd", "us dollar", "刀")):
        return "USD"
    if "usdt" in normalized or "u " in normalized or normalized.endswith("u"):
        return "USDT"
    return "USD"


def _detect_email_intent(text: str) -> bool:
    return True


def _merge_task(existing: dict, message: str, user_email: str) -> dict:
    merged = dict(existing or {})
    asset = _extract_asset(message)
    operator = _extract_operator(message)
    threshold = _extract_threshold(message)
    currency = _extract_currency(message)
    if asset:
        merged["asset_symbol"] = asset
    if operator:
        merged["operator"] = operator
    if threshold is not None:
        merged["threshold_value"] = threshold
    if currency:
        merged["threshold_currency"] = currency
    merged["recipient_email"] = merged.get("recipient_email") or user_email
    merged["workflow_type"] = WORKFLOW_PRICE_THRESHOLD_EMAIL
    return merged


def _missing_fields(task: dict) -> list[str]:
    missing = []
    if not task.get("asset_symbol"):
        missing.append("asset_symbol")
    if not task.get("operator"):
        missing.append("operator")
    if task.get("threshold_value") in (None, ""):
        missing.append("threshold_value")
    return missing


def _operator_label(language: str, operator: str) -> str:
    copy = _language_copy(language)
    if operator == "below":
        return copy["operator_below"]
    return copy["operator_above"]


def _build_title(asset_symbol: str, operator: str, threshold_value: float, currency: str) -> str:
    operator_label = "below" if operator == "below" else "above"
    return f"Alert: {asset_symbol} {operator_label} {threshold_value:.4f} {currency}".replace(".0000", "")


def _build_subject(asset_symbol: str, operator: str, threshold_value: float, currency: str) -> str:
    return _build_title(asset_symbol, operator, threshold_value, currency)


def parse_user_request(state: AuthoringState) -> AuthoringState:
    message = _normalize_space(state.get("message") or "")
    language = state.get("language") or "en"
    user_email = state.get("user_email") or ""
    current_task = dict(state.get("draft_task") or {})

    if not _detect_email_intent(message):
        state["status"] = "waiting_for_input"
        state["assistant_message"] = _language_copy(language)["not_email"]
        state["draft_task"] = current_task
        state["missing_fields"] = []
        state["needs_confirmation"] = False
        return state

    merged_task = _merge_task(current_task, message, user_email)
    state["draft_task"] = merged_task
    return state


def collect_missing_fields(state: AuthoringState) -> AuthoringState:
    language = state.get("language") or "en"
    task = dict(state.get("draft_task") or {})
    missing = _missing_fields(task)
    state["missing_fields"] = missing
    if not missing:
        return state

    copy = _language_copy(language)
    if "asset_symbol" in missing:
        message = copy["missing_asset"]
    elif "operator" in missing:
        message = copy["missing_operator"]
    else:
        message = copy["missing_threshold"]

    state["status"] = "waiting_for_input"
    state["assistant_message"] = message
    state["needs_confirmation"] = False
    return state


def normalize_condition(state: AuthoringState) -> AuthoringState:
    task = dict(state.get("draft_task") or {})
    language = state.get("language") or "en"

    if not task:
        return state

    task["asset_symbol"] = str(task["asset_symbol"]).upper()
    task["threshold_currency"] = str(task.get("threshold_currency") or "USD").upper()
    task["threshold_value"] = float(task["threshold_value"])
    task["recipient_email"] = task.get("recipient_email") or state.get("user_email") or ""
    task["title"] = _build_title(
        task["asset_symbol"],
        task["operator"],
        task["threshold_value"],
        task["threshold_currency"],
    )
    task["email_subject"] = _build_subject(
        task["asset_symbol"],
        task["operator"],
        task["threshold_value"],
        task["threshold_currency"],
    )
    task["summary_text"] = _language_copy(language)["summary"].format(
        asset=task["asset_symbol"],
        operator_label=_operator_label(language, task["operator"]),
        threshold=f"{task['threshold_value']:.4f}".rstrip("0").rstrip("."),
        currency=task["threshold_currency"],
        recipient=task["recipient_email"],
    )
    state["draft_task"] = task
    return state


def draft_task_summary(state: AuthoringState) -> AuthoringState:
    task = dict(state.get("draft_task") or {})
    state["status"] = "waiting_for_confirmation"
    state["assistant_message"] = task.get("summary_text") or ""
    state["needs_confirmation"] = True
    state["missing_fields"] = []
    return state


def load_task(state: ExecutionState) -> ExecutionState:
    return state


def evaluate_condition(state: ExecutionState) -> ExecutionState:
    task = state.get("task") or {}
    price_payload = state.get("price_payload") or {}
    price_value = float(price_payload.get("price") or 0.0)
    threshold_value = float(task.get("threshold_value") or 0.0)
    operator = task.get("operator")
    if operator == "below":
        state["triggered"] = price_value <= threshold_value
    else:
        state["triggered"] = price_value >= threshold_value
    return state


def handle_failure(state: ExecutionState) -> ExecutionState:
    return state


def mark_completed(state: ExecutionState) -> ExecutionState:
    return state


def _authoring_router(state: AuthoringState) -> str:
    if state.get("missing_fields"):
        return "done"
    return "normalize_condition"


def _execution_router(state: ExecutionState) -> str:
    if state.get("error"):
        return "handle_failure"
    if state.get("triggered"):
        return "mark_completed"
    return END


def build_authoring_graph():
    graph = StateGraph(AuthoringState)
    graph.add_node("parse_user_request", parse_user_request)
    graph.add_node("collect_missing_fields", collect_missing_fields)
    graph.add_node("normalize_condition", normalize_condition)
    graph.add_node("draft_task_summary", draft_task_summary)
    graph.set_entry_point("parse_user_request")
    graph.add_edge("parse_user_request", "collect_missing_fields")
    graph.add_conditional_edges(
        "collect_missing_fields",
        _authoring_router,
        {
            "done": END,
            "normalize_condition": "normalize_condition",
        },
    )
    graph.add_edge("normalize_condition", "draft_task_summary")
    graph.add_edge("draft_task_summary", END)
    return graph.compile()


def build_execution_graph(fetch_price_node, send_email_node):
    graph = StateGraph(ExecutionState)
    graph.add_node("load_task", load_task)
    graph.add_node("fetch_price_via_mcp", fetch_price_node)
    graph.add_node("evaluate_condition", evaluate_condition)
    graph.add_node("send_email", send_email_node)
    graph.add_node("mark_completed", mark_completed)
    graph.add_node("handle_failure", handle_failure)
    graph.set_entry_point("load_task")
    graph.add_edge("load_task", "fetch_price_via_mcp")
    graph.add_edge("fetch_price_via_mcp", "evaluate_condition")
    graph.add_conditional_edges(
        "evaluate_condition",
        _execution_router,
        {
            "handle_failure": "handle_failure",
            "mark_completed": "send_email",
            END: END,
        },
    )
    graph.add_edge("send_email", "mark_completed")
    graph.add_edge("mark_completed", END)
    graph.add_edge("handle_failure", END)
    return graph.compile()


AUTHORING_GRAPH = build_authoring_graph()

# ──────────────────────────────────────────────
# Cron email workflow
# ──────────────────────────────────────────────

WORKFLOW_CRON_EMAIL = "cron_email"


def _compute_relative_cron(offset_minutes: int) -> str:
    """Compute an absolute cron expression for X minutes from now (UTC)."""
    target_ts = time.time() + offset_minutes * 60
    target_utc = datetime.datetime.fromtimestamp(target_ts, tz=datetime.timezone.utc)
    return f"{target_utc.minute} {target_utc.hour} * * *"


def _preprocess_cn_digits(text: str) -> str:
    """Replace simple Chinese numerals with ASCII digits for easier regex matching."""
    if not text:
        return text
    replacements = {"零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
                    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    result = text
    for cn, digit in replacements.items():
        result = result.replace(cn, digit)
    return result


def detect_cron_intent(text: str, language: str = "en") -> bool:
    """Detect if a message describes a cron/scheduled task."""
    normalized = (text or "").strip().lower()
    if language.startswith("zh"):
        # also check with Chinese digits converted
        cn_normalized = _preprocess_cn_digits(normalized)
        # Relative time: "再过X分钟", "X分钟后", "过半小时"
        # ASCII digit patterns
        if re.search(r'(再过|过)\s*\d+\s*分钟', cn_normalized):
            return True
        if re.search(r'\d+\s*分钟\s*(后|之后)', cn_normalized):
            return True
        if re.search(r'\d+\s*小时\s*(后|之后)', cn_normalized):
            return True
        # Chinese number words: 十(10), 二十(20), 半(30), 一刻(15)
        if re.search(r'(再过|过)\s*(十|二十|三十|半|一刻)\s*(分钟|小时|钟)', cn_normalized):
            return True
        if re.search(r'半\s*个?\s*小时\s*(后|之后)', cn_normalized):
            return True
        if re.search(r'每\s*\d*\s*[小时分天周]', cn_normalized):
            return True
        if re.search(r'(定时|定期|每天|每日|每周)', cn_normalized):
            return True
        # implicit "每天" — "天" at start + time reference
        if re.search(r'^天[^\n]*[点时分]', cn_normalized):
            return True
        # time-of-day implies daily schedule
        if re.search(r'(凌晨|早上|早晨|上午|下午|晚上|今晚|明天).*[点]', cn_normalized):
            return True
    else:
        if re.search(r'\b(every|each)\s+(\d+\s+)?(minutes?|hours?|days?|weeks?|mornings?|afternoons?|evenings?|nights?)\b', normalized):
            return True
        if re.search(r'\b(hourly|daily|weekly|cron|schedule|recurring|scheduled)\b', normalized):
            return True
    return False


def _beijing_to_utc_hour(bj_hour: int) -> int:
    """Convert Beijing time (UTC+8) hour to UTC hour."""
    return (bj_hour + 16) % 24


def _extract_cron_expression(text: str, language: str = "en") -> str | None:
    """Extract a cron expression from natural language text."""
    normalized = text.lower().strip()
    if language.startswith("zh"):
        # pre-process Chinese digits so "两点" → "2点" etc.
        normalized = _preprocess_cn_digits(normalized)
        patterns = [
            # Relative time: "再过X分钟" / "X分钟后" (one-shot, compute absolute time)
            (r'(再过|过)\s*十\s*分钟', lambda _: _compute_relative_cron(10)),
            (r'(再过|过)\s*二十\s*分钟', lambda _: _compute_relative_cron(20)),
            (r'(再过|过)\s*三十\s*分钟', lambda _: _compute_relative_cron(30)),
            (r'(再过|过)\s*半\s*个?\s*小时', lambda _: _compute_relative_cron(30)),
            (r'(再过|过)\s*一刻\s*钟', lambda _: _compute_relative_cron(15)),
            (r'(再过|过)\s*(\d+)\s*分钟', lambda m: _compute_relative_cron(int(m.group(2)))),
            (r'(\d+)\s*分钟\s*(后|之后)', lambda m: _compute_relative_cron(int(m.group(1)))),
            (r'(\d+)\s*小时\s*(后|之后)', lambda m: _compute_relative_cron(int(m.group(1)) * 60)),
            (r'半\s*个?\s*小时\s*(后|之后)', lambda _: _compute_relative_cron(30)),
            (r'过\s*半\s*个?\s*小时', lambda _: _compute_relative_cron(30)),
            (r'每\s*(\d+)\s*分钟', lambda m: f'*/{m.group(1)} * * * *'),
            (r'每\s*(\d+)\s*小时', lambda m: f'0 */{m.group(1)} * * *'),
            # X点Y(分) — specific minute, must come before bare X点 / X点半
            (r'每天\s*(\d+)\s*点\s*(\d+)(?:\s*分)?', lambda m: f'{int(m.group(2))} {_beijing_to_utc_hour(int(m.group(1)))} * * *'),
            (r'每日\s*(\d+)\s*点\s*(\d+)(?:\s*分)?', lambda m: f'{int(m.group(2))} {_beijing_to_utc_hour(int(m.group(1)))} * * *'),
            (r'(凌晨|早上|早晨|上午)\s*(\d+)\s*点\s*(\d+)(?:\s*分)?', lambda m: f'{int(m.group(3))} {_beijing_to_utc_hour(int(m.group(2)))} * * *'),
            (r'(下午|晚上)\s*(\d+)\s*点\s*(\d+)(?:\s*分)?', lambda m: f'{int(m.group(3))} {_beijing_to_utc_hour(int(m.group(2)) + 12)} * * *'),
            # X点半
            (r'每天\s*(\d+)\s*点\s*半', lambda m: f'30 {_beijing_to_utc_hour(int(m.group(1)))} * * *'),
            (r'每天\s*(\d+)\s*点', lambda m: f'0 {_beijing_to_utc_hour(int(m.group(1)))} * * *'),
            (r'每日\s*(\d+)\s*点\s*半', lambda m: f'30 {_beijing_to_utc_hour(int(m.group(1)))} * * *'),
            (r'每日\s*(\d+)\s*点', lambda m: f'0 {_beijing_to_utc_hour(int(m.group(1)))} * * *'),
            (r'(凌晨|早上|早晨|上午)\s*(\d+)\s*点\s*半', lambda m: f'30 {_beijing_to_utc_hour(int(m.group(2)))} * * *'),
            (r'(凌晨|早上|早晨|上午)\s*(\d+)\s*点', lambda m: f'0 {_beijing_to_utc_hour(int(m.group(2)))} * * *'),
            (r'(下午|晚上)\s*(\d+)\s*点\s*半', lambda m: f'30 {_beijing_to_utc_hour(int(m.group(2)) + 12)} * * *'),
            (r'(下午|晚上)\s*(\d+)\s*点', lambda m: f'0 {_beijing_to_utc_hour(int(m.group(2)) + 12)} * * *'),
            (r'每小时', lambda _: '0 * * * *'),
            (r'每\s*(\d+)\s*天', lambda m: f'0 0 */{m.group(1)} * *'),
            (r'每天', lambda _: '0 0 * * *'),
            (r'每周', lambda _: '0 0 * * 0'),
        ]
    else:
        patterns = [
            # Relative time (compute absolute cron from now + offset)
            (r'in\s+(\d+)\s*minutes?\b', lambda m: _compute_relative_cron(int(m.group(1)))),
            (r'in\s+(\d+)\s*hours?\b', lambda m: _compute_relative_cron(int(m.group(1)) * 60)),
            (r'in\s+half\s*an?\s*hour\b', lambda _: _compute_relative_cron(30)),
            (r'(\d+)\s*minutes?\s+(later|from now)\b', lambda m: _compute_relative_cron(int(m.group(1)))),
            (r'(\d+)\s*hours?\s+(later|from now)\b', lambda m: _compute_relative_cron(int(m.group(1)) * 60)),
            (r'every\s+(\d+)\s*minutes?', lambda m: f'*/{int(m.group(1))} * * * *'),
            (r'every\s+(\d+)\s*hours?', lambda m: f'0 */{int(m.group(1))} * * *'),
            (r'every\s+day\s+at\s+(\d{1,2})', lambda m: f'0 {int(m.group(1)) % 24} * * *'),
            (r'daily\s+at\s+(\d{1,2})', lambda m: f'0 {int(m.group(1)) % 24} * * *'),
            (r'every\s+(morning)', lambda _: '0 9 * * *'),
            (r'every\s+(evening)', lambda _: '0 18 * * *'),
            (r'every\s+(afternoon)', lambda _: '0 13 * * *'),
            (r'\bevery\s+hour\b', lambda _: '0 * * * *'),
            (r'\bhourly\b', lambda _: '0 * * * *'),
            (r'\bdaily\b', lambda _: '0 0 * * *'),
            (r'\bweekly\b', lambda _: '0 0 * * 0'),
        ]
    for pattern_str, builder in patterns:
        match = re.search(pattern_str, normalized)
        if match:
            return builder(match)
    return None


def cron_parse_request(state: AuthoringState) -> AuthoringState:
    """Parse a cron email request — extract asset and schedule."""
    message = _normalize_space(state.get("message") or "")
    language = state.get("language") or "en"
    user_email = state.get("user_email") or ""
    current_task = dict(state.get("draft_task") or {})

    asset = _extract_asset(message)
    cron_expr = _extract_cron_expression(message, language)

    merged = dict(current_task)
    if asset:
        merged["asset_symbol"] = asset
    if cron_expr:
        merged["cron_expression"] = cron_expr
    merged["recipient_email"] = merged.get("recipient_email") or user_email
    merged["workflow_type"] = WORKFLOW_CRON_EMAIL

    state["draft_task"] = merged
    return state


def cron_collect_missing_fields(state: AuthoringState) -> AuthoringState:
    """Check for missing fields in a cron draft task."""
    language = state.get("language") or "en"
    task = dict(state.get("draft_task") or {})

    missing = []
    if not task.get("asset_symbol"):
        missing.append("asset_symbol")
    if not task.get("cron_expression"):
        missing.append("cron_expression")

    state["missing_fields"] = missing
    if not missing:
        return state

    if "asset_symbol" in missing:
        message = _language_copy(language)["missing_asset"]
    else:
        message = (
            "请告诉我发送频率，例如：每天 9 点、每小时、每 30 分钟。"
            if language.startswith("zh")
            else "Tell me the schedule, e.g. every day at 9am, every hour, every 30 minutes."
        )

    state["status"] = "waiting_for_input"
    state["assistant_message"] = message
    state["needs_confirmation"] = False
    return state


def cron_normalize(state: AuthoringState) -> AuthoringState:
    """Normalize cron task fields and build summary."""
    task = dict(state.get("draft_task") or {})
    language = state.get("language") or "en"

    task["asset_symbol"] = str(task["asset_symbol"]).upper()
    task["recipient_email"] = task.get("recipient_email") or state.get("user_email") or ""
    task["threshold_currency"] = "USD"
    task["threshold_value"] = 0.0
    task["operator"] = ""

    asset = task["asset_symbol"]
    cron_exp = task.get("cron_expression", "recurring")
    task["title"] = f"Scheduled: {asset} ({cron_exp})"
    task["email_subject"] = f"Scheduled Report: {asset}"
    if language.startswith("zh"):
        task["summary_text"] = (
            f"我将按计划（{cron_exp}）向 {task['recipient_email']} 发送 {asset} 的价格报告。确认创建吗？"
        )
    else:
        task["summary_text"] = (
            f"I will send {asset} price reports to {task['recipient_email']} "
            f"on schedule ({cron_exp}). Confirm to create?"
        )

    state["draft_task"] = task
    return state


def _cron_authoring_router(state: AuthoringState) -> str:
    if state.get("missing_fields"):
        return "done"
    return "cron_normalize"


def build_cron_authoring_graph():
    graph = StateGraph(AuthoringState)
    graph.add_node("cron_parse_request", cron_parse_request)
    graph.add_node("cron_collect_missing_fields", cron_collect_missing_fields)
    graph.add_node("cron_normalize", cron_normalize)
    graph.add_node("draft_task_summary", draft_task_summary)
    graph.set_entry_point("cron_parse_request")
    graph.add_edge("cron_parse_request", "cron_collect_missing_fields")
    graph.add_conditional_edges(
        "cron_collect_missing_fields",
        _cron_authoring_router,
        {
            "done": END,
            "cron_normalize": "cron_normalize",
        },
    )
    graph.add_edge("cron_normalize", "draft_task_summary")
    graph.add_edge("draft_task_summary", END)
    return graph.compile()


def build_cron_execution_graph(fetch_price_node, send_email_node):
    """Simpler execution graph — fetch price, send email, done (no condition check)."""
    graph = StateGraph(ExecutionState)
    graph.add_node("load_task", load_task)
    graph.add_node("fetch_price_via_mcp", fetch_price_node)
    graph.add_node("send_email", send_email_node)
    graph.add_node("handle_failure", handle_failure)
    graph.set_entry_point("load_task")
    graph.add_edge("load_task", "fetch_price_via_mcp")
    graph.add_edge("fetch_price_via_mcp", "send_email")
    graph.add_edge("send_email", END)
    graph.add_edge("handle_failure", END)
    return graph.compile()


CRON_AUTHORING_GRAPH = build_cron_authoring_graph()


def _cron_to_description(cron_expr: str, language: str) -> str:
    """Convert cron MM HH * * * to a human-readable time description."""
    parts = (cron_expr or "").strip().split()
    if len(parts) >= 2:
        try:
            minute = int(parts[0])
            hour_utc = int(parts[1])
            hour_bj = (hour_utc + 8) % 24
            if language.startswith("zh"):
                return f"每天 {hour_bj:02d}:{minute:02d}（北京时间）"
            return f"Daily at {hour_bj:02d}:{minute:02d} (Beijing Time)"
        except ValueError:
            pass
    # Fallback: return the raw expression
    return cron_expr


def _build_cron_summary(draft: dict, language: str) -> str:
    """Build a human-readable summary for a cron task."""
    asset = draft.get("asset_symbol") or "?"
    email = draft.get("recipient_email") or "?"
    cron = draft.get("cron_expression") or ""
    desc = _cron_to_description(cron, language)
    if language.startswith("zh"):
        return f"我将{desc}向 {email} 发送 {asset} 的价格报告。确认创建吗？"
    return f"I will send {asset} price reports to {email} {desc}. Confirm to create?"


def _build_threshold_summary(draft: dict, language: str) -> str:
    """Build a human-readable summary for a threshold task."""
    asset = draft.get("asset_symbol") or "?"
    operator = draft.get("operator") or ""
    threshold = draft.get("threshold_value") or 0
    currency = draft.get("threshold_currency") or "USD"
    email = draft.get("recipient_email") or "?"
    if language.startswith("zh"):
        op_label = "跌破" if operator == "below" else "涨破"
        return f"当 {asset} {op_label} {threshold} {currency} 时，向 {email} 发送提醒邮件。确认创建吗？"
    op_label = "below" if operator == "below" else "above"
    return f"When {asset} goes {op_label} {threshold} {currency}, send an alert to {email}. Confirm to create?"


# ---------------------------------------------------------------------------
# LLM-based authoring (replaces the regex-based graphs above)
# ---------------------------------------------------------------------------

LLM_AUTHORING_SYSTEM_PROMPT = """你是一个任务创建助手，通过对话帮用户创建邮件通知任务。

当前草稿：
{draft_json}

用户最新消息：{message}

请严格按照以下 JSON Schema 更新草稿，只返回 JSON，不要 markdown 包裹，不要加任何说明：

{{
  "draft_task": {{
    "workflow_type": "cron_email 或 price_threshold_email",
    "asset_symbol": "币种大写符号，如 BTC、ETH、SOL",
    "operator": "阈值类型：below(跌破) 或 above(涨破)，仅 price_threshold_email 需要",
    "threshold_value": 阈值数字，仅 price_threshold_email 需要,
    "threshold_currency": "USD",
    "cron_expression": "cron 定时表达式，仅 cron_email 需要，如 30 5 * * *",
    "cron_description": "cron 表达式的自然语言描述，仅 cron_email 需要",
    "recipient_email": "{default_email}",
    "title": "任务的简短标题",
    "email_subject": "邮件主题",
    "summary_text": "任务摘要，确认时展示给用户"
  }},
  "assistant_message": "对用户说的话。如果 needs_confirmation=false 就问缺失信息，一次只问一个最关键的问题；如果 needs_confirmation=true 就说任务摘要让用户确认",
  "needs_confirmation": true或false,
  "missing_fields": ["缺失的字段名列表，全部填了就空数组"]
}}

时间处理规则（所有时间用 UTC）：
- "再过X分钟"、"X分钟后" → 计算当前 UTC 时间加 X 分钟 → 绝对 cron "MM HH * * *"
- "每天早上/上午 X 点" → cron "0 (X+16)%24 * * *"
- "每X分钟" → cron "*/X * * * *"
- "每X小时" → cron "0 */X * * *"
- cron_description 用中文写 "今天 HH:MM（北京时间）" 格式

注意字段名必须是 workflow_type / asset_symbol / cron_expression，不要自己改名。

用 {language} 回复用户。"""


def llm_authoring_turn(state: dict, message: str) -> dict:
    """One turn of LLM-based task authoring.

    Takes current state + user message, returns updated state.
    The LLM decides what fields to fill and whether to ask for more info.
    """
    draft_task = state.get("draft_task") or {}
    language = state.get("language") or "en"
    default_email = state.get("user_email") or ""

    prompt = LLM_AUTHORING_SYSTEM_PROMPT.format(
        draft_json=json.dumps(draft_task, ensure_ascii=False),
        message=message,
        language=language,
        default_email=default_email,
    )

    try:
        result = _chat_completion_raw(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.1,
        )
        content = (result.get("content") or "").strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        parsed = json.loads(content)
    except Exception:
        # Fallback: ask the user to rephrase
        fallback_msg = "请换一种方式描述你要创建的任务，比如：每天早上9点发BTC价格邮件。" if language.startswith("zh") else "Please rephrase your task request, e.g.: send BTC price every day at 9am."
        return {
            "draft_task": draft_task,
            "assistant_message": fallback_msg,
            "needs_confirmation": False,
            "missing_fields": ["unknown"],
            "status": "waiting_for_input",
        }

    llm_draft = parsed.get("draft_task") or {}
    new_draft = dict(draft_task)
    new_draft.update(llm_draft)

    # Extract workflow_type from anywhere in the parsed response
    wt = llm_draft.get("workflow_type") or parsed.get("workflow_type") or draft_task.get("workflow_type") or ""
    if wt:
        new_draft["workflow_type"] = wt

    # Override with deterministic extraction for reliability
    asset = _extract_asset(message)
    if asset:
        new_draft["asset_symbol"] = asset
    op = _extract_operator(message)
    if op:
        new_draft["operator"] = op
    thresh = _extract_threshold(message)
    if thresh is not None:
        new_draft["threshold_value"] = thresh

    assistant_message = parsed.get("assistant_message") or ""
    needs_confirmation = bool(parsed.get("needs_confirmation", False))
    missing_fields = parsed.get("missing_fields") or []

    # Rebuild summary with deterministic time description.
    # Prefer regex-extracted cron over LLM for reliability on common patterns.
    regex_cron = _extract_cron_expression(message, language)
    if regex_cron and new_draft.get("workflow_type") == WORKFLOW_CRON_EMAIL:
        new_draft["cron_expression"] = regex_cron
    cron_expr = new_draft.get("cron_expression") or ""
    if cron_expr and new_draft.get("workflow_type") == WORKFLOW_CRON_EMAIL:
        new_draft["cron_description"] = _cron_to_description(cron_expr, language)
    if needs_confirmation and new_draft.get("workflow_type") == WORKFLOW_CRON_EMAIL:
        s = _build_cron_summary(new_draft, language)
        if s:
            new_draft["summary_text"] = s
            assistant_message = s
    elif needs_confirmation and new_draft.get("workflow_type") == WORKFLOW_PRICE_THRESHOLD_EMAIL:
        s = _build_threshold_summary(new_draft, language)
        if s:
            new_draft["summary_text"] = s
            assistant_message = s

    return {
        "draft_task": new_draft,
        "assistant_message": assistant_message,
        "needs_confirmation": needs_confirmation,
        "missing_fields": missing_fields,
        "status": "waiting_for_confirmation" if needs_confirmation else "waiting_for_input",
    }

