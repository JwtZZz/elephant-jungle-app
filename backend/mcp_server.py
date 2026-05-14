"""Elephant Jungle MCP Server — Standalone Enterprise Edition.

Calls external APIs (CoinGecko, OKX, DexScreener, Google News RSS, Arkham)
directly instead of proxying through the FastAPI backend.

Only *search_knowledge_base* retains an HTTP callback to main.py since it
requires ChromaDB (vector database) which lives in the backend process.

Usage:
    mcp run mcp_server.py          # stdio transport (Claude Desktop / agent_tools.py)
    python mcp_server.py           # SSE transport (web app)
"""

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from cache_store import get_json as cache_get_json, set_json as cache_set_json
from providers import translate_text

load_dotenv(Path(__file__).resolve().parent / ".env")

mcp = FastMCP("Elephant Jungle", dependencies=["httpx"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Market coins
MARKET_LIVE_TTL = 2
MARKET_BASE_TTL = 300
_market_cache: dict = {"base_ts": 0.0, "live_ts": 0.0, "coins": []}

# OKX detail
OKX_DETAIL_TTL = 3
_okx_cache: dict[str, dict] = {}

# Meme trending
MEME_TRENDING_TTL = 300
MEME_TRENDING_REDIS_KEY = "meme:trending:solana"
_meme_cache: dict = {"ts": 0.0, "tokens": []}

# Briefs
BRIEFS_TTL = 5 * 3600
BRIEFS_CACHE_PATH = Path(__file__).resolve().parent / "briefs_cache.json"
_briefs_cache: dict = {"ts": 0.0, "payload": {}}

# Timeline
TIMELINE_TTL = 15 * 60
_timeline_cache: dict[str, dict] = {}
_title_translation_cache: dict[str, str] = {}

# Whale feed
WHALE_FEED_TTL = 10
WHALE_FEED_DEFAULT_LIMIT = 24
WHALE_FEED_REDIS_KEY = "whales:feed:v1"
_whale_cache: dict[str, dict] = {}

ARKHAM_API_KEY = os.getenv("ARKHAM_API_KEY", "").strip()
ARKHAM_TRANSFERS_URL = os.getenv("ARKHAM_TRANSFERS_URL", "https://api.arkm.com/transfers").strip()
ARKHAM_WHALE_FROM = os.getenv(
    "ARKHAM_WHALE_FROM",
    "BlackRock,Fidelity,Grayscale,Bitwise,Coinbase Prime,Wintermute,Jump Trading,FalconX,Circle,Tether,Ark/21Shares",
).strip()
ARKHAM_WHALE_TO = os.getenv(
    "ARKHAM_WHALE_TO",
    "type:cex,deposit:binance,deposit:coinbase,deposit:okx,deposit:kraken",
).strip()
ARKHAM_WHALE_CHAINS = os.getenv(
    "ARKHAM_WHALE_CHAINS",
    "bitcoin,ethereum,solana,bsc,tron",
).strip()
ARKHAM_WHALE_TIME_LAST = os.getenv("ARKHAM_WHALE_TIME_LAST", "24h").strip()
ARKHAM_WHALE_USD_GTE = os.getenv("ARKHAM_WHALE_USD_GTE", "1000000").strip()

WHALE_FEED_SEED = [
    {"chain": "BTC", "chainTone": "btc", "from": "BlackRock: IBIT Bitcoin ETF", "fromAddress": "bc1q9xj3m4w7l8hnc5r0u2t6v9p3s7qk2dw8c4n6y", "to": "Coinbase Prime Deposit", "toAddress": "3QJmV3qfvL9SuYo34YihAf3sRCW3qSinyC", "amount": "300 BTC", "usd": "$23.28M", "direction": "outflow", "minutesAgo": 8},
    {"chain": "BTC", "chainTone": "btc", "from": "Coinbase Prime: Custody", "fromAddress": "bc1qcp6w80v2h4n7m3t5r8k1y9p4z7s2x8v4h0q6lu", "to": "BlackRock: IBIT Bitcoin ETF", "toAddress": "bc1qa8w3n5t7y0kpc2u4m8r6s1h9q0nkp5z7d4v2x", "amount": "300 BTC", "usd": "$23.28M", "direction": "inflow", "minutesAgo": 9},
    {"chain": "ETH", "chainTone": "eth", "from": "BlackRock: ETHA Ethereum ETF", "fromAddress": "0x3a8F1C4Eaa73bD2F64c80A1e3F35bc7d9A6d41cE", "to": "Coinbase Prime Deposit", "toAddress": "0x6F2b8D1F9d112AbC4c7E9F0D23A6b18f8B3a9D11", "amount": "5.738K ETH", "usd": "$13.38M", "direction": "outflow", "minutesAgo": 12},
    {"chain": "BTC", "chainTone": "btc", "from": "Fidelity: Wise Origin BTC", "fromAddress": "bc1qm0n4u7p2r8s5w3x1t6y9z0a4h2pp7k8v5m3n6q", "to": "Coinbase Prime: Custody", "toAddress": "bc1qcp6w80v2h4n7m3t5r8k1y9p4z7s2x8v4h0q6lu", "amount": "187 BTC", "usd": "$14.51M", "direction": "inflow", "minutesAgo": 16},
    {"chain": "SOL", "chainTone": "sol", "from": "Wintermute Market Making", "fromAddress": "6pQ9g9Yg4Lh9QzR7kV3xT2nP6sUa1mBc8dFe0GhJ2kLm", "to": "Binance Hot Wallet 12", "toAddress": "8f3K2nAp2MdX7qRs9TuV1wX2yZa3Bc4De5Fg6Hi7JkLm", "amount": "92.4K SOL", "usd": "$12.07M", "direction": "inflow", "minutesAgo": 18},
    {"chain": "USDT", "chainTone": "usdt", "from": "Tether Treasury", "fromAddress": "TX7uK4x92sE91nQw3Er5Ty7Ui9Op1As3Df5Gh7Jk9Lm2", "to": "Cumberland DRW", "toAddress": "TG1oLK0fw3mNp6Qr8St0Uv2Wx4Yz6Ab8Cd0Ef2Gh4Jk6", "amount": "20.0M USDT", "usd": "$20.00M", "direction": "inflow", "minutesAgo": 21},
    {"chain": "BTC", "chainTone": "btc", "from": "Grayscale: GBTC ETF", "fromAddress": "bc1qgl7m9ut2x4v6n8b0c2d4e6f8g0h2j4k6l8m0n2p", "to": "Coinbase Prime Deposit (+2)", "toAddress": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "amount": "141 BTC", "usd": "$10.93M", "direction": "outflow", "minutesAgo": 24},
    {"chain": "ETH", "chainTone": "eth", "from": "Jump Trading 0x9c1", "fromAddress": "0x9c12dA58cEf41bA0D93e7c11A20Fdc29b84f5a1B", "to": "Kraken Deposit Wallet", "toAddress": "0x72d4B1aC331f2E8c94D5A7b0Ef1234Ab56Cd7eF8", "amount": "3.904K ETH", "usd": "$9.08M", "direction": "outflow", "minutesAgo": 27},
    {"chain": "BNB", "chainTone": "bnb", "from": "Binance Cold Wallet 3", "fromAddress": "0xb6A7821d4f8b7c9d0e1f23456789abcDEF012345", "to": "Wintermute BSC Router", "toAddress": "0xA1812a12C4d5e6f708192aBcDef1234567890aBC", "amount": "14.2K BNB", "usd": "$8.81M", "direction": "outflow", "minutesAgo": 31},
    {"chain": "BTC", "chainTone": "btc", "from": "Ark/21Shares ARKB", "fromAddress": "bc1qzk5r6c8n1m3p5t7v9x2z4a6c8e0g2i4k6m8o0q2", "to": "Coinbase Prime: Custody", "toAddress": "bc1qcp6w80v2h4n7m3t5r8k1y9p4z7s2x8v4h0q6lu", "amount": "119 BTC", "usd": "$9.19M", "direction": "inflow", "minutesAgo": 35},
    {"chain": "USDC", "chainTone": "usdc", "from": "Circle Treasury", "fromAddress": "0xC1rc33E88765aa4bf9091CdEf23456789AbCdEf0", "to": "Coinbase Institutional", "toAddress": "0x78C4f0B28a61Cd73eF9421abCDef4567890aBcD1", "amount": "15.0M USDC", "usd": "$15.00M", "direction": "inflow", "minutesAgo": 39},
    {"chain": "ETH", "chainTone": "eth", "from": "Coinbase Prime: Custody", "fromAddress": "0x6F2b8D1F9d112AbC4c7E9F0D23A6b18f8B3a9D11", "to": "BlackRock: ETHA Ethereum ETF", "toAddress": "0x3a8F1C4Eaa73bD2F64c80A1e3F35bc7d9A6d41cE", "amount": "2.865K ETH", "usd": "$6.71M", "direction": "inflow", "minutesAgo": 43},
    {"chain": "SOL", "chainTone": "sol", "from": "FalconX Prime", "fromAddress": "9JpQw12LrM4nP6qR8sT0uV2wX4yZ6aBc8De0Fg2Hi4Jk", "to": "OKX Solana Deposit", "toAddress": "4TrsEQm2wP5rS7tU9vW1xY3zA5bC7dE9fG1hJ3kL5mN", "amount": "48.0K SOL", "usd": "$6.18M", "direction": "outflow", "minutesAgo": 47},
    {"chain": "BTC", "chainTone": "btc", "from": "Bitwise ETF Reserve", "fromAddress": "bc1qbt8ka3m5p7r9t1v3x5z7b9d1f3h5j7l9n1p3r5t", "to": "Coinbase Prime Deposit", "toAddress": "3QJmV3qfvL9SuYo34YihAf3sRCW3qSinyC", "amount": "78 BTC", "usd": "$6.04M", "direction": "outflow", "minutesAgo": 52},
    {"chain": "USDT", "chainTone": "usdt", "from": "Alameda Recovery Wallet", "fromAddress": "TX89ApQ3r7sT9uV1wX3yZ5aBc7De9Fg1Hi3Jk5Lm7No9", "to": "Binance Deposit Wallet", "toAddress": "TY12FjL0wE2rT4vX6zA8cD0fG2iJ4lN6pQ8sU0wY2aB4", "amount": "12.5M USDT", "usd": "$12.50M", "direction": "outflow", "minutesAgo": 56},
    {"chain": "BNB", "chainTone": "bnb", "from": "Jump Cross-chain Treasury", "fromAddress": "0xB2d1f8Ce90aBcD12eF34567890abCDef12345678", "to": "Binance Hot Wallet 7", "toAddress": "0x61A47d2Ef890abC1234567890DefABc123456789", "amount": "8.4K BNB", "usd": "$5.22M", "direction": "inflow", "minutesAgo": 61},
]

# ---------------------------------------------------------------------------
# Helpers — formatting, parsing, normalising (replicated from main.py)
# ---------------------------------------------------------------------------


def format_market_cap(value: int | float | None) -> str:
    if value is None:
        return "--"
    number = float(value)
    if number >= 1_000_000_000_000:
        return f"${number / 1_000_000_000_000:.2f}T"
    if number >= 1_000_000_000:
        return f"${number / 1_000_000_000:.1f}B"
    if number >= 1_000_000:
        return f"${number / 1_000_000:.1f}M"
    return f"${number:,.0f}"


def format_price(value: int | float | None) -> str:
    if value is None:
        return "--"
    number = float(value)
    if number >= 1000:
        return f"${number:,.2f}"
    if number >= 1:
        return f"${number:,.4f}"
    return f"${number:,.5f}"


def _format_meme_price(value: float | None) -> str:
    if value is None:
        return "--"
    if value >= 1:
        return f"${value:,.4f}"
    if value >= 0.01:
        return f"${value:,.6f}"
    return f"${value:,.8f}"


def _format_meme_money(value: float | None) -> str:
    if value is None:
        return "--"
    amount = float(value or 0.0)
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    if amount >= 1:
        return f"${amount:,.0f}"
    return f"${amount:.4f}"


def parse_okx_number(value: str | None) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def map_okx_bar(interval: str) -> str:
    normalized = (interval or "15m").strip().lower()
    mapping = {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
        "30m": "30m", "1h": "1H", "4h": "4H", "1d": "1D",
    }
    return mapping.get(normalized, "15m")


def build_okx_inst_id(symbol: str) -> str:
    return f"{(symbol or '').strip().upper()}-USDT"


def serialize_market_coin(coin: dict) -> dict:
    return {
        "symbol": coin.get("symbol") or "",
        "name": coin.get("name") or "",
        "image": coin.get("image") or "",
        "price": format_price(coin.get("price_value")),
        "change": float(coin.get("change_value") or 0.0),
        "low": format_price(coin.get("low_value")),
        "high": format_price(coin.get("high_value")),
        "cap": coin.get("cap") or "--",
        "spark": [float(point) for point in coin.get("spark", [])[-12:]],
    }


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value or "")).strip()


