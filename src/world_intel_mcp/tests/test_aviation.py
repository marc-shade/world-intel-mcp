"""Tests for aviation source module — uses respx to mock HTTP calls."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher

FAA_URL = "https://nasstatus.faa.gov/api/airport-status-information"

# Trimmed copy of the live FAA NAS Status response.
FAA_XML = (
    "<AIRPORT_STATUS_INFORMATION><Update_Time>Tue Nov 17 01:29:40 2026 GMT</Update_Time>"
    "<Delay_type><Name>Ground Stop Programs</Name><Ground_Stop_List><Program>"
    "<ARPT>LGA</ARPT><Reason>airport volume</Reason><End_Time>8:30 pm EST</End_Time>"
    "</Program></Ground_Stop_List></Delay_type>"
    "<Delay_type><Name>Ground Delay Programs</Name><Ground_Delay_List>"
    "<Ground_Delay><ARPT>SFO</ARPT><Reason>low ceilings</Reason>"
    "<Avg>1 hour and 38 minutes</Avg><Max>5 hours and 24 minutes</Max></Ground_Delay>"
    "<Ground_Delay><ARPT>LGA</ARPT><Reason>airport volume</Reason>"
    "<Avg>44 minutes</Avg><Max>2 hours and 3 minutes</Max></Ground_Delay>"
    "</Ground_Delay_List></Delay_type>"
    "<Delay_type><Name>Airport Closures</Name><Airport_Closure_List><Airport>"
    "<ARPT>SNA</ARPT><Reason>!SNA 11/020 SNA AD AP CLSD DLY 0730-1415</Reason>"
    "<Start>Nov 15 at 07:30 UTC.</Start><Reopen>Nov 21 at 14:15 UTC.</Reopen>"
    "</Airport></Airport_Closure_List></Delay_type>"
    "</AIRPORT_STATUS_INFORMATION>"
)
FAA_XML_EMPTY = (
    "<AIRPORT_STATUS_INFORMATION><Update_Time>x</Update_Time></AIRPORT_STATUS_INFORMATION>"
)


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


@respx.mock
@pytest.mark.asyncio
async def test_fetch_airport_delays(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.aviation import fetch_airport_delays

    respx.get(FAA_URL).mock(return_value=httpx.Response(200, text=FAA_XML))

    result = await fetch_airport_delays(fetcher)
    assert "error" not in result
    assert result["source"] == "faa"
    assert result["delayed_count"] == 2
    by_code = {d["code"]: d for d in result["delayed"]}
    assert set(by_code) == {"LGA", "SFO"}
    assert by_code["SFO"]["delay"] is True
    assert by_code["SFO"]["status"][0] == {
        "type": "Ground Delay Programs",
        "reason": "low ceilings",
        "avg_delay": "1 hour and 38 minutes",
        "closure_begin": "",
        "closure_end": "",
    }
    # LGA has a ground stop and a ground delay program: one entry, two statuses
    assert [s["type"] for s in by_code["LGA"]["status"]] == [
        "Ground Stop Programs",
        "Ground Delay Programs",
    ]
    assert by_code["LGA"]["status"][0]["avg_delay"] == "until 8:30 pm EST"
    # Closures are reported separately, not as delays
    assert [c["code"] for c in result["closures"]] == ["SNA"]
    assert result["closures"][0]["closure_end"] == "Nov 21 at 14:15 UTC."


@respx.mock
@pytest.mark.asyncio
async def test_fetch_airport_delays_empty(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.aviation import fetch_airport_delays

    respx.get(FAA_URL).mock(return_value=httpx.Response(200, text=FAA_XML_EMPTY))

    result = await fetch_airport_delays(fetcher)
    assert "error" not in result
    assert result["delayed"] == []
    assert result["delayed_count"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_fetch_airport_delays_api_failure(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.aviation import fetch_airport_delays

    respx.get(FAA_URL).mock(return_value=httpx.Response(500))

    result = await fetch_airport_delays(fetcher)
    assert "error" in result
    assert "delayed_count" not in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_airport_delays_invalid_xml(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.aviation import fetch_airport_delays

    respx.get(FAA_URL).mock(return_value=httpx.Response(200, text="<html>maintenance"))

    result = await fetch_airport_delays(fetcher)
    assert "error" in result
    assert "delayed_count" not in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_airport_delays_cache_hit(fetcher: Fetcher) -> None:
    from world_intel_mcp.sources.aviation import fetch_airport_delays

    route = respx.get(FAA_URL).mock(return_value=httpx.Response(200, text=FAA_XML))

    first = await fetch_airport_delays(fetcher)
    second = await fetch_airport_delays(fetcher)
    assert route.call_count == 1
    assert second["delayed"] == first["delayed"]
