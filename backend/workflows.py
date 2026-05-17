from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, StateGraph


WORKFLOW_PRICE_THRESHOLD_EMAIL = "price_threshold_email"

ASSET_STOPWORDS = {
    "WHEN", "EMAIL", "MAIL", "SEND", "PRICE", "USD", "USDT", "IF", "THE", "THEN",
    "WORK", "ALERT", "BELOW", "ABOVE", "UNDER", "OVER",
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
    matches = re.findall(r"\b[A-Za-z][A-Za-z0-9]{1,9}\b", text or "")
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
