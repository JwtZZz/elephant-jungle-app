from pathlib import Path
import os
import time
import threading
import json
from html import unescape
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx
from fastapi import FastAPI, HTTPException
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from rag import DEFAULT_TOP_K, chat, ingest_document, search
from store import init_db, sync_chroma_index
from providers import ocr_image_data_url, translate_text, validate_provider_env
from cache_store import get_json as cache_get_json, redis_status, set_json as cache_set_json
from task_broker import get_job_status, publish_ingest_job, rabbitmq_status, start_ingest_worker


app = FastAPI(title="Minimal RAG Backend", version="0.1.0")
load_dotenv(Path(__file__).resolve().parent / ".env")
MARKET_BASE_TTL_SECONDS = 5 * 60
MARKET_LIVE_TTL_SECONDS = 2
market_cache: dict[str, object] = {
    "base_timestamp": 0.0,
    "live_timestamp": 0.0,
    "coins": [],
}
BRIEFS_CACHE_TTL_SECONDS = 5 * 60 * 60
briefs_cache: dict[str, object] = {"timestamp": 0.0, "payload": {}}
BRIEFS_CACHE_PATH = Path(__file__).resolve().parent / "briefs_cache.json"
TIMELINE_CACHE_TTL_SECONDS = 15 * 60
TIMELINE_PREWARM_INTERVAL_SECONDS = 10 * 60
TIMELINE_PREWARM_ASSETS = [
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
]
timeline_cache: dict[str, dict] = {}
title_translation_cache: dict[str, str] = {}
timeline_prewarm_started = False
OKX_DETAIL_TTL_SECONDS = 3
okx_detail_cache: dict[str, dict] = {}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    source: str = Field(default="manual")
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    doc_type: str | None = None
    project: str | None = None
    category: str | None = None
    region: str | None = None
    source_type: str | None = None
    language: str | None = None
    summary: str | None = None
    content: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=20)


class ChatRequest(BaseModel):
    query: str
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=20)
    use_rag: bool = True


class OcrImageRequest(BaseModel):
    image_data_url: str
    filename: str | None = None
    prompt: str | None = None


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


def fetch_okx_tickers() -> dict[str, dict]:
    url = "https://www.okx.com/api/v5/market/tickers"
    params = {"instType": "SPOT"}
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    tickers: dict[str, dict] = {}
    for item in payload.get("data", []):
        inst_id = (item.get("instId") or "").upper()
        if not inst_id.endswith("-USDT"):
            continue
        base_symbol = inst_id.split("-")[0]
        tickers[base_symbol] = item
    return tickers


def map_okx_bar(interval: str) -> str:
    normalized = (interval or "15m").strip().lower()
    mapping = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1H",
        "4h": "4H",
        "1d": "1D",
    }
    return mapping.get(normalized, "15m")


def parse_okx_number(value: str | None) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def build_okx_inst_id(symbol: str) -> str:
    return f"{(symbol or '').strip().upper()}-USDT"