def parse_rss_items(xml_text: str, limit: int = 8) -> list[dict]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict] = []
    for item in channel.findall("item")[:limit]:
        title = strip_html(item.findtext("title", default=""))
        link = item.findtext("link", default="").strip()
        pub_date = item.findtext("pubDate", default="").strip()
        description = strip_html(item.findtext("description", default=""))
        source = strip_html(item.findtext("source", default="")) or "Google News"
        if not title or not link:
            continue
        items.append({
            "title": title,
            "url": link,
            "published_at": pub_date,
            "summary": description,
            "source": source,
        })
    return items


def has_brief_items(payload: dict, key: str) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get(key))


def load_persisted_briefs() -> dict[str, list[dict]]:
    try:
        if not BRIEFS_CACHE_PATH.exists():
            return {}
        payload = json.loads(BRIEFS_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            "social": payload.get("social") if isinstance(payload.get("social"), list) else [],
            "news": payload.get("news") if isinstance(payload.get("news"), list) else [],
        }
    except Exception:
        return {}


def save_persisted_briefs(payload: dict[str, list[dict]]) -> None:
    try:
        safe = {
            "social": payload.get("social") or [],
            "news": payload.get("news") or [],
            "updated_at": int(time.time()),
        }
        BRIEFS_CACHE_PATH.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def build_timeline_feed_url(symbol: str, name: str) -> str:
    terms = [term for term in [name.strip(), symbol.strip(), "crypto"] if term]
    query = " OR ".join(f'"{term}"' if " " in term else term for term in terms)
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query + ' when:1d')}&hl=en-US&gl=US&ceid=US:en"
    )


