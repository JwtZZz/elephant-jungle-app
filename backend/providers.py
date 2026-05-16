import json
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
    if os.getenv("DASHSCOPE_API_KEY", "").strip():
        return "dashscope"
    if os.getenv("NVIDIA_API_KEY", "").strip():
        return "nvidia"
    if os.getenv("OLLAMA_BASE_URL", "").strip():
        return "ollama"
    return "minimax"


def validate_provider_env() -> None:
    _must_env("DASHSCOPE_API_KEY")
    provider = _get_chat_provider()
    if provider == "dashscope":
        return
    if provider == "nvidia":
        _must_env("NVIDIA_API_KEY")
        return
    if provider == "minimax":
        _must_env("MINIMAX_API_KEY")
        return
    if provider == "bigmodel":
        _must_env("BIGMODEL_API_KEY")
        return
    if provider == "ollama":
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


def _dashscope_chat_completion(messages: list[dict], temperature: float = 0.2) -> str:
    api_key = _must_env("DASHSCOPE_API_KEY")
    model = os.getenv("ALI_CHAT_MODEL", "qwen3.5-flash")
    url = os.getenv(
        "ALI_CHAT_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
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
        content = _extract_message_text(message)
        if content:
            return content
    raise RuntimeError(f"Bad DashScope response: {payload}")


def _chat_completion(
    messages: list[dict],
    temperature: float = 0.2,
    provider: str | None = None,
) -> str:
    provider = provider or _get_chat_provider()
    if provider == "dashscope":
        return _dashscope_chat_completion(messages, temperature=temperature)
    if provider == "nvidia":
        return _nvidia_chat_completion(messages, temperature=temperature)
    if provider == "minimax":
        return _minimax_chat_completion(messages, temperature=temperature)
    # _chat_completion_raw supports bigmodel and ollama, reuse it
    msg = _chat_completion_raw(messages, temperature=temperature, provider=provider)
    return (msg.get("content") or "").strip()


def _chat_completion_raw(
    messages: list[dict],
    temperature: float = 0.2,
    tools: list[dict] | None = None,
    provider: str | None = None,
) -> dict:
    """Send a chat completion and return the full assistant message dict.

    When *tools* are provided they are included in the request so the model
    can respond with ``tool_calls``.  The returned dict may contain
    ``content`` (str | None) and/or ``tool_calls`` (list).

    Raises on HTTP / API errors.
    """
    provider = provider or _get_chat_provider()

    if provider == "ollama":
        api_key = "ollama"
        model = os.getenv("OLLAMA_MODEL", "gemma3:4b").strip()
        url = (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
               + "/v1/chat/completions")
    elif provider == "dashscope":
        api_key = _must_env("DASHSCOPE_API_KEY")
        model = os.getenv("ALI_CHAT_MODEL", "qwen3.5-flash")
        url = os.getenv(
            "ALI_CHAT_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
    elif provider == "nvidia":
        api_key = _must_env("NVIDIA_API_KEY")
        model = os.getenv("NVIDIA_MODEL", "z-ai/glm5")
        url = os.getenv(
            "NVIDIA_CHAT_URL",
            "https://integrate.api.nvidia.com/v1/chat/completions",
        )
    elif provider == "minimax":
        api_key = _must_env("MINIMAX_API_KEY")
        model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
        url = os.getenv(
            "MINIMAX_CHAT_URL",
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
        )
    elif provider == "bigmodel":
        api_key = _must_env("BIGMODEL_API_KEY")
        model = os.getenv("BIGMODEL_MODEL", "glm-4-flash")
        url = os.getenv(
            "BIGMODEL_CHAT_URL",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )
    else:
        raise RuntimeError(f"Unsupported CHAT_PROVIDER: {provider}")

    data: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2048,
        "stream": False,
    }
    if tools:
        data["tools"] = tools
        data["tool_choice"] = "auto"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    timeout = httpx.Timeout(60.0, connect=5.0) if provider == "ollama" else httpx.Timeout(120.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=data)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.ConnectError:
        if provider == "ollama":
            raise RuntimeError(f"调用本地模型失败（{model}），请检查 Ollama 是否已启动")
        raise
    except httpx.TimeoutException:
        if provider == "ollama":
            raise RuntimeError(f"调用本地模型超时（{model}），请检查 Ollama 状态")
        raise

    choices = payload.get("choices", [])
    if not choices:
        raise RuntimeError(f"Bad chat completion response: {payload}")
    message = choices[0].get("message", {})
    if not message:
        raise RuntimeError(f"Empty message in response: {payload}")

    return message


def _extract_message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            for key in ("text", "content"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    text_parts.append(value.strip())
        if text_parts:
            return "\n".join(text_parts).strip()
    reasoning = message.get("reasoning_content", "")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()
    return ""


def _parse_ocr_payload_text(payload: dict) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    return _extract_message_text(message)


def ocr_image_data_url(image_data_url: str, prompt: str | None = None) -> str:
    api_key = _must_env("DASHSCOPE_API_KEY")
    configured_model = os.getenv("ALI_OCR_MODEL", "").strip()
    fallback_models = os.getenv("ALI_OCR_FALLBACK_MODELS", "qwen-vl-ocr,qwen-vl-plus").strip()
    url = os.getenv(
        "ALI_VISION_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    models: list[str] = []
    primary_model = configured_model or "qwen-vl-ocr-latest"
    for name in [primary_model, *[item.strip() for item in fallback_models.split(",") if item.strip()]]:
        if name and name not in models:
            models.append(name)

    instructions = [item for item in [
        prompt.strip() if isinstance(prompt, str) and prompt.strip() else "",
        "Extract all visible text from this image. Return plain text only. Preserve line breaks where useful.",
        "Read the image carefully and transcribe every visible word, number, symbol, and punctuation mark. Return plain text only. If text is faint, small, rotated, or partially obscured, still provide the best-effort transcription.",
        "This is an OCR task. Output only the text seen in the image, line by line. Do not explain. Do not summarize. If you can read even part of the text, return that partial transcription.",
    ] if item]

    last_payload: dict | None = None
    with httpx.Client(timeout=120) as client:
        for model in models:
            for instruction in instructions:
                data = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": image_data_url}},
                                {"type": "text", "text": instruction},
                            ],
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 800,
                    "stream": False,
                }
                resp = client.post(url, headers=headers, json=data)
                resp.raise_for_status()
                payload = resp.json()
                last_payload = payload
                text = _parse_ocr_payload_text(payload)
                if text:
                    return text

    if last_payload is not None:
        raise RuntimeError("OCR did not return readable text.")
    raise RuntimeError("OCR request failed.")


def generate_answer(query: str, contexts: list[str], provider: str | None = None) -> str:
    context_text = "\n\n".join([f"[{i + 1}] {c}" for i, c in enumerate(contexts)])
    system_prompt = (
        "You are a cryptocurrency and Web3 knowledge assistant. "
        "Answer in natural Chinese with a warm, human tone. "
        "Use the provided reference material to answer the question. "
        "Cite sources by their number in brackets, e.g. [1] [2]. "
        "If the provided material does not contain enough information to answer reliably, "
        "say so honestly - do not invent facts or speculate beyond the references. "
        "Do not use Markdown headings, bold markers, bullet lists, or numbered lists "
        "unless the user explicitly asks for structured formatting. "
        "Prefer short natural paragraphs that sound like a person explaining something clearly."
    )
    user_prompt = f"Reference material:\n{context_text}\n\nQuestion: {query}"
    return _chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        provider=provider,
    )


def generate_general_answer(query: str, provider: str | None = None) -> str:
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
        provider=provider,
    )


def translate_text(text: str, target_language: str = "zh") -> str:
    content = (text or "").strip()
    if not content:
        return ""
    if target_language.lower().startswith("zh"):
        system_prompt = (
            "Translate the user's text into concise, natural Simplified Chinese. "
            "Return only the translated text with no explanations."
        )
    else:
        system_prompt = (
            f"Translate the user's text into {target_language}. "
            "Return only the translated text with no explanations."
        )
    return _chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        temperature=0.1,
    )
