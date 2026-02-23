"""Military aviation tracking source for world-intel-mcp.

Provides real-time military aircraft tracking via OpenSky Network and
aircraft detail lookups via hexdb.io (free, no API key).
"""

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.military")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
_HEXDB_BASE_URL = "https://hexdb.io/api/v1/aircraft"

# ICAO hex prefix ranges known to be allocated to military operators.
MILITARY_ICAO_PREFIXES = [
    "AE",                                  # US Military
    "A8", "A9", "AA", "AB", "AC", "AD",   # US Military extended
    "43C", "43D", "43E", "43F",            # UK Military
    "3F",                                  # Germany Military
    "3A8", "3A9", "3AA", "3AB",            # France Military
    "500", "501", "502",                   # Israel Military
    "70",                                  # Pakistan Military
    "C0",                                  # Canada Military
]

# Callsign prefixes commonly used by military flights.
MILITARY_CALLSIGN_PREFIXES = [
    "RCH", "DUKE", "REACH", "EVAC", "JAKE", "TOPCAT", "BOXER",
    "IRON", "CASA", "NATO", "LAGR", "TEAL", "SAM", "EXEC",
    "SPAR", "VALOR", "BLADE",
]

# Theater bounding boxes for global military posture assessment.
THEATERS = {
    "european": {"bbox": "35,-25,72,45", "desc": "NATO/Russia theater"},
    "indo_pacific": {"bbox": "-10,95,55,155", "desc": "China/Taiwan/SCS"},
    "middle_east": {"bbox": "10,25,45,65", "desc": "Persian Gulf/Red Sea"},
    "arctic": {"bbox": "65,-180,90,180", "desc": "Arctic region"},
    "korean_peninsula": {"bbox": "33,124,43,132", "desc": "Korean DMZ"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_military_icao(icao24: str) -> bool:
    """Check whether an ICAO24 hex address falls within known military ranges."""
    upper = icao24.upper()
    for prefix in MILITARY_ICAO_PREFIXES:
        if upper.startswith(prefix):
            return True
    return False


def _is_military_callsign(callsign: str | None) -> bool:
    """Check whether a callsign matches known military callsign patterns."""
    if not callsign:
        return False
    cs = callsign.strip().upper()
    for prefix in MILITARY_CALLSIGN_PREFIXES:
        if cs.startswith(prefix):
            return True
    return False


def _build_opensky_auth_headers() -> dict[str, str] | None:
    """Build HTTP Basic auth header from OpenSky env vars, or None if unset."""
    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    if client_id and client_secret:
        credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}"}
    return None


def _extract_aircraft(state: list) -> dict:
    """Extract a structured aircraft dict from an OpenSky state vector."""
    return {
        "icao24": state[0],
        "callsign": state[1].strip() if state[1] else None,
        "origin_country": state[2],
        "latitude": state[6],
        "longitude": state[5],
        "altitude_m": state[7],
        "velocity_ms": state[9],
        "heading": state[10],
        "on_ground": state[8],
        "squawk": state[14],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_military_flights(
    fetcher: Fetcher,
    bbox: str | None = None,
) -> dict:
    """Fetch current military aircraft positions from the OpenSky Network.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        bbox: Optional bounding box as "lamin,lomin,lamax,lomax".

    Returns:
        Dict with aircraft list, count, filter description, source, and timestamp.
    """
    params: dict[str, str] = {}
    if bbox is not None:
        parts = bbox.split(",")
        if len(parts) == 4:
            params["lamin"] = parts[0]
            params["lomin"] = parts[1]
            params["lamax"] = parts[2]
            params["lomax"] = parts[3]

    headers = _build_opensky_auth_headers()
    cache_label = bbox or "global"

    data = await fetcher.get_json(
        url=_OPENSKY_STATES_URL,
        source="opensky",
        cache_key=f"military:flights:{cache_label}",
        cache_ttl=120,
        headers=headers,
        params=params if params else None,
    )

    if data is None:
        logger.warning("OpenSky API returned no data (bbox=%s)", cache_label)
        return {
            "aircraft": [],
            "count": 0,
            "military_filter": "icao_prefix+callsign",
            "source": "opensky",
            "timestamp": _utc_now_iso(),
        }

    states = data.get("states") or []
    military_aircraft: list[dict] = []

    for state in states:
        if not state or len(state) < 17:
            continue

        icao24 = state[0] or ""
        callsign = state[1] or ""

        if _is_military_icao(icao24) or _is_military_callsign(callsign):
            military_aircraft.append(_extract_aircraft(state))

    return {
        "aircraft": military_aircraft,
        "count": len(military_aircraft),
        "military_filter": "icao_prefix+callsign",
        "source": "opensky",
        "timestamp": _utc_now_iso(),
    }


async def fetch_theater_posture(fetcher: Fetcher) -> dict:
    """Assess global military air posture across 5 theater regions.

    Calls fetch_military_flights for each theater in parallel and aggregates
    the results into a per-theater summary.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.

    Returns:
        Dict with per-theater summaries, total count, source, and timestamp.
    """
    # Check cache first to avoid redundant parallel fetches.
    cached = fetcher.cache.get("military:posture")
    if cached is not None:
        return cached

    async def _fetch_theater(name: str, info: dict) -> tuple[str, dict]:
        result = await fetch_military_flights(fetcher, bbox=info["bbox"])
        aircraft_list = result.get("aircraft", [])

        countries: set[str] = set()
        callsigns: list[str] = []
        for ac in aircraft_list:
            if ac.get("origin_country"):
                countries.add(ac["origin_country"])
            if ac.get("callsign"):
                callsigns.append(ac["callsign"])

        return (name, {
            "count": len(aircraft_list),
            "countries": sorted(countries),
            "sample_callsigns": callsigns[:5],
            "bbox": info["bbox"],
            "description": info["desc"],
        })

    tasks = [
        _fetch_theater(name, info) for name, info in THEATERS.items()
    ]
    results = await asyncio.gather(*tasks)

    theaters: dict[str, dict] = {}
    total = 0
    for name, summary in results:
        theaters[name] = summary
        total += summary["count"]

    response = {
        "theaters": theaters,
        "total_military_aircraft": total,
        "source": "opensky",
        "timestamp": _utc_now_iso(),
    }

    fetcher.cache.set("military:posture", response, 300)
    return response


async def fetch_aircraft_details(fetcher: Fetcher, icao24: str) -> dict:
    """Look up detailed aircraft information from hexdb.io (free, no API key).

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        icao24: The ICAO 24-bit hex address of the aircraft.

    Returns:
        Dict with aircraft detail payload, source, and timestamp.
    """
    url = f"{_HEXDB_BASE_URL}/{icao24}"

    data = await fetcher.get_json(
        url=url,
        source="hexdb",
        cache_key=f"military:aircraft:{icao24}",
        cache_ttl=3600,
    )

    if data is None:
        logger.warning("hexdb.io returned no data for icao24=%s", icao24)
        return {
            "aircraft": {},
            "source": "hexdb",
            "timestamp": _utc_now_iso(),
        }

    return {
        "aircraft": data,
        "source": "hexdb",
        "timestamp": _utc_now_iso(),
    }
