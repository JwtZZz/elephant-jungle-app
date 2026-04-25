from pathlib import Path
import os
import time
import threading
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
    now = time.time()
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
    return [serialize_market_coin(coin) for coin in updated_coins]


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


def fetch_market_briefs() -> dict:
    now = time.time()
    cached_payload = briefs_cache.get("payload", {})
    cached_at = float(briefs_cache.get("timestamp", 0.0))
    if cached_payload and (now - cached_at) < BRIEFS_CACHE_TTL_SECONDS:
        return dict(cached_payload)

    feeds = {
        "social": "https://news.google.com/rss/search?q=site:x.com+(bitcoin+OR+ethereum+OR+solana+OR+crypto)+when:1d&hl=en-US&gl=US&ceid=US:en",
        "news": "https://news.google.com/rss/search?q=(bitcoin+OR+ethereum+OR+crypto)+finance+when:1d&hl=en-US&gl=US&ceid=US:en",
    }

    payload: dict[str, list[dict]] = {}
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            for key, url in feeds.items():
                response = client.get(url)
                response.raise_for_status()
                payload[key] = parse_rss_items(response.text, limit=8)
    except Exception:
        if cached_payload:
            return dict(cached_payload)
        raise

    briefs_cache["timestamp"] = now
    briefs_cache["payload"] = payload
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
    cached = title_translation_cache.get(clean_title)
    if cached:
        return cached
    try:
        translated = translate_text(clean_title, target_language="zh").strip()
    except Exception:
        translated = clean_title
    title_translation_cache[clean_title] = translated or clean_title
    return title_translation_cache[clean_title]


def fetch_market_timeline(symbol: str, name: str, language: str = "en") -> list[dict]:
    normalized_symbol = (symbol or "").strip().upper()
    normalized_name = (name or "").strip()
    normalized_language = (language or "en").strip().lower()
    cache_key = f"{normalized_symbol}:{normalized_name}:{normalized_language}"
    now = time.time()
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
    return items


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


@app.get("/market/timeline/prewarm")
def market_timeline_prewarm() -> dict:
    prewarm_market_timeline_once()
    return {"ok": True, "assets": [symbol for symbol, _ in TIMELINE_PREWARM_ASSETS]}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "providers": "ready"}


@app.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    try:
        return ingest_document(
            source=req.source,
            title=req.title,
            url=req.url,
            published_at=req.published_at,
            doc_type=req.doc_type,
            project=req.project,
            category=req.category,
            region=req.region,
            source_type=req.source_type,
            language=req.language,
            summary=req.summary,
            content=req.content,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