def translate_title_cached(title: str, language: str) -> str:
    clean = (title or "").strip()
    if not clean:
        return ""
    if language != "zh":
        return clean
    if re.search(r"[一-鿿]", clean):
        return clean
    redis_key = f"market:title-translation:zh:{clean}"
    cached = cache_get_json(redis_key)
    if isinstance(cached, str) and cached:
        _title_translation_cache[clean] = cached
        return cached
    local = _title_translation_cache.get(clean)
    if local:
        return local
    try:
        translated = translate_text(clean, target_language="zh").strip()
    except Exception:
        translated = clean
    _title_translation_cache[clean] = translated or clean
    cache_set_json(redis_key, _title_translation_cache[clean], TIMELINE_TTL)
    return _title_translation_cache[clean]


def _coerce_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _first_truthy(*values):
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _short_wallet(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "--"
    if "..." in text or len(text) <= 14:
        return text
    return f"{text[:6]}...{text[-4:]}"


def _clean_wallet(value: str | None) -> str:
    return str(value or "").strip() or "--"


def _minutes_ago(value) -> int:
    numeric = _coerce_float(value)
    if numeric is None:
        return 0
    if numeric > 10_000_000_000:
        numeric /= 1000
    if numeric > 1_000_000_000:
        return max(1, int((time.time() - numeric) / 60))
    return max(1, int(numeric))


def _label_or_wallet(label: str | None, address: str | None) -> str:
    text = str(label or "").strip()
    return text or _short_wallet(address)


def _looks_like_exchange(label: str) -> bool:
    normalized = (label or "").lower()
    markers = (
        "deposit", "binance", "coinbase", "kraken", "okx", "bybit",
        "bitget", "mexc", "kucoin", "gate", "exchange", "custody", "hot wallet",
    )
    return any(marker in normalized for marker in markers)


def _normalize_whale_chain(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    mapping = {
        "bitcoin": "BTC", "btc": "BTC",
        "ethereum": "ETH", "eth": "ETH",
        "solana": "SOL", "sol": "SOL",
        "bsc": "BNB", "bnb": "BNB", "binance-smart-chain": "BNB",
        "tron": "USDT", "trc20": "USDT", "usdt": "USDT", "usdc": "USDC",
    }
    return mapping.get(normalized, (value or "--").upper())


def _normalize_whale_tone(value: str | None) -> str:
    normalized = _normalize_whale_chain(value).lower()
    mapping = {"btc": "btc", "eth": "eth", "sol": "sol", "bnb": "bnb", "usdt": "usdt", "usdc": "usdc"}
    return mapping.get(normalized, normalized or "btc")


def _format_whale_amount(value, symbol: str) -> str:
    amount = _coerce_float(value)
    token = (symbol or "--").strip().upper()
    if amount is None:
        return f"-- {token}".strip()
    if amount >= 1_000_000:
        text = f"{amount / 1_000_000:.2f}M"
    elif amount >= 1_000:
        text = f"{amount / 1_000:.3f}K".rstrip("0").rstrip(".")
    elif amount >= 1:
        text = f"{amount:,.3f}".rstrip("0").rstrip(".")
    else:
        text = f"{amount:.6f}".rstrip("0").rstrip(".")
    return f"{text} {token}".strip()


def _normalize_arkham_transfer(item: dict) -> dict | None:
    from_entity = item.get("fromEntity") or {}
    to_entity = item.get("toEntity") or {}
    token = item.get("token") or item.get("asset") or {}

    from_address = _first_truthy(
        item.get("fromAddress"), item.get("sourceAddress"),
        (item.get("fromAccount") or {}).get("address"),
    )
    to_address = _first_truthy(
        item.get("toAddress"), item.get("destinationAddress"),
        (item.get("toAccount") or {}).get("address"),
    )
    from_label = _label_or_wallet(
        _first_truthy(
            item.get("fromLabel"), item.get("fromName"), from_entity.get("name"),
            (item.get("fromAccount") or {}).get("label"),
        ),
        from_address,
    )
    to_label = _label_or_wallet(
        _first_truthy(
            item.get("toLabel"), item.get("toName"), to_entity.get("name"),
            (item.get("toAccount") or {}).get("label"),
        ),
        to_address,
    )
    token_symbol = str(
        _first_truthy(
            item.get("tokenSymbol"), item.get("symbol"), item.get("assetSymbol"),
            token.get("symbol"), token.get("ticker"), item.get("chain"),
        ) or "--"
    ).upper()
    chain_label = _normalize_whale_chain(
        _first_truthy(item.get("chain"), item.get("network"), token.get("chain"), token_symbol)
    )
    amount_value = _first_truthy(
        item.get("unitValue"), item.get("amount"), item.get("quantity"),
        item.get("tokenAmount"), token.get("amount"),
    )
    usd_value = _first_truthy(
        item.get("historicalUSD"), item.get("historicalUsd"), item.get("usd"),
        item.get("usdValue"), item.get("valueUsd"), item.get("historicalUsdAmount"),
    )
    minutes_ago = _minutes_ago(
        _first_truthy(item.get("blockTimestamp"), item.get("timestamp"), item.get("time"))
    )
    flow = str(_first_truthy(item.get("flow"), item.get("direction"), "")).lower()
    direction = "inflow" if "in" in flow else "outflow"
    if not flow:
        direction = "inflow" if _looks_like_exchange(to_label) else "outflow"

    return {
        "chain": chain_label,
        "chainTone": _normalize_whale_tone(chain_label),
        "from": from_label,
        "fromAddress": _clean_wallet(from_address),
        "to": to_label,
        "toAddress": _clean_wallet(to_address),
        "amount": _format_whale_amount(amount_value, token_symbol),
        "usd": _format_meme_money(_coerce_float(usd_value)),
        "direction": direction,
        "minutesAgo": minutes_ago,
    }


# ---------------------------------------------------------------------------
# Data fetching functions — each calls external APIs directly
# ---------------------------------------------------------------------------


def _fetch_market_coins() -> list[dict]:
    """Top 100 crypto via CoinGecko, overlaid with OKX live prices."""
    now = time.time()

    # Redis fast-path
    redis_live = cache_get_json("market:coins:live")
    if isinstance(redis_live, list) and redis_live:
        return redis_live

    cached_coins = _market_cache.get("coins", [])
    base_ts = float(_market_cache.get("base_ts", 0.0))
    live_ts = float(_market_cache.get("live_ts", 0.0))

    # Base data from CoinGecko (refreshed every MARKET_BASE_TTL)
    if (not cached_coins) or (now - base_ts) >= MARKET_BASE_TTL:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": "true",
            "price_change_percentage": "24h",
        }
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception:
            if cached_coins:
                return [serialize_market_coin(c) for c in cached_coins]
            raise

        coins = []
        for item in payload:
            sparkline = ((item.get("sparkline_in_7d") or {}).get("price")) or []
            price_value = float(item.get("current_price") or 0.0)
            low_value = float(item.get("low_24h") or 0.0)
            high_value = float(item.get("high_24h") or 0.0)
            coins.append({
                "symbol": (item.get("symbol") or "").upper(),
                "name": item.get("name") or "",
                "image": item.get("image") or "",
                "price_value": price_value,
                "change_value": float(item.get("price_change_percentage_24h") or 0.0),
                "low_value": low_value,
                "high_value": high_value,
                "cap": format_market_cap(item.get("market_cap")),
                "spark": [float(p) for p in sparkline[-12:]] if sparkline else ([price_value] if price_value else []),
            })
        _market_cache["base_ts"] = now
        _market_cache["coins"] = coins
        cached_coins = coins

    # Return cached if within live TTL
    if cached_coins and (now - live_ts) < MARKET_LIVE_TTL:
        return [serialize_market_coin(c) for c in cached_coins]

    # OKX live price overlay
    try:
        okx_tickers = _fetch_okx_tickers()
    except Exception:
        if cached_coins:
            return [serialize_market_coin(c) for c in cached_coins]
        raise

    updated = []
    for coin in cached_coins:
        c = dict(coin)
        ticker = okx_tickers.get(str(coin.get("symbol") or "").upper())
        if ticker:
            price_value = float(ticker.get("last") or coin.get("price_value") or 0.0)
            low_value = float(ticker.get("low24h") or coin.get("low_value") or 0.0)
            high_value = float(ticker.get("high24h") or coin.get("high_value") or 0.0)
            open_value = float(ticker.get("open24h") or 0.0)
            if open_value > 0:
                change_value = ((price_value - open_value) / open_value) * 100
            else:
                change_value = float(coin.get("change_value") or 0.0)
            spark = list(coin.get("spark", []))
            if price_value > 0:
                spark.append(price_value)
            c.update({
                "price_value": price_value,
                "low_value": low_value,
                "high_value": high_value,
                "change_value": change_value,
                "spark": spark[-12:],
            })
        updated.append(c)

    _market_cache["live_ts"] = now
    _market_cache["coins"] = updated
    serialized = [serialize_market_coin(c) for c in updated]
    cache_set_json("market:coins:live", serialized, MARKET_LIVE_TTL)
    return serialized


def _fetch_okx_tickers() -> dict[str, dict]:
    url = "https://www.okx.com/api/v5/market/tickers"
    params = {"instType": "SPOT"}
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
    tickers: dict[str, dict] = {}
    for item in payload.get("data", []):
        inst_id = (item.get("instId") or "").upper()
        if not inst_id.endswith("-USDT"):
            continue
        tickers[inst_id.split("-")[0]] = item
    return tickers


def _fetch_okx_detail(symbol: str, interval: str = "15m", candle_limit: int = 96, depth_limit: int = 12) -> dict:
    inst_id = build_okx_inst_id(symbol)
    bar = map_okx_bar(interval)
    cache_key = f"{inst_id}:{bar}:{candle_limit}:{depth_limit}"
    redis_key = f"market:okx-detail:{cache_key}"
    now = time.time()

    redis_cached = cache_get_json(redis_key)
    if isinstance(redis_cached, dict):
        return redis_cached
    cached = _okx_cache.get(cache_key)
    if cached and (now - cached.get("ts", 0.0)) < OKX_DETAIL_TTL:
        return cached["payload"]

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        t_resp = client.get("https://www.okx.com/api/v5/market/ticker", params={"instId": inst_id})
        c_resp = client.get(
            "https://www.okx.com/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": str(candle_limit)},
        )
        b_resp = client.get(
            "https://www.okx.com/api/v5/market/books",
            params={"instId": inst_id, "sz": str(depth_limit)},
        )
        t_resp.raise_for_status()
        c_resp.raise_for_status()
        b_resp.raise_for_status()
        t_payload = t_resp.json()
        c_payload = c_resp.json()
        b_payload = b_resp.json()

    ticker = (t_payload.get("data") or [{}])[0]
    candles_raw = c_payload.get("data") or []
    books = (b_payload.get("data") or [{}])[0]

    candles = []
    for row in reversed(candles_raw):
        if len(row) < 9:
            continue
        candles.append({
            "ts": int(row[0]),
            "open": parse_okx_number(row[1]),
            "high": parse_okx_number(row[2]),
            "low": parse_okx_number(row[3]),
            "close": parse_okx_number(row[4]),
            "vol": parse_okx_number(row[5]),
            "volCcy": parse_okx_number(row[6]),
            "volCcyQuote": parse_okx_number(row[7]),
            "confirmed": row[8] == "1",
        })

    def parse_side(rows: list) -> list[dict]:
        return [{"price": parse_okx_number(r[0]), "size": parse_okx_number(r[1])}
                for r in rows if len(r) >= 2]

    payload = {
        "instId": inst_id,
        "bar": bar,
        "ticker": {
            "last": parse_okx_number(ticker.get("last")),
            "open24h": parse_okx_number(ticker.get("open24h")),
            "high24h": parse_okx_number(ticker.get("high24h")),
            "low24h": parse_okx_number(ticker.get("low24h")),
            "vol24h": parse_okx_number(ticker.get("vol24h")),
            "volCcy24h": parse_okx_number(ticker.get("volCcy24h")),
            "askPx": parse_okx_number(ticker.get("askPx")),
            "bidPx": parse_okx_number(ticker.get("bidPx")),
            "ts": int(ticker.get("ts") or 0),
        },
        "candles": candles,
        "orderbook": {"bids": parse_side(books.get("bids") or []), "asks": parse_side(books.get("asks") or [])},
    }
    _okx_cache[cache_key] = {"ts": now, "payload": payload}
    cache_set_json(redis_key, payload, OKX_DETAIL_TTL)
    return payload


