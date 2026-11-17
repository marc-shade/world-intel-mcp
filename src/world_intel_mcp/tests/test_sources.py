"""Tests for source modules — uses respx to mock HTTP calls."""

import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[Cache]:
    cache = Cache(db_path=tmp_path / "test_cache.db")
    try:
        yield cache
    finally:
        cache.close()


@pytest.fixture
async def fetcher(cache: Cache) -> AsyncIterator[Fetcher]:
    breaker = CircuitBreaker()
    fetcher = Fetcher(cache=cache, breaker=breaker, default_timeout=5.0)
    try:
        yield fetcher
    finally:
        await fetcher.close()


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_market_quotes(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.markets import fetch_market_quotes

    # Mock Yahoo Finance v8 chart response for ^GSPC
    chart_response = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "^GSPC",
                        "regularMarketPrice": 5123.45,
                        "regularMarketChangePercent": 0.42,
                        "currency": "USD",
                    }
                }
            ]
        }
    }

    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC").mock(
        return_value=httpx.Response(200, json=chart_response)
    )

    result = await fetch_market_quotes(fetcher, symbols=["^GSPC"])
    assert "quotes" in result
    assert len(result["quotes"]) == 1
    assert result["quotes"][0]["symbol"] == "^GSPC"
    assert result["quotes"][0]["price"] == 5123.45
    assert result["source"] == "yahoo-finance"


@respx.mock
@pytest.mark.asyncio
async def test_fetch_crypto_quotes(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.markets import fetch_crypto_quotes

    coins = [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "current_price": 98000,
            "market_cap": 1900000000000,
            "price_change_percentage_24h": 2.5,
            "sparkline_in_7d": {"price": [95000, 96000, 97000, 98000]},
        }
    ]

    respx.get("https://api.coingecko.com/api/v3/coins/markets").mock(
        return_value=httpx.Response(200, json=coins)
    )

    result = await fetch_crypto_quotes(fetcher, limit=5)
    assert "coins" in result
    assert len(result["coins"]) == 1
    assert result["coins"][0]["symbol"] == "btc"
    assert result["source"] == "coingecko"


# ---------------------------------------------------------------------------
# Seismology
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_earthquakes(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.seismology import fetch_earthquakes

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "us7000abc1",
                "properties": {
                    "mag": 5.2,
                    "place": "100km SSW of Somewhere",
                    "time": 1708700000000,
                    "tsunami": 0,
                    "felt": 15,
                    "alert": "green",
                    "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abc1",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [-120.5, 35.2, 10.0],
                },
            }
        ],
    }

    respx.get("https://earthquake.usgs.gov/fdsnws/event/1/query").mock(
        return_value=httpx.Response(200, json=geojson)
    )

    result = await fetch_earthquakes(fetcher, min_magnitude=4.0, hours=24)
    assert result["count"] == 1
    eq = result["earthquakes"][0]
    assert eq["magnitude"] == 5.2
    assert eq["id"] == "us7000abc1"
    assert eq["depth_km"] == 10.0
    assert eq["latitude"] == 35.2
    assert eq["longitude"] == -120.5
    assert result["source"] == "usgs"


