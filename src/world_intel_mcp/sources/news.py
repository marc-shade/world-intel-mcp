"""RSS news aggregation, keyword trending, and GDELT search for world-intel-mcp.

Provides multi-category RSS feed aggregation from 20+ high-quality intelligence
and news sources, keyword spike detection from recent headlines, and full-text
search via the GDELT 2.0 Doc API. No API keys required.
"""

import asyncio
import logging
import re
import string
from datetime import datetime, timezone

from ..fetcher import Fetcher

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

logger = logging.getLogger("world-intel-mcp.sources.news")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RSS_FEEDS: dict[str, list[tuple[str, str]]] = {
    "geopolitics": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("AP Top News", "https://feedx.net/rss/ap.xml"),
        ("Reuters World", "https://news.google.com/rss/search?q=source:Reuters&hl=en-US&gl=US&ceid=US:en"),
        ("The Guardian World", "https://www.theguardian.com/world/rss"),
        ("DW News", "https://rss.dw.com/rss/en/top_news/rss-en-top"),
        ("France24", "https://www.france24.com/en/rss"),
    ],
    "security": [
        ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
        ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
        ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
        ("Schneier on Security", "https://www.schneier.com/feed/atom/"),
        ("Dark Reading", "https://www.darkreading.com/rss.xml"),
        ("CISA Alerts", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    ],
    "technology": [
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Wired", "https://www.wired.com/feed/rss"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ],
    "finance": [
        ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("FT World", "https://www.ft.com/rss/home/uk"),
        ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
        ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
        ("Zero Hedge", "https://feeds.feedburner.com/zerohedge/feed"),
    ],
    "military": [
        ("Defense One", "https://www.defenseone.com/rss/all/"),
        ("War on the Rocks", "https://warontherocks.com/feed/"),
        ("The War Zone", "https://www.twz.com/feed"),
        ("Breaking Defense", "https://breakingdefense.com/feed/"),
        ("Military Times", "https://www.militarytimes.com/arc/outboundfeeds/rss/?outputType=xml"),
        ("USNI News", "https://news.usni.org/feed"),
    ],
    "science": [
        ("Nature", "https://www.nature.com/nature.rss"),
        ("Science", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science"),
        ("Phys.org", "https://phys.org/rss-feed/"),
        ("New Scientist", "https://www.newscientist.com/feed/home/"),
    ],
    "think_tanks": [
        ("RAND", "https://www.rand.org/blog.xml"),
        ("Brookings", "https://www.brookings.edu/feed/"),
        ("Carnegie", "https://carnegieendowment.org/rss/solr.xml"),
    ],
    "middle_east": [
        ("Middle East Eye", "https://www.middleeasteye.net/rss"),
        ("The National UAE", "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml"),
        ("Times of Israel", "https://www.timesofisrael.com/feed/"),
        ("Iran Intl", "https://www.iranintl.com/en/feed"),
    ],
    "asia_pacific": [
        ("SCMP", "https://www.scmp.com/rss/91/feed"),
        ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar"),
        ("The Diplomat", "https://thediplomat.com/feed/"),
        ("Channel News Asia", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml"),
        ("Lowy Interpreter", "https://www.lowyinstitute.org/the-interpreter/rss.xml"),
    ],
    "africa": [
        ("allAfrica", "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf"),
    ],
    "latin_america": [
        ("MercoPress", "https://en.mercopress.com/rss"),
        ("Dialogo Americas", "https://dialogo-americas.com/feed/"),
    ],
    "energy": [
        ("Oil Price", "https://oilprice.com/rss/main"),
        ("Rigzone", "https://www.rigzone.com/news/rss/rigzone_latest.aspx"),
        ("Utility Dive", "https://www.utilitydive.com/feeds/news/"),
    ],
    "government": [
        ("State Dept", "https://www.state.gov/rss-feed/press-releases/feed/"),
        ("DoD News", "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10"),
        ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
    ],
    "crisis": [
        ("ReliefWeb", "https://reliefweb.int/updates/rss.xml"),
        ("ICG", "https://www.crisisgroup.org/rss.xml"),
    ],
}

# Source tier classification for propaganda/reliability scoring
SOURCE_TIERS: dict[str, str] = {
    "AP Top News": "wire",
    "Reuters World": "wire",
    "BBC World": "major",
    "Al Jazeera": "major",
    "The Guardian World": "major",
    "DW News": "major",
    "France24": "major",
    "CNBC": "major",
    "FT World": "major",
    "Bloomberg": "major",
    "WSJ Markets": "major",
    "Nature": "major",
    "Science": "major",
    "Defense One": "specialty",
    "Breaking Defense": "specialty",
    "USNI News": "specialty",
    "War on the Rocks": "specialty",
    "The War Zone": "specialty",
    "Military Times": "specialty",
    "RAND": "think_tank",
    "Brookings": "think_tank",
    "Carnegie": "think_tank",
    "ICG": "think_tank",
    "BleepingComputer": "specialty",
    "Krebs on Security": "specialty",
    "The Hacker News": "specialty",
    "CISA Alerts": "government",
    "State Dept": "government",
    "DoD News": "government",
    "UN News": "government",
    "ReliefWeb": "intl_org",
    "Lowy Interpreter": "think_tank",
    "Dialogo Americas": "specialty",
    "Nikkei Asia": "major",
    "The National UAE": "major",
    "Zero Hedge": "aggregator",
}

_STOPWORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "in", "on", "at",
    "to", "for", "of", "and", "or", "but", "nor", "not", "no", "so",
    "yet", "both", "either", "neither", "with", "from", "by", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "over", "about", "against", "out", "off", "up",
    "down", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "each", "every", "any", "few", "more", "most", "some",
    "such", "only", "own", "same", "than", "too", "very", "just", "also",
    "now", "it", "its", "he", "she", "they", "them", "their", "his",
    "her", "we", "you", "your", "our", "my", "me", "him", "us",
    "that", "this", "these", "those", "which", "who", "whom", "what",
    "if", "while", "because", "until", "although", "since", "whether",
    "new", "says", "said", "one", "two", "first", "last", "many",
    "much", "get", "got", "back", "even", "still", "well", "way",
    "s", "t", "re", "ve", "d", "ll", "m",
}

_GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Regex to strip punctuation from words
_PUNCT_RE = re.compile(f"[{re.escape(string.punctuation)}]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_published(entry: dict) -> str | None:
    """Parse an RSS entry's published date to ISO 8601 UTC string.

    feedparser stores the parsed time struct in ``published_parsed``.
    Falls back to the raw ``published`` string if parsing fails.
    """
    import time as _time

    parsed_tuple = entry.get("published_parsed")
    if parsed_tuple is not None:
        try:
            epoch = _time.mktime(parsed_tuple[:9])
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError, OverflowError):
            pass

    # Fallback: try updated_parsed
    updated_tuple = entry.get("updated_parsed")
    if updated_tuple is not None:
        try:
            epoch = _time.mktime(updated_tuple[:9])
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError, OverflowError):
            pass

    # Last resort: return raw string or None
    return entry.get("published") or entry.get("updated")


def _truncate(text: str | None, max_len: int = 200) -> str:
    """Truncate text to max_len characters, appending '...' if trimmed."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ---------------------------------------------------------------------------
# Function 1: RSS News Feed Aggregation
# ---------------------------------------------------------------------------

async def fetch_news_feed(
    fetcher: Fetcher,
    category: str | None = None,
    limit: int = 50,
) -> dict:
    """Aggregate news from 20+ RSS feeds across intelligence/news categories.

    Uses ``feedparser`` to parse RSS/Atom feeds fetched via the shared HTTP
    fetcher. Feeds within each category are fetched in parallel.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        category: Optional category key (geopolitics, security, technology,
                  finance, military, science). If None, fetches all categories.
        limit: Maximum number of items to return.

    Returns:
        Dict with items list, count, categories fetched, source, and timestamp.
    """
    if feedparser is None:
        return {
            "error": "feedparser not installed — run: pip install feedparser",
            "items": [],
            "count": 0,
        }

    now = datetime.now(timezone.utc)

    # Determine which categories to fetch
    if category is not None:
        if category not in _RSS_FEEDS:
            return {
                "items": [],
                "count": 0,
                "categories_fetched": [],
                "error": f"Unknown category '{category}'. Valid: {list(_RSS_FEEDS.keys())}",
                "source": "rss-aggregator",
                "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        categories_to_fetch = {category: _RSS_FEEDS[category]}
    else:
        categories_to_fetch = dict(_RSS_FEEDS)

    all_items: list[dict] = []

    async def _fetch_single_feed(
        feed_name: str,
        url: str,
        cat: str,
    ) -> list[dict]:
        """Fetch and parse a single RSS feed, returning extracted items."""
        safe_name = feed_name.lower().replace(" ", "_")
        xml_text = await fetcher.get_xml(
            url,
            source=f"rss:{safe_name}",
            cache_key=f"news:rss:{safe_name}",
            cache_ttl=300,
        )

        if xml_text is None:
            logger.debug("No data from RSS feed %s (%s)", feed_name, url)
            return []

        parsed = feedparser.parse(xml_text)
        items: list[dict] = []

        for entry in parsed.get("entries", []):
            published = _parse_published(entry)
            summary_raw = entry.get("summary") or entry.get("description") or ""
            items.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": published,
                "summary": _truncate(summary_raw, 200),
                "feed_name": feed_name,
                "category": cat,
                "source_tier": SOURCE_TIERS.get(feed_name, "unknown"),
            })

        return items

    # Fetch all feeds within each category in parallel
    for cat, feeds in categories_to_fetch.items():
        tasks = [
            _fetch_single_feed(feed_name, url, cat)
            for feed_name, url in feeds
        ]
        results = await asyncio.gather(*tasks)
        for items in results:
            all_items.extend(items)

    # Sort by published date descending (entries without dates go last)
    all_items.sort(
        key=lambda item: item.get("published") or "",
        reverse=True,
    )

    # Apply limit
    all_items = all_items[:limit]

    return {
        "items": all_items,
        "count": len(all_items),
        "categories_fetched": list(categories_to_fetch.keys()),
        "source": "rss-aggregator",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Function 2: Keyword Trending / Spike Detection
# ---------------------------------------------------------------------------

async def fetch_trending_keywords(
    fetcher: Fetcher,
    hours: int = 6,
    min_count: int = 3,
) -> dict:
    """Detect trending keywords from recent news headlines.

    Fetches up to 200 recent news items via ``fetch_news_feed``, extracts
    words from titles, removes stopwords and short tokens, and returns the
    most frequently occurring keywords sorted by count.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        hours: Not used for time-windowing (RSS feeds are inherently recent),
               but kept for API symmetry with other source functions.
        min_count: Minimum occurrences for a keyword to be included.

    Returns:
        Dict with keywords list (word + count), total items analyzed,
        source, and timestamp.
    """
    now = datetime.now(timezone.utc)

    # Fetch a broad set of recent items
    feed_data = await fetch_news_feed(fetcher, limit=200)
    items = feed_data.get("items", [])

    # Count word frequencies across all titles
    word_counts: dict[str, int] = {}
    for item in items:
        title = item.get("title") or ""
        # Lowercase, strip punctuation, split into words
        cleaned = _PUNCT_RE.sub(" ", title.lower())
        words = cleaned.split()
        for word in words:
            word = word.strip()
            if len(word) < 3:
                continue
            if word in _STOPWORDS:
                continue
            word_counts[word] = word_counts.get(word, 0) + 1

    # Filter by min_count and sort descending
    keywords = [
        {"word": word, "count": count}
        for word, count in word_counts.items()
        if count >= min_count
    ]
    keywords.sort(key=lambda k: k["count"], reverse=True)

    # Return top 50
    keywords = keywords[:50]

    return {
        "keywords": keywords,
        "total_items_analyzed": len(items),
        "source": "keyword-analysis",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Function 3: GDELT 2.0 Doc API Search
# ---------------------------------------------------------------------------

async def fetch_gdelt_search(
    fetcher: Fetcher,
    query: str = "conflict",
    mode: str = "artlist",
    limit: int = 50,
) -> dict:
    """Search the GDELT 2.0 Doc API for articles or volume timelines.

    No API key required. Supports article list and timeline volume modes.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        query: Search query string.
        mode: Either ``artlist`` (article list) or ``timelinevol``
              (volume timeline).
        limit: Maximum number of records (artlist mode).

    Returns:
        Dict with articles/timeline data, count, query info, source,
        and timestamp.
    """
    now = datetime.now(timezone.utc)

    params: dict = {
        "query": query,
        "mode": mode,
        "maxrecords": limit,
        "format": "json",
    }

    safe_query = re.sub(r"[^a-zA-Z0-9_-]", "_", query)[:64]
    data = await fetcher.get_json(
        _GDELT_DOC_URL,
        source="gdelt",
        cache_key=f"news:gdelt:{safe_query}:{mode}",
        cache_ttl=600,
        params=params,
    )

    if data is None:
        logger.warning("GDELT API returned no data for query=%s mode=%s", query, mode)
        return {
            "articles": [] if mode == "artlist" else None,
            "timeline": None if mode == "artlist" else [],
            "count": 0,
            "query": query,
            "mode": mode,
            "source": "gdelt",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    if mode == "artlist":
        articles = []
        for article in data.get("articles", []):
            articles.append({
                "title": article.get("title"),
                "url": article.get("url"),
                "seendate": article.get("seendate"),
                "socialimage": article.get("socialimage"),
                "domain": article.get("domain"),
                "language": article.get("language"),
                "sourcecountry": article.get("sourcecountry"),
            })

        return {
            "articles": articles,
            "count": len(articles),
            "query": query,
            "mode": mode,
            "source": "gdelt",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # timelinevol mode — return timeline data as-is
    timeline = data.get("timeline", [])
    return {
        "timeline": timeline,
        "count": len(timeline) if isinstance(timeline, list) else 0,
        "query": query,
        "mode": mode,
        "source": "gdelt",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
