"""Social signals source for world-intel-mcp.

Monitors Reddit public JSON endpoints for geopolitical discussion
velocity across r/worldnews and r/geopolitics. No API keys required.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.social")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUBREDDITS: list[str] = ["worldnews", "geopolitics"]

_REDDIT_HOT_URL = "https://www.reddit.com/r/{subreddit}/hot.json"

_CACHE_TTL = 300  # 5 minutes

_HEADERS = {
    "User-Agent": "PhoenixAGI-WorldIntel/0.1 (intelligence monitoring)",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_social_signals(
    fetcher: Fetcher,
    limit: int = 25,
) -> dict:
    """Fetch hot posts from geopolitical subreddits for velocity analysis.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        limit: Max posts per subreddit.

    Returns:
        Dict with posts, velocity_metrics, subreddits_queried, source.
    """
    now = datetime.now(timezone.utc)

    all_posts: list[dict] = []

    async def _fetch_subreddit(subreddit: str) -> list[dict]:
        url = _REDDIT_HOT_URL.format(subreddit=subreddit)
        data = await fetcher.get_json(
            url,
            source="reddit",
            cache_key=f"social:reddit:{subreddit}:hot",
            cache_ttl=_CACHE_TTL,
            headers=_HEADERS,
            params={"limit": str(limit), "raw_json": "1"},
        )

        if data is None:
            logger.debug("No data from r/%s", subreddit)
            return []

        posts: list[dict] = []
        children = data.get("data", {}).get("children", [])

        for child in children:
            post_data = child.get("data", {})
            if not post_data:
                continue

            created_utc = post_data.get("created_utc")
            created_iso = None
            if created_utc is not None:
                try:
                    created_iso = datetime.fromtimestamp(
                        float(created_utc), tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                except (ValueError, TypeError, OSError):
                    pass

            posts.append({
                "title": post_data.get("title", ""),
                "subreddit": subreddit,
                "score": post_data.get("score", 0),
                "num_comments": post_data.get("num_comments", 0),
                "upvote_ratio": post_data.get("upvote_ratio"),
                "created": created_iso,
                "url": f"https://reddit.com{post_data.get('permalink', '')}",
                "is_self": post_data.get("is_self", False),
            })

        return posts

    tasks = [_fetch_subreddit(sub) for sub in _SUBREDDITS]
    results = await asyncio.gather(*tasks)
    for posts in results:
        all_posts.extend(posts)

    # Sort by score descending
    all_posts.sort(key=lambda p: p.get("score", 0), reverse=True)

    # Velocity metrics
    total_score = sum(p.get("score", 0) for p in all_posts)
    total_comments = sum(p.get("num_comments", 0) for p in all_posts)
    avg_score = round(total_score / len(all_posts), 1) if all_posts else 0
    avg_comments = round(total_comments / len(all_posts), 1) if all_posts else 0

    # High engagement threshold
    high_engagement = [
        p for p in all_posts
        if p.get("score", 0) > 1000 or p.get("num_comments", 0) > 200
    ]

    velocity_metrics = {
        "total_posts": len(all_posts),
        "total_score": total_score,
        "total_comments": total_comments,
        "avg_score": avg_score,
        "avg_comments": avg_comments,
        "high_engagement_count": len(high_engagement),
    }

    return {
        "posts": all_posts,
        "velocity_metrics": velocity_metrics,
        "subreddits_queried": _SUBREDDITS,
        "source": "reddit-public",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
