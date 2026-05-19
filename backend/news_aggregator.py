"""Multi-source news aggregator for cryptocurrency news.

Fetches from RSS feeds + Reddit hot posts, deduplicates by normalized
title, sorts by recency, and provides topic filtering.

Used by mcp_server.py as the "live data" source for time-sensitive queries.
"""

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from html import unescape

import httpx

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("Blockworks", "https://blockworks.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
]

REDDIT_SUBREDDITS = [
    "cryptocurrency",
    "bitcoin",
    "ethereum",
    "solana",
]

REDDIT_URL = "https://www.reddit.com/r/{sub}/hot/.json"

REQUEST_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; ElephantJungleBot/1.0)"

# Coin name aliases — used by fetch_by_topic to match variations (BTC ↔ bitcoin)
_COIN_ALIASES: dict[str, set[str]] = {
    "bitcoin": {"bitcoin", "btc", "比特币"},
    "ethereum": {"ethereum", "eth", "以太坊"},
    "solana": {"solana", "sol"},
    "bnb": {"bnb", "bsc", "binance coin"},
    "xrp": {"xrp", "ripple"},
    "cardano": {"cardano", "ada"},
    "dogecoin": {"dogecoin", "doge", "狗狗币"},
    "polkadot": {"polkadot", "dot"},
    "avalanche": {"avalanche", "avax"},
    "sui": {"sui"},
    "aptos": {"aptos", "apt"},
    "arbitrum": {"arbitrum", "arb"},
    "optimism": {"optimism", "op"},
    "ton": {"ton", "toncoin"},
    "tron": {"tron", "trx"},
    "chainlink": {"chainlink", "link"},
    "polygon": {"polygon", "matic"},
    "near": {"near"},
}


# ---------------------------------------------------------------------------
# Normalisation & dedup helpers
# ---------------------------------------------------------------------------


def _normalize_title(title: str) -> str:
    """Lowercase, strip extra whitespace, remove trailing punctuation."""
    text = (title or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".,!?;:…\"'”）")
    return text


def _title_hash(title: str) -> str:
    return hashlib.md5(_normalize_title(title).encode()).hexdigest()


def _parse_rfc822_pubdate(value: str) -> float:
    """Best-effort parse of RFC 822 / RFC 2822 pubDate to unix timestamp.
    Also handles plain Unix timestamp strings (e.g. from Reddit API).
    """
    if not value:
        return 0.0
    # Plain numeric string (Unix timestamp) — convert directly
    if value.strip().isdigit():
        return float(value.strip())
    # Try common RSS date formats
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            ts = time.strptime(value.rstrip(), fmt[:len(value.rstrip())])
            return time.mktime(ts)
        except (ValueError, OverflowError):
            continue
    # Handle +0000 / -0500 / +000 / -0500 manually
    try:
        import datetime
        if " +" in value or " -" in value:
            date_part = value[:-6].strip()
            ts = time.strptime(date_part, "%a, %d %b %Y %H:%M:%S")
            return time.mktime(ts)
        if value.endswith("GMT") or value.endswith("UTC"):
            date_part = value[:-4].strip()
            ts = time.strptime(date_part, "%a, %d %b %Y %H:%M:%S")
            return time.mktime(ts)
    except Exception:
        pass
    return time.time()  # fallback: now


# ---------------------------------------------------------------------------
# RSS parsing
# ---------------------------------------------------------------------------


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value or "")).strip()


