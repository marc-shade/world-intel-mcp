"""Disease outbreak monitoring source for world-intel-mcp.

Aggregates disease outbreak alerts from WHO Disease Outbreak News (DON),
ProMED-mail, and CIDRAP. Uses RSS/Atom feeds via feedparser. No API keys required.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

logger = logging.getLogger("world-intel-mcp.sources.health")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEALTH_FEEDS: list[tuple[str, str]] = [
    ("WHO DON", "https://www.who.int/feeds/entity/don/en/rss.xml"),
    ("ProMED", "https://promedmail.org/feed/"),
    ("CIDRAP", "https://www.cidrap.umn.edu/infectious-disease-topics/rss.xml"),
]

HIGH_CONCERN_PATHOGENS: set[str] = {
    "ebola", "marburg", "mpox", "h5n1", "avian influenza", "bird flu",
    "nipah", "mers", "sars", "cholera", "plague", "anthrax",
    "polio", "yellow fever", "hantavirus", "lassa", "rift valley",
    "dengue", "zika", "chikungunya",
}

_CACHE_TTL = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_published(entry: dict) -> str | None:
    """Parse RSS entry published date to ISO 8601."""
    import time as _time

    for field in ("published_parsed", "updated_parsed"):
        parsed_tuple = entry.get(field)
        if parsed_tuple is not None:
            try:
                epoch = _time.mktime(parsed_tuple[:9])
                dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError, OverflowError):
                pass

    return entry.get("published") or entry.get("updated")


def _flag_severity(title: str, summary: str) -> tuple[bool, list[str]]:
    """Check if title/summary mentions high-concern pathogens."""
    combined = f"{title} {summary}".lower()
    matched = [p for p in HIGH_CONCERN_PATHOGENS if p in combined]
    return bool(matched), matched


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_disease_outbreaks(
    fetcher: Fetcher,
    limit: int = 50,
) -> dict:
    """Aggregate disease outbreak alerts from WHO, ProMED, and CIDRAP.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        limit: Maximum items to return.

    Returns:
        Dict with items, count, high_concern_count, by_organization, source.
    """
    if feedparser is None:
        return {
            "error": "feedparser not installed — run: pip install feedparser",
            "items": [],
            "count": 0,
        }

    all_items: list[dict] = []

    async def _fetch_feed(name: str, url: str) -> list[dict]:
        safe_name = name.lower().replace(" ", "_")
        xml_text = await fetcher.get_xml(
            url,
            source=f"health:{safe_name}",
            cache_key=f"health:rss:{safe_name}",
            cache_ttl=_CACHE_TTL,
        )

        if xml_text is None:
            logger.debug("No data from health feed %s", name)
            return []

        parsed = feedparser.parse(xml_text)
        items: list[dict] = []

        for entry in parsed.get("entries", [])[:30]:
            title = entry.get("title", "")
            summary = entry.get("summary") or entry.get("description") or ""
            is_high_concern, pathogens = _flag_severity(title, summary)

            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": _parse_published(entry),
                "summary": summary[:200] if len(summary) > 200 else summary,
                "organization": name,
                "is_high_concern": is_high_concern,
                "pathogens_mentioned": pathogens,
            })

        return items

    tasks = [_fetch_feed(name, url) for name, url in _HEALTH_FEEDS]
    results = await asyncio.gather(*tasks)
    for items in results:
        all_items.extend(items)

    # Sort by published date descending
    all_items.sort(key=lambda item: item.get("published") or "", reverse=True)
    all_items = all_items[:limit]

    # Counts
    high_concern_count = sum(1 for i in all_items if i.get("is_high_concern"))
    by_organization: dict[str, int] = {}
    for item in all_items:
        org = item.get("organization", "unknown")
        by_organization[org] = by_organization.get(org, 0) + 1

    return {
        "items": all_items,
        "count": len(all_items),
        "high_concern_count": high_concern_count,
        "by_organization": by_organization,
        "source": "health-outbreak-monitor",
        "timestamp": _utc_now_iso(),
    }