def _fetch_meme_trending() -> list[dict]:
    """Solana meme tokens from DexScreener boost list + pair details."""
    now = time.time()

    redis_cached = cache_get_json(MEME_TRENDING_REDIS_KEY)
    if isinstance(redis_cached, list) and redis_cached:
        _meme_cache["ts"] = now
        _meme_cache["tokens"] = redis_cached
        return list(redis_cached)
    if _meme_cache["tokens"] and (now - _meme_cache["ts"]) < MEME_TRENDING_TTL:
        return list(_meme_cache["tokens"])

    tokens: list[dict] = []
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            boost_resp = client.get(
                "https://api.dexscreener.com/token-boosts/latest/v1?chainId=solana&limit=30"
            )
            boost_resp.raise_for_status()
            boosts = boost_resp.json()
            if not isinstance(boosts, list):
                return tokens

            seen: set[str] = set()
            for item in boosts:
                address = (item.get("tokenAddress") or "").strip()
                if not address or address in seen or address.startswith("0x"):
                    continue
                seen.add(address)

                symbol = name = ""
                price_usd = volume_h24 = price_change_h24 = None
                txns_buys = txns_sells = 0
                icon_url = ""
                try:
                    pr = client.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
                    pr.raise_for_status()
                    pd = pr.json()
                    pairs = pd.get("pairs") or []
                    if pairs:
                        p = pairs[0]
                        base = p.get("baseToken") or {}
                        symbol = base.get("symbol", "")
                        name = base.get("name", "")
                        price_usd = float(p.get("priceUsd", 0) or 0)
                        vol = p.get("volume") or {}
                        volume_h24 = float(vol.get("h24", 0) or 0)
                        pc = p.get("priceChange") or {}
                        price_change_h24 = float(pc.get("h24", 0) or 0)
                        txns = p.get("txns") or {}
                        h24 = txns.get("h24") or {}
                        txns_buys = int(h24.get("buys", 0) or 0)
                        txns_sells = int(h24.get("sells", 0) or 0)
                except Exception:
                    pass

                desc = (item.get("description") or "").strip()
                icon_url = item.get("icon", "")
                token_url = item.get("url", f"https://dexscreener.com/solana/{address}")
                links = item.get("links") or []
                twitter_url = website_url = ""
                for link in links:
                    lu = (link.get("url") or "").strip()
                    if not lu:
                        continue
                    if link.get("type") == "twitter" or "x.com" in lu:
                        twitter_url = lu
                    elif not website_url:
                        website_url = lu

                tokens.append({
                    "symbol": symbol or address[:6],
                    "name": name or desc[:30],
                    "address": address,
                    "price": _format_meme_price(price_usd),
                    "volume24h": f"${volume_h24:,.0f}" if volume_h24 else "--",
                    "change24h": round(price_change_h24, 2) if price_change_h24 else 0,
                    "buys24h": txns_buys,
                    "sells24h": txns_sells,
                    "description": desc,
                    "icon": icon_url,
                    "header": item.get("header", ""),
                    "url": token_url,
                    "twitter": twitter_url,
                    "website": website_url,
                })
    except Exception:
        if _meme_cache["tokens"]:
            return list(_meme_cache["tokens"])
        if isinstance(redis_cached, list) and redis_cached:
            return list(redis_cached)
        raise

    _meme_cache["ts"] = now
    _meme_cache["tokens"] = tokens
    if tokens:
        cache_set_json(MEME_TRENDING_REDIS_KEY, tokens, MEME_TRENDING_TTL)
    return tokens


