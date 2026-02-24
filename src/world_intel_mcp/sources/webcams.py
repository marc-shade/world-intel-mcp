"""Public webcam / CCTV data source for world-intel-mcp.

Fetches worldwide public camera locations and previews via the
Windy Webcams API (webcams.travel).  Free tier: 100 requests/day.
"""

import logging
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.webcams")

_WEBCAMS_URL = "https://api.windy.com/webcams/api/v3/webcams"


async def fetch_webcams(
    fetcher: Fetcher,
    category: str = "traffic",
    limit: int = 50,
) -> dict:
    """Fetch public webcam locations from Windy Webcams API.

    Args:
        fetcher: Shared HTTP fetcher.
        category: Webcam category filter (traffic, weather, landscape, etc).
        limit: Max cameras to return.

    Returns:
        Dict with camera list, count, source, and timestamp.
    """
    api_key = os.environ.get("WINDY_API_KEY")
    if not api_key:
        return {
            "error": "WINDY_API_KEY not configured",
            "note": "Free at api.windy.com (100 req/day)",
        }

    data = await fetcher.get_json(
        _WEBCAMS_URL,
        source="windy-webcams",
        cache_key=f"webcams:{category}:{limit}",
        cache_ttl=1800,
        headers={"x-windy-api-key": api_key},
        params={
            "limit": limit,
            "offset": 0,
            "include": "categories,location,images,player",
            "categories": category,
        },
    )

    if data is None or not isinstance(data, dict):
        return {
            "cameras": [],
            "count": 0,
            "error": "Windy API unavailable",
            "source": "windy-webcams",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    cameras = []
    for cam in data.get("webcams", []):
        loc = cam.get("location", {})
        images = cam.get("images", {})
        current = images.get("current", {})
        player = cam.get("player", {})

        cameras.append({
            "id": cam.get("webcamId") or cam.get("id", ""),
            "title": cam.get("title", "Unknown Camera"),
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "city": loc.get("city", ""),
            "country": loc.get("country", ""),
            "preview_url": current.get("preview", ""),
            "thumbnail_url": current.get("thumbnail", ""),
            "player_url": player.get("day", {}).get("embed", "") if isinstance(player.get("day"), dict) else "",
            "status": cam.get("status", "unknown"),
        })

    return {
        "cameras": cameras,
        "count": len(cameras),
        "category": category,
        "source": "windy-webcams",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
