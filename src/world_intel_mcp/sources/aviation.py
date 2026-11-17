"""Aviation data sources for world-intel-mcp.

Provides real-time US airport delay information from the FAA NAS Status
feed, and global domestic air traffic counts from OpenSky Network.  No API key required for either.
"""

import base64
import logging
import os
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.aviation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAA_STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_events(root: ET.Element) -> tuple[list[dict], list[dict]]:
    """Group the FAA national event list by airport.

    Returns (delayed, closures). Closures are NOTAM-based and often only
    restrict general aviation, so they are not counted as delays.
    """
    delayed: dict[str, dict] = {}
    closures: list[dict] = []

    for delay_type in root.iter("Delay_type"):
        type_name = (delay_type.findtext("Name") or "").strip()
        for item in delay_type.iter():
            code = (item.findtext("ARPT") or "").strip()
            if not code:
                continue
            reason = (item.findtext("Reason") or "").strip()
            if "Closure" in type_name:
                closures.append({
                    "code": code,
                    "reason": reason,
                    "closure_begin": (item.findtext("Start") or "").strip(),
                    "closure_end": (item.findtext("Reopen") or "").strip(),
                })
                continue
            avg = (item.findtext("Avg") or "").strip()
            if not avg and item.findtext("End_Time"):
                avg = f"until {item.findtext('End_Time').strip()}"
            entry = delayed.setdefault(
                code, {"code": code, "name": code, "delay": True, "status": []}
            )
            entry["status"].append({
                "type": type_name,
                "reason": reason,
                "avg_delay": avg,
                "closure_begin": "",
                "closure_end": "",
            })

    return list(delayed.values()), closures


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_airport_delays(fetcher: Fetcher) -> dict:
    """Fetch current US airport delays from the FAA NAS Status feed.

    One national XML list of active ground stops, ground delay programs,
    arrival/departure delays and closures; grouped here by airport.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.

    Returns:
        Dict with delayed airports list, counts, source, and timestamp.
    """
    now_iso = _utc_now_iso()
    xml_text = await fetcher.get_xml(
        _FAA_STATUS_URL,
        source="faa",
        cache_key="aviation:faa:status",
        cache_ttl=300,
    )
    if xml_text is None:
        return {"error": "FAA NAS Status API unavailable", "source": "faa", "timestamp": now_iso}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("FAA NAS Status returned unparseable XML: %s", exc)
        return {"error": "FAA NAS Status returned invalid XML", "source": "faa", "timestamp": now_iso}
    if root.tag != "AIRPORT_STATUS_INFORMATION":
        return {"error": "FAA NAS Status returned unexpected XML", "source": "faa", "timestamp": now_iso}

    delayed, closures = _parse_events(root)

    return {
        "delayed": delayed,
        "delayed_count": len(delayed),
        # The feed lists every US airport with an active event, not a fixed set.
        "total_checked": len(delayed),
        "closures": closures,
        "errors": 0,
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

    # Sample every Nth aircraft for map markers (keep payload <200KB)
    sample_step = 10
    sampled: list[dict] = []

    for idx, s in enumerate(states):
        if not isinstance(s, list) or len(s) < 15:
            continue
        if s[8]:  # on_ground
            continue

        total += 1
        lat, lon = s[6], s[5]
        callsign = (s[1] or "").strip()
        origin = s[2] or "Unknown"

        region = _classify_region(lat, lon)
        is_comm = _is_commercial(callsign)
        by_region[region]["count"] += 1
        if is_comm:
            by_region[region]["commercial"] += 1
        else:
            by_region[region]["general"] += 1

        country_counts[origin] = country_counts.get(origin, 0) + 1

        # Sample for map display
        if idx % sample_step == 0 and lat is not None and lon is not None:
            sampled.append({
                "lat": round(lat, 2),
                "lon": round(lon, 2),
                "callsign": callsign or None,
                "origin": origin,
                "alt": round(s[7]) if s[7] else None,
                "commercial": is_comm,
            })

    # Remove empty regions
    by_region = {k: v for k, v in by_region.items() if v["count"] > 0}

    busiest = sorted(country_counts.items(), key=lambda x: -x[1])[:15]

    return {
        "total_aircraft": total,
        "by_region": by_region,
        "busiest_origins": [{"country": c, "count": n} for c, n in busiest],
        "positions": sampled,
        "source": "opensky-domestic",
        "timestamp": _utc_now_iso(),
    }
