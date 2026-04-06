"""Live smoke tests — hit real public APIs to verify endpoints work.

Run with:  pytest -m smoke
Skip in CI: these tests are excluded by default (require network access).

Each test verifies:
  1. The API responds with valid JSON (not HTML error pages).
  2. The response contains expected top-level keys.
  3. Data items have plausible structure.
"""

import pytest

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher

pytestmark = pytest.mark.smoke


@pytest.fixture
async def live_fetcher(tmp_path):
    """Real fetcher with a temp cache — hits actual APIs."""
    cache = Cache(db_path=tmp_path / "smoke.db")
    breaker = CircuitBreaker()
    fetcher = Fetcher(cache=cache, breaker=breaker)
    yield fetcher
    await fetcher.close()
    cache.close()


# ── Financial Markets ────────────────────────────────────────────────


async def test_live_market_quotes(live_fetcher):
    from world_intel_mcp.sources.markets import fetch_market_quotes

    result = await fetch_market_quotes(live_fetcher, symbols=["^GSPC"])
    assert "quotes" in result
    assert result["source"] == "yahoo-finance"
    if result["quotes"]:
        q = result["quotes"][0]
        assert "symbol" in q
        assert "price" in q


async def test_live_crypto_quotes(live_fetcher):
    from world_intel_mcp.sources.markets import fetch_crypto_quotes

    result = await fetch_crypto_quotes(live_fetcher, limit=3)
    assert "coins" in result
    assert result["source"] == "coingecko"
    if result["coins"]:
        coin = result["coins"][0]
        assert "id" in coin
        assert "current_price" in coin
        assert isinstance(coin["current_price"], (int, float))


async def test_live_fear_greed(live_fetcher):
    from world_intel_mcp.sources.markets import fetch_macro_signals

    result = await fetch_macro_signals(live_fetcher)
    assert "signals" in result
    fg = result["signals"].get("fear_greed")
    if fg is not None:
        assert "value" in fg
        assert 0 <= fg["value"] <= 100


# ── Seismology ───────────────────────────────────────────────────────


async def test_live_earthquakes(live_fetcher):
    from world_intel_mcp.sources.seismology import fetch_earthquakes

    result = await fetch_earthquakes(live_fetcher, min_magnitude=5.0, limit=5)
    assert "earthquakes" in result
    assert result["source"] == "usgs"
    if result["earthquakes"]:
        eq = result["earthquakes"][0]
        assert "magnitude" in eq
        assert "place" in eq
        assert isinstance(eq["magnitude"], (int, float))


# ── Forex ────────────────────────────────────────────────────────────


async def test_live_forex_rates(live_fetcher):
    from world_intel_mcp.sources.forex import fetch_forex_rates

    result = await fetch_forex_rates(live_fetcher, base="USD", symbols="EUR,GBP")
    assert "rates" in result
    assert result["source"] in ("frankfurter", "ecb-forex")


# ── News ─────────────────────────────────────────────────────────────


async def test_live_news_feed(live_fetcher):
    from world_intel_mcp.sources.news import fetch_news_feed

    result = await fetch_news_feed(live_fetcher, limit=5)
    assert "items" in result
    assert result["source"] == "rss-aggregator"


# ── Space Weather ────────────────────────────────────────────────────


async def test_live_space_weather(live_fetcher):
    from world_intel_mcp.sources.space_weather import fetch_space_weather

    result = await fetch_space_weather(live_fetcher)
    assert "source" in result
    assert any(
        k in result
        for k in ("kp_index", "solar_flares", "alerts", "error")
    )


# ── Hacker News ──────────────────────────────────────────────────────


async def test_live_hacker_news(live_fetcher):
    from world_intel_mcp.sources.hacker_news import fetch_hacker_news

    result = await fetch_hacker_news(live_fetcher, limit=5)
    assert "stories" in result
    assert result["source"] == "hackernews"
    if result["stories"]:
        story = result["stories"][0]
        assert "title" in story


# ── Aviation ─────────────────────────────────────────────────────────


async def test_live_airport_delays(live_fetcher):
    from world_intel_mcp.sources.aviation import fetch_airport_delays

    result = await fetch_airport_delays(live_fetcher)
    assert "source" in result
    assert result["source"] == "faa"
    assert "delayed_count" in result or "error" in result


# ── Infrastructure ───────────────────────────────────────────────────


async def test_live_service_status(live_fetcher):
    from world_intel_mcp.sources.service_status import fetch_service_status

    result = await fetch_service_status(live_fetcher)
    assert "incidents" in result
    assert "source" in result


# ── Geospatial (static config — always works) ───────────────────────


async def test_live_military_bases():
    """Pure config query — no fetcher needed, no network."""
    from world_intel_mcp.sources.geospatial import fetch_military_bases

    result = await fetch_military_bases()
    assert "bases" in result
    assert len(result["bases"]) > 50


async def test_live_stock_exchanges():
    """Pure config query — no fetcher needed, no network."""
    from world_intel_mcp.sources.geospatial import fetch_stock_exchanges

    result = await fetch_stock_exchanges()
    assert "exchanges" in result
    assert len(result["exchanges"]) > 70


# ── SEC EDGAR ────────────────────────────────────────────────────────


async def test_live_sec_filings(live_fetcher):
    from world_intel_mcp.sources.sec_edgar import fetch_sec_filings

    result = await fetch_sec_filings(live_fetcher, query="artificial intelligence", limit=3)
    assert "filings" in result
    assert result["source"] == "sec-edgar"


# ── Bonds & Yields ───────────────────────────────────────────────────


async def test_live_bond_indices(live_fetcher):
    from world_intel_mcp.sources.bonds import fetch_bond_indices

    result = await fetch_bond_indices(live_fetcher)
    assert "indices" in result or "bonds" in result
    assert result["source"] == "yahoo-finance"


# ── BTC Technicals ───────────────────────────────────────────────────


async def test_live_btc_technicals(live_fetcher):
    from world_intel_mcp.sources.markets import fetch_btc_technicals

    result = await fetch_btc_technicals(live_fetcher)
    assert "source" in result
    if "error" not in result:
        assert "price" in result
        assert "sma_50" in result
        assert isinstance(result["price"], (int, float))


# ── Central Banks ────────────────────────────────────────────────────


async def test_live_central_bank_rates(live_fetcher):
    from world_intel_mcp.sources.central_banks import fetch_central_bank_rates

    result = await fetch_central_bank_rates(live_fetcher)
    assert "rates" in result
    assert result["source"] == "multi"
    assert result["count"] > 0
    bank = result["rates"][0]
    assert "bank" in bank
    assert "rate" in bank


# ── Environmental ────────────────────────────────────────────────────


async def test_live_environmental_events(live_fetcher):
    from world_intel_mcp.sources.environmental import fetch_environmental_events

    result = await fetch_environmental_events(live_fetcher)
    assert "events" in result
    assert result["source"] == "eonet"


# ── Cyber Threats ────────────────────────────────────────────────────


async def test_live_cyber_threats(live_fetcher):
    from world_intel_mcp.sources.cyber import fetch_cyber_threats

    result = await fetch_cyber_threats(live_fetcher)
    assert "source" in result
    assert any(
        k in result
        for k in ("urlhaus", "feodotracker", "cisa_kev", "threats", "error")
    )
