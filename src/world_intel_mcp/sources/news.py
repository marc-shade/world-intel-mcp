"""RSS news aggregation, keyword trending, and GDELT search for world-intel-mcp.

Provides multi-category RSS feed aggregation from 20+ high-quality intelligence
and news sources, keyword spike detection from recent headlines, and full-text
search via the GDELT 2.0 Doc API. No API keys required.
"""

import asyncio
import functools
import hashlib
import json
import logging
import re
import string
from datetime import datetime, timezone

from ..fetcher import Fetcher
from .freshness import json_answer_freshness

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
        (
            "Reuters World",
            "https://news.google.com/rss/search?q=source:Reuters&hl=en-US&gl=US&ceid=US:en",
        ),
        ("The Guardian World", "https://www.theguardian.com/world/rss"),
        ("DW News", "https://rss.dw.com/xml/rss-en-top"),
        ("France24", "https://www.france24.com/en/rss"),
        ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
        ("VOA News", "https://www.voanews.com/api/zyrttemnuq"),
    ],
    "security": [
        ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
        ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
        ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
        ("Schneier on Security", "https://www.schneier.com/feed/atom/"),
        ("Dark Reading", "https://www.darkreading.com/rss.xml"),
        ("CISA Alerts", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
        ("The Record", "https://therecord.media/feed"),
        ("Security Week", "https://www.securityweek.com/feed/"),
    ],
    "technology": [
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Wired", "https://www.wired.com/feed/rss"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("The Register", "https://www.theregister.com/headlines.atom"),
    ],
    "finance": [
        (
            "CNBC",
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        ),
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
        (
            "Military Times",
            "https://www.militarytimes.com/arc/outboundfeeds/rss/?outputType=xml",
        ),
        ("USNI News", "https://news.usni.org/feed"),
    ],
    "science": [
        ("Nature", "https://www.nature.com/nature.rss"),
        (
            "Science",
            "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
        ),
        ("Phys.org", "https://phys.org/rss-feed/"),
        ("New Scientist", "https://www.newscientist.com/feed/home/"),
        ("Scientific American", "https://www.scientificamerican.com/platform/syndication/rss/"),
        ("SpaceNews", "https://spacenews.com/feed/"),
    ],
    "think_tanks": [
        ("RAND", "https://www.rand.org/blog.xml"),
        ("Brookings", "https://www.brookings.edu/feed/"),
        ("Carnegie", "https://carnegieendowment.org/rss/solr.xml"),
        ("CFR", "https://www.cfr.org/feed"),
        ("CSIS", "https://www.csis.org/rss/all"),
        ("Atlantic Council", "https://www.atlanticcouncil.org/feed/"),
        ("Chatham House", "https://www.chathamhouse.org/path/83/feed.xml"),
    ],
    "middle_east": [
        ("Middle East Eye", "https://www.middleeasteye.net/rss"),
        (
            "The National UAE",
            "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml",
        ),
        ("Times of Israel", "https://www.timesofisrael.com/feed/"),
        ("Iran Intl", "https://www.iranintl.com/en/feed"),
    ],
    "asia_pacific": [
        ("SCMP", "https://www.scmp.com/rss/91/feed"),
        ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar"),
        ("The Diplomat", "https://thediplomat.com/feed/"),
        (
            "Channel News Asia",
            "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml",
        ),
        ("Lowy Interpreter", "https://www.lowyinstitute.org/the-interpreter/rss.xml"),
    ],
    "africa": [
        ("allAfrica", "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf"),
        ("The Africa Report", "https://www.theafricareport.com/feed/"),
        ("African Arguments", "https://africanarguments.org/feed/"),
        ("ISS Africa", "https://issafrica.org/iss-today/feed"),
        ("Daily Maverick", "https://www.dailymaverick.co.za/rss"),
    ],
    "latin_america": [
        ("MercoPress", "https://en.mercopress.com/rss"),
        ("Dialogo Americas", "https://dialogo-americas.com/feed/"),
        ("Americas Quarterly", "https://www.americasquarterly.org/feed/"),
        ("Buenos Aires Times", "https://www.batimes.com.ar/feed"),
        ("Tico Times", "https://ticotimes.net/feed"),
        ("InSight Crime", "https://insightcrime.org/feed/"),
        ("Brazil Reports", "https://brazilian.report/feed/"),
        ("Mexico News Daily", "https://mexiconewsdaily.com/feed/"),
    ],
    "multilingual": [
        ("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml"),
        ("DW Español", "https://rss.dw.com/xml/rss-sp-top"),
        ("DW Deutsch", "https://rss.dw.com/xml/rss-de-top"),
        ("France24 Français", "https://www.france24.com/fr/rss"),
        ("RFI Français", "https://www.rfi.fr/fr/rss"),
        ("UN News Español", "https://news.un.org/feed/subscribe/es/news/all/rss.xml"),
        ("UN News Français", "https://news.un.org/feed/subscribe/fr/news/all/rss.xml"),
    ],
    "energy": [
        ("Oil Price", "https://oilprice.com/rss/main"),
        ("Rigzone", "https://www.rigzone.com/news/rss/rigzone_latest.aspx"),
        ("Utility Dive", "https://www.utilitydive.com/feeds/news/"),
        ("Carbon Brief", "https://www.carbonbrief.org/feed/"),
        ("CleanTechnica", "https://cleantechnica.com/feed/"),
    ],
    "government": [
        ("State Dept", "https://www.state.gov/rss-feed/press-releases/feed/"),
        (
            "DoD News",
            "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10",
        ),
        ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
        ("White House", "https://www.whitehouse.gov/news/feed/"),
    ],
    "crisis": [
        ("ReliefWeb", "https://reliefweb.int/updates/rss.xml"),
        ("ICG", "https://www.crisisgroup.org/rss.xml"),
        ("Amnesty Intl", "https://www.amnesty.org/en/feed/"),
        ("HRW", "https://www.hrw.org/rss/news"),
    ],
    "europe": [
        ("EurActiv", "https://www.euractiv.com/feed/"),
        ("Politico EU", "https://www.politico.eu/feed/"),
        ("EU Observer", "https://euobserver.com/rss"),
        ("DW Europe", "https://rss.dw.com/xml/rss-en-eu"),
    ],
    "south_asia": [
        ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
        ("Dawn Pakistan", "https://www.dawn.com/feeds/home"),
        ("Scroll India", "https://scroll.in/feed"),
    ],
    "health": [
        ("STAT News", "https://www.statnews.com/feed/"),
        ("WHO News", "https://www.who.int/rss-feeds/news-english.xml"),
        ("Medical Xpress", "https://medicalxpress.com/rss-feed/"),
        ("The Lancet", "https://www.thelancet.com/rssfeed/lancet_current.xml"),
    ],
    "central_asia": [
        ("Eurasianet", "https://eurasianet.org/rss"),
        ("The Astana Times", "https://astanatimes.com/feed/"),
        ("Radio Free Europe", "https://www.rferl.org/api/zyrttemnuq"),
    ],
    "arctic": [
        ("The Barents Observer", "https://thebarentsobserver.com/en/rss.xml"),
        ("Arctic Today", "https://www.arctictoday.com/feed/"),
        ("High North News", "https://www.highnorthnews.com/en/rss.xml"),
    ],
    "maritime": [
        ("Maritime Executive", "https://maritime-executive.com/articles.rss"),
        ("gCaptain", "https://gcaptain.com/feed/"),
        ("Lloyd's List", "https://lloydslist.maritimeintelligence.informa.com/rss/all"),
    ],
    "space": [
        ("SpaceRef", "https://spaceref.com/feed/"),
        ("NASASpaceFlight", "https://www.nasaspaceflight.com/feed/"),
        ("Space.com", "https://www.space.com/feeds/all"),
    ],
    "nuclear": [
        ("World Nuclear News", "https://world-nuclear-news.org/rss"),
        ("Arms Control Assn", "https://www.armscontrol.org/rss.xml"),
        ("Nuclear Threat Initiative", "https://www.nti.org/feed/"),
    ],
    "climate": [
        ("Climate Home News", "https://www.climatechangenews.com/feed/"),
        ("InsideClimate News", "https://insideclimatenews.org/feed/"),
        ("E&E News", "https://www.eenews.net/feed/"),
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
    "InSight Crime": "specialty",
    "Brazil Reports": "specialty",
    "Mexico News Daily": "specialty",
    "BBC Mundo": "major",
    "DW Español": "major",
    "DW Deutsch": "major",
    "France24 Français": "major",
    "RFI Français": "major",
    "UN News Español": "government",
    "UN News Français": "government",
    "Nikkei Asia": "major",
    "The National UAE": "major",
    "Zero Hedge": "aggregator",
    # Phase 15 additions
    "NPR World": "major",
    "VOA News": "government",
    "The Record": "specialty",
    "Security Week": "specialty",
    "Scientific American": "major",
    "SpaceNews": "specialty",
    "CFR": "think_tank",
    "CSIS": "think_tank",
    "Atlantic Council": "think_tank",
    "Chatham House": "think_tank",
    "The Africa Report": "specialty",
    "African Arguments": "specialty",
    "ISS Africa": "think_tank",
    "Daily Maverick": "major",
    "Carbon Brief": "specialty",
    "CleanTechnica": "specialty",
    "EurActiv": "specialty",
    "Politico EU": "major",
    "EU Observer": "specialty",
    "DW Europe": "major",
    "NDTV": "major",
    "Dawn Pakistan": "major",
    "Scroll India": "specialty",
    "STAT News": "specialty",
    "WHO News": "intl_org",
    "Medical Xpress": "specialty",
    "Amnesty Intl": "intl_org",
    "HRW": "intl_org",
    "The Register": "specialty",
    "White House": "government",
    # Phase 16 additions
    "The Lancet": "major",
    "Eurasianet": "specialty",
    "The Astana Times": "specialty",
    "Radio Free Europe": "government",
    "The Barents Observer": "specialty",
    "Arctic Today": "specialty",
    "High North News": "specialty",
    "Maritime Executive": "specialty",
    "gCaptain": "specialty",
    "Lloyd's List": "specialty",
    "SpaceRef": "specialty",
    "NASASpaceFlight": "specialty",
    "Space.com": "major",
    "World Nuclear News": "specialty",
    "Arms Control Assn": "think_tank",
    "Nuclear Threat Initiative": "think_tank",
    "Climate Home News": "specialty",
    "InsideClimate News": "specialty",
    "E&E News": "specialty",
}

# Feeds that are sister editions of one publisher. Story breadth counts
# outlets, not feeds: BBC World and BBC Mundo carrying a story is one
# outlet's coverage. Feeds not listed are their own outlet.
FEED_OUTLETS: dict[str, str] = {
    "BBC World": "BBC",
    "BBC Mundo": "BBC",
    "DW News": "DW",
    "DW Español": "DW",
    "DW Deutsch": "DW",
    "DW Europe": "DW",
    "France24": "France 24",
    "France24 Français": "France 24",
    "UN News": "UN News",
    "UN News Español": "UN News",
    "UN News Français": "UN News",
}


def outlet_for(feed_name: str) -> str:
    """The publisher behind a feed name (the feed name itself if unmapped)."""
    return FEED_OUTLETS.get(feed_name, feed_name)


_STOPWORDS: set[str] = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "and",
    "or",
    "but",
    "nor",
    "not",
    "no",
    "so",
    "yet",
    "both",
    "either",
    "neither",
    "with",
    "from",
    "by",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "over",
    "about",
    "against",
    "out",
    "off",
    "up",
    "down",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "any",
    "few",
    "more",
    "most",
    "some",
    "such",
    "only",
    "own",
    "same",
    "than",
    "too",
    "very",
    "just",
    "also",
    "now",
    "it",
    "its",
    "he",
    "she",
    "they",
    "them",
    "their",
    "his",
    "her",
    "we",
    "you",
    "your",
    "our",
    "my",
    "me",
    "him",
    "us",
    "that",
    "this",
    "these",
    "those",
    "which",
    "who",
    "whom",
    "what",
    "if",
    "while",
    "because",
    "until",
    "although",
    "since",
    "whether",
    "new",
    "says",
    "said",
    "one",
    "two",
    "first",
    "last",
    "many",
    "much",
    "get",
    "got",
    "back",
    "even",
    "still",
    "well",
    "way",
    "s",
    "t",
    "re",
    "ve",
    "d",
    "ll",
    "m",
}

_GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT's TLS handshake is slow and erratic: measured 2026-09-02 at
# 19.7 s, 17.4 s, then >45 s across three samples (TCP connect 0.03 s;
# Nominatim and USGS handshake in 0.05 s on the same network). The
# Fetcher's 15 s default counts TLS inside the connect phase, so every
# live GDELT fetch was a ConnectTimeout that stale cache then hid.
# Shared by every GDELT call site.
GDELT_TIMEOUT = 45.0

# Regex to strip punctuation from words
_PUNCT_RE = re.compile(f"[{re.escape(string.punctuation)}]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_published(entry: dict) -> str | None:
    """Parse an RSS entry's published date to ISO 8601 UTC string.

    feedparser stores the parsed time struct in ``published_parsed``, in
    UTC. ``calendar.timegm`` reads it as UTC; ``time.mktime`` (used before
    2026-10-17) read it as local time and shifted every stamp by the host's
    standard UTC offset (the struct carries tm_isdst=0). Falls back to the
    raw ``published`` string if parsing fails.
    """
    from calendar import timegm

    parsed_tuple = entry.get("published_parsed")
    if parsed_tuple is not None:
        try:
            epoch = timegm(parsed_tuple[:9])
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError, OverflowError):
            pass

    # Fallback: try updated_parsed
    updated_tuple = entry.get("updated_parsed")
    if updated_tuple is not None:
        try:
            epoch = timegm(updated_tuple[:9])
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