# ---------------------------------------------------------------------------
# Wildfire
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_wildfires_no_api_key(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.wildfire import fetch_wildfires

    with patch.dict("os.environ", {}, clear=False):
        # Remove the key if present
        import os

        os.environ.pop("NASA_FIRMS_API_KEY", None)
        result = await fetch_wildfires(fetcher, api_key=None)

    assert "error" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_wildfires_single_region(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.wildfire import fetch_wildfires

    csv_data = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
        "34.5,-118.2,350.0,0.5,0.5,2024-02-23,1200,N,high,2.0,290.0,45.0,D\n"
        "34.6,-118.3,360.0,0.5,0.5,2024-02-23,1200,N,high,2.0,295.0,55.0,D\n"
        "34.5,-118.2,340.0,0.5,0.5,2024-02-23,1200,N,low,2.0,285.0,30.0,D\n"
    )

    respx.get(url__regex=r".*firms\.modaps\.eosdis\.nasa\.gov.*").mock(
        return_value=httpx.Response(200, text=csv_data)
    )

    result = await fetch_wildfires(fetcher, region="north_america", api_key="testkey")
    assert "fires_by_region" in result
    na = result["fires_by_region"]["north_america"]
    assert na["count"] == 2  # only 2 high-confidence
    assert result["total_fires"] == 2


# ---------------------------------------------------------------------------
# Economic
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_fred_series_no_key(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.economic import fetch_fred_series

    import os

    os.environ.pop("FRED_API_KEY", None)
    result = await fetch_fred_series(fetcher, series_id="UNRATE", api_key=None)
    assert "error" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_world_bank_indicators(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.economic import fetch_world_bank_indicators

    wb_response = [
        {"page": 1, "pages": 1, "per_page": 5, "total": 2},
        [
            {
                "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"},
                "date": "2023",
                "value": 25000000000000,
            },
            {
                "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"},
                "date": "2022",
                "value": 24000000000000,
            },
        ],
    ]

    respx.get(url__regex=r".*api\.worldbank\.org.*").mock(
        return_value=httpx.Response(200, json=wb_response)
    )

    result = await fetch_world_bank_indicators(
        fetcher, country="USA", indicators=["NY.GDP.MKTP.CD"]
    )
    assert "indicators" in result
    assert len(result["indicators"]) == 1
    assert result["indicators"][0]["id"] == "NY.GDP.MKTP.CD"
    assert result["source"] == "world-bank"


# ---------------------------------------------------------------------------
# Gas prices, natural gas, electricity
# ---------------------------------------------------------------------------


_AAA_HTML = """<html><body>
<table><thead><tr><th></th><th>Regular</th><th>Mid-Grade</th><th>Premium</th>
<th>Diesel</th><th>E85</th></tr></thead><tbody>
<tr><td>Current Avg.</td><td>$3.450</td><td>$3.942</td><td>$4.306</td><td>$4.595</td><td>$2.762</td></tr>
<tr><td>Yesterday Avg.</td><td>$3.413</td><td>$3.897</td><td>$4.260</td><td>$4.510</td><td>$2.717</td></tr>
<tr><td>Week Ago Avg.</td><td>$2.984</td><td>$3.482</td><td>$3.851</td><td>$3.761</td><td>$2.319</td></tr>
<tr><td>Month Ago Avg.</td><td>$2.897</td><td>$3.402</td><td>$3.765</td><td>$3.644</td><td>$2.306</td></tr>
<tr><td>Year Ago Avg.</td><td>$3.095</td><td>$3.572</td><td>$3.925</td><td>$3.640</td><td>$2.523</td></tr>
</tbody></table></body></html>"""


@pytest.mark.asyncio
async def test_fetch_gas_prices(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    from world_intel_mcp.sources import economic

    monkeypatch.setattr(economic, "_fetch_aaa_html", lambda: _AAA_HTML)

    result = await economic.fetch_gas_prices(fetcher)
    assert result["source"] == "aaa"
    assert result["region"] == "US"
    assert "regular" in result["prices"]
    assert result["prices"]["regular"]["price_per_gallon"] == 3.450
    assert "diesel" in result["prices"]
    assert result["prices"]["diesel"]["price_per_gallon"] == 4.595
    # Day-over-day delta: 3.450 - 3.413 = 0.037
    assert result["prices"]["regular"]["change"] == 0.037
    assert result["prices"]["regular"]["change_pct"] is not None
    # Week-over-week comparison
    assert result["prices"]["regular"]["week_ago_pct"] is not None


@pytest.mark.asyncio
async def test_fetch_gas_prices_no_data(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    from world_intel_mcp.sources import economic

    monkeypatch.setattr(economic, "_fetch_aaa_html", lambda: "<html>maintenance</html>")

    result = await economic.fetch_gas_prices(fetcher)
    assert result["source"] == "aaa"
    assert result["prices"] == {}


@pytest.mark.asyncio
async def test_fetch_gas_prices_stale_fallback_preserves_original_fetch_time(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #5: on live-fetch failure, stale cached gas prices must keep
    their ORIGINAL fetch timestamp and carry a _stale marker instead of
    being restamped with datetime.now() — which made 3-day-old prices
    look like they were fetched seconds ago."""
    import json
    import time as time_mod
    from datetime import datetime, timezone

    from world_intel_mcp.sources import economic

    # Seed a cache entry whose created_at is 3 days in the past (Cache.set
    # always uses now(), so write the row directly to backdate it).
    conn = fetcher.cache._get_conn()
    old_created_at = time_mod.time() - 3 * 86400
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (
            "economic:gas_prices:aaa",
            json.dumps(_AAA_HTML),
            old_created_at + 1800,  # expired long ago
            old_created_at,
        ),
    )
    conn.commit()

    # _fetch_aaa_html() swallows its own errors and returns None on a real
    # failure (e.g. AAA's Cloudflare 403) rather than raising.
    monkeypatch.setattr(economic, "_fetch_aaa_html", lambda: None)

    result = await economic.fetch_gas_prices(fetcher)

    assert result["_stale"] is True
    assert result["_stale_age_seconds"] > 2.9 * 86400
    fetched_at = datetime.fromisoformat(result["fetched_at"])
    age_days = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 86400
    assert age_days > 2.9, "fetched_at must preserve the original (stale) fetch time"
    # The stale payload still parses normally.
    assert result["prices"]["regular"]["price_per_gallon"] == 3.450


@respx.mock
@pytest.mark.asyncio
async def test_fetch_residential_natgas(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.economic import fetch_residential_natgas_prices

    eia_response = {
        "response": {
            "data": [
                {"value": 15.42, "period": "2026-01"},
                {"value": 14.87, "period": "2025-12"},
            ]
        }
    }

    respx.get(url__regex=r".*api\.eia\.gov.*natural-gas/pri/sum.*").mock(
        return_value=httpx.Response(200, json=eia_response)
    )

    result = await fetch_residential_natgas_prices(fetcher, api_key="test-key")
    assert result["source"] == "eia"
    assert len(result["prices"]) == 2
    assert result["prices"][0]["price"] == 15.42


@respx.mock
@pytest.mark.asyncio
async def test_fetch_electricity_rates(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.economic import fetch_electricity_rates

    eia_response = {
        "response": {
            "data": [
                {"sectorid": "RES", "price": 16.21, "period": "2026-01"},
                {"sectorid": "COM", "price": 13.45, "period": "2026-01"},
                {"sectorid": "IND", "price": 8.76, "period": "2026-01"},
                {"sectorid": "ALL", "price": 12.89, "period": "2026-01"},
            ]
        }
    }

    respx.get(url__regex=r".*api\.eia\.gov.*electricity/retail-sales.*").mock(
        return_value=httpx.Response(200, json=eia_response)
    )

    result = await fetch_electricity_rates(fetcher, api_key="test-key")
    assert result["source"] == "eia"
    assert result["state"] == "US"
    assert "residential" in result["rates"]
    assert result["rates"]["residential"]["price_cents_kwh"] == 16.21
    assert "commercial" in result["rates"]
    assert "industrial" in result["rates"]


# ---------------------------------------------------------------------------
# Health (disease outbreaks)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_disease_outbreaks(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.health import fetch_disease_outbreaks

    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>WHO</title>
    <item>
        <title>Ebola outbreak in DRC - Update 5</title>
        <link>https://who.int/ebola-update</link>
        <pubDate>Mon, 10 Feb 2026 12:00:00 GMT</pubDate>
        <description>Ebola virus disease outbreak continues in North Kivu.</description>
    </item>
    <item>
        <title>Seasonal influenza update</title>
        <link>https://who.int/flu</link>
        <pubDate>Sun, 09 Feb 2026 08:00:00 GMT</pubDate>
        <description>Northern hemisphere flu season report.</description>
    </item>
    </channel></rss>"""

    # Mock all 3 health feeds returning same XML
    respx.get(url__regex=r".*who\.int.*").mock(
        return_value=httpx.Response(200, text=rss_xml)
    )
    respx.get(url__regex=r".*cdc\.gov.*").mock(
        return_value=httpx.Response(200, text=rss_xml)
    )
    respx.get(url__regex=r".*outbreaknewstoday.*").mock(
        return_value=httpx.Response(200, text=rss_xml)
    )

    result = await fetch_disease_outbreaks(fetcher)
    assert result["source"] == "health-outbreak-monitor"
    assert result["count"] > 0
    assert result["high_concern_count"] > 0  # "ebola" in title
    assert any(item["is_high_concern"] for item in result["items"])


# ---------------------------------------------------------------------------
# Sanctions (OFAC SDN)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_sanctions_search(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.sanctions import fetch_sanctions_search

    csv_data = (
        '100,"DOE, John",individual,SDGT,"","","","","","","","nationality Iran; DOB 01 Jan 1970"\n'
        '101,"ACME CORP",entity,CUBA,"","","","","","","",""\n'
        '102,"SMITH, Jane",individual,SYRIA,"","","","","","","","nationality Syria"\n'
    )

    respx.get(url__regex=r".*treasury\.gov.*sdn\.csv.*").mock(
        return_value=httpx.Response(200, text=csv_data)
    )

    result = await fetch_sanctions_search(fetcher, query="DOE")
    assert result["source"] == "ofac-sdn"
    assert result["count"] == 1
    assert result["matches"][0]["name"] == "DOE, John"
    assert result["total_entities"] >= 1


@respx.mock
@pytest.mark.asyncio
async def test_fetch_sanctions_search_country_filter(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.sanctions import fetch_sanctions_search

    csv_data = (
        '100,"DOE, John",individual,SDGT,"","","","","","","","nationality Iran; DOB 01 Jan 1970"\n'
        '101,"ACME CORP",entity,CUBA,"","","","","","","",""\n'
    )

    respx.get(url__regex=r".*treasury\.gov.*sdn\.csv.*").mock(
        return_value=httpx.Response(200, text=csv_data)
    )

    result = await fetch_sanctions_search(fetcher, country="iran")
    assert result["count"] == 1
    assert result["matches"][0]["name"] == "DOE, John"


# ---------------------------------------------------------------------------
# Elections (pure data — no HTTP mocking needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_election_calendar(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.elections import fetch_election_calendar

    result = await fetch_election_calendar(fetcher)
    assert result["source"] == "election-calendar"
    assert result["count"] > 0
    assert "elections" in result

    # Each election should have risk_score
    for election in result["elections"]:
        assert "risk_score" in election
        assert "days_until" in election
        assert election["status"] in ("past", "upcoming")


@pytest.mark.asyncio
async def test_fetch_election_calendar_country_filter(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.elections import fetch_election_calendar

    result = await fetch_election_calendar(fetcher, country="USA")
    # May or may not match depending on config data
    assert result["source"] == "election-calendar"
    assert isinstance(result["elections"], list)


# ---------------------------------------------------------------------------
# Shipping (Yahoo Finance quotes)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_shipping_index(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.shipping import fetch_shipping_index

    chart_response = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "BDRY",
                        "regularMarketPrice": 15.50,
                        "regularMarketChangePercent": 4.2,
                        "currency": "USD",
                    }
                }
            ]
        }
    }

    # Mock all 4 shipping symbols
    respx.get(url__regex=r".*finance\.yahoo\.com.*").mock(
        return_value=httpx.Response(200, json=chart_response)
    )

    result = await fetch_shipping_index(fetcher)
    assert result["source"] == "yahoo-finance"
    assert len(result["quotes"]) > 0
    assert isinstance(result["stress_score"], (int, float))
    assert result["assessment"] in ("low", "moderate", "elevated", "high", "extreme")


# ---------------------------------------------------------------------------
# Social (Reddit)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_social_signals(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.social import fetch_social_signals

    reddit_response = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "Ukraine conflict escalation analysis",
                        "score": 5000,
                        "num_comments": 300,
                        "upvote_ratio": 0.95,
                        "created_utc": 1708700000,
                        "permalink": "/r/worldnews/comments/abc123/",
                        "is_self": False,
                    }
                },
                {
                    "data": {
                        "title": "US-China trade tensions rise",
                        "score": 2000,
                        "num_comments": 150,
                        "upvote_ratio": 0.88,
                        "created_utc": 1708690000,
                        "permalink": "/r/worldnews/comments/def456/",
                        "is_self": True,
                    }
                },
            ]
        }
    }

    respx.get(url__regex=r".*reddit\.com.*hot\.json.*").mock(
        return_value=httpx.Response(200, json=reddit_response)
    )

    result = await fetch_social_signals(fetcher)
    assert result["source"] == "reddit-public"
    assert result["velocity_metrics"]["total_posts"] > 0
    assert result["velocity_metrics"]["high_engagement_count"] > 0
    assert result["subreddits_queried"] == ["worldnews", "geopolitics"]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_social_signals_blocked_is_error(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.social import fetch_social_signals

    respx.get(url__regex=r".*reddit\.com.*hot\.json.*").mock(
        return_value=httpx.Response(403, text="Blocked")
    )

    result = await fetch_social_signals(fetcher)
    assert "Reddit unavailable" in result["error"]
    assert result["subreddits_failed"] == ["worldnews", "geopolitics"]
    assert "velocity_metrics" not in result


# ---------------------------------------------------------------------------
# Nuclear (USGS near test sites)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_nuclear_monitor(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.nuclear import fetch_nuclear_monitor

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "nn00900001",
                "properties": {
                    "mag": 2.8,
                    "place": "50km N of Test Site",
                    "time": 1708700000000,
                    "tsunami": 0,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [129.08, 41.30, 3.0],  # Near Punggye-ri
                },
            }
        ],
    }

    # Mock USGS for all nuclear sites
    respx.get("https://earthquake.usgs.gov/fdsnws/event/1/query").mock(
        return_value=httpx.Response(200, json=geojson)
    )

    result = await fetch_nuclear_monitor(fetcher, hours=72)
    assert result["source"] == "usgs-nuclear-monitor"
    assert len(result["sites"]) == 5  # 5 nuclear test sites
    assert isinstance(result["total_flagged_events"], int)
    assert isinstance(result["critical_flags"], int)


