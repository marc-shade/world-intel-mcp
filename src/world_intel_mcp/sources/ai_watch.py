"""AI/AGI development tracking source for world-intel-mcp.

Monitors the latest AI research publications, model releases, and
industry developments via RSS feeds from arXiv, Hugging Face, and
major AI news outlets. No API keys required.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

logger = logging.getLogger("world-intel-mcp.sources.ai_watch")

# ---------------------------------------------------------------------------
# Feed sources
# ---------------------------------------------------------------------------

_AI_FEEDS: list[tuple[str, str, str]] = [
    # (name, url, category)
    ("arXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI", "research"),
    ("arXiv cs.LG", "https://rss.arxiv.org/rss/cs.LG", "research"),
    ("arXiv cs.CL", "https://rss.arxiv.org/rss/cs.CL", "research"),
    ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml", "industry"),
    ("The Gradient", "https://thegradient.pub/rss/", "analysis"),
    ("Import AI", "https://importai.substack.com/feed", "newsletter"),
]

# Key AI labs to track mentions of
_AI_LABS = [
    "openai", "anthropic", "google", "deepmind", "meta", "mistral",
    "xai", "cohere", "stability", "midjourney", "nvidia", "microsoft",
    "apple", "hugging face", "databricks", "together", "groq",
]

_CACHE_TTL = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_published(entry: dict) -> str | None:
    """Parse an RSS entry's published date to ISO 8601 UTC string."""
    import time as _time

    parsed_tuple = entry.get("published_parsed")
    if parsed_tuple is not None:
        try:
            epoch = _time.mktime(parsed_tuple[:9])
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError, OverflowError):
            pass

    updated_tuple = entry.get("updated_parsed")
    if updated_tuple is not None:
        try:
            epoch = _time.mktime(updated_tuple[:9])
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError, OverflowError):
            pass

    return entry.get("published") or entry.get("updated")


def _extract_lab_mentions(text: str) -> list[str]:
    """Extract AI lab names mentioned in text."""
    lower = text.lower()
    return [lab for lab in _AI_LABS if lab in lower]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_ai_watch(
    fetcher: Fetcher,
    limit: int = 50,
) -> dict:
    """Fetch latest AI/AGI developments from research and industry feeds.

    Aggregates recent papers, blog posts, and announcements from key
    AI sources, sorted by recency. Extracts lab mentions for trend
    tracking.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        limit: Maximum number of items to return.

    Returns:
        Dict with items list, lab mention counts, source counts, and metadata.
    """
    if feedparser is None:
        return {
            "error": "feedparser not installed — run: pip install feedparser",
            "items": [],
            "count": 0,
        }

    all_items: list[dict] = []

    async def _fetch_feed(
        name: str, url: str, category: str,
    ) -> list[dict]:
        safe_name = name.lower().replace(" ", "_").replace(".", "_")
        xml_text = await fetcher.get_xml(
            url,
            source=f"ai_watch:{safe_name}",
            cache_key=f"ai_watch:rss:{safe_name}",
            cache_ttl=_CACHE_TTL,
        )

        if xml_text is None:
            logger.debug("No data from AI feed %s", name)
            return []

        parsed = feedparser.parse(xml_text)
        items: list[dict] = []

        for entry in parsed.get("entries", [])[:30]:
            title = entry.get("title", "")
            summary = entry.get("summary") or entry.get("description") or ""
            combined_text = f"{title} {summary}"

            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": _parse_published(entry),
                "summary": summary[:200] if len(summary) > 200 else summary,
                "feed_name": name,
                "category": category,
                "lab_mentions": _extract_lab_mentions(combined_text),
            })

        return items

    # Fetch all feeds in parallel
    tasks = [_fetch_feed(name, url, cat) for name, url, cat in _AI_FEEDS]
    results = await asyncio.gather(*tasks)
    for items in results:
        all_items.extend(items)

    # Sort by published date descending
    all_items.sort(
        key=lambda item: item.get("published") or "",
        reverse=True,
    )
    all_items = all_items[:limit]

    # Compute lab mention counts
    lab_counts: dict[str, int] = {}
    for item in all_items:
        for lab in item.get("lab_mentions", []):
            lab_counts[lab] = lab_counts.get(lab, 0) + 1

    # Sort by count descending
    lab_trending = sorted(
        [{"lab": k, "mentions": v} for k, v in lab_counts.items()],
        key=lambda x: x["mentions"],
        reverse=True,
    )

    # Count by category
    by_category: dict[str, int] = {}
    for item in all_items:
        cat = item.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "items": all_items,
        "count": len(all_items),
        "lab_trending": lab_trending,
        "by_category": by_category,
        "feeds_used": len(_AI_FEEDS),
        "source": "ai-watch",
        "timestamp": _utc_now_iso(),
    }