# Feed titles are upstream text: capped like summaries, at a length no real
# headline reaches.
_MAX_TITLE_CHARS = 500

# A partial RSS outage is marked degraded when fewer than this share of the
# attempted feeds answered live. Measured 2026-10-17: 95 of 119 feeds (80 %)
# answered, and the 24 that did not were permanent (16 x 404, 6 x 403, one
# 410) plus one timeout, so the normal state stays unflagged with margin;
# below half, a result rests on a minority of its feeds.
_MIN_LIVE_FEED_SHARE = 0.5


def _web_link(value: object) -> str:
    """The link if it is an http(s) URL, else "" (javascript:, data:, relative)."""
    if not isinstance(value, str):
        return ""
    link = value.strip()
    return link if link.lower().startswith(("http://", "https://")) else ""


# ---------------------------------------------------------------------------
# Function 1: RSS News Feed Aggregation
# ---------------------------------------------------------------------------

# In-flight all-feeds reads, keyed by (fetcher, event loop, feed set);
# an entry lives only while its read runs.
_INFLIGHT_READS: dict[tuple, asyncio.Future] = {}


def _release_read(key: tuple, task: asyncio.Future) -> None:
    if _INFLIGHT_READS.get(key) is task:
        del _INFLIGHT_READS[key]
    if not task.cancelled():
        # Retrieved here so a read every caller abandoned never logs
        # "exception was never retrieved"; awaiting callers still get it.
        task.exception()


