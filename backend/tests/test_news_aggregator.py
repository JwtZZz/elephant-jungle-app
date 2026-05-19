"""Tests for news_aggregator module."""
from unittest.mock import patch, MagicMock

from news_aggregator import (
    _normalize_title,
    _title_hash,
    dedup,
    _strip_html,
    _parse_rss,
    _parse_reddit_json,
    fetch_headlines,
    fetch_by_topic,
)


class TestNormalisation:
    def test_normalize_title_lowercases(self):
        assert _normalize_title("Hello World") == "hello world"

    def test_normalize_title_strips_punctuation(self):
        assert _normalize_title("Bitcoin Price Up!") == "bitcoin price up"

    def test_normalize_title_collapses_spaces(self):
        assert _normalize_title("  hello   world  ") == "hello world"

    def test_normalize_title_trailing_period(self):
        assert _normalize_title("Breaking news.") == "breaking news"

    def test_title_hash_consistency(self):
        h1 = _title_hash("Hello World")
        h2 = _title_hash("Hello World")
        assert h1 == h2

    def test_title_hash_different_titles(self):
        h1 = _title_hash("Bitcoin News")
        h2 = _title_hash("Ethereum News")
        assert h1 != h2


class TestDedup:
    def test_dedup_removes_duplicates(self):
        items = [
            {"title": "Bitcoin Price Up", "source": "A"},
            {"title": "Bitcoin Price Up", "source": "B"},
            {"title": "Ethereum Surges", "source": "A"},
        ]
        result = dedup(items)
        assert len(result) == 2

    def test_dedup_normalizes_before_comparing(self):
        items = [
            {"title": "Bitcoin Price Up!", "source": "A"},
            {"title": "Bitcoin Price Up", "source": "B"},
        ]
        result = dedup(items)
        assert len(result) == 1

    def test_dedup_empty(self):
        assert dedup([]) == []


class TestRSSParsing:
    def test_strip_html(self):
        assert _strip_html("<b>hello</b>") == "hello"
        assert _strip_html("plain text") == "plain text"
        assert _strip_html("") == ""

    def test_parse_rss_empty_xml(self):
        assert _parse_rss("<xml></xml>", "Test") == []

    def test_parse_rss_basic(self):
        xml = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
  <item>
    <title>Bitcoin News</title>
    <link>https://example.com/1</link>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    <description>Some description</description>
    <source>CoinDesk</source>
  </item>
  <item>
    <title>Ethereum Update</title>
    <link>https://example.com/2</link>
  </item>
</channel>
</rss>"""
        items = _parse_rss(xml, "TestSource")
        assert len(items) == 2
        assert items[0]["title"] == "Bitcoin News"
        assert items[0]["source"] == "TestSource"
        assert items[0]["link"] == "https://example.com/1"
        assert items[1]["title"] == "Ethereum Update"


class TestRedditParsing:
    def test_parse_reddit_json(self):
        data = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Hot Crypto Topic",
                            "permalink": "/r/crypto/comments/abc/",
                            "created_utc": 1700000000,
                            "selftext": "Discussion text",
                            "stickied": False,
                        }
                    },
                    {
                        "data": {
                            "title": "Sticky Post",
                            "permalink": "/r/crypto/comments/sticky/",
                            "created_utc": 1700000001,
                            "selftext": "",
                            "stickied": True,
                        }
                    },
                ]
            }
        }
        items = _parse_reddit_json(data, "cryptocurrency")
        assert len(items) == 1
        assert items[0]["title"] == "Hot Crypto Topic"
        assert "reddit" in items[0]["source"]
        assert items[0]["link"] == "https://www.reddit.com/r/crypto/comments/abc/"


class TestFetchByTopic:
    def test_fetch_by_topic_no_query(self):
        assert fetch_by_topic("") == []
        assert fetch_by_topic("  ") == []

    @patch("news_aggregator.fetch_headlines")
    def test_fetch_by_topic_filters(self, mock_fetch):
        mock_fetch.return_value = [
            {"title": "Bitcoin Rally", "summary": "BTC is up", "source": "A"},
            {"title": "Ethereum News", "summary": "ETH is strong", "source": "B"},
            {"title": "Solana Update", "summary": "SOL upgrade", "source": "C"},
        ]
        result = fetch_by_topic("bitcoin", max_items=10)
        assert len(result) == 1
        assert "Bitcoin" in result[0]["title"]

    @patch("news_aggregator.fetch_headlines")
    def test_fetch_by_topic_summary_search(self, mock_fetch):
        mock_fetch.return_value = [
            {"title": "Daily Roundup", "summary": "Bitcoin and Ethereum lead", "source": "A"},
            {"title": "Altcoin Watch", "summary": "Solana and ADA rising", "source": "B"},
        ]
        result = fetch_by_topic("solana", max_items=10)
        assert len(result) == 1

    @patch("news_aggregator.fetch_headlines")
    def test_fetch_by_topic_max_items(self, mock_fetch):
        mock_fetch.return_value = [
            {"title": f"Bitcoin Update {i}", "summary": "", "source": "A"} for i in range(10)
        ]
        result = fetch_by_topic("bitcoin", max_items=3)
        assert len(result) == 3


class TestFetchHeadlines:
    @patch("news_aggregator._fetch_rss")
    @patch("news_aggregator._fetch_reddit")
    def test_fetch_headlines_integration(self, mock_reddit, mock_rss):
        mock_rss.return_value = [
            {"title": "RSS Article", "link": "https://rss.com/1", "published": "", "summary": "", "source": "CoinDesk"}
        ]
        mock_reddit.return_value = [
            {"title": "Reddit Post", "link": "https://reddit.com/1", "published": "", "summary": "", "source": "reddit"}
        ]
        items = fetch_headlines(max_items=10)
        assert len(items) == 2  # dedup won't remove them since they're different

    @patch("news_aggregator._fetch_rss")
    @patch("news_aggregator._fetch_reddit")
    def test_fetch_headlines_dedup(self, mock_reddit, mock_rss):
        # Both return same normalized title
        mock_rss.return_value = [
            {"title": "Bitcoin News!", "link": "https://rss.com/1", "published": "", "summary": "", "source": "CoinDesk"}
        ]
        mock_reddit.return_value = [
            {"title": "Bitcoin News", "link": "https://reddit.com/1", "published": "", "summary": "", "source": "reddit"}
        ]
        items = fetch_headlines(max_items=10)
        assert len(items) == 1
