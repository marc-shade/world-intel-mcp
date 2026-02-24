"""Population exposure analysis near active events.

Estimates population at risk by finding major cities within a radius of
active earthquakes, wildfires, and conflict events. Uses Haversine formula
for distance calculation and a static dataset of ~120 major cities.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger("world-intel-mcp.analysis.exposure")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


async def _safe(coro, label: str) -> dict:
    try:
        return await coro
    except Exception as exc:
        logger.warning("Exposure: %s failed: %s", label, exc)
        return {}


def _find_exposed_cities(
    events: list[dict],
    cities: list[dict],
    radius_km: float,
) -> list[dict]:
    """Find cities within radius_km of any event. Returns unique cities with nearest event."""
    exposed: dict[str, dict] = {}  # city_name -> info

    for event in events:
        elat = event.get("lat")
        elon = event.get("lon")
        if elat is None or elon is None:
            continue

        for city in cities:
            dist = _haversine_km(elat, elon, city["lat"], city["lon"])
            if dist <= radius_km:
                cname = city["name"]
                if cname not in exposed or dist < exposed[cname]["distance_km"]:
                    exposed[cname] = {
                        "city": cname,
                        "country": city["country"],
                        "lat": city["lat"],
                        "lon": city["lon"],
                        "population": city["pop"],
                        "distance_km": round(dist, 1),
                        "nearest_event": event.get("type", "unknown"),
                        "event_detail": event.get("detail", ""),
                    }

    return sorted(exposed.values(), key=lambda c: c["distance_km"])


async def fetch_population_exposure(
    fetcher,
    radius_km: float = 200.0,
    event_types: list[str] | None = None,
) -> dict:
    """Estimate population exposure near active events.

    Gathers active earthquakes (M4.5+), wildfires, and conflict events,
    then finds major cities within radius_km of each event.

    Args:
        fetcher: Shared HTTP fetcher.
        radius_km: Search radius in km (default 200).
        event_types: Filter to specific types: earthquake, wildfire, conflict.
                     Default: all three.
    """
    from ..config.population import MAJOR_CITIES
    from ..sources import seismology, wildfire, conflict

    types = set(event_types or ["earthquake", "wildfire", "conflict"])

    coros = {}
    if "earthquake" in types:
        coros["earthquake"] = seismology.fetch_earthquakes(fetcher, min_magnitude=4.5, hours=48, limit=50)
    if "wildfire" in types:
        coros["wildfire"] = wildfire.fetch_wildfires(fetcher)
    if "conflict" in types:
        coros["conflict"] = conflict.fetch_acled_events(fetcher, days=7, limit=200)

    results = {}
    if coros:
        fetched = await asyncio.gather(
            *[_safe(c, k) for k, c in coros.items()]
        )
        for key, data in zip(coros.keys(), fetched):
            results[key] = data

    # Normalize events to [{lat, lon, type, detail}]
    events: list[dict] = []

    # Earthquakes
    for eq in results.get("earthquake", {}).get("earthquakes", []):
        lat = eq.get("latitude") or eq.get("lat")
        lon = eq.get("longitude") or eq.get("lon")
        if lat is not None and lon is not None:
            events.append({
                "lat": float(lat),
                "lon": float(lon),
                "type": "earthquake",
                "detail": f"M{eq.get('magnitude', '?')} {eq.get('place', '')}",
            })

    # Wildfires
    for region_data in results.get("wildfire", {}).get("regions", []):
        for fire in region_data.get("detections", []):
            lat = fire.get("latitude") or fire.get("lat")
            lon = fire.get("longitude") or fire.get("lon")
            if lat is not None and lon is not None:
                events.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "type": "wildfire",
                    "detail": f"FRP {fire.get('frp', '?')} in {region_data.get('region', '?')}",
                })

    # Conflict
    for ev in results.get("conflict", {}).get("events", []):
        lat = ev.get("latitude") or ev.get("lat")
        lon = ev.get("longitude") or ev.get("lon")
        if lat is not None and lon is not None:
            events.append({
                "lat": float(lat),
                "lon": float(lon),
                "type": "conflict",
                "detail": f"{ev.get('event_type', 'conflict')}: {ev.get('location', ev.get('admin1', ''))}",
            })

    # Find exposed cities
    exposed_cities = _find_exposed_cities(events, MAJOR_CITIES, radius_km)
    total_exposed_pop = sum(c["population"] for c in exposed_cities)

    # Group by event type
    by_type: dict[str, int] = {}
    for c in exposed_cities:
        t = c["nearest_event"]
        by_type[t] = by_type.get(t, 0) + c["population"]

    # Group by country
    by_country: dict[str, int] = {}
    for c in exposed_cities:
        country = c["country"]
        by_country[country] = by_country.get(country, 0) + c["population"]

    return {
        "exposed_cities": exposed_cities,
        "exposed_city_count": len(exposed_cities),
        "total_exposed_population": total_exposed_pop,
        "total_exposed_population_formatted": _format_pop(total_exposed_pop),
        "by_event_type": {k: _format_pop(v) for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)},
        "by_country": {k: _format_pop(v) for k, v in sorted(by_country.items(), key=lambda x: x[1], reverse=True)[:10]},
        "events_analyzed": len(events),
        "radius_km": radius_km,
        "event_types": sorted(types),
        "source": "population-exposure-analysis",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _format_pop(pop: int) -> str:
    if pop >= 1_000_000:
        return f"{pop / 1_000_000:.1f}M"
    elif pop >= 1_000:
        return f"{pop / 1_000:.0f}K"
    return str(pop)