# ---------------------------------------------------------------------------
# Infrastructure (Cloudflare + IODA fallback)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_internet_outages_ioda_fallback(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.infrastructure import fetch_internet_outages

    # IODA /v2/outages/events?format=ioda response shape (trimmed live)
    now = int(time.time())
    ioda_response = {
        "type": "outages.events",
        "error": None,
        "data": [
            # IODA lists events oldest first; the source must return newest first.
            {
                "entity": {"code": "NF", "name": "Norfolk Island", "type": "country"},
                "from": now - 200000,
                "until": now - 100000,
                "score": 25950.3,
                "datasource": "gtr",
            },
            {
                "entity": {"code": "GI", "name": "Gibraltar", "type": "country"},
                "from": now - 86400,
                "until": now,
                "score": 19687.8,
                "datasource": "bgp",
            },
        ],
    }

    # Cloudflare returns 403 (no token)
    respx.get(url__regex=r".*cloudflare\.com.*").mock(
        return_value=httpx.Response(403, json={"error": "unauthorized"})
    )
    # IODA responds
    respx.get(url__regex=r".*ioda\.inetintel.*").mock(
        return_value=httpx.Response(200, json=ioda_response)
    )

    import os

    os.environ.pop("CLOUDFLARE_API_TOKEN", None)

    result = await fetch_internet_outages(fetcher)
    assert result["source"] == "ioda-gatech"
    assert result["total_7d"] == 2
    assert result["ongoing_count"] == 1
    assert result["outages"][0]["countries"] == ["GI"]
    assert result["outages"][0]["end"] is None
    assert isinstance(result["outages"][1]["end"], str)


