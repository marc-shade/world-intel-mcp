"""Comprehensive country intelligence dossier.

Aggregates data from multiple sources into a single country profile:
country brief (World Bank + ACLED), stock index, election calendar,
sanctions exposure, news mentions, and associated hotspots/conflict zones.

All sub-queries are run in parallel for speed.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger("world-intel-mcp.analysis.dossier")

# Mentions listed in the news section; the match count is not capped.
_MAX_MENTIONS = 15

# Compound names that contain a tier-1 keyword but name somewhere else.
# They are removed before the whole-word keyword test (checked 2026-10-17
# against headlines the plain keyword test counted for the wrong country).
_COMPOUND_EXCLUSIONS: dict[str, re.Pattern[str]] = {
    "SDN": re.compile(r"\bsouth sudan\w*"),
    "IND": re.compile(r"\bindian oceans?\b"),
    "USA": re.compile(r"\b(?:latin|south|central|north) americans?\b"),
    "MEX": re.compile(r"\bnew mexic\w*"),
}

_MATCH_METHOD = (
    "whole-word match of each headline against the country's tier-1 keywords "
    "(name, demonym, capital), each allowed an -n, -ns or -s ending on its last "
    "word ('North Koreans', 'Gazan', 'Afghans'), so 'Tirana' is not Iran and "
    "'Indiana' is not India; South Sudan, the Indian "
    "Ocean, Latin/South/Central/North American and New Mexico are removed "
    "first. Other compound names still count (Lagos in Portugal, the Republic "
    "of the Congo). Searched: the newest items across every RSS feed."
)


@functools.lru_cache(maxsize=None)
def _keyword_pattern(iso3: str) -> re.Pattern[str] | None:
    from ..config.countries import TIER1_COUNTRIES

    keywords = (TIER1_COUNTRIES.get(iso3) or {}).get("keywords") or []
    if not keywords:
        return None
    # The keyword table lists names and some demonyms, not every form:
    # "north korea" must also find "North Korean(s)", "gaza" "Gazan(s)".
    parts = [
        re.escape(kw.lower()) + "(?:n|ns|s)?"
        for kw in sorted(keywords, key=len, reverse=True)
    ]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b")


def _utc_stamp(value: object) -> datetime | None:
    """A feed item's published time if it is the feed's ISO UTC form."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso_z(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _names_country(title: str, iso3: str) -> bool:
    """Whether a headline names the tier-1 country ``iso3`` (whole words)."""
    pattern = _keyword_pattern(iso3)
    if pattern is None:
        return False
    text = (title or "").lower()
    exclusion = _COMPOUND_EXCLUSIONS.get(iso3)
    if exclusion is not None:
        text = exclusion.sub(" ", text)
    return pattern.search(text) is not None

# Minimal ISO-2 <-> ISO-3 mapping for the 22 tier-1 countries + major extras.
_ISO2_TO_ISO3: dict[str, str] = {
    "US": "USA", "CN": "CHN", "RU": "RUS", "UA": "UKR", "SY": "SYR",
    "YE": "YEM", "MM": "MMR", "SD": "SDN", "NG": "NGA", "AF": "AFG",
    "IQ": "IRQ", "IR": "IRN", "TW": "TWN", "KP": "PRK", "IL": "ISR",
    "PS": "PSE", "LB": "LBN", "ET": "ETH", "CD": "COD", "PK": "PAK",
    "IN": "IND", "MX": "MEX", "GB": "GBR", "DE": "DEU", "FR": "FRA",
    "JP": "JPN", "KR": "KOR", "BR": "BRA", "AU": "AUS", "CA": "CAN",
    "SA": "SAU", "TR": "TUR", "EG": "EGY", "ZA": "ZAF", "ID": "IDN",
    "TH": "THA", "VN": "VNM", "PH": "PHL", "PL": "POL", "IT": "ITA",
    "ES": "ESP", "SE": "SWE", "NO": "NOR", "CH": "CHE", "NL": "NLD",
    "BE": "BEL", "AR": "ARG", "CL": "CHL", "CO": "COL", "PE": "PER",
}
_ISO3_TO_ISO2: dict[str, str] = {v: k for k, v in _ISO2_TO_ISO3.items()}

