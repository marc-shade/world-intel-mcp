"""Naval fleet activity report.

Aggregates theater posture, vessel snapshot at strategic waterways,
military surge detections, and military base data into a fleet-focused
intelligence report.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("world-intel-mcp.sources.fleet")


async def _safe(coro, label: str) -> dict:
    try:
        return await coro
    except Exception as exc:
        logger.warning("Fleet report: %s failed: %s", label, exc)
        return {}


def _fleet_readiness(theaters: list, waterways: list, surges: list) -> tuple[str, int]:
    """Assess overall fleet readiness from component data.

    Returns (level, score 0-100).
    """
    score = 0.0

    # Theater activity: more aircraft = higher activity
    total_aircraft = sum(t.get("aircraft_count", 0) for t in theaters)
    score += min(30.0, total_aircraft * 0.5)

    # Waterway status: elevated/critical waterways raise score
    status_map = {"clear": 0, "advisory": 10, "elevated": 20, "critical": 30}
    for ww in waterways:
        score += status_map.get(ww.get("status", "clear"), 0) / max(len(waterways), 1)

    # Active surges
    score += min(30.0, len(surges) * 15.0)

    score = min(100.0, score)

    if score >= 70:
        level = "HIGH_ACTIVITY"
    elif score >= 40:
        level = "ELEVATED_ACTIVITY"
    elif score >= 15:
        level = "NORMAL_OPERATIONS"
    else:
        level = "LOW_ACTIVITY"

    return level, round(score)


async def fetch_fleet_report(fetcher) -> dict:
    """Generate naval fleet activity report.

    Aggregates:
    - Theater posture (5 theaters, aircraft counts)
    - Vessel snapshot (9 strategic waterways, naval status)
    - Military surge detections (anomalous foreign aircraft concentration)
    - Naval bases (filtered from static dataset)
    """
    from . import intelligence, military, geospatial

    (
        posture_data,
        vessel_data,
        surge_data,
    ) = await asyncio.gather(
        _safe(military.fetch_theater_posture(fetcher), "theater_posture"),
        _safe(intelligence.fetch_vessel_snapshot(fetcher), "vessel_snapshot"),
        _safe(intelligence.fetch_military_surge(fetcher), "military_surge"),
    )

    # Get naval bases (sync, no fetcher needed)
    naval_bases = await geospatial.fetch_military_bases(base_type="naval_base")
    naval_base_count = naval_bases.get("count", 0)

    # Extract key data
    theaters = posture_data.get("theaters", [])
    waterways = vessel_data.get("waterways", [])
    surges = surge_data.get("surges", [])

    # Compute fleet readiness
    readiness_level, readiness_score = _fleet_readiness(theaters, waterways, surges)

    # Theater summary
    theater_summary = []
    for t in theaters:
        theater_summary.append({
            "name": t.get("name", "Unknown"),
            "aircraft_count": t.get("aircraft_count", 0),
            "top_types": t.get("top_types", [])[:3],
        })

    # Waterway summary
    waterway_summary = []
    for ww in waterways:
        waterway_summary.append({
            "name": ww.get("name", "Unknown"),
            "status": ww.get("status", "unknown"),
            "warning_count": ww.get("warning_count", 0),
        })

    # Active surges
    active_surges = []
    for s in surges:
        active_surges.append({
            "region": s.get("region", "Unknown"),
            "aircraft_count": s.get("aircraft_count", 0),
            "baseline": s.get("baseline", 0),
            "ratio": s.get("ratio", 0),
        })

    return {
        "readiness_level": readiness_level,
        "readiness_score": readiness_score,
        "theater_summary": theater_summary,
        "theater_count": len(theater_summary),
        "waterway_summary": waterway_summary,
        "waterway_count": len(waterway_summary),
        "active_surges": active_surges,
        "surge_count": len(active_surges),
        "naval_base_count": naval_base_count,
        "total_tracked_aircraft": sum(t.get("aircraft_count", 0) for t in theaters),
        "source": "fleet-activity-report",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
