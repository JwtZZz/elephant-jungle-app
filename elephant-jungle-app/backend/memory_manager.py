import json
from pathlib import Path
from typing import Any

from intent import classify_intent
from providers import _chat_completion_raw, embed_texts
from store import (
    get_conversation_history as store_get_conversation_history,
    get_long_term_memory as store_get_long_term_memory,
    save_chat_message,
    save_long_term_memory,
    search_chunks,
)


MEMORY_ROOT = Path(__file__).resolve().parent / "memory"
REFLECTION_PROMPT = (
    "你是 Hermes Memory System 的长期记忆管理器。"
    "请从最新一轮对话和已有长期记忆中，只提取值得长期保留的信息："
    "用户偏好、稳定事实、长期规则、长期项目背景。"
    "不要记录临时任务、一次性问题、瞬时市场数据。"
    "输出为简洁项目符号列表，每行一条，不超过 12 条。"
)


def _trim_text(value: str, limit: int = 1200) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _coerce_list_of_dicts(items: list[Any] | None) -> list[dict]:
    normalized: list[dict] = []
    for item in items or []:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def _safe_markdown_text(value: str) -> str:
    text = (value or "").strip()
    return text or "_empty_"


class MemoryManager:
    def __init__(self, *, provider: str | None = None):
        self.provider = provider

    def get_long_term_memory(self, user_id: int | None) -> str:
        if not user_id:
            return ""
        memory = store_get_long_term_memory(user_id)
        self._write_user_markdown(user_id=user_id, memory=memory)
        return memory

    def get_conversation_history(self, session_id: str | None, user_id: int | None = None) -> list[dict]:
        if not session_id:
            return []
        history = store_get_conversation_history(session_id, user_id)
        self._write_session_markdown(session_id=session_id, history=history)
        return history

    def vector_search(self, query: str, top_k: int = 5) -> list[dict]:
        cleaned = (query or "").strip()
        if not cleaned:
            return []
        try:
            embedding = embed_texts([cleaned])[0]
            return search_chunks(query_embedding=embedding, top_k=top_k)
        except Exception:
            return []

    def build_working_memory(
        self,
        l2: str,
        l3: list[dict],
        l4: list[dict],
        *,
        query: str = "",
        tool_context: list[dict] | None = None,
        intent: str | None = None,
    ) -> dict:
        resolved_intent = intent or classify_intent(query or "")
        recent_turns = l3[-6:]
        conversation_lines = [
            f"{item.get('created_at', '')} | 用户：{item.get('user_content', '').strip()} | 助手：{item.get('bot_content', '').strip()}"
            for item in recent_turns
            if item.get("user_content") or item.get("bot_content")
        ]
        conversation_summary = _trim_text("\n".join(conversation_lines), limit=1800)

        relevant_facts = [line.strip("-• ").strip() for line in (l2 or "").splitlines() if line.strip()]
        retrieved_context = [
            {
                "document_id": hit.get("document_id"),
                "title": hit.get("title", ""),
                "heading_path": hit.get("heading_path", ""),
                "content": _trim_text(hit.get("content", ""), limit=400),
                "score": hit.get("score", 0.0),
                "source": hit.get("source", ""),
                "url": hit.get("url", ""),
                "chunk_type": hit.get("chunk_type", "paragraph"),
            }
            for hit in l4
        ]

        return {
            "user_intent": resolved_intent,
            "relevant_facts": relevant_facts,
            "conversation_summary": conversation_summary,
            "retrieved_context": retrieved_context,
            "tool_context": _coerce_list_of_dicts(tool_context),
        }

    def render_working_memory(self, working_memory: dict) -> str:
        return json.dumps(working_memory or {}, ensure_ascii=False, indent=2)

    def history_as_messages(self, l3: list[dict], limit_turns: int = 6) -> list[dict]:
        if not l3:
            return []
        messages: list[dict] = []
        for item in l3[-limit_turns:]:
            user_content = (item.get("user_content") or "").strip()
            bot_content = (item.get("bot_content") or "").strip()
            if user_content:
                messages.append({"role": "user", "content": user_content})
            if bot_content:
                messages.append({"role": "assistant", "content": bot_content})
        return messages

    def write_history_log(
        self,
        *,
        user_id: int | None,
        session_id: str,
        user_email: str = "",
        user_input: str,
        assistant_output: str,
        intent: str = "",
        mode: str = "",
        tool_calls: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        errors: list[dict] | None = None,
        state_transitions: list[str] | None = None,
    ) -> int | None:
        if not user_id:
            return None
        row_id = save_chat_message(
            user_id,
            user_input,
            assistant_output,
            session_id=session_id,
            intent=intent,
            mode=mode,
            tool_calls=_coerce_list_of_dicts(tool_calls),
            tool_results=_coerce_list_of_dicts(tool_results),
            errors=_coerce_list_of_dicts(errors),
            state_transitions=state_transitions or [],
        )
        history = store_get_conversation_history(session_id, user_id) if session_id else []
        self._write_session_markdown(
            session_id=session_id,
            history=history,
            last_tool_calls=_coerce_list_of_dicts(tool_calls),
            last_tool_results=_coerce_list_of_dicts(tool_results),
            last_errors=_coerce_list_of_dicts(errors),
            last_state_transitions=state_transitions or [],
        )
        self._write_user_markdown(user_id=user_id, memory=store_get_long_term_memory(user_id), user_email=user_email)
        return row_id

    def reflect_and_update_memory(
        self,
        *,
        user_id: int | None,
        working_memory: dict,
        query: str,
        answer: str,
        current_memory: str = "",
    ) -> str:
        if not user_id:
            return current_memory

        messages = [
            {"role": "system", "content": REFLECTION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"已有长期记忆：\n{current_memory or '（无）'}\n\n"
                    f"工作记忆：\n{self.render_working_memory(working_memory)}\n\n"
                    f"最新对话：\n用户：{query}\n助手：{answer}\n\n"
                    "请输出更新后的长期记忆："
                ),
            },
        ]
        try:
            result = _chat_completion_raw(messages, temperature=0.1, provider=self.provider)
            updated = (result.get("content") or "").strip() or current_memory
        except Exception:
            updated = current_memory
        if updated != current_memory:
            save_long_term_memory(user_id, updated)
        self._write_user_markdown(user_id=user_id, memory=updated)
        return updated

    def get_user_memory_path(self, user_id: int) -> Path:
        return MEMORY_ROOT / "users" / str(user_id) / "user.md"

    def get_session_memory_path(self, session_id: str) -> Path:
        return MEMORY_ROOT / "sessions" / session_id / "memory.md"

    def _write_user_markdown(self, *, user_id: int, memory: str, user_email: str = "") -> None:
        path = self.get_user_memory_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(
            [
                "# User Memory",
                "",
                f"- user_id: {user_id}",
                f"- user_email: {user_email or '_unknown_'}",
                "",
                "## Long-Term Memory (L2)",
                _safe_markdown_text(memory),
                "",
                "## What Belongs Here",
                "- Stable user preferences",
                "- Long-term rules",
                "- Persistent facts",
                "- Long-term interests and project background",
                "",
            ]
        )
        path.write_text(body, encoding="utf-8")

    def _write_session_markdown(
        self,
        *,
        session_id: str,
        history: list[dict],
        last_tool_calls: list[dict] | None = None,
        last_tool_results: list[dict] | None = None,
        last_errors: list[dict] | None = None,
        last_state_transitions: list[str] | None = None,
    ) -> None:
        if not session_id:
            return
        path = self.get_session_memory_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        recent_history = history[-10:]
        conversation_lines: list[str] = []
        for item in recent_history:
            conversation_lines.extend(
                [
                    f"### Turn {item.get('id', '')}",
                    f"- created_at: {item.get('created_at', '')}",
                    f"- intent: {item.get('intent', '') or '_unknown_'}",
                    f"- mode: {item.get('mode', '') or '_unknown_'}",
                    f"- user: {item.get('user_content', '').strip() or '_empty_'}",
                    f"- assistant: {item.get('bot_content', '').strip() or '_empty_'}",
                    "",
                ]
            )

        latest_tool_calls_text = json.dumps(last_tool_calls or [], ensure_ascii=False, indent=2)
        latest_tool_results_text = json.dumps(last_tool_results or [], ensure_ascii=False, indent=2)
        latest_errors_text = json.dumps(last_errors or [], ensure_ascii=False, indent=2)
        latest_state_transitions_text = json.dumps(last_state_transitions or [], ensure_ascii=False, indent=2)

        body = "\n".join(
            [
                "# Session Memory",
                "",
                f"- session_id: {session_id}",
                f"- turn_count: {len(history)}",
                "",
                "## Conversation Summary (L3 Mirror)",
                _safe_markdown_text(_trim_text(self._summarize_history(history), limit=1600)),
                "",
                "## Recent Turns",
                "\n".join(conversation_lines).strip() or "_empty_",
                "",
                "## Latest Tool Calls",
                "```json",
                latest_tool_calls_text,
                "```",
                "",
                "## Latest Tool Results",
                "```json",
                latest_tool_results_text,
                "```",
                "",
                "## Latest Errors",
                "```json",
                latest_errors_text,
                "```",
                "",
                "## State Transitions",
                "```json",
                latest_state_transitions_text,
                "```",
                "",
                "## What Belongs Here",
                "- Session-level conversation mirror",
                "- Recent turns",
                "- Latest tool traces",
                "- Latest execution state transitions",
                "",
            ]
        )
        path.write_text(body, encoding="utf-8")

    def _summarize_history(self, history: list[dict]) -> str:
        if not history:
            return ""
        lines = [
            f"{item.get('created_at', '')} 用户：{item.get('user_content', '').strip()} 助手：{item.get('bot_content', '').strip()}"
            for item in history[-6:]
        ]
        return "\n".join(line for line in lines if line.strip())