@respx.mock
@pytest.mark.asyncio
async def test_fetch_internet_outages_ioda_error(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.infrastructure import fetch_internet_outages

    respx.get(url__regex=r".*ioda\.inetintel.*").mock(return_value=httpx.Response(500))
    import os

    os.environ.pop("CLOUDFLARE_API_TOKEN", None)

    result = await fetch_internet_outages(fetcher)
    assert result["degraded"] is True
    assert result["outages"] == []
    assert "error" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_cable_health(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.infrastructure import fetch_cable_health

    warnings = [
        {
            "msgYear": 2026,
            "msgNumber": 42,
            "navArea": "XII",
            "subregion": "31",
            "status": "in force",
            "issueDate": "2026-02-20",
            "text": "SUBMARINE CABLE OPERATIONS 40-30.5N/030-15.2E VESSELS ADVISED",
        }
    ]

    respx.get(url__regex=r".*nga\.mil.*broadcast-warn.*").mock(
        return_value=httpx.Response(200, json=warnings)
    )

    result = await fetch_cable_health(fetcher)
    assert result["source"] == "nga-msi"
    assert "corridors" in result
    assert len(result["corridors"]) == 6
    assert result["cable_related_warnings"] >= 1  # "cable" keyword in text


# ---------------------------------------------------------------------------
# Conflict (UCDP + ACLED)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_ucdp_events(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.conflict import fetch_ucdp_events
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ucdp_response = {
        "TotalPages": 1,
        "Result": [
            {
                "id": 12345,
                "relid": "11-1",
                "year": 2026,
                "date_start": today,
                "date_end": today,
                "country": "Ukraine",
                "region": "Europe",
                "type_of_violence": 1,
                "side_a": "Government of Ukraine",
                "side_b": "DPR",
                "best": 5,
                "high": 10,
                "low": 2,
                "latitude": 48.0,
                "longitude": 37.5,
                "source_article": "Reuters",
                "source_headline": "Fighting continues",
            }
        ],
    }

    respx.get(url__regex=r".*ucdpapi\.pcr\.uu\.se.*").mock(
        return_value=httpx.Response(200, json=ucdp_response)
    )

    result = await fetch_ucdp_events(fetcher, days=30)
    assert result["source"] == "ucdp"
    assert result["count"] == 1
    assert result["events"][0]["country"] == "Ukraine"
    assert result["total_fatalities_best"] == 5


@pytest.mark.asyncio
async def test_fetch_acled_events_distinguishes_fetch_failure_from_zero_events(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #3: a post-auth ACLED fetch failure (rate limit, 500,
    malformed payload) must not be byte-identical to a genuine zero-match
    result. Repro per the issue: patch the OAuth token to succeed and
    get_json to return None (the post-auth failure path)."""
    from world_intel_mcp.sources import conflict

    async def _fake_token() -> str:
        return "fake-token"

    async def _fake_get_json(*args, **kwargs):
        return None

    monkeypatch.setattr(conflict, "_acled_get_token", _fake_token)
    monkeypatch.setattr(fetcher, "get_json", _fake_get_json)

    result = await conflict.fetch_acled_events(fetcher, country="Sudan", days=7)

    assert result.get("error") is not None
    assert result.get("degraded") is True
    assert result.get("reason") == "acled_fetch_failed"
    # Additive-only: events/count keep their normal shape (empty list / 0,
    # not None) so existing callers that don't check "error" or "degraded"
    # still iterate an empty list instead of crashing.
    assert result["events"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_fetch_acled_events_genuine_zero_has_no_error(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real zero-match query (fetch succeeds, API returns no data) must
    NOT be flagged as degraded — only actual fetch failures are."""
    from world_intel_mcp.sources import conflict

    async def _fake_token() -> str:
        return "fake-token"

    async def _fake_get_json(*args, **kwargs):
        return {"data": []}

    monkeypatch.setattr(conflict, "_acled_get_token", _fake_token)
    monkeypatch.setattr(fetcher, "get_json", _fake_get_json)

    result = await conflict.fetch_acled_events(fetcher, country="Iceland", days=7)

    assert result.get("error") is None
    assert result.get("degraded") is None
    assert result["events"] == []
    assert result["count"] == 0


def _acled_pool_route(pool_size: int):
    """A respx side effect for the ACLED read endpoint that, like the real
    API, returns at most `limit` rows from a pool, and records each limit."""
    sent: list[int] = []

    def _answer(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        sent.append(limit)
        rows = [
            {
                "event_id_cnty": f"SDN{i}",
                "event_date": "2026-10-01",
                "event_type": "Battles",
                "country": "Sudan",
                "latitude": str(10.0 + i),
                "longitude": str(30.0 + i),
                "fatalities": "1",
            }
            for i in range(min(limit, pool_size))
        ]
        return httpx.Response(200, json={"data": rows})

    return _answer, sent


@pytest.mark.asyncio
async def test_acled_events_cache_does_not_answer_a_larger_limit(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short list cached for a small limit must not come back, inside the
    cache TTL, for a call that asked for more rows: a count below the limit
    would then read as a complete list."""
    from world_intel_mcp.sources import conflict

    async def _fake_token() -> str:
        return "fake-token"

    monkeypatch.setattr(conflict, "_acled_get_token", _fake_token)
    answer, sent = _acled_pool_route(5)
    with respx.mock(assert_all_called=False) as router:
        router.get(conflict._ACLED_API_URL).mock(side_effect=answer)
        small = await conflict.fetch_acled_events(
            fetcher, country="Sudan", days=60, limit=2
        )
        large = await conflict.fetch_acled_events(
            fetcher, country="Sudan", days=60, limit=1000
        )

    assert small["count"] == 2
    assert large["count"] == 5
    assert sent == [2, 1000]


@pytest.mark.asyncio
async def test_unrest_events_cache_does_not_answer_a_larger_limit(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    from world_intel_mcp.sources import conflict, intelligence

    async def _fake_token() -> str:
        return "fake-token"

    monkeypatch.setattr(conflict, "_acled_get_token", _fake_token)
    answer, sent = _acled_pool_route(5)
    with respx.mock(assert_all_called=False) as router:
        router.get(conflict._ACLED_API_URL).mock(side_effect=answer)
        small = await intelligence.fetch_unrest_events(
            fetcher, country="Sudan", days=60, limit=2
        )
        large = await intelligence.fetch_unrest_events(
            fetcher, country="Sudan", days=60, limit=1000
        )

    assert small["count"] + small["deduplicated"] == 2
    assert large["count"] + large["deduplicated"] == 5
    assert sent == [2, 1000]


@pytest.fixture
def acled_signed_out(monkeypatch: pytest.MonkeyPatch):
    """No cached ACLED token, so every call goes through sign-in."""
    from world_intel_mcp.sources import conflict

    monkeypatch.setattr(conflict, "_acled_token", None)
    monkeypatch.setattr(conflict, "_acled_token_expires", 0.0)
    monkeypatch.setattr(conflict, "_acled_refresh_token", None)
    return conflict


@pytest.mark.asyncio
async def test_acled_refused_sign_in_is_not_reported_as_unconfigured(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch, acled_signed_out
) -> None:
    """Both variables set, token request refused: the operator has to fix
    the account or wait out the sign-in outage, not set variables that are
    already set."""
    from world_intel_mcp.sources import intelligence

    conflict = acled_signed_out
    monkeypatch.setenv("ACLED_EMAIL", "analyst@example.org")
    monkeypatch.setenv("ACLED_PASSWORD", "offline-fake-value")
    with respx.mock(assert_all_called=False) as router:
        sign_in_route = router.post(conflict._ACLED_TOKEN_URL).mock(
            return_value=httpx.Response(401, json={"error": "invalid_grant"})
        )
        read = router.get(conflict._ACLED_API_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        events = await conflict.fetch_acled_events(fetcher, country="Sudan", days=7)
        risk = await intelligence.fetch_risk_scores(fetcher)
        unrest = await intelligence.fetch_unrest_events(fetcher, country="Sudan")

    assert sign_in_route.call_count >= 1
    assert read.call_count == 0
    assert events["reason"] == "acled_auth_failed"
    assert events["degraded"] is True
    assert events["error"].startswith("ACLED sign-in failed")
    for result in (events, risk, unrest):
        assert "not configured" not in result["error"]
        assert "sign-in failed" in result["error"]
        assert result["degraded"] is True


@pytest.mark.asyncio
async def test_acled_unset_variables_are_still_reported_as_unconfigured(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch, acled_signed_out
) -> None:
    conflict = acled_signed_out
    monkeypatch.delenv("ACLED_EMAIL", raising=False)
    monkeypatch.delenv("ACLED_PASSWORD", raising=False)
    with respx.mock(assert_all_called=False) as router:
        sign_in_route = router.post(conflict._ACLED_TOKEN_URL).mock(
            return_value=httpx.Response(401)
        )
        result = await conflict.fetch_acled_events(fetcher, country="Sudan", days=7)

    assert sign_in_route.call_count == 0
    assert result["reason"] == "acled_unconfigured"
    assert "ACLED credentials not configured" in result["error"]


# ---------------------------------------------------------------------------
# News (GDELT search)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_gdelt_search_distinguishes_rate_limit_from_zero_hits(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #17: GDELT rate-limits at roughly one request per 5 seconds.
    A 429 that exhausts every retry must not be byte-identical to a
    genuine zero-hit search: same class as the ACLED defect fixed in #3.
    Exercises the real Fetcher retry path via respx (not a monkeypatched
    get_json) so the failure mode actually hit live (429) is what's under
    test. The exponential backoff sleep is stubbed to keep the test fast;
    that doesn't change what's exercised, only how long waiting for it
    takes."""
    import asyncio as asyncio_mod

    from world_intel_mcp.sources.news import fetch_gdelt_search

    async def _no_sleep(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(asyncio_mod, "sleep", _no_sleep)

    respx.get(url__regex=r".*api\.gdeltproject\.org.*").mock(
        return_value=httpx.Response(429, text="rate limited")
    )

    result = await fetch_gdelt_search(
        fetcher, query="Pittsburgh", mode="artlist", limit=10
    )

    assert result.get("error") is not None
    assert result.get("degraded") is True
    assert result.get("reason") == "gdelt_fetch_failed"
    # Additive-only: articles/count keep their normal shape (empty list / 0,
    # not None) so existing callers that don't check "error" or "degraded"
    # still iterate an empty list instead of crashing.
    assert result["articles"] == []
    assert result["count"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_fetch_gdelt_search_genuine_zero_has_no_error(fetcher: Fetcher) -> None:
    """A real zero-hit query (fetch succeeds, GDELT returns no articles)
    must NOT be flagged as degraded: only actual fetch failures are."""
    from world_intel_mcp.sources.news import fetch_gdelt_search

    respx.get(url__regex=r".*api\.gdeltproject\.org.*").mock(
        return_value=httpx.Response(200, json={"articles": []})
    )

    result = await fetch_gdelt_search(
        fetcher, query="zzzznohitszzzz", mode="artlist", limit=10
    )

    assert result.get("error") is None
    assert result.get("degraded") is None
    assert result["articles"] == []
    assert result["count"] == 0


# ---------------------------------------------------------------------------
# Hacker News
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_hacker_news(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.hacker_news import fetch_hacker_news

    respx.get("https://hacker-news.firebaseio.com/v0/topstories.json").mock(
        return_value=httpx.Response(200, json=[101, 102])
    )
    respx.get("https://hacker-news.firebaseio.com/v0/item/101.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 101,
                "title": "Show HN: AI Tool",
                "url": "https://example.com",
                "score": 200,
                "by": "user1",
                "time": 1700000000,
                "descendants": 50,
            },
        )
    )
    respx.get("https://hacker-news.firebaseio.com/v0/item/102.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 102,
                "title": "Rust 2.0",
                "url": "https://example.com/rust",
                "score": 150,
                "by": "user2",
                "time": 1700001000,
                "descendants": 30,
            },
        )
    )

    result = await fetch_hacker_news(fetcher, limit=2)
    assert result["source"] == "hackernews"
    assert result["count"] == 2
    assert result["stories"][0]["score"] >= result["stories"][1]["score"]


# ---------------------------------------------------------------------------
# GitHub Trending
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_trending_repos(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.github_trending import fetch_trending_repos

    respx.get(url__regex=r".*api\.github\.com/search/repositories.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 1,
                "items": [
                    {
                        "full_name": "user/cool-repo",
                        "description": "A cool tool",
                        "html_url": "https://github.com/user/cool-repo",
                        "stargazers_count": 500,
                        "forks_count": 20,
                        "language": "Python",
                        "created_at": "2026-02-20T00:00:00Z",
                        "topics": ["ai", "ml"],
                    }
                ],
            },
        )
    )

    result = await fetch_trending_repos(fetcher, limit=5)
    assert result["source"] == "github"
    assert result["count"] == 1
    assert result["repos"][0]["name"] == "user/cool-repo"
    assert result["repos"][0]["stars"] == 500


# ---------------------------------------------------------------------------
# arXiv Papers
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_arxiv_papers(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.arxiv_papers import fetch_arxiv_papers

    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2602.12345v1</id>
        <title>Attention Is Still All You Need</title>
        <summary>We show transformers continue to dominate.</summary>
        <author><name>Jane Doe</name></author>
        <author><name>John Smith</name></author>
        <published>2026-02-20T00:00:00Z</published>
        <link href="http://arxiv.org/abs/2602.12345v1" rel="alternate"/>
        <link href="http://arxiv.org/pdf/2602.12345v1" title="pdf" rel="related"/>
        <category term="cs.AI"/>
        <category term="cs.LG"/>
      </entry>
    </feed>"""

    respx.get(url__regex=r".*export\.arxiv\.org/api/query.*").mock(
        return_value=httpx.Response(200, text=arxiv_xml)
    )

    result = await fetch_arxiv_papers(fetcher, limit=5)
    assert result["source"] == "arxiv"
    assert result["count"] == 1
    assert "Attention" in result["papers"][0]["title"]
    assert len(result["papers"][0]["authors"]) == 2


_ARXIV_ONE_ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2610.00001v1</id><title>One paper</title>
<summary>s</summary><published>2026-10-16T00:00:00Z</published>
</entry></feed>"""


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_tool_without_query_searches_the_default(fetcher: Fetcher, monkeypatch) -> None:
    """The schema and the guide present query as optional; the handler
    used to pass None into the source, which raised before any request."""
    from types import SimpleNamespace

    from world_intel_mcp.sources import arxiv_papers
    from world_intel_mcp.tools import society

    default = "cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
    route = respx.get(url__regex=r".*export\.arxiv\.org/api/query.*").mock(
        return_value=httpx.Response(200, text=_ARXIV_ONE_ENTRY)
    )
    monkeypatch.setattr(society, "runtime", SimpleNamespace(fetcher=fetcher))
    result = await society.HANDLERS["intel_arxiv_papers"]({})

    assert result["count"] == 1
    assert result["query"] == default == getattr(arxiv_papers, "DEFAULT_QUERY", default)
    assert route.call_count == 1
    assert dict(route.calls[0].request.url.params) == {
        "search_query": default,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": "25",
    }


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_first_request_carries_the_search(fetcher: Fetcher) -> None:
    """A bare request to the API URL searches for nothing; the query must
    be in the first request, not only in a fallback."""
    from world_intel_mcp.sources.arxiv_papers import fetch_arxiv_papers

    route = respx.get(url__regex=r".*export\.arxiv\.org/api/query.*").mock(
        return_value=httpx.Response(200, text=_ARXIV_ONE_ENTRY)
    )
    result = await fetch_arxiv_papers(fetcher, query="cat:cs.CV", limit=3)

    assert result["count"] == 1
    assert [dict(c.request.url.params).get("search_query") for c in route.calls] == ["cat:cs.CV"]
    assert dict(route.calls[0].request.url.params)["max_results"] == "3"


# ---------------------------------------------------------------------------
# USA Spending
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usa_spending(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usa_spending import fetch_usa_spending

    respx.get(url__regex=r".*api\.usaspending\.gov.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "agency_name": "Department of Defense",
                        "abbreviation": "DOD",
                        "current_total_budget_authority_amount": 850000000000,
                        "obligated_amount": 700000000000,
                        "outlay_amount": 650000000000,
                        "agency_id": 97,
                    }
                ],
                "page_metadata": {"total": 1},
            },
        )
    )

    result = await fetch_usa_spending(fetcher, limit=5)
    assert result["source"] == "usaspending"
    assert result["count"] == 1
    assert result["agencies"][0]["name"] == "Department of Defense"


