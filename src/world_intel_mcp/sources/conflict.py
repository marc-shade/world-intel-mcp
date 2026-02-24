"""Conflict and crisis data sources for world-intel-mcp.

Fetches armed conflict events (ACLED), state-based violence data (UCDP),
and humanitarian dataset metadata (HDX) for the world-intel-mcp server.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.conflict")


# ---------------------------------------------------------------------------
# ACLED: Armed Conflict Location & Event Data
# ---------------------------------------------------------------------------

_ACLED_URL = "https://api.acleddata.com/acled/read"


async def fetch_acled_events(
    fetcher: Fetcher,
    country: str | None = None,
    days: int = 7,
    limit: int = 100,
) -> dict:
    """Fetch recent armed conflict events from the ACLED API v3.

    Requires ``ACLED_ACCESS_TOKEN`` in the environment.  Free academic
    access can be obtained at https://acleddata.com.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        country: Optional country name to filter events.
        days: How far back to search (in days from now).
        limit: Maximum number of results.

    Returns:
        Dict with events list, count, query params, source, and timestamp.
    """
    now = datetime.now(timezone.utc)

    access_token = os.environ.get("ACLED_ACCESS_TOKEN")
    if not access_token:
        return {
            "error": "ACLED_ACCESS_TOKEN not configured",
            "note": "Free academic access at acleddata.com",
        }

    start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    params: dict = {
        "key": access_token,
        "email": os.environ.get("ACLED_EMAIL", "phoenix@2acrestudios.com"),
        "limit": limit,
        "event_date": f"{start_date}|{end_date}",
        "event_date_where": "BETWEEN",
    }
    if country:
        params["country"] = country

    cache_country = country or "global"
    data = await fetcher.get_json(
        _ACLED_URL,
        source="acled",
        cache_key=f"conflict:acled:{cache_country}:{days}",
        cache_ttl=900,
        params=params,
    )

    if data is None:
        logger.warning("ACLED API returned no data")
        return {
            "events": [],
            "count": 0,
            "query": {"country": country, "days": days},
            "source": "acled",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    events = []
    for event in data.get("data", []):
        fatalities_raw = event.get("fatalities")
        fatalities = int(fatalities_raw) if fatalities_raw is not None else 0
        events.append({
            "event_id_cnty": event.get("event_id_cnty"),
            "event_date": event.get("event_date"),
            "event_type": event.get("event_type"),
            "sub_event_type": event.get("sub_event_type"),
            "actor1": event.get("actor1"),
            "actor2": event.get("actor2"),
            "country": event.get("country"),
            "admin1": event.get("admin1"),
            "admin2": event.get("admin2"),
            "location": event.get("location"),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
            "fatalities": fatalities,
            "notes": event.get("notes"),
            "source": event.get("source"),
        })

    # Sort by fatalities descending, then event_date descending
    # Negate fatalities for desc; negate date lexicographically is not possible,
    # so use a two-pass stable sort: secondary key first, primary key second.
    events.sort(key=lambda e: e.get("event_date") or "", reverse=True)
    events.sort(key=lambda e: e.get("fatalities") or 0, reverse=True)

    return {
        "events": events,
        "count": len(events),
        "query": {"country": country, "days": days},
        "source": "acled",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# UCDP: Uppsala Conflict Data Program (GED API)
# ---------------------------------------------------------------------------

_UCDP_GED_URL = "https://ucdpapi.pcr.uu.se/api/gedevents/24.1"

_VIOLENCE_TYPES = {
    1: "state-based",
    2: "non-state",
    3: "one-sided",
}


async def fetch_ucdp_events(
    fetcher: Fetcher,
    days: int = 30,
    limit: int = 100,
) -> dict:
    """Fetch recent conflict events from the UCDP GED API.

    No API key required.  Fetches multiple pages in parallel when the
    dataset spans more than one page.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        days: Only include events whose ``date_start`` is within this
              many days from now.
        limit: Page size (max 1000 per page).

    Returns:
        Dict with events list, count, total fatalities, query params,
        source, and timestamp.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Fetch page 1 to discover total pages (UCDP is slow — 30s timeout)
    page1_data = await fetcher.get_json(
        _UCDP_GED_URL,
        source="ucdp",
        cache_key=f"conflict:ucdp:{days}:page1",
        cache_ttl=21600,
        params={"pagesize": min(limit, 1000), "page": 0},
        timeout=30.0,
    )

    if page1_data is None:
        logger.warning("UCDP GED API returned no data")
        return {
            "events": [],
            "count": 0,
            "total_fatalities_best": 0,
            "query": {"days": days},
            "source": "ucdp",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    total_pages = page1_data.get("TotalPages", 1)
    all_results = list(page1_data.get("Result", []))

    # Fetch remaining pages in parallel
    if total_pages > 1:
        page_tasks = [
            fetcher.get_json(
                _UCDP_GED_URL,
                source="ucdp",
                cache_key=f"conflict:ucdp:{days}:page{p}",
                cache_ttl=21600,
                params={"pagesize": min(limit, 1000), "page": p},
                timeout=30.0,
            )
            for p in range(1, total_pages)
        ]
        page_results = await asyncio.gather(*page_tasks)
        for page_data in page_results:
            if page_data is not None:
                all_results.extend(page_data.get("Result", []))

    # Filter to recent events and extract fields
    events = []
    total_fatalities_best = 0

    for record in all_results:
        date_start = record.get("date_start")
        if date_start is None:
            continue

        # Parse date_start and filter by cutoff
        try:
            event_date = datetime.strptime(date_start[:10], "%Y-%m-%d").replace(
                tzinfo=timezone.utc,
            )
        except (ValueError, TypeError):
            continue

        if event_date < cutoff:
            continue

        violence_type_raw = record.get("type_of_violence")
        violence_type_int = None
        if violence_type_raw is not None:
            try:
                violence_type_int = int(violence_type_raw)
            except (ValueError, TypeError):
                pass

        best = 0
        if record.get("best") is not None:
            try:
                best = int(record["best"])
            except (ValueError, TypeError):
                pass

        high = 0
        if record.get("high") is not None:
            try:
                high = int(record["high"])
            except (ValueError, TypeError):
                pass

        low = 0
        if record.get("low") is not None:
            try:
                low = int(record["low"])
            except (ValueError, TypeError):
                pass

        total_fatalities_best += best

        events.append({
            "id": record.get("id"),
            "relid": record.get("relid"),
            "year": record.get("year"),
            "date_start": date_start,
            "date_end": record.get("date_end"),
            "country": record.get("country"),
            "region": record.get("region"),
            "type_of_violence": violence_type_int,
            "type_of_violence_label": _VIOLENCE_TYPES.get(violence_type_int, "unknown") if violence_type_int is not None else "unknown",
            "side_a": record.get("side_a"),
            "side_b": record.get("side_b"),
            "best": best,
            "high": high,
            "low": low,
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "source_article": record.get("source_article"),
            "source_headline": record.get("source_headline"),
        })

    return {
        "events": events,
        "count": len(events),
        "total_fatalities_best": total_fatalities_best,
        "query": {"days": days},
        "source": "ucdp",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# HDX: Humanitarian Data Exchange (CKAN API)
# ---------------------------------------------------------------------------

_HDX_SEARCH_URL = "https://data.humdata.org/api/3/action/package_search"


async def fetch_humanitarian_summary(
    fetcher: Fetcher,
    country: str | None = None,
) -> dict:
    """Fetch recent humanitarian crisis datasets from HDX (Humanitarian Data Exchange).

    No API key required.  Uses the CKAN package_search API.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        country: Optional ISO 3166-1 alpha-3 country code (lowercase) to
                 filter datasets by geographic group.

    Returns:
        Dict with datasets list, count, source, and timestamp.
    """
    now = datetime.now(timezone.utc)

    params: dict = {
        "q": "crisis",
        "rows": 20,
        "sort": "metadata_modified desc",
    }
    if country:
        params["fq"] = f"groups:{country.lower()}"

    cache_country = country or "global"
    data = await fetcher.get_json(
        _HDX_SEARCH_URL,
        source="hdx",
        cache_key=f"conflict:humanitarian:{cache_country}",
        cache_ttl=21600,
        params=params,
    )

    if data is None:
        logger.warning("HDX API returned no data")
        return {
            "datasets": [],
            "count": 0,
            "source": "hdx",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    datasets = []
    results = data.get("result", {}).get("results", [])

    for dataset in results:
        notes = dataset.get("notes") or ""
        if len(notes) > 200:
            notes = notes[:200] + "..."

        org = dataset.get("organization") or {}
        org_title = org.get("title") if isinstance(org, dict) else None

        datasets.append({
            "name": dataset.get("name"),
            "title": dataset.get("title"),
            "organization": org_title,
            "metadata_modified": dataset.get("metadata_modified"),
            "num_resources": dataset.get("num_resources"),
            "notes": notes,
        })

    return {
        "datasets": datasets,
        "count": len(datasets),
        "source": "hdx",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
