import os
from typing import Iterable

import httpx


def _must_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _get_chat_provider() -> str:
    provider = os.getenv("CHAT_PROVIDER", "").strip().lower()
    if provider:
        return provider
    if os.getenv("NVIDIA_API_KEY", "").strip():
        return "nvidia"
    return "minimax"


def validate_provider_env() -> None:
    _must_env("DASHSCOPE_API_KEY")
    provider = _get_chat_provider()
    if provider == "nvidia":
        _must_env("NVIDIA_API_KEY")
        return
    if provider == "minimax":
        _must_env("MINIMAX_API_KEY")
        return
    raise RuntimeError(f"Unsupported CHAT_PROVIDER: {provider}")


def _batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    api_key = _must_env("DASHSCOPE_API_KEY")
    model = os.getenv("ALI_EMBEDDING_MODEL", "text-embedding-v4")
    url = os.getenv(
        "ALI_EMBEDDING_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    batch_size = int(os.getenv("ALI_EMBEDDING_BATCH_SIZE", "10"))
    text_list = list(texts)
    all_embeddings: list[list[float]] = []

    with httpx.Client(timeout=60) as client:
        for batch in _batched(text_list, batch_size):
            data = {"model": model, "input": batch}
            resp = client.post(url, headers=headers, json=data)
            resp.raise_for_status()
            payload = resp.json()

            items = payload.get("data", [])
            embeddings = [item.get("embedding") for item in items]
            if not embeddings or any(not isinstance(v, list) for v in embeddings):
                raise RuntimeError(f"Bad embedding response: {payload}")
            all_embeddings.extend(embeddings)

    return all_embeddings


def _minimax_chat_completion(messages: list[dict], temperature: float = 0.2) -> str:
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


def _nvidia_chat_completion(messages: list[dict], temperature: float = 0.2) -> str:
    api_key = _must_env("NVIDIA_API_KEY")
    model = os.getenv("NVIDIA_MODEL", "z-ai/glm5")
    url = os.getenv(
        "NVIDIA_CHAT_URL",
        "https://integrate.api.nvidia.com/v1/chat/completions",
    )
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=120) as client:
        resp = client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        payload = resp.json()

    choices = payload.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise RuntimeError(f"Bad NVIDIA response: {payload}")


def _chat_completion(messages: list[dict], temperature: float = 0.2) -> str:
    provider = _get_chat_provider()
    if provider == "nvidia":
        return _nvidia_chat_completion(messages, temperature=temperature)
    if provider == "minimax":
        return _minimax_chat_completion(messages, temperature=temperature)
    raise RuntimeError(f"Unsupported CHAT_PROVIDER: {provider}")


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