# ---------------------------------------------------------------------------
# Environmental Events (NASA EONET)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_environmental_events(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.environmental import fetch_environmental_events

    respx.get(url__regex=r".*eonet\.gsfc\.nasa\.gov.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "events": [
                    {
                        "id": "EONET_1234",
                        "title": "Wildfire in California",
                        "categories": [{"id": "wildfires", "title": "Wildfires"}],
                        "sources": [
                            {"id": "InciWeb", "url": "https://inciweb.example.com"}
                        ],
                        "geometry": [
                            {
                                "date": "2026-02-20T00:00:00Z",
                                "coordinates": [-119.5, 34.5],
                            }
                        ],
                    }
                ],
            },
        )
    )

    result = await fetch_environmental_events(fetcher, days=7)
    assert result["source"] == "eonet"
    assert result["count"] == 1
    assert "Wildfire" in result["events"][0]["title"]


# ---------------------------------------------------------------------------
# Disaster Alerts (GDACS)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_disaster_alerts(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.environmental import fetch_disaster_alerts

    gdacs_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "eventtype": "EQ",
                    "eventname": "M6.5 Earthquake",
                    "alertlevel": "orange",
                    "alertscore": 2.5,
                    "severity": {"value": 6.5, "unit": "M"},
                    "country": "Turkey",
                    "fromdate": "2026-02-20T12:00:00Z",
                    "todate": "2026-02-20T12:05:00Z",
                    "url": {"report": "https://gdacs.example.com/report"},
                    "population": {"value": 500000},
                },
                "geometry": {"type": "Point", "coordinates": [29.0, 38.5]},
            }
        ],
    }

    respx.get(url__regex=r".*gdacs\.org.*").mock(
        return_value=httpx.Response(200, json=gdacs_geojson)
    )

    result = await fetch_disaster_alerts(fetcher)
    assert result["source"] == "gdacs"
    assert result["count"] == 1
    assert result["alerts"][0]["event_type"] == "EQ"
    assert result["alerts"][0]["alert_level"] == "orange"


