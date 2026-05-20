from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

import auth
from store import (
    cancel_work_task,
    claim_due_work_tasks,
    clear_work_task_lock,
    create_work_session,
    create_work_task,
    get_work_session,
    get_work_task,
    get_work_task_by_id,
    list_work_tasks,
    update_work_session,
    update_work_task_runtime,
)
from task_broker import publish_work_job, start_work_worker
from work_mcp import get_asset_price
from workflows import (
    AUTHORING_GRAPH,
    CRON_AUTHORING_GRAPH,
    WORKFLOW_PRICE_THRESHOLD_EMAIL,
    WORKFLOW_CRON_EMAIL,
    build_execution_graph,
    build_cron_execution_graph,
    llm_authoring_turn,
)


_scheduler_started = False
_execution_graph = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _scheduler_interval_seconds() -> int:
    return max(60, int(os.getenv("WORK_SCHEDULER_INTERVAL_SECONDS", "60")))


def _task_check_interval_seconds() -> int:
    return _scheduler_interval_seconds()


def _language_from(value: str | None) -> str:
    return "zh" if str(value or "").lower().startswith("zh") else "en"


def _empty_state(language: str, user_email: str, workflow_type: str = WORKFLOW_PRICE_THRESHOLD_EMAIL) -> dict:
    return {
        "language": _language_from(language),
        "user_email": user_email,
        "workflow_type": workflow_type,
        "draft_task": {"workflow_type": workflow_type, "recipient_email": user_email},
        "missing_fields": [],
        "status": "draft",
        "assistant_message": "",
        "needs_confirmation": False,
    }


