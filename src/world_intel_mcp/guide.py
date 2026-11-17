"""Research guide served over MCP as resources and prompts.

A model connecting to this server sees every registered tool and, before
this module, nothing else: no map of which tool answers which question, and no
statement of what the data cannot support. The guide fills that gap with
three read-only resources, a set of worked research prompts
(``guide_prompts.py``) and the server's ``instructions`` at initialize:

- ``intel://guide``: how to ask a strong question, what an answer
  contains, what this server will not do, the prompts, and every
  registered tool grouped by its domain module, with the environment
  variables a tool cannot work without. The tool list is built from the
  live registry (``tools._MODULES``) on every read, so it cannot drift
  from what ``tools/list`` serves.
- ``intel://guide/source-health``: circuit breakers, stale serves, cache
  freshness and which keyed sources have their environment variables
  set, with a one-line verdict that says when there is nothing to go on
  yet. It reads in-process state and the cache database only; reading it
  never starts a fetch, and an unreadable cache is reported, not raised.
- ``intel://guide/measures``: a glossary of the measures the tools
  return and the mistakes they invite.

Gaps / not covered:
- Source health cannot see the collector's run log or schedule, nor the
  breaker state of other processes (collector, dashboard, CLI); it says
  so in its ``scope`` field.
- ``keyed_sources`` reports whether a variable is set, not whether the
  key is valid or within quota.
- A cache file moved, deleted or replaced while the server holds it open
  keeps answering from the open handle. Source health marks it
  (cache.moved) by comparing the path with the file it first read, so a
  replacement made before the first source-health read is not detected.
- The guide states no count of tools that return no failure marker under
  a total outage, because the count changes as tools are added. A review
  sweep at 7782d22 (137 of its 139 tools, each in a fresh process with a
  fresh breaker and cache, every request failing) found 68 of the
  105 tools that called a source returned no error, degraded or data_gaps
  field; an earlier single-process sweep read 53 of 85 because shared
  circuit breakers stopped 17 tools from calling at all. Neither figure
  is recomputed here.
"""

import json
import os
import re
import sqlite3
import time
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.shared.exceptions import McpError
from mcp.types import (
    INVALID_PARAMS,
    ErrorData,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
)

from . import guide_prompts
from .guide_prompts import PROMPTS, PromptArgumentError

GUIDE_URI = "intel://guide"
HEALTH_URI = "intel://guide/source-health"
MEASURES_URI = "intel://guide/measures"

# Sent as ``instructions`` at initialize (server.py), so a client that
# never lists resources still learns the guide exists.
SERVER_INSTRUCTIONS = (
    "Read the intel://guide resource before your first tool call: it maps "
    "research questions to tools, says what the data cannot support, and "
    "marks the tools that need an API key. prompts/list has worked research "
    "prompts. intel://guide/source-health shows which sources are failing, "
    "serving stale copies or missing keys. Many tools do not mark a failure: "
    "an empty list, a zero, a LOW label, an all-clear or a false flag can "
    "mean a source failed, not that nothing happened."
)

# Display names for the domain modules under tools/. A module missing
# here still appears in the guide, titled from its module name.
_DOMAIN_TITLES = {
    "markets": "Markets and economy",
    "hazards": "Natural hazards and space",
    "conflict": "Conflict and military",
    "infrastructure": "Infrastructure and transport",
    "society": "News, society and migration",
    "intelligence": "Intelligence analysis",
    "geospatial": "Static geospatial datasets",
    "synthesis": "NLP and strategic synthesis",
    "finance": "Business finance",
    "vector": "Stored history (vector store)",
    "aoi": "Areas of interest, briefs and reports",
    "system": "System",
    "prediction_markets": "Prediction markets",
    "news_signals": "News signals",
    "liquidity": "Liquidity and money",
    "news_market": "News and market reaction",
    "history": "Stored history (history store)",
    "lagged_connections": "Lagged connections between stored series",
    "day_timeline": "Day timeline",
    "history_backfill": "History backfill",
}


@dataclass(frozen=True)
class KeyedSource:
    source: str
    env: tuple[str, ...]
    without_key: str
    # Tools that return an error naming these variables when they are not
    # set. The guide's tool list marks them "[needs ...]".
    needed_by: tuple[str, ...] = ()


