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
_ADSBLOL_MIL_URL = "https://api.adsb.lol/v2/mil"
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

# ICAO hex prefix → country mapping for military aircraft.
_ICAO_COUNTRY: list[tuple[str, str]] = [
    ("AE", "United States"), ("A8", "United States"), ("A9", "United States"),
    ("AA", "United States"), ("AB", "United States"), ("AC", "United States"),
    ("AD", "United States"),
    ("43C", "United Kingdom"), ("43D", "United Kingdom"),
    ("43E", "United Kingdom"), ("43F", "United Kingdom"),
    ("3F", "Germany"), ("3A8", "France"), ("3A9", "France"),
    ("3AA", "France"), ("3AB", "France"),
    ("500", "Israel"), ("501", "Israel"), ("502", "Israel"),
    ("70", "Pakistan"), ("C0", "Canada"),
    ("34", "Italy"), ("3C", "Germany"),
    ("E4", "Brazil"), ("71", "Turkey"),
    ("50", "Israel"), ("48", "Netherlands"),
    ("44", "Austria"), ("45", "Belgium"),
    ("46", "Bulgaria"), ("49", "Denmark"),
    ("4A", "Finland"), ("39", "France"),
    ("4B", "Greece"), ("4D", "Hungary"),
    ("4C", "Ireland"), ("30", "Italy"),
    ("73", "Japan"), ("78", "China"),
    ("7C", "Australia"), ("C8", "Australia"),
]


def _icao_to_country(icao24: str) -> str:
    """Derive country from ICAO24 hex address prefix."""
    upper = icao24.upper()
    # Try longest prefixes first for specificity
    for prefix, country in sorted(_ICAO_COUNTRY, key=lambda x: -len(x[0])):
        if upper.startswith(prefix):
            return country
    return ""

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

async def _fetch_adsblol_military(fetcher: Fetcher) -> list[dict] | None:
    """Fetch military aircraft from adsb.lol free API (pre-filtered)."""
    data = await fetcher.get_json(
        url=_ADSBLOL_MIL_URL,
        source="adsblol",
        cache_key="military:adsblol:mil",
        cache_ttl=300,
    )
    if data is None:
        return None

    aircraft: list[dict] = []
    for ac in data.get("ac") or []:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue
        icao24 = ac.get("hex", "")
        aircraft.append({
            "icao24": icao24,
            "callsign": (ac.get("flight") or "").strip() or None,
            "origin_country": _icao_to_country(icao24),
            "latitude": lat,
            "longitude": lon,
            "altitude_m": ac.get("alt_baro"),
            "velocity_ms": ac.get("gs"),
            "heading": ac.get("track"),
            "on_ground": ac.get("alt_baro") == "ground",
            "squawk": ac.get("squawk"),
            "aircraft_type": ac.get("t"),
            "registration": ac.get("r"),
        })
    return aircraft


async def _fetch_opensky_military(
    fetcher: Fetcher, bbox: str | None = None,
) -> list[dict] | None:
    """Fetch military aircraft from OpenSky (requires filtering)."""
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
        cache_ttl=300,
        headers=headers,
        params=params if params else None,
    )

    if data is None:
        return None

    states = data.get("states") or []
    aircraft: list[dict] = []
    for state in states:
        if not state or len(state) < 17:
            continue
        icao24 = state[0] or ""
        callsign = state[1] or ""
        if _is_military_icao(icao24) or _is_military_callsign(callsign):
            aircraft.append(_extract_aircraft(state))
    return aircraft


async def fetch_military_flights(
    fetcher: Fetcher,
    bbox: str | None = None,
) -> dict:
    """Fetch current military aircraft positions.

    Tries adsb.lol (free, pre-filtered military endpoint) first,
    falls back to OpenSky Network if unavailable.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        bbox: Optional bounding box as "lamin,lomin,lamax,lomax" (OpenSky only).

    Returns:
        Dict with aircraft list, count, filter description, source, and timestamp.
    """
    # Primary: adsb.lol (free, dedicated military endpoint, no filtering needed)
    aircraft = await _fetch_adsblol_military(fetcher)
    if aircraft is not None and len(aircraft) > 0:
        # Apply bbox filter client-side if requested
        if bbox is not None:
            parts = bbox.split(",")
            if len(parts) == 4:
                la_min, lo_min, la_max, lo_max = map(float, parts)
                aircraft = [
                    a for a in aircraft
                    if a["latitude"] is not None and a["longitude"] is not None
                    and la_min <= a["latitude"] <= la_max
                    and lo_min <= a["longitude"] <= lo_max
                ]
        return {
            "aircraft": aircraft,
            "count": len(aircraft),
            "military_filter": "adsblol_mil_endpoint",
            "source": "adsb.lol",
            "timestamp": _utc_now_iso(),
        }

    # Fallback: OpenSky Network
    logger.debug("adsb.lol unavailable, trying OpenSky")
    aircraft = await _fetch_opensky_military(fetcher, bbox)
    if aircraft is not None:
        return {
            "aircraft": aircraft,
            "count": len(aircraft),
            "military_filter": "icao_prefix+callsign",
            "source": "opensky",
            "timestamp": _utc_now_iso(),
        }

    return {
        "aircraft": [],
        "count": 0,
        "military_filter": "icao_prefix+callsign",
        "source": "none",
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
