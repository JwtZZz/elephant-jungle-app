import json
import os
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover - keeps the app bootable before deps install.
    redis = None


_client = None


def _prefix() -> str:
    return os.getenv("REDIS_KEY_PREFIX", "elephant").strip() or "elephant"


def _key(key: str) -> str:
    return f"{_prefix()}:{key}"


def get_redis_client():
    global _client
    if redis is None:
        return None
    if _client is not None:
        return _client
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=2)
        client.ping()
        _client = client
        return _client
    except Exception:
        return None


def get_json(key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(_key(key))
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def set_json(key: str, payload: Any, ttl_seconds: int) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.setex(_key(key), int(ttl_seconds), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:
        return False


def redis_status() -> dict:
    client = get_redis_client()
    if client is None:
        return {"enabled": False, "ok": False}
    try:
        return {"enabled": True, "ok": bool(client.ping())}
    except Exception as exc:
        return {"enabled": True, "ok": False, "error": str(exc)}
