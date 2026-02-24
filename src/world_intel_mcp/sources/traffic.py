"""Road traffic intelligence for world-intel-mcp.

Provides real-time city congestion levels and traffic incidents via
the TomTom Traffic API (free tier: 2,500 requests/day).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.traffic")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
_INCIDENTS_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"

_TRAFFIC_CITIES = [
    {"name": "New York", "lat": 40.7580, "lon": -73.9855, "country": "US"},
    {"name": "London", "lat": 51.5074, "lon": -0.1278, "country": "UK"},
    {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503, "country": "JP"},
    {"name": "Beijing", "lat": 39.9042, "lon": 116.4074, "country": "CN"},
    {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777, "country": "IN"},
    {"name": "São Paulo", "lat": -23.5505, "lon": -46.6333, "country": "BR"},
    {"name": "Cairo", "lat": 30.0444, "lon": 31.2357, "country": "EG"},
    {"name": "Lagos", "lat": 6.5244, "lon": 3.3792, "country": "NG"},
    {"name": "Moscow", "lat": 55.7558, "lon": 37.6173, "country": "RU"},
    {"name": "Istanbul", "lat": 41.0082, "lon": 28.9784, "country": "TR"},
    {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437, "country": "US"},
    {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "country": "FR"},
    {"name": "Berlin", "lat": 52.5200, "lon": 13.4050, "country": "DE"},
    {"name": "Sydney", "lat": -33.8688, "lon": 151.2093, "country": "AU"},
    {"name": "Dubai", "lat": 25.2048, "lon": 55.2708, "country": "AE"},
    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198, "country": "SG"},
    {"name": "Seoul", "lat": 37.5665, "lon": 126.9780, "country": "KR"},
    {"name": "Mexico City", "lat": 19.4326, "lon": -99.1332, "country": "MX"},
    {"name": "Jakarta", "lat": -6.2088, "lon": 106.8456, "country": "ID"},
    {"name": "Bangkok", "lat": 13.7563, "lon": 100.5018, "country": "TH"},
]

# Incident severity categories
_INCIDENT_REGIONS = [
    {"name": "US East", "bbox": "-82,25,-65,48"},
    {"name": "US West", "bbox": "-125,30,-100,50"},
    {"name": "Europe", "bbox": "-10,35,30,60"},
    {"name": "Middle East", "bbox": "25,20,60,42"},
    {"name": "East Asia", "bbox": "100,20,145,50"},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_traffic_flow(fetcher: Fetcher) -> dict:
    """Fetch real-time traffic congestion for major world cities.

    Uses TomTom Traffic Flow API. Requires TOMTOM_API_KEY env var.
    """
    api_key = os.environ.get("TOMTOM_API_KEY")
    if not api_key:
        return {
            "error": "TOMTOM_API_KEY not configured",
            "note": "Free at developer.tomtom.com (2500 req/day)",
        }

    async def _fetch_city(city: dict) -> dict:
        data = await fetcher.get_json(
            _FLOW_URL,
            source="tomtom",
            cache_key=f"traffic:flow:{city['name']}",
            cache_ttl=300,
            params={
                "key": api_key,
                "point": f"{city['lat']},{city['lon']}",
                "unit": "KMPH",
            },
        )
        if data is None or not isinstance(data, dict):
            return {**city, "congestion_pct": -1, "error": True}

        flow = data.get("flowSegmentData", {})
        current = flow.get("currentSpeed", 0)
        freeflow = flow.get("freeFlowSpeed", 1)
        congestion = max(0, round((1 - current / freeflow) * 100)) if freeflow > 0 else 0

        return {
            "name": city["name"],
            "country": city["country"],
            "lat": city["lat"],
            "lon": city["lon"],
            "congestion_pct": congestion,
            "current_speed_kmh": round(current, 1),
            "free_flow_speed_kmh": round(freeflow, 1),
        }

    results = await asyncio.gather(
        *[_fetch_city(c) for c in _TRAFFIC_CITIES],
        return_exceptions=True,
    )

    cities = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Traffic flow fetch failed: %s", r)
            continue
        if r.get("error"):
            continue
        cities.append(r)

    cities.sort(key=lambda c: c["congestion_pct"], reverse=True)

    avg = round(sum(c["congestion_pct"] for c in cities) / max(len(cities), 1), 1)

    return {
        "cities": cities,
        "global_avg_congestion": avg,
        "most_congested": cities[0] if cities else None,
        "count": len(cities),
        "source": "tomtom",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_traffic_incidents(fetcher: Fetcher) -> dict:
    """Fetch major traffic incidents from TomTom.

    Queries strategic regions for severity 1-3 incidents.
    Requires TOMTOM_API_KEY env var.
    """
    api_key = os.environ.get("TOMTOM_API_KEY")
    if not api_key:
        return {
            "error": "TOMTOM_API_KEY not configured",
            "note": "Free at developer.tomtom.com",
        }

    async def _fetch_region(region: dict) -> list[dict]:
        data = await fetcher.get_json(
            _INCIDENTS_URL,
            source="tomtom-incidents",
            cache_key=f"traffic:incidents:{region['name']}",
            cache_ttl=300,
            params={
                "key": api_key,
                "bbox": region["bbox"],
                "fields": "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description},startTime,endTime,from,to,length,delay,roadNumbers}}}",
                "language": "en-US",
                "categoryFilter": "0,1,2,3,4,5,6,7,8,9,10,11,14",
                "timeValidityFilter": "present",
            },
        )
        if data is None or not isinstance(data, dict):
            return []

        incidents = []
        for inc in data.get("incidents", [])[:20]:
            props = inc.get("properties", {})
            geom = inc.get("geometry", {})
            coords = geom.get("coordinates", [[]])
            if coords and isinstance(coords[0], list) and len(coords[0]) >= 2:
                lon, lat = coords[0][0], coords[0][1]
            else:
                lon, lat = None, None

            events = props.get("events", [])
            desc = events[0].get("description", "") if events else ""

            incidents.append({
                "region": region["name"],
                "type": inc.get("type", ""),
                "description": desc,
                "from_road": props.get("from", ""),
                "to_road": props.get("to", ""),
                "delay_seconds": props.get("delay", 0),
                "length_meters": props.get("length", 0),
                "magnitude": props.get("magnitudeOfDelay", 0),
                "lat": lat,
                "lon": lon,
                "road_numbers": props.get("roadNumbers", []),
            })
        return incidents

    results = await asyncio.gather(
        *[_fetch_region(r) for r in _INCIDENT_REGIONS],
        return_exceptions=True,
    )

    all_incidents = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Traffic incidents fetch failed: %s", r)
            continue
        all_incidents.extend(r)

    # Sort by delay severity
    all_incidents.sort(key=lambda i: i.get("delay_seconds", 0), reverse=True)

    return {
        "incidents": all_incidents[:50],
        "total_count": len(all_incidents),
        "regions_checked": len(_INCIDENT_REGIONS),
        "source": "tomtom-incidents",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