# English names for the codes above that are not tier-1 countries (those
# carry their own name in TIER1_COUNTRIES). Used to screen the SDN list.
_EXTRA_COUNTRY_NAMES: dict[str, str] = {
    "ARG": "Argentina", "AUS": "Australia", "BEL": "Belgium", "BRA": "Brazil",
    "CAN": "Canada", "CHE": "Switzerland", "CHL": "Chile", "COL": "Colombia",
    "DEU": "Germany", "EGY": "Egypt", "ESP": "Spain", "FRA": "France",
    "GBR": "United Kingdom", "IDN": "Indonesia", "ITA": "Italy", "JPN": "Japan",
    "KOR": "Korea, South", "NLD": "Netherlands", "NOR": "Norway", "PER": "Peru",
    "PHL": "Philippines", "POL": "Poland", "SAU": "Saudi Arabia", "SWE": "Sweden",
    "THA": "Thailand", "TUR": "Turkey", "VNM": "Vietnam", "ZAF": "South Africa",
}

# Entries listed in the sanctions section.
_SANCTIONS_LIMIT = 10

_SANCTIONS_METHOD = (
    "OFAC SDN entries whose remarks name the country (nationality, citizenship, "
    "address, registration), substring match on the English country name. Not "
    "an exposure screen: entries tied to the country in other ways are missed, "
    "and a name inside another also matches (Niger in Nigeria, Sudan in South Sudan). "
    "total_entities is the number of SDN rows read before the search stopped, "
    "not the size of the list."
)


def _normalize_country(code: str) -> tuple[str, str]:
    """Return (iso2, iso3) from either format. Raises ValueError if unknown."""
    code = code.upper().strip()
    if len(code) == 2:
        iso2 = code
        iso3 = _ISO2_TO_ISO3.get(code)
        if iso3 is None:
            raise ValueError(f"Unknown ISO-2 code: {code}")
        return iso2, iso3
    if len(code) == 3:
        iso3 = code
        iso2 = _ISO3_TO_ISO2.get(code)
        if iso2 is None:
            raise ValueError(f"Unknown ISO-3 code: {code}")
        return iso2, iso3
    raise ValueError(f"Country code must be 2 or 3 characters: {code}")


def _sanctions_country_name(iso3: str) -> str:
    from ..config.countries import TIER1_COUNTRIES

    return (TIER1_COUNTRIES.get(iso3) or {}).get("name") or _EXTRA_COUNTRY_NAMES[iso3]