# ---------------------------------------------------------------------------
# Geospatial — Extended datasets (static, no HTTP mock needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_undersea_cables() -> None:
    from world_intel_mcp.sources.geospatial import fetch_undersea_cables

    result = await fetch_undersea_cables()
    assert result["count"] > 0
    assert result["source"] == "static-geospatial"
    assert "total_length_km" in result
    assert "total_capacity_tbps" in result


@pytest.mark.asyncio
async def test_fetch_ai_datacenters() -> None:
    from world_intel_mcp.sources.geospatial import fetch_ai_datacenters

    result = await fetch_ai_datacenters(country="USA")
    assert result["count"] > 0
    assert result["source"] == "static-geospatial"
    assert "total_power_mw" in result


@pytest.mark.asyncio
async def test_fetch_spaceports() -> None:
    from world_intel_mcp.sources.geospatial import fetch_spaceports

    result = await fetch_spaceports()
    assert result["count"] > 0
    assert result["source"] == "static-geospatial"


@pytest.mark.asyncio
async def test_fetch_critical_minerals() -> None:
    from world_intel_mcp.sources.geospatial import fetch_critical_minerals

    result = await fetch_critical_minerals(mineral="lithium")
    assert result["count"] > 0
    assert all(d["mineral"] == "lithium" for d in result["deposits"])


@pytest.mark.asyncio
async def test_fetch_stock_exchanges() -> None:
    from world_intel_mcp.sources.geospatial import fetch_stock_exchanges

    result = await fetch_stock_exchanges(tier="mega")
    assert result["count"] > 0
    assert all(e["tier"] == "mega" for e in result["exchanges"])
    assert "total_market_cap_usd_t" in result


# ---------------------------------------------------------------------------
# Country Stocks
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_country_stocks(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.markets import fetch_country_stocks

    chart_response = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "^GSPC",
                        "regularMarketPrice": 5200.0,
                        "regularMarketChangePercent": 0.75,
                        "currency": "USD",
                    }
                }
            ]
        }
    }

    respx.get(url__regex=r".*query1\.finance\.yahoo\.com.*").mock(
        return_value=httpx.Response(200, json=chart_response)
    )

    result = await fetch_country_stocks(fetcher, country="USA")
    assert result["source"] == "yahoo-finance"
    assert result["country"] == "USA"
    assert "quote" in result


# ---------------------------------------------------------------------------
# Aircraft Batch
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_aircraft_details_batch(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.military import fetch_aircraft_details_batch

    respx.get(url__regex=r".*hexdb\.io/api/v1/aircraft/ae1234.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "Registration": "12-3456",
                "Type": "C-17A",
                "Operator": "USAF",
            },
        )
    )
    respx.get(url__regex=r".*hexdb\.io/api/v1/aircraft/ae5678.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "Registration": "78-9012",
                "Type": "KC-135R",
                "Operator": "USAF",
            },
        )
    )

    result = await fetch_aircraft_details_batch(
        fetcher, icao24_list=["ae1234", "ae5678"]
    )
    assert result["source"] == "hexdb"
    assert result["count"] == 2
    assert result["requested"] == 2


# ---------------------------------------------------------------------------
# BTC Technicals (CoinGecko)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_btc_technicals(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.markets import fetch_btc_technicals

    # Generate 201 daily price points (enough for SMA-200)
    prices = [[1700000000 + i * 86400, 90000 + i * 10] for i in range(201)]

    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart").mock(
        return_value=httpx.Response(200, json={"prices": prices})
    )

    result = await fetch_btc_technicals(fetcher)
    assert result["source"] == "coingecko"
    assert result["price"] == prices[-1][1]
    assert result["sma_50"] > 0
    assert result["sma_200"] > 0
    assert result["mayer_multiple"] > 0
    assert result["cross_signal"] in ("golden_cross", "death_cross", "neutral")
    assert result["ath_distance_pct"] <= 0  # Current price <= ATH
    assert result["data_points"] == 201


@respx.mock
@pytest.mark.asyncio
async def test_fetch_btc_technicals_insufficient_data(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.markets import fetch_btc_technicals

    # Only 10 data points — not enough for SMA-50
    prices = [[1700000000 + i * 86400, 90000 + i * 10] for i in range(10)]

    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart").mock(
        return_value=httpx.Response(200, json={"prices": prices})
    )

    result = await fetch_btc_technicals(fetcher)
    assert "error" in result
    assert result["source"] == "coingecko"


