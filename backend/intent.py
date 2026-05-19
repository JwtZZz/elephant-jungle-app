"""Intent classifier — keyword fast-path + LLM fallback."""

import re

from providers import _chat_completion_raw

INTENT_MARKET = "market"
INTENT_KNOWLEDGE = "knowledge"
INTENT_GENERAL = "general"
INTENT_MIXED = "mixed"

_MARKET_KEYWORDS = [
    "价格", "行情", "涨", "跌", "多少钱", "市值", "k线", "k-line", "K线",
    "盘口", "深度", "成交量", "走势", "candle",
    "meme", "土狗", "铭文", "whale", "鲸鱼", "转账",
    "快讯", "新闻", "news", "brief", "消息", "资讯",
    "trending", "热点", "热门", "最新",
    "最近", "今天", "近期", "昨天", "本周", "本月",
    "breaking", "headlines", "news", "recents", "hot",
    "happened", "happening",
    "solana", "比特币",
    "币安", "okx", "交易所", "去哪个所",
    "买", "卖", "做多", "做空",
    "合约", "现货", "期权",
    "gas", "gas费", "手续费",
    "空投", "airdop", "发币",
    "前景", "值得买", "推荐", "抄底", "上车",
]

_KNOWLEDGE_KEYWORDS = [
    "什么是", "是什么意思", "怎么理解", "如何理解",
    "原理", "概念", "介绍", "是什么",
    "是谁", "作者是谁", "谁写的", "谁创建", "谁开发的",
    "技术", "白皮书", "文档", "protocol",
    "如何工作", "怎么工作", "工作机制",
    "怎么用", "如何使用", "如何用",
    "区别", "差异", "比较", "vs",
    "为什么", "原因", "理由", "风险", "安全",
    "defi", "lending", "借贷", "质押", "stake",
    "nft", "erc", "brc", "spl", "etf",
    "挖矿", "矿机", "算力", "hash",
    "分叉", "侧链", "layer", "l2", "rollup",
    "跨链", "bridge", "桥", "预言机", "oracle",
]

_CLASSIFY_PROMPT = """Analyze the user's question about cryptocurrency. Output exactly one word.

market — asks about real-time data: price, chart, trading, news, trending, whales, outlook/prospects of specific coins, comparisons of coins' performance
knowledge — asks about concepts, principles, technical docs, how things work, definitions, author info
general — greeting, chit-chat, opinions, questions without specific knowledge or data needs
mixed — needs BOTH real-time data AND knowledge to fully answer (e.g. "how is Bitcoin doing and what is its halving cycle?")

Query: {query}
Classification:"""


def _keyword_classify(query: str) -> str | None:
    """Fast keyword pass. Returns None when ambiguous."""
    q = query.lower()

    has_market = any(kw in q for kw in _MARKET_KEYWORDS)
    has_knowledge = any(kw in q for kw in _KNOWLEDGE_KEYWORDS)

    if has_market and has_knowledge:
        return INTENT_MIXED
    if has_market:
        return INTENT_MARKET
    if has_knowledge:
        return INTENT_KNOWLEDGE

    # Short queries mentioning a known crypto ticker → likely market
    if re.search(r"\b(btc|eth|sol|bnb|xrp|ada|doge|sui|apt|op|arb|avax|dot|trx)\b", q):
        if len(q) < 40:
            return INTENT_MARKET

    return None


def classify_intent(query: str) -> str:
    """Classify query intent. Keyword fast-path, then LLM fallback."""
    text = (query or "").strip()
    if not text:
        return INTENT_GENERAL

    result = _keyword_classify(text)
    if result is not None:
        return result

    # LLM fallback for ambiguous queries
    try:
        msg = _chat_completion_raw(
            [
                {"role": "system", "content": _CLASSIFY_PROMPT.format(query=text)},
                {"role": "user", "content": f"Query: {text}\nClassification:"},
            ],
            temperature=0.1,
        )
        content = (msg.get("content") or "").strip().lower()
        if content in (INTENT_MARKET, INTENT_KNOWLEDGE, INTENT_GENERAL, INTENT_MIXED):
            return content
        return INTENT_GENERAL
    except Exception:
        return INTENT_GENERAL
