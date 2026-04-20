import os
from typing import Iterable

import httpx


def _must_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def validate_provider_env() -> None:
    _must_env("DASHSCOPE_API_KEY")
    _must_env("MINIMAX_API_KEY")


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    api_key = _must_env("DASHSCOPE_API_KEY")
    model = os.getenv("ALI_EMBEDDING_MODEL", "text-embedding-v4")
    url = os.getenv(
        "ALI_EMBEDDING_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    )
    data = {"model": model, "input": list(texts)}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        payload = resp.json()

    items = payload.get("data", [])
    embeddings = [item.get("embedding") for item in items]
    if not embeddings or any(not isinstance(v, list) for v in embeddings):
        raise RuntimeError(f"Bad embedding response: {payload}")
    return embeddings


def _chat_completion(messages: list[dict], temperature: float = 0.2) -> str:
    api_key = _must_env("MINIMAX_API_KEY")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
    url = os.getenv(
        "MINIMAX_CHAT_URL",
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
    )
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=120) as client:
        resp = client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        payload = resp.json()

    # Compatible with OpenAI-like response shape.
    choices = payload.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise RuntimeError(f"Bad MiniMax response: {payload}")


def generate_answer(query: str, contexts: list[str]) -> str:
    context_text = "\n\n".join([f"[{i + 1}] {c}" for i, c in enumerate(contexts)])
    system_prompt = (
        "You are a RAG assistant. Answer in natural Chinese with a warm, human tone. "
        "Use the provided context first. If the context is weak or incomplete, still be helpful, "
        "but stay honest about uncertainty. Do not use Markdown headings, bold markers, bullet lists, "
        "or numbered lists unless the user explicitly asks for structured formatting. "
        "Prefer short natural paragraphs that sound like a person explaining something clearly."
    )
    user_prompt = f"Context:\n{context_text}\n\nQuestion:\n{query}"
    return _chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )


def generate_general_answer(query: str) -> str:
    system_prompt = (
        "You are a helpful assistant. Give clear, direct answers in natural Chinese unless the user asks otherwise. "
        "Do not use Markdown headings, bold markers, bullet lists, or numbered lists unless the user explicitly asks. "
        "Prefer a warm, conversational explanation that sounds human."
    )
    return _chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.5,
    )