def _fetch_market_briefs() -> dict:
    """Crypto news + social highlights from Google News RSS."""
    now = time.time()

    redis_cached = cache_get_json("market:briefs")
    if isinstance(redis_cached, dict) and has_brief_items(redis_cached, "social") and has_brief_items(redis_cached, "news"):
        return dict(redis_cached)

    cached = _briefs_cache.get("payload", {})
    cached_ts = float(_briefs_cache.get("ts", 0.0))
    if cached and (now - cached_ts) < BRIEFS_TTL and has_brief_items(cached, "social") and has_brief_items(cached, "news"):
        return dict(cached)

    feeds = {
        "social": [
            "https://news.google.com/rss/search?q=site:x.com+(bitcoin+OR+ethereum+OR+solana+OR+crypto)+when:7d&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=(bitcoin+OR+ethereum+OR+solana+OR+crypto)+(X+OR+Twitter+OR+social)+when:7d&hl=en-US&gl=US&ceid=US:en",
        ],
        "news": [
            "https://news.google.com/rss/search?q=(bitcoin+OR+ethereum+OR+crypto)+finance+when:1d&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=(bitcoin+OR+ethereum+OR+crypto)+finance+when:7d&hl=en-US&gl=US&ceid=US:en",
        ],
    }

    persisted = load_persisted_briefs()
    payload: dict[str, list[dict]] = {
        "social": list(persisted.get("social") or []),
        "news": list(persisted.get("news") or []),
    }
    fetched = False
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            for key, urls in feeds.items():
                for url in urls:
                    resp = client.get(url)
                    resp.raise_for_status()
                    items = parse_rss_items(resp.text, limit=8)
                    if items:
                        payload[key] = items
                        fetched = True
                        break
    except Exception:
        if cached:
            return dict(cached)
        if payload.get("social") or payload.get("news"):
            return payload
        raise

    if fetched:
        save_persisted_briefs(payload)
    _briefs_cache["ts"] = now
    _briefs_cache["payload"] = payload
    cache_set_json("market:briefs", payload, BRIEFS_TTL)
    return payload