# Every credential-like variable the package reads. A test scans every
# module outside tests/ and fails when a variable is read there but
# missing here, or listed here but no longer read.
KEYED_SOURCES: tuple[KeyedSource, ...] = (
    KeyedSource(
        "ACLED",
        ("ACLED_EMAIL", "ACLED_PASSWORD"),
        "ACLED event, unrest and risk tools return an error naming the missing "
        "credentials, and so does intel_instability_index without a "
        "country_code. With a country_code the index still scores, without "
        "its unrest and conflict inputs, and lists acled_unconfigured in "
        "data_gaps. When both are set but the sign-in request fails, the "
        "error says ACLED sign-in failed instead (reason acled_auth_failed).",
        needed_by=(
            "intel_acled_events",
            "intel_unrest_events",
            "intel_risk_scores",
            "intel_instability_index",
        ),
    ),
    KeyedSource(
        "UCDP",
        ("UCDP_ACCESS_TOKEN",),
        "intel_ucdp_events still sends the request; the API refuses it, and the "
        "tool returns an error with reason ucdp_unconfigured.",
        needed_by=("intel_ucdp_events",),
    ),
    KeyedSource(
        "NASA FIRMS",
        ("NASA_FIRMS_API_KEY",),
        "intel_wildfires returns an error.",
        needed_by=("intel_wildfires",),
    ),
    KeyedSource(
        "EIA",
        ("EIA_API_KEY",),
        "Energy prices, residential natural gas and electricity rates return an error.",
        needed_by=("intel_energy_prices", "intel_residential_natgas", "intel_electricity_rates"),
    ),
    KeyedSource(
        "FRED",
        ("FRED_API_KEY",),
        "intel_fred_series returns an error; the yield curve falls back to four Yahoo "
        "maturities with no 2s10s spread and no observation dates; central bank rates "
        "come only from a hand-kept table dated 2024-11 to 2025-02.",
        needed_by=("intel_fred_series",),
    ),
    KeyedSource(
        "Cloudflare Radar",
        ("CLOUDFLARE_API_TOKEN",),
        "Internet outages fall back to the IODA public API.",
    ),
    KeyedSource(
        "URLhaus",
        ("URLHAUS_AUTH_KEY",),
        "intel_cyber_threats skips the URLhaus feed and reports three of four feeds; "
        "abuse.ch no longer serves it without a key.",
    ),
    KeyedSource(
        "OpenSky",
        ("OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET", "OPENSKY_USERNAME", "OPENSKY_PASSWORD"),
        "Requests are anonymous, with OpenSky's lower anonymous limits.",
    ),
    KeyedSource(
        "TomTom",
        ("TOMTOM_API_KEY",),
        "Traffic flow and incident tools return an error.",
        needed_by=("intel_traffic_flow", "intel_traffic_incidents"),
    ),
    KeyedSource(
        "Windy Webcams",
        ("WINDY_API_KEY",),
        "intel_webcams returns an error.",
        needed_by=("intel_webcams",),
    ),
)

_NEEDS: dict[str, tuple[str, ...]] = {
    tool: ks.env for ks in KEYED_SOURCES for tool in ks.needed_by
}


@dataclass(frozen=True)
class Domain:
    key: str
    title: str
    summary: str
    tools: tuple[Any, ...]


# Notes for maintainers in a module docstring (a build phase, a pointer
# to a source file) stay out of the guide a model reads.
_DEVELOPER_NOTE = re.compile(r"\s*\(Phase \d+\)")


def _module_summary(module: Any) -> str:
    doc = (module.__doc__ or "").strip()
    first_paragraph = doc.split("\n\n", 1)[0]
    return _DEVELOPER_NOTE.sub("", _first_sentence(" ".join(first_paragraph.split())))


def domains(modules: list | None = None) -> list[Domain]:
    """The live registry grouped by domain module, in list_tools order."""
    if modules is None:
        from . import tools as tools_pkg

        modules = tools_pkg._MODULES
    out = []
    for module in modules:
        key = module.__name__.rsplit(".", 1)[-1]
        title = _DOMAIN_TITLES.get(key, key.replace("_", " ").capitalize())
        out.append(Domain(key, title, _module_summary(module), tuple(module.TOOLS)))
    return out


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
# A period that closes an abbreviation (U.S., e.g., i.e.) does not end a
# sentence, though a capital may follow it.
_ABBREVIATION = re.compile(r"(?:\b(?:[A-Za-z]\.){2,}|\b(?:etc|vs|approx|Inc|No|St)\.)$")