# ---------------------------------------------------------------------------
# Central Bank Rates
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_central_bank_rates_no_fred(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.central_banks import fetch_central_bank_rates

    import os

    os.environ.pop("FRED_API_KEY", None)

    result = await fetch_central_bank_rates(fetcher)
    assert result["source"] == "multi"
    assert result["fred_available"] is False
    # Should have all 15 banks (12 curated + 3 FRED-fallback curated)
    assert result["count"] == 15
    # Sorted by rate descending — CBRT (45%) should be first
    assert result["rates"][0]["bank"] == "Central Bank of Turkey"
    assert result["rates"][0]["rate"] == 45.00
    # All should be curated source
    assert all(r["source"] == "curated" for r in result["rates"])


@respx.mock
@pytest.mark.asyncio
async def test_fetch_central_bank_rates_with_fred(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.central_banks import fetch_central_bank_rates

    import os

    os.environ["FRED_API_KEY"] = "test_key_123"

    fred_response = {"observations": [{"date": "2026-02-25", "value": "4.33"}]}

    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(200, json=fred_response)
    )

    try:
        result = await fetch_central_bank_rates(fetcher)
        assert result["source"] == "multi"
        assert result["fred_available"] is True
        assert result["count"] == 15
        # At least some should be from FRED
        fred_sources = [r for r in result["rates"] if r["source"] == "fred"]
        assert len(fred_sources) >= 1
    finally:
        os.environ.pop("FRED_API_KEY", None)


# ---------------------------------------------------------------------------
# Space Weather
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_space_weather_current_kp_dict_payload(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.space_weather import (
        _ALERTS_URL,
        _FLARE_URL,
        _KP_URL,
        fetch_space_weather,
    )

    respx.get(_KP_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "time_tag": "2026-06-04T03:00:00",
                    "Kp": 4.67,
                    "a_running": 17,
                    "station_count": 8,
                },
                {
                    "time_tag": "2026-06-04T06:00:00",
                    "Kp": 5.0,
                    "a_running": 20,
                    "station_count": 8,
                },
            ],
        )
    )
    respx.get(_FLARE_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"time_tag": "2026-06-04T06:00:00Z", "flux": 1.2e-5}],
        )
    )
    respx.get(_ALERTS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "issue_datetime": "2026-06-04T06:10:00Z",
                    "message": "Geomagnetic storm conditions observed",
                    "product_id": "WATA50",
                }
            ],
        )
    )

    result = await fetch_space_weather(fetcher)

    assert result["source"] == "noaa-swpc"
    assert result["current_kp"] == 5.0
    assert result["kp_level"] == "G1 Minor"
    assert result["kp_recent"][-1] == {
        "time": "2026-06-04T06:00:00",
        "kp": 5.0,
    }
    assert result["latest_flare_class"] == "M1.2"
    assert result["alerts"][0]["product_id"] == "WATA50"


# ---------------------------------------------------------------------------
# USNI Fleet Tracker
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usni_fleet(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usni_fleet import fetch_usni_fleet

    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
    <channel>
        <title>USNI News Fleet Tracker</title>
        <item>
            <title>USNI News Fleet and Marine Tracker: Feb. 24, 2026</title>
            <link>https://news.usni.org/2026/02/24/fleet-tracker</link>
            <pubDate>Mon, 24 Feb 2026 14:00:00 GMT</pubDate>
            <description>
            298 ships (237 USS, 61 USNS). 100 deployed (67 USS, 33 USNS). 72 underway (55 deployed, 17 local).
            Carrier Strike Group 3 is currently conducting routine operations in the Western Pacific theater of operations, focused on maintaining freedom of navigation and regional security.
            In the Philippine Sea, USS Abraham Lincoln (CVN-72) is conducting routine flight operations with embarked Carrier Air Wing Nine as part of a scheduled deployment to the Western Pacific region.
            Meanwhile in the Mediterranean Sea near the coast of southern Europe, USS Spruance (DDG-111) is operating independently as part of standing NATO maritime forces conducting presence operations.
            In the Persian Gulf near the Strait of Hormuz, Expeditionary Strike Group 7 continues its deployment supporting maritime security operations in the region.
            USS Bataan (LHD-5) continues operations in the Red Sea supporting regional stability efforts and conducting routine training exercises with coalition partners.
            </description>
        </item>
    </channel>
    </rss>"""

    respx.get("https://news.usni.org/category/fleet-tracker/feed").mock(
        return_value=httpx.Response(200, text=rss_xml)
    )

    result = await fetch_usni_fleet(fetcher)
    assert result["source"] == "usni-fleet-tracker"
    assert result["ship_count"] >= 3  # CVN-72, DDG-111, LHD-5
    assert result["report_title"] == "USNI News Fleet and Marine Tracker: Feb. 24, 2026"

    # Check ships were extracted
    hull_numbers = [s["hull_number"] for s in result["ships"]]
    assert "CVN-72" in hull_numbers
    assert "DDG-111" in hull_numbers
    assert "LHD-5" in hull_numbers

    # Check strike groups
    sg_names = [sg["name"] for sg in result["strike_groups"]]
    assert "CSG-3" in sg_names

    # Check force totals extracted
    assert result["force_totals"]["battle_force"]["total"] == 298
    assert result["force_totals"]["deployed"]["total"] == 100
    assert result["force_totals"]["underway"]["total"] == 72

    # Check region classification (±200 char context windows may overlap in short text,
    # but at least some ships should get classified to a known COCOM region)
    regions = set(s["region"] for s in result["ships"])
    assert len(regions - {"UNKNOWN"}) > 0  # At least one classified


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usni_fleet_empty_feed(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usni_fleet import fetch_usni_fleet

    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Empty</title></channel></rss>"""

    respx.get("https://news.usni.org/category/fleet-tracker/feed").mock(
        return_value=httpx.Response(200, text=rss_xml)
    )

    result = await fetch_usni_fleet(fetcher)
    assert result["source"] == "usni-fleet-tracker"
    assert "error" in result
    assert result["ship_count"] == 0


# ---------------------------------------------------------------------------
# Trade Routes (static — no HTTP mock needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_trade_routes() -> None:
    from world_intel_mcp.sources.geospatial import fetch_trade_routes

    result = await fetch_trade_routes()
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert result["total_oil_flow_mbd"] > 0
    assert "by_type" in result
    assert "chokepoint" in result["by_type"]


@pytest.mark.asyncio
async def test_fetch_trade_routes_filter_type() -> None:
    from world_intel_mcp.sources.geospatial import fetch_trade_routes

    result = await fetch_trade_routes(route_type="canal")
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert all(r["type"] == "canal" for r in result["routes"])


@pytest.mark.asyncio
async def test_fetch_trade_routes_filter_country() -> None:
    from world_intel_mcp.sources.geospatial import fetch_trade_routes

    result = await fetch_trade_routes(country="EGY")
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert all("EGY" in r["countries"] for r in result["routes"])


# ---------------------------------------------------------------------------
# Cloud Regions (static — no HTTP mock needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_cloud_regions() -> None:
    from world_intel_mcp.sources.geospatial import fetch_cloud_regions

    result = await fetch_cloud_regions()
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert "by_provider" in result
    assert "AWS" in result["by_provider"]


@pytest.mark.asyncio
async def test_fetch_cloud_regions_filter_provider() -> None:
    from world_intel_mcp.sources.geospatial import fetch_cloud_regions

    result = await fetch_cloud_regions(provider="GCP")
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert all(r["provider"] == "GCP" for r in result["regions"])


# ---------------------------------------------------------------------------
# Financial Centers (static — no HTTP mock needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_financial_centers() -> None:
    from world_intel_mcp.sources.geospatial import fetch_financial_centers

    result = await fetch_financial_centers()
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert "by_country" in result


@pytest.mark.asyncio
async def test_fetch_financial_centers_filter_rank() -> None:
    from world_intel_mcp.sources.geospatial import fetch_financial_centers

    result = await fetch_financial_centers(min_rank=5)
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert result["count"] <= 5
    assert all(fc["gfci_rank"] <= 5 for fc in result["centers"])


@pytest.mark.asyncio
async def test_fetch_financial_centers_filter_country() -> None:
    from world_intel_mcp.sources.geospatial import fetch_financial_centers

    result = await fetch_financial_centers(country="USA")
    assert result["source"] == "static-geospatial"
    assert result["count"] > 0
    assert all(fc["iso3"] == "USA" for fc in result["centers"])


# ---------------------------------------------------------------------------
# Country Dossier (Phase 16)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_country_dossier(fetcher: Fetcher) -> None:
    """Dossier aggregates country brief, stocks, elections, sanctions, news."""
    from world_intel_mcp.analysis.dossier import fetch_country_dossier

    # Mock World Bank GDP
    respx.get("https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"page": 1},
                [{"date": "2024", "value": 28000000000000}],
            ],
        )
    )
    # Mock World Bank inflation
    respx.get("https://api.worldbank.org/v2/country/US/indicator/FP.CPI.TOTL.ZG").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"page": 1},
                [{"date": "2024", "value": 3.2}],
            ],
        )
    )
    # Mock ACLED (no key = skip)
    # Mock Yahoo Finance for country stocks
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC").mock(
        return_value=httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 5800,
                                "chartPreviousClose": 5750,
                                "currency": "USD",
                                "exchangeName": "SNP",
                            }
                        }
                    ]
                },
            },
        )
    )
    # Mock OFAC sanctions
    respx.get(
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML"
    ).mock(return_value=httpx.Response(200, text="<sdnList></sdnList>"))
    # Mock news feeds — just one category needed
    respx.route().mock(
        return_value=httpx.Response(
            200,
            text="""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><title>US Economy Grows</title><link>https://example.com/1</link></item>
    <item><title>China Trade</title><link>https://example.com/2</link></item>
    </channel></rss>""",
        )
    )

    result = await fetch_country_dossier(fetcher, country="US")

    assert result["source"] == "country-dossier"
    assert result["overview"]["iso2"] == "US"
    assert result["overview"]["iso3"] == "USA"
    assert "economy" in result
    assert "markets" in result
    assert "elections" in result
    assert "sanctions" in result
    assert "news" in result
    assert "security" in result
    assert len(result["sections"]) == 7