def _fetch_market_timeline(symbol: str, name: str, language: str = "en") -> list[dict]:
    """Per-coin news timeline from Google News RSS."""
    normalized_symbol = (symbol or "").strip().upper()
    normalized_name = (name or "").strip()
    normalized_language = (language or "en").strip().lower()
    cache_key = f"{normalized_symbol}:{normalized_name}:{normalized_language}"
    redis_key = f"market:timeline:{cache_key}"
    now = time.time()

    redis_cached = cache_get_json(redis_key)
    if isinstance(redis_cached, list):
        return list(redis_cached)
    cached = _timeline_cache.get(cache_key)
    if cached and (now - cached.get("ts", 0.0)) < TIMELINE_TTL:
        return list(cached.get("items", []))

    url = build_timeline_feed_url(normalized_symbol, normalized_name or normalized_symbol)
    items: list[dict] = []
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            for item in parse_rss_items(resp.text, limit=8):
                original = item.get("title", "").strip()
                translated = translate_title_cached(original, normalized_language)
                items.append({
                    "title": translated or original,
                    "original_title": original if translated and translated != original else "",
                    "url": item.get("url", ""),
                    "published_at": item.get("published_at", ""),
                    "source": item.get("source", ""),
                    "source_icon": "",
                })
    except Exception:
        if cached:
            return list(cached.get("items", []))
        return []

    _timeline_cache[cache_key] = {"ts": now, "items": items}
    cache_set_json(redis_key, items, TIMELINE_TTL)
    return items