def _first_sentence(text: str) -> str:
    for end in _SENTENCE_END.finditer(text):
        if not _ABBREVIATION.search(text[: end.start()]):
            return text[: end.start()]
    return text


def _one_line(description: str) -> str:
    first = _first_sentence(" ".join(description.split()))
    # Em dashes in tool descriptions become hyphens: the guide is
    # published text.
    return first.replace(" — ", " - ").replace("—", "-")


def _arg_list(tool: Any) -> str:
    schema = tool.inputSchema or {}
    required = set(schema.get("required", []))
    names = [
        f"{name} (required)" if name in required else name
        for name in schema.get("properties", {})
    ]
    return ", ".join(names)


def tool_line(tool: Any) -> str:
    args = _arg_list(tool)
    args_part = f" [{args}]" if args else ""
    # Only the first sentence of a description is shown, which can drop
    # its "Requires ..." sentence; the key requirement comes from
    # KEYED_SOURCES instead.
    needs = _NEEDS.get(tool.name)
    needs_part = f" [needs {', '.join(needs)}]" if needs else ""
    return f"- `{tool.name}`{args_part}: {_one_line(tool.description or '')}{needs_part}"


_GUIDE_INTRO = """\
# World Intelligence MCP: research guide

This server answers questions about the world with live public data:
markets, conflict, hazards, migration, aviation, cyber, infrastructure,
news and more. This guide is generated from the running server: {tools}
tools in {domains} domains, and {prompts} worked research prompts.

Other resources: `intel://guide/source-health` (which sources are
failing, stale or missing keys right now) and `intel://guide/measures`
(what the numbers mean and how they mislead).

## How to ask a strong question

- Name the period: "the last 30 days against the 30 days before", not
  "recently".
- Name the comparison: an earlier period, another place, or a stated
  baseline.
- Name the measure: event count or fatalities, price level or percentage
  change, people displaced at year end or arrivals during the year.
- Name the place: a country (many tools take an ISO-3 code), a region, a
  bounding box, or a saved area of interest.

A question with all four can be answered from tool output. A question
with none of them invites a story.

## What an answer from this server contains

- Values as the sources published them. Most responses name their source
  and carry a fetch timestamp; the date a value describes is often earlier
  than the fetch, so give both. Some tools return no observation date at
  all; say so rather than using the fetch time.
- Failures, sometimes. Some tools return `error`, `degraded` or
  `data_gaps` when a source is down or not configured. Many do not: when
  every upstream request fails they return an empty list, a zero count, a
  neutral score, a LOW risk label, an all-clear status or a false flag,
  with no marker. Read an empty list or a zero count as nothing returned,
  not nothing happened, and confirm with a second tool before calling a
  place quiet. `failing_sources` in the source-health resource names the
  sources whose last call failed.
- Citations. Briefs and digests number their sources.
- Old copies, counted. When a live fetch fails and an older cached copy
  exists, that copy is served. Dictionary responses carry `_stale` and
  `_stale_age_seconds`, but tools that reshape a response do not always
  pass the marker through. `stale_serves` in the source-health resource
  counts every stale copy this process served, per source.

## What this server will not do

- Trade, place orders, or say what to buy or sell.
- Forecast prices, elections or wars. Escalation, instability, risk and
  composite scores are weighted summaries of current readings against
  stated baselines, not probabilities.
- Prove causation. Series that move together, or one shortly after the
  other, may share a cause or be coincidence.
- Show history it did not record. Collected history (semantic search,
  timelines, baselines, area change detection) covers only the time the
  collector or server was running and storing. The exception is
  intel_history_backfill, which loads FRED and ECB publisher history
  into the history store for intel_series_history, intel_revisions and
  intel_day_timeline. Those values are the publisher's current vintage,
  so revisions made before the backfill do not show.
- Use keyed sources without their keys. Tools marked [needs ...] in the
  list below return an error naming the variable when it is not set; a
  few others fall back to a keyless source with less detail.
  `without_key` in the source-health resource says which, and whether
  each variable is set.
- See what its sources do not publish. Aircraft without a broadcast
  position, unlisted outlets, and regions outside a feed's coverage are
  absent, which is not the same as quiet.
- Confirm identities. A sanctions or entity name match is a text match.
"""