def _parse_rss(xml_text: str, source_name: str) -> list[dict]:
    """Parse RSS 2.0 XML into list of {title, link, published, summary, source}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Handle both RSS 2.0 (<channel><item>) and Atom (<feed><entry>)
    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
    else:
        # Atom
        items = root.findall("{http://www.w3.org/2005/Atom}entry")
        if items:
            return _parse_atom_entries(items, source_name)
        return []

    results = []
    for item in items:
        title = _strip_html(item.findtext("title", default=""))
        link = (item.findtext("link", default="") or "").strip()
        pub_date = (item.findtext("pubDate", default="") or "").strip()
        summary = _strip_html(item.findtext("description", default=""))
        if not title and not link:
            continue
        results.append({
            "title": title or "(no title)",
            "link": link,
            "published": pub_date,
            "summary": summary[:500],
            "source": source_name,
        })
    return results


def _parse_atom_entries(entries: list, source_name: str) -> list[dict]:
    results = []
    for entry in entries:
        ns = "{http://www.w3.org/2005/Atom}"
        title = _strip_html(entry.findtext(f"{ns}title", default=""))
        link_el = entry.find(f"{ns}link")
        link = (link_el.get("href") if link_el is not None else "").strip()
        published = (entry.findtext(f"{ns}published", default="") or
                     entry.findtext(f"{ns}updated", default="") or "").strip()
        summary = _strip_html(
            entry.findtext(f"{ns}summary", default="") or
            entry.findtext(f"{ns}content", default="")
        )
        if not title and not link:
            continue
        results.append({
            "title": title or "(no title)",
            "link": link,
            "published": published,
            "summary": summary[:500],
            "source": source_name,
        })
    return results


# ---------------------------------------------------------------------------
# Reddit JSON parsing
# ---------------------------------------------------------------------------


def _parse_reddit_json(data: dict, subreddit: str) -> list[dict]:
    """Parse Reddit JSON /hot/.json response."""
    results = []
    children = data.get("data", {}).get("children", [])
    for child in children:
        ch_data = child.get("data", {})
        # Skip stickied posts
        if ch_data.get("stickied"):
            continue
        title = ch_data.get("title", "")
        permalink = ch_data.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else ""
        created_utc = ch_data.get("created_utc", 0)
        summary = ch_data.get("selftext", "")[:300]
        results.append({
            "title": title,
            "link": url,
            "published": str(int(created_utc)),
            "summary": summary,
            "source": f"reddit/r/{subreddit}",
        })
    return results


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _fetch_rss(url: str, source_name: str) -> list[dict]:
    """Fetch and parse an RSS feed."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return _parse_rss(resp.text, source_name)
    except Exception:
        return []


def _fetch_reddit(subreddit: str) -> list[dict]:
    """Fetch Reddit /hot from a subreddit."""
    try:
        url = REDDIT_URL.format(sub=subreddit)
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return _parse_reddit_json(resp.json(), subreddit)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def dedup(items: list[dict]) -> list[dict]:
    """Remove duplicates based on normalized title MD5, keeping the newest."""
    seen: set[str] = set()
    result = []
    for item in items:
        key = _title_hash(item.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_headlines(max_items: int = 30) -> list[dict]:
    """Fetch and merge headlines from all sources, sorted by recency.

    Returns up to *max_items* entries, each with:
        {title, link, published, summary, source, _ts}
    where _ts is a unix timestamp for sorting.
    """
    all_items: list[dict] = []

    # Parallel fetch RSS feeds
    for source, url in RSS_FEEDS:
        all_items.extend(_fetch_rss(url, source))

    # Fetch Reddit hot posts
    for sub in REDDIT_SUBREDDITS:
        all_items.extend(_fetch_reddit(sub))

    # Dedup
    unique = dedup(all_items)

    # Add sort timestamp and sort
    now = time.time()
    for item in unique:
        item["_ts"] = _parse_rfc822_pubdate(item.get("published", ""))
        if item["_ts"] <= 0:
            item["_ts"] = now

    unique.sort(key=lambda x: x["_ts"], reverse=True)

    return unique[:max_items]


def fetch_by_topic(topic: str, max_items: int = 20) -> list[dict]:
    """Filter headlines by topic keyword, with coin alias expansion.

    Supports Chinese coin names (比特币, 以太坊, 狗狗币) and coin
    aliases (bitcoin ↔ btc, ethereum ↔ eth, etc.).

    Returns items where the topic (or its aliases) appears in title/summary.
    """
    topic_lower = (topic or "").strip().lower()
    if not topic_lower:
        return []

    # Resolve coin aliases: "btc" → {"bitcoin", "btc", "比特币"}
    keywords: set[str] = set()
    for coin, aliases in _COIN_ALIASES.items():
        if topic_lower in aliases:
            keywords = aliases
            break
    if not keywords:
        keywords = {topic_lower}

    # Get enough headlines so the topic filter can find matches
    all_items = fetch_headlines(max(50, max_items * 5))

    matched = []
    for item in all_items:
        title = (item.get("title", "") or "").lower()
        summary = (item.get("summary", "") or "").lower()
        if any(kw in title or kw in summary for kw in keywords):
            matched.append(item)
            if len(matched) >= max_items:
                break

    return matched
