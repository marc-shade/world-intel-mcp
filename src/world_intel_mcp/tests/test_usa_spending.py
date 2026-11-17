"""Tests for USAspending source module — uses respx to mock HTTP calls."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher

_URL = "https://api.usaspending.gov/api/v2/references/toptier_agencies/"


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[Cache]:
    cache = Cache(db_path=tmp_path / "test_cache.db")
    try:
        yield cache
    finally:
        cache.close()


@pytest.fixture
async def fetcher(cache: Cache) -> AsyncIterator[Fetcher]:
    fetcher = Fetcher(cache=cache, breaker=CircuitBreaker(), default_timeout=5.0)
    try:
        yield fetcher
    finally:
        await fetcher.close()


_RESPONSE = {
    "results": [
        {
            "agency_id": 806,
            "toptier_code": "075",
            "abbreviation": "HHS",
            "agency_name": "Department of Health and Human Services",
            "obligated_amount": 2803832148217.51,
            "budget_authority_amount": 3709407922072.44,
            "percentage_of_total_budget_authority": 0.229,
        },
        {
            "agency_id": 1146,
            "abbreviation": "USAB",
            "agency_name": "Access Board",
            "obligated_amount": 8462766.63,
            "budget_authority_amount": 13636598.19,
            "percentage_of_total_budget_authority": 8.4e-07,
        },
    ]
}


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usa_spending(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usa_spending import fetch_usa_spending

    respx.get(_URL).mock(return_value=httpx.Response(200, json=_RESPONSE))

    result = await fetch_usa_spending(fetcher)
    assert result["source"] == "usaspending"
    assert result["count"] == 2
    assert result["agencies"][0]["abbreviation"] == "HHS"
    assert result["agencies"][0]["budget_authority"] == 3709407922072.44
    assert "error" not in result

    filtered = await fetch_usa_spending(fetcher, agency="access")
    assert [a["abbreviation"] for a in filtered["agencies"]] == ["USAB"]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usa_spending_empty(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usa_spending import fetch_usa_spending

    respx.get(_URL).mock(return_value=httpx.Response(200, json={"results": []}))

    result = await fetch_usa_spending(fetcher)
    assert result["agencies"] == []
    assert result["count"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usa_spending_error(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usa_spending import fetch_usa_spending

    respx.get(_URL).mock(return_value=httpx.Response(404))

    result = await fetch_usa_spending(fetcher)
    assert result["agencies"] == []
    assert result["degraded"] is True
    assert "error" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_usa_spending_cache_hit(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.usa_spending import fetch_usa_spending

    route = respx.get(_URL).mock(return_value=httpx.Response(200, json=_RESPONSE))

    await fetch_usa_spending(fetcher)
    await fetch_usa_spending(fetcher)
    assert route.call_count == 1
