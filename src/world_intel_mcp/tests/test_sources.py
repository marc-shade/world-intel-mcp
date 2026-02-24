"""Tests for source modules — uses respx to mock HTTP calls."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(db_path=tmp_path / "test_cache.db")


@pytest.fixture
def fetcher(cache: Cache) -> Fetcher:
    breaker = CircuitBreaker()
    return Fetcher(cache=cache, breaker=breaker, default_timeout=5.0)


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
            "result": [{
                "meta": {
                    "symbol": "^GSPC",
                    "regularMarketPrice": 5123.45,
                    "regularMarketChangePercent": 0.42,
                    "currency": "USD",
                }
            }]
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
            {"indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"}, "date": "2023", "value": 25000000000000},
            {"indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"}, "date": "2022", "value": 24000000000000},
        ],
    ]

    respx.get(url__regex=r".*api\.worldbank\.org.*").mock(
        return_value=httpx.Response(200, json=wb_response)
    )

    result = await fetch_world_bank_indicators(fetcher, country="USA", indicators=["NY.GDP.MKTP.CD"])
    assert "indicators" in result
    assert len(result["indicators"]) == 1
    assert result["indicators"][0]["id"] == "NY.GDP.MKTP.CD"
    assert result["source"] == "world-bank"


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
            "result": [{
                "meta": {
                    "symbol": "BDRY",
                    "regularMarketPrice": 15.50,
                    "regularMarketChangePercent": 4.2,
                    "currency": "USD",
                }
            }]
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

    # IODA response shape
    ioda_response = {
        "data": [
            {
                "entity": {"code": "US", "name": "United States"},
                "events": [
                    {
                        "id": "out-123",
                        "from": "2026-02-20T00:00:00Z",
                        "until": None,
                        "summary": "BGP outage detected",
                        "level": "country",
                    }
                ],
            }
        ]
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
    assert result["total_7d"] == 1
    assert result["ongoing_count"] == 1


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