def fetch_okx_market_detail(symbol: str, interval: str = "15m", candle_limit: int = 96, depth_limit: int = 12) -> dict:
    inst_id = build_okx_inst_id(symbol)
    bar = map_okx_bar(interval)
    cache_key = f"{inst_id}:{bar}:{candle_limit}:{depth_limit}"
    redis_key = f"market:okx-detail:{cache_key}"
    now = time.time()
    redis_cached = cache_get_json(redis_key)
    if isinstance(redis_cached, dict):
        return redis_cached
    cached = okx_detail_cache.get(cache_key)
    if cached and (now - cached.get("timestamp", 0.0)) < OKX_DETAIL_TTL_SECONDS:
        return cached["payload"]

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        ticker_resp = client.get("https://www.okx.com/api/v5/market/ticker", params={"instId": inst_id})
        candles_resp = client.get(
            "https://www.okx.com/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": str(candle_limit)},
        )
        books_resp = client.get(
            "https://www.okx.com/api/v5/market/books",
            params={"instId": inst_id, "sz": str(depth_limit)},
        )
        ticker_resp.raise_for_status()
        candles_resp.raise_for_status()
        books_resp.raise_for_status()
        ticker_payload = ticker_resp.json()
        candles_payload = candles_resp.json()
        books_payload = books_resp.json()

    ticker = (ticker_payload.get("data") or [{}])[0]
    candles_raw = candles_payload.get("data") or []
    books = (books_payload.get("data") or [{}])[0]

    candles = []
    for row in reversed(candles_raw):
        if len(row) < 9:
            continue
        candles.append(
            {
                "ts": int(row[0]),
                "open": parse_okx_number(row[1]),
                "high": parse_okx_number(row[2]),
                "low": parse_okx_number(row[3]),
                "close": parse_okx_number(row[4]),
                "vol": parse_okx_number(row[5]),
                "volCcy": parse_okx_number(row[6]),
                "volCcyQuote": parse_okx_number(row[7]),
                "confirmed": row[8] == "1",
            }
        )

    bids = []
    for row in books.get("bids") or []:
        if len(row) < 2:
            continue
        bids.append({"price": parse_okx_number(row[0]), "size": parse_okx_number(row[1])})

    asks = []
    for row in books.get("asks") or []:
        if len(row) < 2:
            continue
        asks.append({"price": parse_okx_number(row[0]), "size": parse_okx_number(row[1])})

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
        "orderbook": {"bids": bids, "asks": asks},
    }
    okx_detail_cache[cache_key] = {"timestamp": now, "payload": payload}
    cache_set_json(redis_key, payload, OKX_DETAIL_TTL_SECONDS)
    return payload


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


def fetch_market_coins() -> list[dict]:
    now = time.time()
    redis_live = cache_get_json("market:coins:live")
    if isinstance(redis_live, list) and redis_live:
        return redis_live
    cached_coins = market_cache.get("coins", [])
    base_at = float(market_cache.get("base_timestamp", 0.0))
    live_at = float(market_cache.get("live_timestamp", 0.0))

    if (not cached_coins) or (now - base_at) >= MARKET_BASE_TTL_SECONDS:
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
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            if cached_coins:
                return [serialize_market_coin(coin) for coin in cached_coins]
            raise

        coins: list[dict] = []
        for item in payload:
            sparkline = ((item.get("sparkline_in_7d") or {}).get("price")) or []
            price_value = float(item.get("current_price") or 0.0)
            low_value = float(item.get("low_24h") or 0.0)
            high_value = float(item.get("high_24h") or 0.0)
            coins.append(
                {
                    "symbol": (item.get("symbol") or "").upper(),
                    "name": item.get("name") or "",
                    "image": item.get("image") or "",
                    "price_value": price_value,
                    "change_value": float(item.get("price_change_percentage_24h") or 0.0),
                    "low_value": low_value,
                    "high_value": high_value,
                    "cap": format_market_cap(item.get("market_cap")),
                    "spark": [float(point) for point in sparkline[-12:]] if sparkline else ([price_value] if price_value else []),
                }
            )
        market_cache["base_timestamp"] = now
        market_cache["coins"] = coins
        cached_coins = coins

    if cached_coins and (now - live_at) < MARKET_LIVE_TTL_SECONDS:
        return [serialize_market_coin(coin) for coin in cached_coins]

    try:
        okx_tickers = fetch_okx_tickers()
    except Exception:
        if cached_coins:
            return [serialize_market_coin(coin) for coin in cached_coins]
        raise

    updated_coins: list[dict] = []
    for coin in cached_coins:
        next_coin = dict(coin)
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
            next_coin.update(
                {
                    "price_value": price_value,
                    "low_value": low_value,
                    "high_value": high_value,
                    "change_value": change_value,
                    "spark": spark[-12:],
                }
            )
        updated_coins.append(next_coin)

    market_cache["live_timestamp"] = now
    market_cache["coins"] = updated_coins
    serialized = [serialize_market_coin(coin) for coin in updated_coins]
    cache_set_json("market:coins:live", serialized, MARKET_LIVE_TTL_SECONDS)
    return serialized


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
        items.append(
            {
                "title": title,
                "url": link,
                "published_at": pub_date,
                "summary": description,
                "source": source,
            }
        )
    return items


