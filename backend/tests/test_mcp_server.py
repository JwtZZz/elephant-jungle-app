"""Tests for mcp_server data fetching functions."""

from unittest.mock import patch, MagicMock

from mcp_server import (
    format_market_cap,
    format_price,
    _format_meme_price,
    _format_meme_money,
    parse_okx_number,
    map_okx_bar,
    build_okx_inst_id,
    strip_html,
    parse_rss_items,
    _coerce_float,
    _short_wallet,
    _minutes_ago,
)


class TestFormatters:
    def test_format_market_cap(self):
        assert format_market_cap(None) == "--"
        assert format_market_cap(1_500_000_000_000) == "$1.50T"
        assert format_market_cap(2_500_000_000) == "$2.5B"
        assert format_market_cap(50_000_000) == "$50.0M"
        assert format_market_cap(5000) == "$5,000"

    def test_format_price(self):
        assert format_price(None) == "--"
        assert format_price(50000) == "$50,000.00"
        assert format_price(2.5) == "$2.5000"
        assert format_price(0.05) == "$0.05000"

    def test_meme_price(self):
        assert _format_meme_price(None) == "--"
        assert _format_meme_price(1.5) == "$1.5000"
        assert _format_meme_price(0.1) == "$0.100000"
        assert _format_meme_price(0.001) == "$0.00100000"

    def test_meme_money(self):
        assert _format_meme_money(None) == "--"
        assert _format_meme_money(2_000_000_000) == "$2.00B"
        assert _format_meme_money(500_000) == "$500.0K"
        assert _format_meme_money(100) == "$100"


class TestOKXHelpers:
    def test_map_okx_bar(self):
        assert map_okx_bar("1m") == "1m"
        assert map_okx_bar("1h") == "1H"
        assert map_okx_bar("4h") == "4H"
        assert map_okx_bar("1d") == "1D"
        assert map_okx_bar("invalid") == "15m"

    def test_parse_okx_number(self):
        assert parse_okx_number("123.45") == 123.45
        assert parse_okx_number(None) == 0.0
        assert parse_okx_number("abc") == 0.0

    def test_build_okx_inst_id(self):
        assert build_okx_inst_id("btc") == "BTC-USDT"
        assert build_okx_inst_id("ETH") == "ETH-USDT"


class TestRSSHelpers:
    def test_strip_html(self):
        assert strip_html("<b>hello</b>") == "hello"
        assert strip_html("plain text") == "plain text"
        assert strip_html("") == ""

    def test_coerce_float(self):
        assert _coerce_float("123") == 123.0
        assert _coerce_float(None) is None
        assert _coerce_float("") is None

    def test_short_wallet(self):
        result = _short_wallet("0x1234567890abcdef1234567890abcdef12345678")
        assert len(result) <= 14
        assert "..." in result

    def test_minutes_ago(self):
        import time
        # Unix timestamp in the past → calculate minutes
        ts = time.time() - 3600  # 1 hour ago
        assert 59 <= _minutes_ago(ts) <= 61


class TestRSSParsing:
    def test_parse_rss_items_empty(self):
        assert parse_rss_items("<xml></xml>") == []

    def test_parse_rss_items_missing_channel(self):
        assert parse_rss_items("<root><not-channel/></root>") == []
