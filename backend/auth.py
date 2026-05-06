import os
import random
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from cache_store import get_json, set_json


JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 7 * 24 * 3600  # 7 days
CODE_TTL_SECONDS = 300  # 5 minutes

_auto_secret: str | None = None
_memory_codes: dict[str, dict] = {}
_auto_user_id: int = 0


def _jwt_secret() -> str:
    global _auto_secret
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret
    if _auto_secret is None:
        _auto_secret = os.urandom(32).hex()
    return _auto_secret


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=JWT_TTL_SECONDS),
    }
    return pyjwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> int | None:
    try:
        payload = pyjwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except Exception:
        return None


def generate_code() -> str:
    return f"{random.randrange(0, 1000000):06d}"


def store_code(email: str, code: str) -> None:
    key = f"verify_code:{email}"
    data = {"code": code, "expires_at": time.time() + CODE_TTL_SECONDS}
    saved = set_json(key, data, CODE_TTL_SECONDS)
    if not saved:
        _memory_codes[email] = data


def verify_code(email: str, code: str) -> bool:
    key = f"verify_code:{email}"
    cached = get_json(key)
    if isinstance(cached, dict):
        data = cached
    else:
        data = _memory_codes.pop(email, None)
    if not data:
        return False
    if time.time() > data.get("expires_at", 0):
        return False
    return data.get("code") == code


def send_verification_email(email: str, code: str) -> None:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if api_key:
        import resend

        resend.api_key = api_key
        sender = os.getenv("RESEND_SENDER", "onboarding@resend.dev")
        resend.Emails.send(
            params={
                "from": sender,
                "to": [email],
                "subject": "Elephant Jungle verification code",
                "html": (
                    "<div style='font-family:sans-serif;padding:24px;max-width:480px'>"
                    "<h2>Elephant Jungle</h2>"
                    f"<p>Your verification code is:</p>"
                    f"<div style='font-size:32px;letter-spacing:6px;font-weight:bold;padding:16px 0'>{code}</div>"
                    f"<p style='color:#666'>This code expires in 5 minutes.</p>"
                    "</div>"
                ),
            }
        )
    else:
        print(f"\n=== DEV MODE: verification code for {email} -> {code} ===\n")