def has_brief_items(payload: dict | object, key: str) -> bool:
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
        safe_payload = {
            "social": payload.get("social") or [],
            "news": payload.get("news") or [],
            "updated_at": int(time.time()),
        }
        BRIEFS_CACHE_PATH.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_market_briefs() -> dict:
    now = time.time()
    redis_cached = cache_get_json("market:briefs")
    if (
        isinstance(redis_cached, dict)
        and has_brief_items(redis_cached, "social")
        and has_brief_items(redis_cached, "news")
    ):
        return dict(redis_cached)
    cached_payload = briefs_cache.get("payload", {})
    cached_at = float(briefs_cache.get("timestamp", 0.0))
    if (
        cached_payload
        and (now - cached_at) < BRIEFS_CACHE_TTL_SECONDS
        and has_brief_items(cached_payload, "social")
        and has_brief_items(cached_payload, "news")
    ):
        return dict(cached_payload)

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

    persisted_payload = load_persisted_briefs()
    payload: dict[str, list[dict]] = {
        "social": list(persisted_payload.get("social") or []),
        "news": list(persisted_payload.get("news") or []),
    }
    fetched_any = False
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            for key, urls in feeds.items():
                for url in urls:
                    response = client.get(url)
                    response.raise_for_status()
                    items = parse_rss_items(response.text, limit=8)
                    if items:
                        payload[key] = items
                        fetched_any = True
                        break
    except Exception:
        if cached_payload:
            return dict(cached_payload)
        if payload.get("social") or payload.get("news"):
            return payload
        raise

    if fetched_any:
        save_persisted_briefs(payload)

    briefs_cache["timestamp"] = now
    briefs_cache["payload"] = payload
    cache_set_json("market:briefs", payload, BRIEFS_CACHE_TTL_SECONDS)
    return payload


def build_timeline_feed_url(symbol: str, name: str) -> str:
    terms = [term for term in [name.strip(), symbol.strip(), "crypto"] if term]
    query = " OR ".join(f'"{term}"' if " " in term else term for term in terms)
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query + ' when:1d')}&hl=en-US&gl=US&ceid=US:en"
    )


def translate_title_cached(title: str, language: str) -> str:
    clean_title = (title or "").strip()
    if not clean_title:
        return ""
    if language != "zh":
        return clean_title
    if re.search(r"[\u4e00-\u9fff]", clean_title):
        return clean_title
    redis_key = f"market:title-translation:zh:{clean_title}"
    redis_cached = cache_get_json(redis_key)
    if isinstance(redis_cached, str) and redis_cached:
        title_translation_cache[clean_title] = redis_cached
        return redis_cached
    cached = title_translation_cache.get(clean_title)
    if cached:
        return cached
    try:
        translated = translate_text(clean_title, target_language="zh").strip()
    except Exception:
        translated = clean_title
    title_translation_cache[clean_title] = translated or clean_title
    cache_set_json(redis_key, title_translation_cache[clean_title], TIMELINE_CACHE_TTL_SECONDS)
    return title_translation_cache[clean_title]


def fetch_market_timeline(symbol: str, name: str, language: str = "en") -> list[dict]:
    normalized_symbol = (symbol or "").strip().upper()
    normalized_name = (name or "").strip()
    normalized_language = (language or "en").strip().lower()
    cache_key = f"{normalized_symbol}:{normalized_name}:{normalized_language}"
    redis_key = f"market:timeline:{cache_key}"
    now = time.time()
    redis_cached = cache_get_json(redis_key)
    if isinstance(redis_cached, list):
        return list(redis_cached)
    cached = timeline_cache.get(cache_key)
    if cached and (now - cached.get("timestamp", 0.0)) < TIMELINE_CACHE_TTL_SECONDS:
        return list(cached.get("items", []))

    url = build_timeline_feed_url(normalized_symbol, normalized_name or normalized_symbol)
    items: list[dict] = []
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            for item in parse_rss_items(response.text, limit=8):
                original_title = item.get("title", "").strip()
                translated_title = translate_title_cached(original_title, normalized_language)
                items.append(
                    {
                        "title": translated_title or original_title,
                        "original_title": original_title if translated_title and translated_title != original_title else "",
                        "url": item.get("url", ""),
                        "published_at": item.get("published_at", ""),
                        "source": item.get("source", ""),
                        "source_icon": "",
                    }
                )
    except Exception:
        if cached:
            return list(cached.get("items", []))
        return []

    timeline_cache[cache_key] = {"timestamp": now, "items": items}
    cache_set_json(redis_key, items, TIMELINE_CACHE_TTL_SECONDS)
    return items