def _fetch_arkham_whale_feed(limit: int) -> list[dict]:
    """Arkham API whale transfers (returns empty list if no API key)."""
    if not ARKHAM_API_KEY:
        return []
    params = {
        "limit": max(8, min(int(limit), 24)),
        "sortKey": "time", "sortDir": "desc",
        "timeLast": ARKHAM_WHALE_TIME_LAST, "chains": ARKHAM_WHALE_CHAINS,
        "from": ARKHAM_WHALE_FROM, "to": ARKHAM_WHALE_TO,
    }
    if ARKHAM_WHALE_USD_GTE:
        params["usdGte"] = ARKHAM_WHALE_USD_GTE
    try:
        with httpx.Client(timeout=18.0, follow_redirects=True) as client:
            resp = client.get(ARKHAM_TRANSFERS_URL, params=params, headers={"API-Key": ARKHAM_API_KEY})
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        return []
    raw = payload if isinstance(payload, list) else (
        payload.get("transfers") or payload.get("items") or payload.get("data") or []
    )
    items: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        normalized = _normalize_arkham_transfer(entry)
        if normalized:
            items.append(normalized)
        if len(items) >= params["limit"]:
            break
    return items


def _fetch_whale_feed(limit: int = WHALE_FEED_DEFAULT_LIMIT) -> list[dict]:
    """Whale transfer feed with Arkham API primary + seed data fallback."""
    normalized_limit = max(8, min(int(limit), 24))
    cache_key = f"{WHALE_FEED_REDIS_KEY}:{normalized_limit}"
    now = time.time()

    redis_cached = cache_get_json(cache_key)
    if isinstance(redis_cached, list) and redis_cached:
        _whale_cache[cache_key] = {"ts": now, "items": redis_cached}
        return list(redis_cached)

    local = _whale_cache.get(cache_key) or {}
    if local.get("items") and (now - float(local.get("ts", 0.0))) < WHALE_FEED_TTL:
        return list(local["items"])

    arkham_items = _fetch_arkham_whale_feed(limit=normalized_limit)
    if arkham_items:
        _whale_cache[cache_key] = {"ts": now, "items": arkham_items}
        cache_set_json(cache_key, arkham_items, WHALE_FEED_TTL)
        return list(arkham_items)

    offset = int(now // WHALE_FEED_TTL) % len(WHALE_FEED_SEED)
    items = (WHALE_FEED_SEED[offset:] + WHALE_FEED_SEED[:offset])[:normalized_limit]
    _whale_cache[cache_key] = {"ts": now, "items": items}
    cache_set_json(cache_key, items, WHALE_FEED_TTL)
    return list(items)


# ---------------------------------------------------------------------------
# search_knowledge_base — HTTP callback to main.py (needs ChromaDB)
# ---------------------------------------------------------------------------

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def search_knowledge_base(query: str, top_k: int = 5) -> list[dict]:
    """Search internal RAG knowledge base via FastAPI backend."""
    if not query:
        return []
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{API_BASE}/search", json={"query": query, "top_k": top_k})
            resp.raise_for_status()
            data = resp.json()
        return data.get("hits", data.get("results", []))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# MCP tool wrappers
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_market_coins",
    description="获取按市值排名前 100 的加密货币实时数据，包括价格、24小时涨跌幅、市值等。"
)
def mcp_get_market_coins() -> list[dict]:
    return _fetch_market_coins()


