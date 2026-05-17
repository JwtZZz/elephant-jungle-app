import json
import time

from agent_tools import _mcp_call


def _ensure_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _ensure_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def get_asset_price(symbol: str) -> dict:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        raise RuntimeError("Asset symbol is required")

    detail_payload = _ensure_dict(_mcp_call("get_okx_detail", {"symbol": normalized, "interval": "1m"}))
    ticker = detail_payload.get("ticker") or {}
    last_price = ticker.get("last")
    if isinstance(last_price, (int, float)) and float(last_price) > 0:
        ts_value = int(ticker.get("ts") or int(time.time() * 1000))
        return {
            "price": float(last_price),
            "currency": "USD",
            "ts": ts_value,
            "source": "mcp:get_okx_detail",
        }

    coins = _ensure_list(_mcp_call("get_market_coins", {}))
    for coin in coins:
        if str(coin.get("symbol") or "").upper() != normalized:
            continue
        price_text = str(coin.get("price") or "").replace("$", "").replace(",", "").strip()
        try:
            price_value = float(price_text)
        except Exception:
            continue
        return {
            "price": price_value,
            "currency": "USD",
            "ts": int(time.time() * 1000),
            "source": "mcp:get_market_coins",
        }

    raise RuntimeError(f"Price not found for {normalized}")