def request_payload(req: IngestRequest) -> dict:
    if hasattr(req, "model_dump"):
        return req.model_dump()
    return req.dict()


def process_ingest_payload(payload: dict) -> dict:
    return ingest_document(
        source=payload.get("source") or "manual",
        title=payload.get("title"),
        url=payload.get("url"),
        published_at=payload.get("published_at"),
        doc_type=payload.get("doc_type"),
        project=payload.get("project"),
        category=payload.get("category"),
        region=payload.get("region"),
        source_type=payload.get("source_type"),
        language=payload.get("language"),
        summary=payload.get("summary"),
        content=payload.get("content") or "",
    )


def prewarm_market_timeline_once() -> None:
    for symbol, name in TIMELINE_PREWARM_ASSETS:
        try:
            fetch_market_timeline(symbol=symbol, name=name, language="zh")
        except Exception as exc:
            print(f"Timeline prewarm failed for {symbol}: {exc}")


def start_timeline_prewarm() -> None:
    global timeline_prewarm_started
    if timeline_prewarm_started:
        return
    timeline_prewarm_started = True

    def worker() -> None:
        while True:
            prewarm_market_timeline_once()
            time.sleep(TIMELINE_PREWARM_INTERVAL_SECONDS)

    thread = threading.Thread(target=worker, name="timeline-prewarm", daemon=True)
    thread.start()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    sync_chroma_index()
    validate_provider_env()
    start_timeline_prewarm()
    start_ingest_worker(process_ingest_payload)


@app.get("/market/timeline/prewarm")
def market_timeline_prewarm() -> dict:
    prewarm_market_timeline_once()
    return {"ok": True, "assets": [symbol for symbol, _ in TIMELINE_PREWARM_ASSETS]}


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "providers": "ready",
        "redis": redis_status(),
        "rabbitmq": rabbitmq_status(),
    }