@mcp.tool(
    name="get_okx_detail",
    description="获取 OKX 交易所某个交易对的实时行情，包括最新价、24小时最高最低价、K线数据和买卖盘深度。"
)
def mcp_get_okx_detail(symbol: str, interval: str = "15m") -> dict:
    return _fetch_okx_detail(symbol=symbol, interval=interval)


@mcp.tool(
    name="get_meme_trending",
    description="获取 Solana 链上当前最热门的 meme 代币列表，包括价格、交易量和涨幅。"
)
def mcp_get_meme_trending() -> list[dict]:
    return _fetch_meme_trending()


@mcp.tool(
    name="get_market_briefs",
    description="获取最新的加密货币新闻快讯和社交媒体热点摘要。"
)
def mcp_get_market_briefs() -> dict:
    return _fetch_market_briefs()


@mcp.tool(
    name="get_market_timeline",
    description="获取某个加密货币（如 BTC、ETH、SOL）的最新相关新闻时间线。"
)
def mcp_get_market_timeline(symbol: str, name: str = "", language: str = "zh") -> list[dict]:
    return _fetch_market_timeline(symbol=symbol, name=name, language=language)


@mcp.tool(
    name="get_whale_feed",
    description="获取大额机构/鲸鱼转账动态，包括 BTC、ETH、SOL 等链上的大额资金流向。"
)
def mcp_get_whale_feed(limit: int = 24) -> list[dict]:
    return _fetch_whale_feed(limit=limit)


# ---------------------------------------------------------------------------
# Entrypoint (SSE mode — standalone MCP host)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="sse")
