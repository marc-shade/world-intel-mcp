"""Aviation data sources for world-intel-mcp.

Provides real-time US airport delay information from the FAA Airport
Status Web Service (ASWS) API, and global domestic air traffic counts
from OpenSky Network.  No API key required for either.
"""

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.aviation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAA_STATUS_URL = "https://soa.smext.faa.gov/asws/api/airport/status"

_MAJOR_AIRPORTS = [
    "ATL", "LAX", "ORD", "DFW", "DEN", "JFK", "SFO", "SEA", "LAS", "MCO",
    "EWR", "CLT", "PHX", "IAH", "MIA", "BOS", "MSP", "FLL", "DTW", "PHL",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_airport_status(code: str, data: dict) -> dict:
    """Extract structured fields from a single FAA airport status response."""
    name = data.get("Name", code)
    delay = data.get("Delay", False)

    # Normalize delay to boolean (API may return string "true"/"false")
    if isinstance(delay, str):
        delay = delay.lower() == "true"

    status_items = data.get("Status", [])
    if not isinstance(status_items, list):
        status_items = [status_items] if isinstance(status_items, dict) else []

    parsed_statuses = []
    for item in status_items:
        if not isinstance(item, dict):
            continue
        parsed_statuses.append({
            "type": item.get("Type", ""),
            "reason": item.get("Reason", ""),
            "avg_delay": item.get("AvgDelay", ""),
            "closure_begin": item.get("ClosureBegin", ""),
            "closure_end": item.get("ClosureEnd", ""),
        })

    return {
        "code": code,
        "name": name,
        "delay": delay,
        "status": parsed_statuses,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_airport_delays(fetcher: Fetcher) -> dict:
    """Fetch current US airport delays from the FAA Airport Status API.

    Queries the FAA ASWS API for each major US airport in parallel and
    returns a summary of which airports currently have active delays.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.

    Returns:
        Dict with delayed airports list, counts, source, and timestamp.
    """

    async def _fetch_one(code: str) -> tuple[str, dict | None]:
        """Fetch status for a single airport, returning (code, data|None)."""
        data = await fetcher.get_json(
            url=f"{_FAA_STATUS_URL}/{code}",
            source="faa",
            cache_key=f"aviation:faa:{code}",
            cache_ttl=300,
        )
        return code, data

    # Fetch all airports in parallel
    results = await asyncio.gather(
        *[_fetch_one(code) for code in _MAJOR_AIRPORTS],
        return_exceptions=True,
    )

    now_iso = _utc_now_iso()

    delayed: list[dict] = []
    all_airports: list[dict] = []
    errors = 0

    for result in results:
        if isinstance(result, Exception):
            logger.warning("Exception fetching airport status: %s", result)
            errors += 1
            continue

        code, data = result

        if data is None:
            logger.debug("No data returned for airport %s", code)
            errors += 1
            continue

        parsed = _parse_airport_status(code, data)
        all_airports.append(parsed)

        if parsed["delay"]:
            delayed.append(parsed)

    return {
        "delayed": delayed,
        "delayed_count": len(delayed),
        "total_checked": len(_MAJOR_AIRPORTS),
        "errors": errors,
        "source": "faa",
        "timestamp": now_iso,
    }


# ---------------------------------------------------------------------------
# Domestic / commercial air traffic (OpenSky Network)
# ---------------------------------------------------------------------------

_OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"

_AIR_REGIONS = {
    "north_america": (15, -170, 72, -50),
    "europe": (35, -25, 72, 45),
    "east_asia": (15, 95, 55, 155),
    "middle_east": (12, 25, 42, 65),
    "south_asia": (5, 60, 40, 100),
    "africa": (-35, -20, 37, 55),
    "south_america": (-56, -82, 15, -34),
    "oceania": (-50, 110, 0, 180),
}

_COMMERCIAL_PREFIXES = [
    "UAL", "AAL", "DAL", "SWA", "JBU", "ASA", "NKS", "FFT", "SKW",
    "BAW", "EZY", "RYR", "DLH", "AFR", "KLM", "SAS", "AUA", "TAP",
    "QFA", "ANZ", "JST", "VOZ", "CPA", "SIA", "THA", "ANA", "JAL",
    "CES", "CSN", "CCA", "HDA", "AIC", "UAE", "ETH", "SAA", "RAM",
    "TAM", "GLO", "AZU", "AVA", "LAN", "THY", "TRK", "SHT",
]


def _opensky_auth_headers() -> dict[str, str] | None:
    username = os.environ.get("OPENSKY_USERNAME")
    password = os.environ.get("OPENSKY_PASSWORD")
    if username and password:
        cred = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}
    return None


def _classify_region(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "unknown"
    for name, (lat_min, lon_min, lat_max, lon_max) in _AIR_REGIONS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return "other"


def _is_commercial(callsign: str | None) -> bool:
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in _COMMERCIAL_PREFIXES)


async def fetch_domestic_flights(fetcher: Fetcher) -> dict:
    """Fetch global air traffic counts from OpenSky Network.

    Queries all airborne aircraft once, then buckets by region and type.
    """
    data = await fetcher.get_json(
        _OPENSKY_STATES_URL,
        source="opensky-domestic",
        cache_key="aviation:opensky:all",
        cache_ttl=120,
        headers=_opensky_auth_headers(),
    )

    if data is None or not isinstance(data, dict):
        return {
            "total_aircraft": 0,
            "by_region": {},
            "busiest_origins": [],
            "error": "OpenSky API unavailable",
            "source": "opensky-domestic",
            "timestamp": _utc_now_iso(),
        }

    states = data.get("states") or []

    by_region: dict[str, dict] = {r: {"count": 0, "commercial": 0, "general": 0} for r in _AIR_REGIONS}
    by_region["other"] = {"count": 0, "commercial": 0, "general": 0}
    by_region["unknown"] = {"count": 0, "commercial": 0, "general": 0}
    country_counts: dict[str, int] = {}
    total = 0

    for s in states:
        if not isinstance(s, list) or len(s) < 15:
            continue
        if s[8]:  # on_ground
            continue

        total += 1
        lat, lon = s[6], s[5]
        callsign = s[1]
        origin = s[2] or "Unknown"

        region = _classify_region(lat, lon)
        by_region[region]["count"] += 1
        if _is_commercial(callsign):
            by_region[region]["commercial"] += 1
        else:
            by_region[region]["general"] += 1

        country_counts[origin] = country_counts.get(origin, 0) + 1

    # Remove empty regions
    by_region = {k: v for k, v in by_region.items() if v["count"] > 0}

    busiest = sorted(country_counts.items(), key=lambda x: -x[1])[:15]

    return {
        "total_aircraft": total,
        "by_region": by_region,
        "busiest_origins": [{"country": c, "count": n} for c, n in busiest],
        "source": "opensky-domestic",
        "timestamp": _utc_now_iso(),
    }