@app.post("/ingest")
def ingest(req: IngestRequest, queue: bool = Query(False)) -> dict:
    try:
        payload = request_payload(req)
        if queue:
            return publish_ingest_job(payload)
        return process_ingest_payload(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/ingest/queued")
def queued_ingest(req: IngestRequest) -> dict:
    try:
        return publish_ingest_job(request_payload(req))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/ingest/jobs/{job_id}")
def ingest_job(job_id: str) -> dict:
    return get_job_status(job_id)


@app.post("/search")
def search_route(req: SearchRequest) -> dict:
    try:
        hits = search(query=req.query, top_k=req.top_k)
        return {"hits": hits}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat")
def chat_route(req: ChatRequest) -> dict:
    try:
        return chat(query=req.query, top_k=req.top_k, use_rag=req.use_rag)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/ocr/image")
def ocr_image_route(req: OcrImageRequest) -> dict:
    try:
        image_data_url = (req.image_data_url or "").strip()
        if not image_data_url.startswith("data:image/"):
            raise HTTPException(status_code=400, detail="Invalid image payload")
        text = ocr_image_data_url(image_data_url=image_data_url, prompt=req.prompt)
        return {
            "text": text,
            "filename": (req.filename or "").strip(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).strip() or "OCR request failed."
        if "readable text" in message.lower():
            message = "OCR could not read text from this image."
        raise HTTPException(status_code=500, detail=message) from exc


@app.get("/market/coins")
def market_coins() -> dict:
    try:
        return {"coins": fetch_market_coins()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/market/briefs")
def market_briefs() -> dict:
    try:
        return fetch_market_briefs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/market/okx-detail")
def market_okx_detail(
    symbol: str = Query(..., min_length=1),
    interval: str = Query("15m", min_length=2, max_length=4),
    candles: int = Query(96, ge=24, le=240),
    depth: int = Query(12, ge=5, le=50),
) -> dict:
    try:
        return fetch_okx_market_detail(symbol=symbol, interval=interval, candle_limit=candles, depth_limit=depth)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/market/timeline")
def market_timeline(
    symbol: str = Query(..., min_length=1),
    name: str = Query("", min_length=0),
    language: str = Query("en", min_length=2, max_length=8),
) -> dict:
    try:
        items = fetch_market_timeline(symbol=symbol, name=name, language=language)
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


MEME_TRENDING_CACHE: dict = {"timestamp": 0.0, "tokens": []}
MEME_TRENDING_TTL = 300
MEME_TRENDING_REDIS_KEY = "meme:trending:solana"
MEME_BANNER_TTL = 600
MEME_BANNER_BATCH_SIZE = 30
MEME_BANNER_DEFAULT_LIMIT = 8
MEME_BANNER_DEFAULT_CHAINS = ("solana", "bsc")
MEME_BANNER_CACHE: dict[str, dict] = {}
WHALE_FEED_TTL = 10
WHALE_FEED_DEFAULT_LIMIT = 18
WHALE_FEED_CACHE: dict[str, dict] = {}
WHALE_FEED_REDIS_KEY = "whales:feed:v1"
WHALE_FEED_SEED = [
    {"chain": "BTC", "chainTone": "btc", "from": "BlackRock: IBIT Bitcoin ETF", "to": "Coinbase Prime Deposit", "amount": "300 BTC", "usd": "$23.28M", "direction": "outflow", "minutesAgo": 8},
    {"chain": "BTC", "chainTone": "btc", "from": "Coinbase Prime: Custody", "to": "BlackRock: IBIT Bitcoin ETF", "amount": "300 BTC", "usd": "$23.28M", "direction": "inflow", "minutesAgo": 9},
    {"chain": "ETH", "chainTone": "eth", "from": "BlackRock: ETHA Ethereum ETF", "to": "Coinbase Prime Deposit", "amount": "5.738K ETH", "usd": "$13.38M", "direction": "outflow", "minutesAgo": 12},
    {"chain": "BTC", "chainTone": "btc", "from": "Fidelity: Wise Origin BTC", "to": "Coinbase Prime: Custody", "amount": "187 BTC", "usd": "$14.51M", "direction": "inflow", "minutesAgo": 16},
    {"chain": "SOL", "chainTone": "sol", "from": "Wintermute Market Making", "to": "Binance Hot Wallet 12", "amount": "92.4K SOL", "usd": "$12.07M", "direction": "inflow", "minutesAgo": 18},
    {"chain": "USDT", "chainTone": "usdt", "from": "Tether Treasury", "to": "Cumberland DRW", "amount": "20.0M USDT", "usd": "$20.00M", "direction": "inflow", "minutesAgo": 21},
    {"chain": "BTC", "chainTone": "btc", "from": "Grayscale: GBTC ETF", "to": "Coinbase Prime Deposit (+2)", "amount": "141 BTC", "usd": "$10.93M", "direction": "outflow", "minutesAgo": 24},
    {"chain": "ETH", "chainTone": "eth", "from": "Jump Trading 0x9c1", "to": "Kraken Deposit Wallet", "amount": "3.904K ETH", "usd": "$9.08M", "direction": "outflow", "minutesAgo": 27},
    {"chain": "BNB", "chainTone": "bnb", "from": "Binance Cold Wallet 3", "to": "Wintermute BSC Router", "amount": "14.2K BNB", "usd": "$8.81M", "direction": "outflow", "minutesAgo": 31},
    {"chain": "BTC", "chainTone": "btc", "from": "Ark/21Shares ARKB", "to": "Coinbase Prime: Custody", "amount": "119 BTC", "usd": "$9.19M", "direction": "inflow", "minutesAgo": 35},
    {"chain": "USDC", "chainTone": "usdc", "from": "Circle Treasury", "to": "Coinbase Institutional", "amount": "15.0M USDC", "usd": "$15.00M", "direction": "inflow", "minutesAgo": 39},
    {"chain": "ETH", "chainTone": "eth", "from": "Coinbase Prime: Custody", "to": "BlackRock: ETHA Ethereum ETF", "amount": "2.865K ETH", "usd": "$6.71M", "direction": "inflow", "minutesAgo": 43},
    {"chain": "SOL", "chainTone": "sol", "from": "FalconX Prime", "to": "OKX Solana Deposit", "amount": "48.0K SOL", "usd": "$6.18M", "direction": "outflow", "minutesAgo": 47},
    {"chain": "BTC", "chainTone": "btc", "from": "Bitwise ETF Reserve", "to": "Coinbase Prime Deposit", "amount": "78 BTC", "usd": "$6.04M", "direction": "outflow", "minutesAgo": 52},
    {"chain": "USDT", "chainTone": "usdt", "from": "Alameda Recovery Wallet", "to": "Binance Deposit Wallet", "amount": "12.5M USDT", "usd": "$12.50M", "direction": "outflow", "minutesAgo": 56},
    {"chain": "BNB", "chainTone": "bnb", "from": "Jump Cross-chain Treasury", "to": "Binance Hot Wallet 7", "amount": "8.4K BNB", "usd": "$5.22M", "direction": "inflow", "minutesAgo": 61},
]


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


def _normalize_meme_chain(value: str) -> str:
    normalized = (value or "").strip().lower()
    mapping = {
        "sol": "solana",
        "solana": "solana",
        "bsc": "bsc",
        "bnb": "bsc",
        "bnbchain": "bsc",
        "binance": "bsc",
        "binance-smart-chain": "bsc",
    }
    return mapping.get(normalized, "")


def _meme_chain_label(chain_id: str) -> str:
    return {"solana": "SOL", "bsc": "BNB"}.get(chain_id, chain_id.upper())


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _meme_banner_cache_key(chains: list[str], limit: int) -> str:
    return f"meme:banner:{','.join(sorted(chains))}:{limit}"


def _meme_banner_score(pair: dict, boost_item: dict | None) -> float:
    txns = (pair.get("txns") or {}).get("h6") or {}
    volume = (pair.get("volume") or {}).get("h6") or 0
    liquidity = ((pair.get("liquidity") or {}).get("usd")) or 0
    price_change = (pair.get("priceChange") or {}).get("h6") or 0
    boosts = (pair.get("boosts") or {}).get("active") or 0
    extra_boost = (boost_item or {}).get("amount") or 0
    total_txns = int(txns.get("buys", 0) or 0) + int(txns.get("sells", 0) or 0)
    return (
        total_txns * 1.8
        + float(volume or 0) / 800
        + float(liquidity or 0) / 6000
        + max(float(price_change or 0), 0.0) * 0.8
        + float(boosts or 0) * 5
        + float(extra_boost or 0) * 0.02
    )


def fetch_whale_feed(limit: int = WHALE_FEED_DEFAULT_LIMIT) -> list[dict]:
    normalized_limit = max(8, min(int(limit or WHALE_FEED_DEFAULT_LIMIT), 24))
    cache_key = f"{WHALE_FEED_REDIS_KEY}:{normalized_limit}"
    now = time.time()

    redis_cached = cache_get_json(cache_key)
    if isinstance(redis_cached, list) and redis_cached:
        WHALE_FEED_CACHE[cache_key] = {"timestamp": now, "items": redis_cached}
        return list(redis_cached)

    local_cached = WHALE_FEED_CACHE.get(cache_key) or {}
    if local_cached.get("items") and (now - float(local_cached.get("timestamp", 0.0))) < WHALE_FEED_TTL:
        return list(local_cached["items"])

    offset = int(now // WHALE_FEED_TTL) % len(WHALE_FEED_SEED)
    ordered = WHALE_FEED_SEED[offset:] + WHALE_FEED_SEED[:offset]
    items = ordered[:normalized_limit]

    WHALE_FEED_CACHE[cache_key] = {"timestamp": now, "items": items}
    try:
        cache_set_json(cache_key, items, WHALE_FEED_TTL)
    except Exception:
        pass
    return list(items)


def fetch_meme_banner(chains: list[str] | None = None, limit: int = MEME_BANNER_DEFAULT_LIMIT) -> list[dict]:
    normalized_chains = [_normalize_meme_chain(item) for item in (chains or MEME_BANNER_DEFAULT_CHAINS)]
    normalized_chains = [item for item in normalized_chains if item]
    if not normalized_chains:
        normalized_chains = list(MEME_BANNER_DEFAULT_CHAINS)
    normalized_chains = list(dict.fromkeys(normalized_chains))
    normalized_limit = max(3, min(int(limit or MEME_BANNER_DEFAULT_LIMIT), 12))
    cache_key = _meme_banner_cache_key(normalized_chains, normalized_limit)
    now = time.time()

    redis_cached = cache_get_json(cache_key)
    if isinstance(redis_cached, list) and redis_cached:
        MEME_BANNER_CACHE[cache_key] = {"timestamp": now, "items": redis_cached}
        return list(redis_cached)

    local_cached = MEME_BANNER_CACHE.get(cache_key) or {}
    if local_cached.get("items") and (now - float(local_cached.get("timestamp", 0.0))) < MEME_BANNER_TTL:
        return list(local_cached["items"])

    try:
        items: list[dict] = []
        boost_meta_by_chain: dict[str, dict[str, dict]] = {chain: {} for chain in normalized_chains}
        headers = {"User-Agent": "Mozilla/5.0"}

        with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
            boost_resp = client.get("https://api.dexscreener.com/token-boosts/latest/v1")
            boost_resp.raise_for_status()
            boosts = boost_resp.json()
            if not isinstance(boosts, list):
                boosts = []

            for item in boosts:
                chain_id = _normalize_meme_chain(item.get("chainId") or "")
                if chain_id not in normalized_chains:
                    continue
                address = (item.get("tokenAddress") or "").strip()
                if not address:
                    continue
                boost_meta_by_chain[chain_id].setdefault(address, item)

            for chain_id in normalized_chains:
                addresses = list(boost_meta_by_chain[chain_id].keys())[:24]
                if not addresses:
                    continue

                best_pairs: dict[str, dict] = {}
                for batch in _chunked(addresses, MEME_BANNER_BATCH_SIZE):
                    pair_resp = client.get(f"https://api.dexscreener.com/tokens/v1/{chain_id}/{','.join(batch)}")
                    pair_resp.raise_for_status()
                    pairs = pair_resp.json()
                    if not isinstance(pairs, list):
                        continue
                    for pair in pairs:
                        base = pair.get("baseToken") or {}
                        address = (base.get("address") or "").strip()
                        if not address or address not in boost_meta_by_chain[chain_id]:
                            continue
                        existing = best_pairs.get(address)
                        existing_score = _meme_banner_score(existing, boost_meta_by_chain[chain_id][address]) if existing else -1
                        next_score = _meme_banner_score(pair, boost_meta_by_chain[chain_id][address])
                        if next_score > existing_score:
                            best_pairs[address] = pair

                for address, pair in best_pairs.items():
                    boost_item = boost_meta_by_chain[chain_id].get(address) or {}
                    base = pair.get("baseToken") or {}
                    info = pair.get("info") or {}
                    txns_h6 = (pair.get("txns") or {}).get("h6") or {}
                    volume_h6 = (pair.get("volume") or {}).get("h6") or 0
                    price_change_h6 = (pair.get("priceChange") or {}).get("h6") or 0
                    liquidity_usd = ((pair.get("liquidity") or {}).get("usd")) or 0
                    market_cap = pair.get("marketCap") or pair.get("fdv") or 0
                    buys = int(txns_h6.get("buys", 0) or 0)
                    sells = int(txns_h6.get("sells", 0) or 0)
                    total_txns = buys + sells

                    items.append({
                        "chain": chain_id,
                        "chainLabel": _meme_chain_label(chain_id),
                        "symbol": base.get("symbol") or address[:6],
                        "name": base.get("name") or (boost_item.get("description") or "")[:24],
                        "icon": (info.get("imageUrl") or boost_item.get("icon") or "").strip(),
                        "url": (pair.get("url") or boost_item.get("url") or f"https://dexscreener.com/{chain_id}/{address}").strip(),
                        "price": _format_meme_price(float(pair.get("priceUsd") or 0)),
                        "change6h": round(float(price_change_h6 or 0), 2),
                        "volume6h": _format_meme_money(float(volume_h6 or 0)),
                        "liquidity": _format_meme_money(float(liquidity_usd or 0)),
                        "marketCap": _format_meme_money(float(market_cap or 0)),
                        "buys6h": buys,
                        "sells6h": sells,
                        "txns6h": total_txns,
                        "score": _meme_banner_score(pair, boost_item),
                    })
    except Exception:
        if local_cached.get("items"):
            return list(local_cached["items"])
        if isinstance(redis_cached, list) and redis_cached:
            return list(redis_cached)
        raise

    ranked_items = sorted(items, key=lambda item: item.get("score", 0), reverse=True)[:normalized_limit]
    for item in ranked_items:
        item.pop("score", None)

    MEME_BANNER_CACHE[cache_key] = {"timestamp": now, "items": ranked_items}
    if ranked_items:
        cache_set_json(cache_key, ranked_items, MEME_BANNER_TTL)
    return ranked_items


def fetch_meme_trending() -> list[dict]:
    now = time.time()
    redis_cached = cache_get_json(MEME_TRENDING_REDIS_KEY)
    if isinstance(redis_cached, list) and redis_cached:
        MEME_TRENDING_CACHE["timestamp"] = now
        MEME_TRENDING_CACHE["tokens"] = redis_cached
        return list(redis_cached)

    if MEME_TRENDING_CACHE["tokens"] and (now - MEME_TRENDING_CACHE["timestamp"]) < MEME_TRENDING_TTL:
        return list(MEME_TRENDING_CACHE["tokens"])

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

                symbol = ""
                name = ""
                price_usd = None
                volume_h24 = None
                price_change_h24 = None
                txns_h24_buys = 0
                txns_h24_sells = 0
                icon_url = ""

                try:
                    pair_resp = client.get(
                        f"https://api.dexscreener.com/latest/dex/tokens/{address}"
                    )
                    pair_resp.raise_for_status()
                    pair_data = pair_resp.json()
                    pairs = pair_data.get("pairs") or []
                    if pairs:
                        pair = pairs[0]
                        base = pair.get("baseToken") or {}
                        symbol = base.get("symbol", "")
                        name = base.get("name", "")
                        price_usd = float(pair.get("priceUsd", 0) or 0)
                        vol = pair.get("volume") or {}
                        volume_h24 = float(vol.get("h24", 0) or 0)
                        price_change = pair.get("priceChange") or {}
                        price_change_h24 = float(price_change.get("h24", 0) or 0)
                        txns = pair.get("txns") or {}
                        h24 = txns.get("h24") or {}
                        txns_h24_buys = int(h24.get("buys", 0) or 0)
                        txns_h24_sells = int(h24.get("sells", 0) or 0)
                except Exception:
                    pass

                description = (item.get("description") or "").strip()
                icon_url = item.get("icon", "")
                header_url = item.get("header", "")
                token_url = item.get("url", f"https://dexscreener.com/solana/{address}")
                links = item.get("links") or []
                twitter_url = ""
                website_url = ""
                for link in links:
                    link_url = (link.get("url") or "").strip()
                    if not link_url:
                        continue
                    if link.get("type") == "twitter" or "x.com" in link_url:
                        twitter_url = link_url
                    elif not website_url:
                        website_url = link_url

                tokens.append({
                    "symbol": symbol or address[:6],
                    "name": name or description[:30],
                    "address": address,
                    "price": _format_meme_price(price_usd),
                    "volume24h": f"${volume_h24:,.0f}" if volume_h24 else "--",
                    "change24h": round(price_change_h24, 2) if price_change_h24 else 0,
                    "buys24h": txns_h24_buys,
                    "sells24h": txns_h24_sells,
                    "description": description,
                    "icon": icon_url,
                    "header": header_url,
                    "url": token_url,
                    "twitter": twitter_url,
                    "website": website_url,
                })
    except Exception:
        if MEME_TRENDING_CACHE["tokens"]:
            return list(MEME_TRENDING_CACHE["tokens"])
        if isinstance(redis_cached, list) and redis_cached:
            return list(redis_cached)
        raise

    MEME_TRENDING_CACHE["timestamp"] = now
    MEME_TRENDING_CACHE["tokens"] = tokens
    if tokens:
        cache_set_json(MEME_TRENDING_REDIS_KEY, tokens, MEME_TRENDING_TTL)
    return tokens


@app.get("/meme/trending")
def meme_trending() -> dict:
    try:
        return {"tokens": fetch_meme_trending()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/whales/feed")
def whale_feed(limit: int = Query(WHALE_FEED_DEFAULT_LIMIT, ge=8, le=24)) -> dict:
    try:
        items = fetch_whale_feed(limit=limit)
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/meme/banner")
def meme_banner(
    chains: str = Query("solana,bsc", min_length=3, max_length=64),
    limit: int = Query(MEME_BANNER_DEFAULT_LIMIT, ge=3, le=12),
) -> dict:
    try:
        chain_items = [item.strip() for item in chains.split(",") if item.strip()]
        return {"items": fetch_meme_banner(chains=chain_items, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