def render_guide(modules: list | None = None, prompts: tuple = PROMPTS) -> str:
    """The guide markdown, built from the live registry."""
    groups = domains(modules)
    total = sum(len(d.tools) for d in groups)
    parts = [
        _GUIDE_INTRO.format(tools=total, domains=len(groups), prompts=len(prompts)),
        "## Worked research prompts\n",
        "Each prompt names the tools to call, the arguments to pass and the "
        "limits to respect. Fetch one with prompts/get.\n",
    ]
    for p in prompts:
        args = ", ".join(
            f"{a.name} (required)" if a.required else a.name for a in p.arguments
        )
        args_part = f" [{args}]" if args else ""
        parts.append(f"- `{p.name}`{args_part}: {p.title}.")
    parts.append("\n## Tools by domain\n")
    for d in groups:
        parts.append(f"### {d.title} ({len(d.tools)})\n")
        if d.summary:
            parts.append(f"{d.summary}\n")
        parts.extend(tool_line(t) for t in d.tools)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


MEASURES = """\
# Measures glossary

What the numbers returned by this server's tools mean, and the mistakes
they invite.

## Amount outstanding versus flow

An amount outstanding (a stock) is a level at one moment: people
displaced at the end of a year, a central bank's balance sheet, money
supply. A flow is what happened during a period: arrivals during a year,
fund inflows in a week, fatalities in a month. Never add a stock to a
flow. A change in a stock is a net figure: a displaced population that
grew by 100,000 may have had 300,000 arrivals and 200,000 returns.

## Growth versus acceleration

Growth is how fast a level changes (prices 3 percent higher than a year
earlier). Acceleration is how fast the growth rate itself changes
(growth up from 2 to 3 percent). Slower growth is still growth: inflation
falling from 4 to 3 percent means prices are still rising, only more
slowly.

## Percent versus percentage points

A rate that moves from 4 percent to 5 percent rose by 1 percentage
point, which is a 25 percent increase in the rate itself. Yields,
spreads, policy rates and shares are compared in points; one point is
100 basis points.

## Seasonally adjusted

Many series repeat a calendar pattern: holiday spending, winter heating,
summer travel. A seasonally adjusted series has the expected pattern
removed, so one month can be compared with the month before. An
unadjusted series should be compared with the same period a year
earlier. Never compare an adjusted figure with an unadjusted one; check
which a series is before comparing.

## Observation, publication and collection dates

- Observation date: the period a value describes (March unemployment,
  the day an event took place).
- Publication date: when the publisher released it, often weeks after
  the observation, with revisions later still.
- Collection date: when this server fetched or saved it.

A value fetched today can describe last month or last year; annual
datasets such as World Bank indicators often trail by a year or more.
Report the observation date. The fetch time only tells you how fresh the
copy is. Some tools return no observation date; say so.

## Revisions

First releases are estimates. Economic series, event datasets and
displacement figures are revised after publication, sometimes by more
than the change being discussed. Say which release you used.

## Correlation and timing offsets

Two series that move together, or where one tends to move a few days
before the other, may share a cause, may be linked in either direction,
or may be coincidence. Coincidence becomes likely when many pairs or
many offsets are tried and only the best is reported. A lead or lag found
in one sample describes that sample. None of this shows that one thing
caused the other.

## Composite scores

Escalation, instability, risk, macro composite and stress scores are
weighted combinations of current inputs against stated baselines. They
summarize their inputs and are not probabilities. Some add a fixed amount
from a static country table: the instability index's `ucdp_floor` and
`displacement_boost` come from a baseline risk table, not from current
data, so a floor score says nothing about this week. Report the
components with the score; a null component was not measured.

## Missing data is not zero

Many tools report a source that failed, is not configured, or does not
cover a place with an error, a note or a `data_gaps` entry. That means
unknown, not none. Many tools do not: when every upstream request fails
they return an empty list, a zero count, a neutral score, a LOW risk
label, an all-clear status or a false flag, so an empty list or a zero
means nothing was returned, not that nothing happened. Zero events from a fetch that worked, in a region the source
covers and for a query that matched the place, is a measurement; zero
events in a region it does not cover is nothing at all.
"""