async def _safe(coro, label: str) -> dict:
    """Run a coroutine, catching exceptions."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("Dossier: %s failed: %s", label, exc)
        return {"_error": str(exc)}


async def fetch_country_dossier(
    fetcher,
    country: str = "US",
) -> dict:
    """Build a comprehensive country intelligence dossier.

    Pulls from 6 sources in parallel:
      1. Country brief (World Bank GDP/inflation + ACLED conflict)
      2. Stock market index (Yahoo Finance)
      3. Election calendar (curated dataset)
      4. Sanctions exposure (OFAC SDN search)
      5. Recent news mentions (RSS feeds)
      6. Country config (baseline risk, hotspots, conflict zones)

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        country: ISO-2 or ISO-3 country code (e.g. "US", "USA", "UA", "UKR").

    Returns:
        Dict with sections: overview, economy, markets, elections, sanctions,
        news, security, and metadata.
    """
    now = datetime.now(timezone.utc)

    try:
        iso2, iso3 = _normalize_country(country)
    except ValueError as exc:
        return {
            "error": str(exc),
            "hint": "Use ISO-2 (US, UA) or ISO-3 (USA, UKR) codes",
            "source": "country-dossier",
            "timestamp": now.isoformat(),
        }

    # Lazy imports to avoid circular deps
    from ..sources.intelligence import fetch_country_brief
    from ..sources.markets import fetch_country_stocks
    from ..sources.elections import fetch_election_calendar
    from ..sources.sanctions import fetch_sanctions_search
    from ..sources.news import fetch_news_feed
    from ..config.countries import TIER1_COUNTRIES, INTEL_HOTSPOTS, CONFLICT_ZONES

    # Run all data fetches in parallel
    (
        brief_data,
        stock_data,
        election_data,
        sanctions_data,
        news_data,
    ) = await asyncio.gather(
        _safe(fetch_country_brief(fetcher, country_code=iso2), "country_brief"),
        _safe(fetch_country_stocks(fetcher, country=iso3), "country_stocks"),
        _safe(fetch_election_calendar(fetcher, country=iso3), "elections"),
        _safe(
            fetch_sanctions_search(
                fetcher,
                country=_sanctions_country_name(iso3),
                limit=_SANCTIONS_LIMIT + 1,
                us_lists=False,
            ),
            "sanctions",
        ),
        _safe(fetch_news_feed(fetcher, category=None, limit=200), "news_feed"),
    )

    # --- Section 1: Overview ---
    country_config = TIER1_COUNTRIES.get(iso3, {})
    country_name = country_config.get("name", iso3)

    overview = {
        "country": country_name,
        "iso2": iso2,
        "iso3": iso3,
        "baseline_risk": country_config.get("baseline_risk"),
        "event_multiplier": country_config.get("event_multiplier"),
    }

    # --- Section 2: Economy (from country brief) ---
    economy = {}
    if "_error" not in brief_data:
        supporting = brief_data.get("supporting_data", {})
        economy = {
            "gdp": supporting.get("gdp", []),
            "inflation": supporting.get("inflation", []),
            "conflict_events_30d": supporting.get("conflict_events_count", 0),
            "llm_available": brief_data.get("llm_available", False),
            "brief_text": brief_data.get("brief", ""),
        }
    else:
        economy = {"_error": brief_data["_error"]}

    # --- Section 3: Markets ---
    markets = {}
    if "_error" not in stock_data and "error" not in stock_data:
        markets = {
            "ticker": stock_data.get("ticker"),
            "exchange": stock_data.get("exchange"),
            "quote": stock_data.get("quote"),
        }
    else:
        markets = {"note": stock_data.get("error", stock_data.get("_error", "unavailable"))}

    # --- Section 4: Elections ---
    elections = {}
    if "_error" not in election_data:
        country_elections = election_data.get("elections", [])
        elections = {
            "upcoming": [e for e in country_elections if e.get("status") == "upcoming"],
            "past": [e for e in country_elections if e.get("status") == "past"],
            "count": len(country_elections),
        }
    else:
        elections = {"_error": election_data["_error"]}

    # --- Section 5: Sanctions ---
    # Until 2026-10-17 this searched entity names for the ISO-3 code and read
    # "results" (the producer emits "matches"), so the list was always empty,
    # and a failed SDN download read as zero matches. One extra row is asked
    # for so a cut-off list is known to be cut off.
    sanctions = {}
    if "_error" in sanctions_data:
        sanctions = {
            "_error": sanctions_data["_error"],
            "match_count": None,
            "data_gaps": [f"sanctions search failed: {sanctions_data['_error']}; not screened"],
        }
    elif not sanctions_data.get("total_entities"):
        sanctions = {
            "matches": [],
            "match_count": None,
            "total_entities": 0,
            "error": "The OFAC SDN list could not be read",
            "degraded": True,
            "reason": "sdn_unavailable",
            "data_gaps": ["OFAC SDN list could not be read; sanctions not screened, not zero"],
        }
    else:
        found = sanctions_data.get("matches") or []
        sanctions = {
            "matches": found[:_SANCTIONS_LIMIT],
            "match_count": min(len(found), _SANCTIONS_LIMIT),
            "more_matches": len(found) > _SANCTIONS_LIMIT,
            "total_entities": sanctions_data.get("total_entities"),
            "country_searched": sanctions_data.get("query", {}).get("country"),
            "match_method": _SANCTIONS_METHOD,
        }

    # --- Section 6: News ---
    # Every RSS feed (category=None), headlines matched on the country's
    # keywords. Until 2026-10-17 this asked for category="all" (not a
    # category, so the feed answered with an error dict), read "articles"
    # and "source" (the producer emits "items" and "feed_name") and checked
    # only "_error": the section was always empty, with no marker. A failed
    # feed is now a gap with mention_count None, never zero mentions.
    # Headlines are matched on whole words (a substring test counted
    # "Tirana" as Iran); mention_count stays the listed (capped) count and
    # matching_items counts every match among the items searched.
    news_mentions = []
    news_gaps: list[str] = []
    news_marker: dict = {}
    news_reach: dict = {}
    country_keywords = country_config.get("keywords")
    if "_error" in news_data:
        news_gaps.append(f"news feed failed: {news_data['_error']}; mentions not measured")
        news_marker = {
            "error": news_data["_error"],
            "degraded": True,
            "reason": "news_feed_exception",
        }
    elif news_data.get("error"):
        news_gaps.append(f"news feed: {news_data['error']}; mentions not measured")
        news_marker = {k: news_data[k] for k in ("error", "degraded", "reason") if k in news_data}
    elif not country_keywords:
        news_gaps.append(
            f"no headline keywords for {iso3} (only the {len(TIER1_COUNTRIES)} tier-1 "
            "countries have them); mentions not searched"
        )
    else:
        items = news_data.get("items", [])
        matching = 0
        for article in items:
            if not _names_country(article.get("title") or "", iso3):
                continue
            matching += 1
            if len(news_mentions) < _MAX_MENTIONS:
                news_mentions.append({
                    "title": article.get("title"),
                    "source": article.get("feed_name"),
                    "published": article.get("published"),
                    "link": article.get("link"),
                    "category": article.get("category"),
                })
        # The span comes from parsed UTC times only: the feed passes a date
        # it cannot parse through raw ("Okt 17, 2026"), which would sort
        # anywhere as text.
        stamps = sorted(t for t in (_utc_stamp(a.get("published")) for a in items) if t)
        news_reach = {
            "matching_items": matching,
            "mention_count_capped": matching > len(news_mentions),
            "items_searched": len(items),
            "searched_span": (
                {"oldest": _iso_z(stamps[0]), "newest": _iso_z(stamps[-1])} if stamps else None
            ),
            "items_without_parsed_time": len(items) - len(stamps),
            "match_method": _MATCH_METHOD,
        }
        if news_data.get("degraded"):
            # Fewer than half of the feeds answered live (fetch_news_feed's
            # partial_feeds_failed): counted, but over a minority.
            news_marker = {k: news_data[k] for k in ("degraded", "reason") if k in news_data}
            news_gaps.append(
                f"only {news_data.get('feeds_ok')} of {news_data.get('feeds_attempted')} RSS "
                "feeds answered live; mention counts rest on a minority of the feeds"
            )
        failed_feeds = news_data.get("feeds_failed") or []
        if failed_feeds:
            news_gaps.append(
                f"{len(failed_feeds)} of {news_data.get('feeds_attempted')} RSS feeds failed "
                f"or timed out; their items are missing: {', '.join(failed_feeds)}"
            )
        stale_feeds = news_data.get("feeds_stale") or []
        if stale_feeds:
            news_gaps.append(
                f"{len(stale_feeds)} RSS feeds were served from an expired cache copy: "
                f"{', '.join(stale_feeds)}"
            )
    news_measured = "error" not in news_marker and bool(country_keywords)

    # --- Section 7: Security (hotspots + conflict zones) ---
    associated_hotspots = []
    for name, hs in INTEL_HOTSPOTS.items():
        if iso3 in hs.get("associated_countries", []):
            associated_hotspots.append({
                "name": name,
                "lat": hs["lat"],
                "lon": hs["lon"],
                "baseline_escalation": hs["baseline_escalation"],
            })

    active_conflicts = []
    for cz in CONFLICT_ZONES:
        cz_name = cz["name"].lower()
        if any(kw in cz_name for kw in country_config.get("keywords", [country_name.lower()])):
            active_conflicts.append(cz)

    security = {
        "hotspots": associated_hotspots,
        "hotspot_count": len(associated_hotspots),
        "active_conflicts": active_conflicts,
        "conflict_count": len(active_conflicts),
    }

    return {
        "overview": overview,
        "economy": economy,
        "markets": markets,
        "elections": elections,
        "sanctions": sanctions,
        "news": {
            "mentions": news_mentions,
            "mention_count": len(news_mentions) if news_measured else None,
            **news_reach,
            **news_marker,
            "data_gaps": news_gaps,
        },
        "security": security,
        "sections": ["overview", "economy", "markets", "elections", "sanctions", "news", "security"],
        "source": "country-dossier",
        "timestamp": now.isoformat(),
    }