@pytest.mark.asyncio
async def test_fetch_country_dossier_invalid_code(fetcher: Fetcher) -> None:
    """Dossier returns error for unknown country code."""
    from world_intel_mcp.analysis.dossier import fetch_country_dossier

    result = await fetch_country_dossier(fetcher, country="XX")
    assert "error" in result
    assert "Unknown" in result["error"]


# ---------------------------------------------------------------------------
# Traffic (Phase 16)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_traffic_flow_no_key(fetcher: Fetcher) -> None:
    """Traffic flow returns error when TOMTOM_API_KEY is not set."""
    from world_intel_mcp.sources.traffic import fetch_traffic_flow

    with patch.dict("os.environ", {}, clear=True):
        result = await fetch_traffic_flow(fetcher)

    assert "error" in result
    assert "TOMTOM_API_KEY" in result["error"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_traffic_flow_with_key(fetcher: Fetcher) -> None:
    """Traffic flow fetches congestion data from TomTom."""
    from world_intel_mcp.sources.traffic import fetch_traffic_flow

    respx.route().mock(
        return_value=httpx.Response(
            200,
            json={
                "flowSegmentData": {
                    "currentSpeed": 30.0,
                    "freeFlowSpeed": 60.0,
                },
            },
        )
    )

    with patch.dict("os.environ", {"TOMTOM_API_KEY": "test-key"}):
        result = await fetch_traffic_flow(fetcher)

    assert result["source"] == "tomtom"
    assert result["count"] > 0
    assert result["global_avg_congestion"] == 50.0  # (1 - 30/60) * 100
    assert result["cities"][0]["congestion_pct"] == 50


@pytest.mark.asyncio
@respx.mock
async def test_fetch_traffic_incidents_no_key(fetcher: Fetcher) -> None:
    """Traffic incidents returns error when no API key."""
    from world_intel_mcp.sources.traffic import fetch_traffic_incidents

    with patch.dict("os.environ", {}, clear=True):
        result = await fetch_traffic_incidents(fetcher)

    assert "error" in result


# ---------------------------------------------------------------------------
# Aviation Domestic (Phase 16)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_domestic_flights(fetcher: Fetcher) -> None:
    """Domestic flights buckets OpenSky states by region."""
    from world_intel_mcp.sources.aviation import fetch_domestic_flights

    # Simulate 3 airborne aircraft at known positions
    respx.route().mock(
        return_value=httpx.Response(
            200,
            json={
                "states": [
                    # [icao24, callsign, origin, ..., on_ground=False, lon, lat, ...]
                    [
                        "abc123",
                        "UAL123 ",
                        "United States",
                        None,
                        None,
                        -73.9,
                        40.7,
                        10000,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                    [
                        "def456",
                        "BAW789 ",
                        "United Kingdom",
                        None,
                        None,
                        -0.1,
                        51.5,
                        11000,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                    [
                        "ghi789",
                        "CCA100 ",
                        "China",
                        None,
                        None,
                        116.4,
                        39.9,
                        12000,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ],
                ],
            },
        )
    )

    result = await fetch_domestic_flights(fetcher)

    assert result["source"] == "opensky-domestic"
    assert result["total_aircraft"] == 3
    assert len(result["by_region"]) > 0
    assert len(result["busiest_origins"]) > 0


# ---------------------------------------------------------------------------
# Webcams (Phase 16)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_webcams_no_key(fetcher: Fetcher) -> None:
    """Webcams returns error when WINDY_API_KEY is not set."""
    from world_intel_mcp.sources.webcams import fetch_webcams

    with patch.dict("os.environ", {}, clear=True):
        result = await fetch_webcams(fetcher)

    assert "error" in result
    assert "WINDY_API_KEY" in result["error"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_webcams_with_key(fetcher: Fetcher) -> None:
    """Webcams fetches camera data from Windy API."""
    from world_intel_mcp.sources.webcams import fetch_webcams

    respx.route().mock(
        return_value=httpx.Response(
            200,
            json={
                "webcams": [
                    {
                        "webcamId": "cam-1",
                        "title": "Times Square",
                        "location": {
                            "latitude": 40.758,
                            "longitude": -73.985,
                            "city": "New York",
                            "country": "US",
                        },
                        "images": {
                            "current": {
                                "preview": "https://example.com/prev.jpg",
                                "thumbnail": "https://example.com/thumb.jpg",
                            }
                        },
                        "player": {"day": {"embed": "https://example.com/player"}},
                        "status": "active",
                    },
                ],
            },
        )
    )

    with patch.dict("os.environ", {"WINDY_API_KEY": "test-key"}):
        result = await fetch_webcams(fetcher, category="traffic", limit=10)

    assert result["source"] == "windy-webcams"
    assert result["count"] == 1
    assert result["cameras"][0]["title"] == "Times Square"
    assert result["cameras"][0]["lat"] == 40.758