_HEALTH_SCOPE = (
    "circuit_breakers covers requests made by this server process since it "
    "started; the collector, dashboard and CLI keep their own. An empty map "
    "means no requests yet, not that every source is healthy.",
    "failing_sources lists every source whose last call from this process "
    "failed, whether or not its breaker has opened. In circuit_breakers, "
    "failures is the count of failed calls since the last success (0 after "
    "a success), and a breaker opens only after several failures in a row; "
    "total_successes and total_failures count every call since the process "
    "started.",
    "stale_serves counts, per source, the stale cached copies this process "
    "served when a live fetch failed, whatever the payload type.",
    "cache_freshness reads the cache database: the newest entry per key "
    "prefix, written by whichever process fetched it. A fresh entry shows a "
    "recent successful fetch, not that the collector is on schedule.",
    "cache.requested_path is the database this process was configured to "
    "use; when it could not be opened, cache.fell_back is true and db_path "
    "is a temporary database that no other process shares. "
    "cache.available is false when the database could not be read at all. "
    "cache.moved is true when the file at db_path is gone, or is not the "
    "file this process first read, while this process still holds the old "
    "one open: its numbers then come from a file no other process shares. "
    "A file replaced before this resource was first read is not detected.",
    "keyed_sources says whether each variable is set in this server's "
    "environment. It never shows values and does not check that a key works.",
    "Not read here: vector store statistics (intel_vector_stats) and the "
    "collector's run history (intel_collection_health). Reading this "
    "resource starts no fetches.",
)


# The file each cache object's database was on when source health first
# read it. A moved or replaced file keeps answering through the open
# handle, so the path is compared with this on every read.
_FIRST_FILE: "weakref.WeakKeyDictionary[Any, tuple[int, int]]" = weakref.WeakKeyDictionary()


def _file_identity(path: Any) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def _cache_moved(cache: Any) -> bool:
    now = _file_identity(cache.db_path)
    if now is None:
        return True
    try:
        first = _FIRST_FILE.setdefault(cache, now)
    except TypeError:
        return False
    return first != now


