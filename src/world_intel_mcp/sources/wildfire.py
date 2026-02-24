"""NASA FIRMS wildfire data source for world-intel-mcp.

Provides real-time active fire detections from the VIIRS/SNPP sensor
via the NASA Fire Information for Resource Management System (FIRMS) API.
Requires a NASA FIRMS API key (env: NASA_FIRMS_API_KEY).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.wildfire")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Bounding boxes: west,south,east,north
REGIONS = {
    "north_america": "-170,15,-50,75",
    "south_america": "-85,-60,-30,15",
    "europe": "-25,35,45,72",
    "africa": "-20,-37,55,38",
    "middle_east": "25,10,65,45",
    "south_asia": "60,5,100,40",
    "east_asia": "95,15,150,55",
    "southeast_asia": "90,-15,155,25",
    "oceania": "105,-50,180,-5",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_fires_csv(csv_text: str) -> list[dict]:
    """Parse FIRMS CSV text into a list of fire dicts.

    Only returns high-confidence detections. Uses header row to find
    column indices dynamically (FIRMS CSV schema varies by sensor).
    """
    if not isinstance(csv_text, str):
        logger.warning("Expected CSV text, got %s", type(csv_text).__name__)
        return []

    lines = csv_text.strip().split("\n")
    if len(lines) < 2:
        return []

    # Parse header to find column indices dynamically
    header = [h.strip().lower() for h in lines[0].split(",")]
    col = {name: idx for idx, name in enumerate(header)}

    idx_lat = col.get("latitude")
    idx_lon = col.get("longitude")
    idx_bright = col.get("bright_ti4")
    idx_conf = col.get("confidence")
    idx_frp = col.get("frp")
    idx_date = col.get("acq_date")
    idx_time = col.get("acq_time")
    idx_dn = col.get("daynight")
    idx_sat = col.get("satellite")

    if idx_lat is None or idx_lon is None or idx_conf is None:
        logger.warning("Missing required columns in FIRMS CSV header: %s", header)
        return []

    fires: list[dict] = []
    for line in lines[1:]:
        fields = line.split(",")
        if len(fields) <= max(idx_lat, idx_lon, idx_conf):
            continue

        confidence = fields[idx_conf].strip().lower()
        if confidence in ("low", "l"):
            continue

        try:
            lat = float(fields[idx_lat])
            lon = float(fields[idx_lon])
            brightness = float(fields[idx_bright]) if idx_bright is not None and idx_bright < len(fields) else 0.0
            frp_val = float(fields[idx_frp]) if idx_frp is not None and idx_frp < len(fields) and fields[idx_frp].strip() else 0.0
        except (ValueError, IndexError):
            continue

        fires.append({
            "latitude": lat,
            "longitude": lon,
            "brightness": brightness,
            "frp": frp_val,
            "confidence": confidence,
            "acq_date": fields[idx_date].strip() if idx_date is not None and idx_date < len(fields) else "",
            "acq_time": fields[idx_time].strip() if idx_time is not None and idx_time < len(fields) else "",
            "daynight": fields[idx_dn].strip() if idx_dn is not None and idx_dn < len(fields) else "",
            "satellite": fields[idx_sat].strip() if idx_sat is not None and idx_sat < len(fields) else "",
        })

    return fires


def _cluster_fires(fires: list[dict], top_n: int = 20) -> list[dict]:
    """Group fires by a 0.5-degree grid and return the top N clusters by count."""
    grid: dict[tuple[float, float], list[dict]] = {}

    for fire in fires:
        # Round to nearest 0.5 degrees
        grid_lat = round(fire["latitude"] * 2) / 2
        grid_lon = round(fire["longitude"] * 2) / 2
        key = (grid_lat, grid_lon)

        if key not in grid:
            grid[key] = []
        grid[key].append(fire)

    # Sort clusters by fire count descending
    sorted_clusters = sorted(grid.items(), key=lambda item: len(item[1]), reverse=True)

    clusters: list[dict] = []
    for (lat, lon), cell_fires in sorted_clusters[:top_n]:
        max_frp = max(f["frp"] for f in cell_fires)
        clusters.append({
            "lat": lat,
            "lon": lon,
            "fire_count": len(cell_fires),
            "max_frp": max_frp,
        })

    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_wildfires(
    fetcher: Fetcher,
    region: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Fetch active wildfire data from NASA FIRMS (VIIRS SNPP NRT, last 24h).

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        region: Region name (key from REGIONS dict). None fetches all regions.
        api_key: NASA FIRMS API key. Falls back to NASA_FIRMS_API_KEY env var.

    Returns:
        Dict with fires_by_region, total_fires, source, and timestamp.
    """
    key = api_key or os.environ.get("NASA_FIRMS_API_KEY")
    if not key:
        return {"error": "NASA_FIRMS_API_KEY not configured"}

    if region is not None:
        bbox = REGIONS.get(region)
        if bbox is None:
            return {
                "error": f"Unknown region '{region}'. Valid: {', '.join(REGIONS.keys())}",
            }
        regions_to_fetch: dict[str, str] = {region: bbox}
    else:
        regions_to_fetch = dict(REGIONS)

    async def _fetch_region(region_name: str, bbox: str) -> tuple[str, list[dict] | None]:
        """Fetch fires for a single region, return (name, fires_list_or_None)."""
        url = f"{_FIRMS_BASE_URL}/{key}/VIIRS_SNPP_NRT/{bbox}/2"

        csv_text = await fetcher.get_text(
            url=url,
            source="nasa-firms",
            cache_key=f"wildfire:csv:{region_name}",
            cache_ttl=1800,
        )

        if csv_text is None:
            logger.warning("FIRMS returned no data for region %s", region_name)
            return (region_name, None)

        fires = _parse_fires_csv(csv_text)
        return (region_name, fires)

    # Fetch all requested regions in parallel
    tasks = [
        _fetch_region(name, bbox)
        for name, bbox in regions_to_fetch.items()
    ]
    results = await asyncio.gather(*tasks)

    # Assemble response
    fires_by_region: dict[str, dict] = {}
    total_fires = 0

    for region_name, fires in results:
        if fires is None:
            fires_by_region[region_name] = {"count": 0, "top_clusters": []}
            continue

        count = len(fires)
        total_fires += count
        top_clusters = _cluster_fires(fires)
        fires_by_region[region_name] = {
            "count": count,
            "top_clusters": top_clusters,
        }

    cache_label = region if region is not None else "global"
    # Store assembled result in cache under the composite key
    fetcher.cache.set(
        f"wildfire:fires:{cache_label}",
        {
            "fires_by_region": fires_by_region,
            "total_fires": total_fires,
            "source": "nasa-firms",
            "timestamp": _utc_now_iso(),
        },
        1800,
    )

    return {
        "fires_by_region": fires_by_region,
        "total_fires": total_fires,
        "source": "nasa-firms",
        "timestamp": _utc_now_iso(),
    }