def _public_task(task: dict) -> dict:
    return {
        "id": task["id"],
        "workflow_type": task["workflow_type"],
        "title": task["title"],
        "status": task["status"],
        "asset_symbol": task["asset_symbol"],
        "operator": task["operator"],
        "threshold_value": task["threshold_value"],
        "threshold_currency": task["threshold_currency"],
        "recipient_email": task["recipient_email"],
        "email_subject": task["email_subject"],
        "cron_expression": task.get("cron_expression") or "",
        "last_checked_at": task.get("last_checked_at"),
        "last_price": task.get("last_price"),
        "last_triggered_at": task.get("last_triggered_at"),
        "last_error": task.get("last_error"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


def _public_session(session: dict) -> dict:
    state = session.get("state") or {}
    draft_task = dict(state.get("draft_task") or {})
    draft_public = None
    if draft_task:
        draft_public = {
            "workflow_type": draft_task.get("workflow_type") or WORKFLOW_PRICE_THRESHOLD_EMAIL,
            "asset_symbol": draft_task.get("asset_symbol"),
            "operator": draft_task.get("operator"),
            "threshold_value": draft_task.get("threshold_value"),
            "threshold_currency": draft_task.get("threshold_currency"),
            "recipient_email": draft_task.get("recipient_email"),
            "title": draft_task.get("title"),
            "email_subject": draft_task.get("email_subject"),
            "summary_text": draft_task.get("summary_text"),
            "cron_expression": draft_task.get("cron_expression") or "",
            "cron_description": draft_task.get("cron_description") or "",
        }
    return {
        "session_id": session["id"],
        "status": session["status"],
        "assistant_message": state.get("assistant_message") or "",
        "draft_task": draft_public,
        "needs_confirmation": bool(state.get("needs_confirmation")),
    }


def handle_work_assistant_message(*, user: dict, message: str, session_id: str | None, language: str | None) -> dict:
    if user is None:
        raise PermissionError("Login required")

    normalized_message = (message or "").strip()
    if not normalized_message:
        raise ValueError("Message is required")

    lang = _language_from(language)
    user_email = user["email"]

    if session_id:
        session = get_work_session(session_id, user["id"])
        if session is None:
            session = None
    else:
        session = None
    if session is None:
        session = create_work_session(
            user_id=user["id"],
            workflow_type="",
            status="draft",
            state=_empty_state(lang, user_email, ""),
        )

    current_state = dict(session.get("state") or {})
    current_state["language"] = lang
    current_state["user_email"] = user_email

    next_state = llm_authoring_turn(current_state, normalized_message)

    workflow_type = next_state.get("draft_task", {}).get("workflow_type") or ""
    updated_session = update_work_session(
        session["id"],
        user["id"],
        status=str(next_state.get("status") or "draft"),
        state=next_state,
    )
    return _public_session(updated_session)


def confirm_work_task(*, user: dict, session_id: str) -> dict:
    if user is None:
        raise PermissionError("Login required")
    session = get_work_session(session_id, user["id"])
    if session is None:
        raise ValueError("Session not found")
    state = dict(session.get("state") or {})
    if session.get("status") != "waiting_for_confirmation":
        raise ValueError("This task is not ready to confirm")

    draft_task = dict(state.get("draft_task") or {})
    is_cron = draft_task.get("workflow_type") == WORKFLOW_CRON_EMAIL

    if is_cron:
        for field in ("asset_symbol", "cron_expression", "recipient_email", "title", "email_subject"):
            if draft_task.get(field) in (None, ""):
                raise ValueError(f"Task draft is missing {field}")
    else:
        for field in ("asset_symbol", "operator", "threshold_value", "threshold_currency", "recipient_email", "title", "email_subject"):
            if draft_task.get(field) in (None, ""):
                raise ValueError(f"Task draft is missing {field}")

    task = create_work_task(
        user_id=user["id"],
        user_email=user["email"],
        workflow_type=draft_task["workflow_type"],
        title=draft_task["title"],
        status="active",
        asset_symbol=draft_task["asset_symbol"],
        operator=draft_task.get("operator", ""),
        threshold_value=float(draft_task.get("threshold_value", 0)),
        threshold_currency=draft_task.get("threshold_currency", "USD"),
        recipient_email=draft_task["recipient_email"],
        email_subject=draft_task["email_subject"],
        email_template_payload={
            "summary_text": draft_task.get("summary_text") or "",
        },
        cron_expression=draft_task.get("cron_expression", ""),
        next_check_at=_next_cron_tick(draft_task.get("cron_expression", ""), int(time.time())) if is_cron else int(time.time()),
    )
    update_work_session(
        session_id,
        user["id"],
        status="completed",
        state={
            **state,
            "assistant_message": "Task created." if _language_from(state.get("language")) == "en" else "任务已创建。",
            "needs_confirmation": False,
            "created_task_id": task["id"],
        },
    )
    return _public_task(task)


def list_user_work_tasks(user: dict, *, include_completed: bool = False) -> list[dict]:
    if user is None:
        raise PermissionError("Login required")
    return [_public_task(task) for task in list_work_tasks(user["id"], include_completed=include_completed)]


def get_user_work_task(user: dict, task_id: str) -> dict:
    if user is None:
        raise PermissionError("Login required")
    task = get_work_task(task_id, user["id"])
    if task is None:
        raise ValueError("Task not found")
    return _public_task(task)


def cancel_user_work_task(user: dict, task_id: str) -> dict:
    if user is None:
        raise PermissionError("Login required")
    task = cancel_work_task(task_id, user["id"])
    if task is None:
        raise ValueError("Task not found")
    return _public_task(task)


def _fetch_price_node(state: dict) -> dict:
    task = state.get("task") or {}
    try:
        payload = get_asset_price(str(task.get("asset_symbol") or ""))
        state["price_payload"] = payload
        state["error"] = ""
    except Exception as exc:
        state["error"] = str(exc)
    return state


def _build_work_email(task: dict, price_payload: dict) -> tuple[str, str]:
    is_cron = task.get("workflow_type") == WORKFLOW_CRON_EMAIL
    actual_price = f"{float(price_payload.get('price') or 0.0):,.6f}".rstrip("0").rstrip(".")
    source = price_payload.get("source") or "mcp"
    triggered_at = _iso_now()
    subject = task["email_subject"]
    currency = price_payload.get("currency", "USD")

    if is_cron:
        text = (
            f"Scheduled Report: {task['title']}\n"
            f"Asset: {task['asset_symbol']}\n"
            f"Current Price: {actual_price} {currency}\n"
            f"Reported at: {triggered_at}\n"
            f"Source: {source}\n"
        )
        html = (
            "<div style='font-family:Georgia,Times New Roman,serif;padding:24px;max-width:560px'>"
            "<h2 style='margin:0 0 16px;color:#c96442'>Elephant Jungle Scheduled Report</h2>"
            f"<p><strong>Asset:</strong> {task['asset_symbol']}</p>"
            f"<p><strong>Current Price:</strong> {actual_price} {currency}</p>"
            f"<p><strong>Reported at:</strong> {triggered_at}</p>"
            f"<p><strong>Source:</strong> {source}</p>"
            "</div>"
        )
    else:
        operator_label = "below" if task.get("operator") == "below" else "above"
        amount_text = f"{float(task['threshold_value']):.4f}".rstrip("0").rstrip(".")
        text = (
            f"Task: {task['title']}\n"
            f"Condition: {task['asset_symbol']} {operator_label} {amount_text} {task['threshold_currency']}\n"
            f"Actual price: {actual_price} {currency}\n"
            f"Triggered at: {triggered_at}\n"
            f"Source: {source}\n"
            f"Task ID: {task['id']}\n"
        )
        html = (
            "<div style='font-family:Georgia,Times New Roman,serif;padding:24px;max-width:560px'>"
            "<h2 style='margin:0 0 16px;color:#c96442'>Elephant Jungle Work Alert</h2>"
            f"<p><strong>Task:</strong> {task['title']}</p>"
            f"<p><strong>Condition:</strong> {task['asset_symbol']} {operator_label} {amount_text} {task['threshold_currency']}</p>"
            f"<p><strong>Actual price:</strong> {actual_price} {currency}</p>"
            f"<p><strong>Triggered at:</strong> {triggered_at}</p>"
            f"<p><strong>Source:</strong> {source}</p>"
            f"<p><strong>Task ID:</strong> {task['id']}</p>"
            "</div>"
        )
    return subject, text + "\n", html


def _send_email_node(state: dict) -> dict:
    task = state.get("task") or {}
    price_payload = state.get("price_payload") or {}
    try:
        subject, text, html = _build_work_email(task, price_payload)
        auth.send_email(
            email=task["recipient_email"],
            subject=subject,
            text=text,
            html=html,
        )
        state["error"] = ""
    except Exception as exc:
        state["error"] = str(exc)
    return state


def _get_execution_graph():
    global _execution_graph
    if _execution_graph is None:
        _execution_graph = build_execution_graph(_fetch_price_node, _send_email_node)
    return _execution_graph


_cron_execution_graph = None


def _get_cron_execution_graph():
    global _cron_execution_graph
    if _cron_execution_graph is None:
        _cron_execution_graph = build_cron_execution_graph(_fetch_price_node, _send_email_node)
    return _cron_execution_graph


def _next_cron_tick(cron_expression: str, after_ts: int) -> int:
    if not cron_expression.strip():
        return after_ts + _task_check_interval_seconds()
    try:
        from croniter import croniter
        import datetime
        base = datetime.datetime.fromtimestamp(after_ts, tz=datetime.timezone.utc)
        cron = croniter(cron_expression, base)
        next_dt = cron.get_next(datetime.datetime)
        return int(next_dt.timestamp())
    except Exception:
        return after_ts + _task_check_interval_seconds()


def run_work_task_job(payload: dict) -> dict:
    task_id = str(payload.get("task_id") or "")
    task = get_work_task_by_id(task_id)
    if task is None:
        return {"ok": False, "error": "task_not_found", "task_id": task_id}
    if task.get("status") != "active":
        return {"ok": True, "skipped": True, "reason": f"status={task.get('status')}", "task_id": task_id}

    is_cron = task.get("workflow_type") == WORKFLOW_CRON_EMAIL
    graph = _get_cron_execution_graph() if is_cron else _get_execution_graph()
    result = graph.invoke({"task": task})
    checked_at = _iso_now()

    if result.get("error"):
        fallback_next = int(time.time()) + _task_check_interval_seconds()
        update_work_task_runtime(
            task_id,
            last_checked_at=checked_at,
            last_error=str(result["error"])[:500],
            next_check_at=fallback_next,
            locked_until=0,
        )
        return {"ok": False, "error": result["error"], "task_id": task_id}

    price_payload = result.get("price_payload") or {}
    last_price = float(price_payload.get("price") or 0.0)

    if is_cron:
        # Cron tasks loop: calculate next tick, don't mark as completed
        next_check_at = _next_cron_tick(task.get("cron_expression") or "", int(time.time()))
        update_work_task_runtime(
            task_id,
            last_checked_at=checked_at,
            last_price=last_price,
            last_error="",
            next_check_at=next_check_at,
            locked_until=0,
        )
        return {"ok": True, "triggered": True, "task_id": task_id, "price": last_price, "cron": True}

    next_check_at = int(time.time()) + _task_check_interval_seconds()
    if result.get("triggered"):
        update_work_task_runtime(
            task_id,
            status="completed",
            last_checked_at=checked_at,
            last_price=last_price,
            last_triggered_at=checked_at,
            last_error="",
            next_check_at=0,
            locked_until=0,
        )
        return {"ok": True, "triggered": True, "task_id": task_id, "price": last_price}

    update_work_task_runtime(
        task_id,
        last_checked_at=checked_at,
        last_price=last_price,
        last_error="",
        next_check_at=next_check_at,
        locked_until=0,
    )
    return {"ok": True, "triggered": False, "task_id": task_id, "price": last_price}


def _scheduler_loop() -> None:
    interval = _scheduler_interval_seconds()
    while True:
        now_ts = int(time.time())
        try:
            tasks = claim_due_work_tasks(now_ts, limit=16, lock_seconds=max(interval + 30, 90))
            for task in tasks:
                try:
                    publish_work_job({"task_id": task["id"]})
                except Exception as exc:
                    clear_work_task_lock(
                        task["id"],
                        last_error=str(exc)[:500],
                        next_check_at=now_ts + interval,
                    )
        except Exception as exc:
            print(f"Work scheduler error: {exc}")
        time.sleep(interval)


def start_work_runtime() -> None:
    global _scheduler_started
    start_work_worker(run_work_task_job)
    if _scheduler_started:
        return
    _scheduler_started = True
    thread = threading.Thread(target=_scheduler_loop, name="work-scheduler", daemon=True)
    thread.start()