def _read_cache(cache: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Cache statistics and per-prefix freshness, or why they are unreadable.

    A broken database (table missing, file corrupt, disk error) becomes
    ``available: false`` with the error text, so the rest of the health
    snapshot still reaches the caller. ``moved`` marks a database file that
    was moved, deleted or replaced while this process holds it open.
    """
    paths = {
        "db_path": str(cache.db_path),
        "requested_path": str(cache.requested_path),
        "fell_back": cache.fell_back,
    }
    try:
        stats = cache.stats()
        by_prefix = cache.freshness()
    except (sqlite3.Error, OSError) as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", **paths}, None
    return {"available": True, **stats, **paths, "moved": _cache_moved(cache)}, by_prefix


def _failing_sources(breakers: dict[str, Any]) -> list[str]:
    """Sources whose last call failed (failures resets to 0 on a success),
    or whose breaker is open or half-open."""
    return sorted(
        name
        for name, info in breakers.items()
        if (info.get("failures") or 0) > 0 or info.get("status") != "closed"
    )


def _verdict(breakers: dict[str, Any], cache_info: dict[str, Any]) -> str:
    entries = cache_info.get("total_entries") or 0
    if not breakers and not entries:
        state = "is empty" if cache_info["available"] else "could not be read"
        verdict = (
            "no information yet: this process has made no requests since it "
            f"started and the cache {state}, so nothing here shows whether any "
            "source works"
        )
    elif not breakers:
        verdict = (
            "cache only: this process has made no requests since it started; "
            "cache_freshness shows what any process sharing the cache fetched last"
        )
    else:
        # A breaker opens only after several failures in a row, so a closed
        # breaker can still mean the last call failed: count both.
        failing = len(_failing_sources(breakers))
        unavailable = sum(1 for info in breakers.values() if info.get("status") != "closed")
        stale = sum(1 for info in breakers.values() if info.get("total_stale_serves"))
        noun = "source" if len(breakers) == 1 else "sources"
        verdict = (
            f"{len(breakers)} {noun} called by this process, {failing} whose "
            f"last call failed, {unavailable} with an open or half-open circuit "
            "breaker"
        )
        if stale:
            verdict += f"; {stale} served a stale cached copy"
    if cache_info["fell_back"]:
        verdict += (
            "; the configured cache could not be opened, so this process uses "
            "a temporary cache of its own"
        )
    if cache_info.get("moved"):
        verdict += (
            "; the cache file at db_path was moved or replaced while this "
            "process held it open, so its cache numbers come from a file no "
            "other process shares"
        )
    return verdict


def source_health(
    breaker: Any,
    cache: Any,
    environ: Mapping[str, str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Read-only health snapshot from in-process state and the cache DB."""
    env = os.environ if environ is None else environ
    breakers = breaker.status()
    cache_info, freshness = _read_cache(cache)
    keyed = []
    for ks in KEYED_SOURCES:
        set_vars = [name for name in ks.env if env.get(name)]
        keyed.append(
            {
                "source": ks.source,
                "env": list(ks.env),
                "configured": [name for name in ks.env if name in set_vars],
                "missing": [name for name in ks.env if name not in set_vars],
                "without_key": ks.without_key,
            }
        )
    generated = datetime.fromtimestamp(time.time() if now is None else now, timezone.utc)
    return {
        "generated_at": generated.isoformat(),
        "verdict": _verdict(breakers, cache_info),
        "scope": list(_HEALTH_SCOPE),
        "failing_sources": _failing_sources(breakers),
        "open_breakers": sorted(
            name for name, info in breakers.items() if info.get("status") != "closed"
        ),
        "stale_serves": {
            name: info["total_stale_serves"]
            for name, info in sorted(breakers.items())
            if info.get("total_stale_serves")
        },
        "stale_cache_prefixes": None
        if freshness is None
        else sorted(prefix for prefix, info in freshness.items() if info.get("is_stale")),
        "circuit_breakers": breakers,
        "cache": cache_info,
        "cache_freshness": freshness,
        "keyed_sources": keyed,
    }


# ---------------------------------------------------------------------------
# MCP glue: server.py's handlers delegate here.
# ---------------------------------------------------------------------------

RESOURCES: tuple[Resource, ...] = (
    Resource(
        uri=GUIDE_URI,
        name="research-guide",
        title="Research guide",
        description=(
            "How to ask this server a strong question, what an answer contains, "
            "what it will not do, the worked prompts, and every tool by domain "
            "(generated from the live registry)."
        ),
        mimeType="text/markdown",
    ),
    Resource(
        uri=HEALTH_URI,
        name="source-health",
        title="Source health",
        description=(
            "Circuit breakers, cache freshness, stale serves and which keyed "
            "sources are configured. Read-only; starts no fetches."
        ),
        mimeType="application/json",
    ),
    Resource(
        uri=MEASURES_URI,
        name="measures-glossary",
        title="Measures glossary",
        description=(
            "Stock versus flow, growth versus acceleration, percentage points, "
            "seasonal adjustment, the three dates, correlation versus causation, "
            "missing data versus zero."
        ),
        mimeType="text/markdown",
    ),
)


def list_resources() -> list[Resource]:
    return list(RESOURCES)


def read_resource(uri: str) -> list[ReadResourceContents]:
    uri = str(uri)
    if uri == GUIDE_URI:
        return [ReadResourceContents(content=render_guide(), mime_type="text/markdown")]
    if uri == MEASURES_URI:
        return [ReadResourceContents(content=MEASURES, mime_type="text/markdown")]
    if uri == HEALTH_URI:
        from . import runtime

        health = source_health(runtime.breaker, runtime.cache)
        return [
            ReadResourceContents(
                content=json.dumps(health, indent=2, default=str),
                mime_type="application/json",
            )
        ]
    known = ", ".join(str(r.uri) for r in RESOURCES)
    raise McpError(
        ErrorData(code=INVALID_PARAMS, message=f"Unknown resource {uri}; available: {known}")
    )


def list_prompts() -> list[Prompt]:
    return [
        Prompt(
            name=p.name,
            title=p.title,
            description=p.description,
            arguments=[
                PromptArgument(name=a.name, description=a.help, required=a.required)
                for a in p.arguments
            ],
        )
        for p in PROMPTS
    ]


def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    prompt = guide_prompts.get(name)
    if prompt is None:
        known = ", ".join(p.name for p in PROMPTS)
        raise McpError(
            ErrorData(code=INVALID_PARAMS, message=f"Unknown prompt '{name}'; available: {known}")
        )
    try:
        text = guide_prompts.render(prompt, arguments)
    except PromptArgumentError as exc:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(exc))) from exc
    return GetPromptResult(
        description=prompt.description,
        messages=[PromptMessage(role="user", content=TextContent(type="text", text=text))],
    )