def _stale_serves(fetcher: Fetcher, source: str) -> int:
    """How many times the fetcher has served ``source`` from an expired copy.

    Text payloads carry no inline ``_stale`` marker (fetcher._stale_fallback
    counts them on the breaker instead), so a change in this count across
    one fetch is the only sign that a feed came back as old cached XML.
    """
    count = fetcher.breaker.status().get(source, {}).get("total_stale_serves", 0)
    return count if isinstance(count, int) else 0


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
        Dict with items list, count, categories fetched, source, and timestamp,
        plus feeds_attempted/feeds_ok/feeds_failed/feeds_stale. ``degraded``
        and ``reason`` mark an outage: ``all_feeds_failed`` (with ``error``)
        when no feed answered live, ``partial_feeds_failed`` (no error) when
        fewer than half did. Links are kept only when they are http(s).
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
    # Feeds whose fetch failed or timed out. A dead feed used to contribute
    # an empty list exactly like a quiet one, so a full outage read as a
    # slow news day (ROADMAP Phase 24.5).
    failed_feeds: list[str] = []
    # Feeds whose live fetch failed but came back as an expired cached copy.
    # In a running deployment the cache is warm, so an outage mostly looks
    # like this, not like failed_feeds.
    stale_feeds: list[str] = []

    async def _fetch_single_feed(
        feed_name: str,
        url: str,
        cat: str,
    ) -> list[dict]:
        """Fetch and parse a single RSS feed, returning extracted items."""
        safe_name = feed_name.lower().replace(" ", "_")
        source = f"rss:{safe_name}"
        stale_before = _stale_serves(fetcher, source)
        xml_text = await fetcher.get_xml(
            url,
            source=source,
            cache_key=f"news:rss:{safe_name}",
            cache_ttl=300,
            timeout=8.0,
        )

        if xml_text is None:
            logger.debug("No data from RSS feed %s (%s)", feed_name, url)
            failed_feeds.append(feed_name)
            return []
        if _stale_serves(fetcher, source) > stale_before:
            stale_feeds.append(feed_name)

        parsed = feedparser.parse(xml_text)
        items: list[dict] = []

        for entry in parsed.get("entries", []):
            published = _parse_published(entry)
            summary_raw = entry.get("summary") or entry.get("description") or ""
            items.append(
                {
                    "title": _truncate(entry.get("title", ""), _MAX_TITLE_CHARS),
                    "link": _web_link(entry.get("link", "")),
                    "published": published,
                    "summary": _truncate(summary_raw, 200),
                    "feed_name": feed_name,
                    "category": cat,
                    "source_tier": SOURCE_TIERS.get(feed_name, "unknown"),
                }
            )

        return items

    async def _safe_fetch(feed_name: str, url: str, cat: str) -> list[dict]:
        """Wrap single feed fetch with a hard timeout."""
        try:
            return await asyncio.wait_for(
                _fetch_single_feed(feed_name, url, cat),
                timeout=12.0,
            )
        except asyncio.TimeoutError:
            logger.debug("RSS feed %s timed out", feed_name)
            failed_feeds.append(feed_name)
            return []

    # Fetch feeds with concurrency cap to avoid saturating the httpx pool.
    # Without this, 119 RSS feeds + other source calls exceed the 50-connection
    # pool limit, causing cascade timeouts across the entire dashboard.
    sem = asyncio.Semaphore(25)

    async def _throttled(feed_name: str, url: str, cat: str) -> list[dict]:
        async with sem:
            return await _safe_fetch(feed_name, url, cat)

    async def _read_all() -> tuple[list[list[dict]], list[str], list[str]]:
        results = await asyncio.gather(
            *(
                _throttled(feed_name, url, cat)
                for cat, feeds in categories_to_fetch.items()
                for feed_name, url in feeds
            )
        )
        return results, sorted(failed_feeds), sorted(stale_feeds)

    # Concurrent reads of one feed set share a single fetch per feed: the
    # collector starts news_feed, trending_keywords, situations and
    # top_stories in one gather, and each used to request every feed.
    # shield() keeps a caller's cancellation (a per-source timeout) from
    # cancelling the read the other callers are waiting on.
    key = (id(fetcher), id(asyncio.get_running_loop()), tuple(categories_to_fetch))
    shared = _INFLIGHT_READS.get(key)
    if shared is None:
        shared = asyncio.ensure_future(_read_all())
        _INFLIGHT_READS[key] = shared
        shared.add_done_callback(functools.partial(_release_read, key))
    results, failed, stale = await asyncio.shield(shared)
    for items in results:
        # Copies: concurrent callers must not share mutable item dicts.
        all_items.extend(dict(item) for item in items)

    # Sort by published date descending (entries without dates go last)
    all_items.sort(
        key=lambda item: item.get("published") or "",
        reverse=True,
    )

    # Apply limit
    all_items = all_items[:limit]

    feeds_attempted = sum(len(feeds) for feeds in categories_to_fetch.values())
    result: dict = {
        "items": all_items,
        "count": len(all_items),
        "categories_fetched": list(categories_to_fetch.keys()),
        "feeds_attempted": feeds_attempted,
        "feeds_ok": feeds_attempted - len(failed) - len(stale),
        "feeds_failed": failed,
        # Served from an expired cached copy after a failed fetch: their
        # items are kept (each carries its own publish time) but are old.
        "feeds_stale": stale,
        "source": "rss-aggregator",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if feeds_attempted and result["feeds_ok"] == 0:
        # No feed answered live: an outage, never "no news", whether or not
        # old cached copies filled in. The items list keeps the normal shape
        # so callers that only iterate still work.
        error = f"All {feeds_attempted} RSS feeds failed or timed out"
        if stale:
            error += f" ({len(stale)} served from an expired cache copy)"
        result["error"] = error
        result["degraded"] = True
        result["reason"] = "all_feeds_failed"
    elif feeds_attempted and result["feeds_ok"] / feeds_attempted < _MIN_LIVE_FEED_SHARE:
        # Most feeds failed: items still flow (no error), but the result
        # rests on a minority of the feeds and says so.
        result["degraded"] = True
        result["reason"] = "partial_feeds_failed"
    return result


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
        source, and timestamp, plus the feed counts and any outage marker
        (error/degraded/reason) of the underlying ``fetch_news_feed`` read.
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

    result = {
        "keywords": keywords,
        "total_items_analyzed": len(items),
        "source": "keyword-analysis",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # An RSS outage is not "nothing trending", and a partial one says how
    # many feeds the counts rest on.
    for key in (
        "feeds_attempted", "feeds_ok", "feeds_failed", "feeds_stale",
        "error", "degraded", "reason",
    ):
        if key in feed_data:
            result[key] = feed_data[key]
    return result


# ---------------------------------------------------------------------------
# Function 3: GDELT 2.0 Doc API Search
# ---------------------------------------------------------------------------


def _gdelt_cache_key(params: dict) -> str:
    """Cache key for one GDELT request: a readable prefix plus a digest of
    every request parameter. The prefix alone (the query reduced to ASCII
    letters, digits, ``_`` and ``-``, cut to 64 characters) maps different
    non-Latin queries to one string ("Київ" and "Суми" both become
    ``______``) and leaves out ``maxrecords``, so one search was answered
    from another's cache entry."""
    safe_query = re.sub(r"[^a-zA-Z0-9_-]", "_", str(params["query"]))[:64]
    digest = hashlib.sha256(
        json.dumps(params, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"news:gdelt:{safe_query}:{params['mode']}:{digest}"


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
        timestamp and ``fetched_at`` (when GDELT answered; earlier than
        ``timestamp`` for a cached answer). An expired cached copy served
        because GDELT did not answer carries ``_stale`` and
        ``_stale_age_seconds``.
    """
    now = datetime.now(timezone.utc)

    params: dict = {
        "query": query,
        "mode": mode,
        "maxrecords": limit,
        "format": "json",
    }

    cache_key = _gdelt_cache_key(params)
    data = await fetcher.get_json(
        _GDELT_DOC_URL,
        source="gdelt",
        cache_key=cache_key,
        cache_ttl=600,
        params=params,
        timeout=GDELT_TIMEOUT,
    )

    if data is None:
        logger.warning("GDELT API returned no data for query=%s mode=%s", query, mode)
        # A live fetch failure (GDELT rate limits at roughly one request per
        # 5 seconds, plus 500s and malformed payloads) must not be
        # byte-identical to a genuine zero-hit search, same class as the
        # ACLED defect fixed in #3. Keep articles/timeline/count in their
        # normal empty shape so existing callers that don't check "error"
        # or "degraded" still iterate an empty list rather than crashing.
        return {
            "error": "GDELT fetch failed (rate limited, API error, or malformed response)",
            "degraded": True,
            "reason": "gdelt_fetch_failed",
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
            articles.append(
                {
                    "title": article.get("title"),
                    "url": article.get("url"),
                    "seendate": article.get("seendate"),
                    "socialimage": article.get("socialimage"),
                    "domain": article.get("domain"),
                    "language": article.get("language"),
                    "sourcecountry": article.get("sourcecountry"),
                }
            )

        return {
            "articles": articles,
            "count": len(articles),
            "query": query,
            "mode": mode,
            "source": "gdelt",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            **json_answer_freshness(fetcher, cache_key, data),
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
        **json_answer_freshness(fetcher, cache_key, data),
    }
