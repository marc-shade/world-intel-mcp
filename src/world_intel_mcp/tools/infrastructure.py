"""Infrastructure and transport tools: internet outages,
undersea cable health, navigational warnings, airport delays, global
air traffic, road traffic, webcams, shipping stress, cloud service
status.

Phase 26 split: Tool definitions moved byte-identical and dispatch
case bodies verbatim from server.py; handlers reach shared
infrastructure via ``runtime``. See tools/system.py for the pattern.
"""

from typing import Any

from mcp.types import Tool

from .. import runtime
from ..sources.jet_cohort import BIZJET_TYPES
from ..sources import (
    infrastructure,
    maritime,
    aviation,
    shipping,
    service_status,
)

TOOLS: list[Tool] = [
    # --- Infrastructure (2 tools) ---
    Tool(
        name="intel_internet_outages",
        description="Get internet outages from Cloudflare Radar (last 7 days). Optional: CLOUDFLARE_API_TOKEN for higher limits.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_cable_health",
        description="Assess undersea cable corridor health from NGA navigational warnings. 6 corridors scored 0-3.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Maritime (1 tool) ---
    Tool(
        name="intel_nav_warnings",
        description="Get active navigational warnings from NGA Maritime Safety, each with every position its text states. feed_stale is true when the feed's newest active warning (before any navarea filter) is past the staleness threshold, and data_gaps then says so. Optional: navarea, an NGA area code (4, 12, A, P, C; IV and XII are accepted for 4 and 12).",
        inputSchema={
            "type": "object",
            "properties": {
                "navarea": {
                    "type": "string",
                    "description": "NGA area code: 4 (NAVAREA IV), 12 (NAVAREA XII), A (HYDROLANT), P (HYDROPAC) or C (HYDROARC); IV and XII are accepted for 4 and 12. Other NAVAREAs arrive inside the A, P and C series, so a value that matches no carried area returns an error and a data_gaps line, never a count of 0.",
                },
            },
        },
    ),
    # --- Aviation (1 tool) ---
    Tool(
        name="intel_airport_delays",
        description="Get current US airport ground stops, delay programs and closures from the FAA NAS Status feed. No API key needed.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Aviation domestic (1 tool) ---
    Tool(
        name="intel_aviation_domestic",
        description="Global air traffic snapshot from OpenSky Network: total airborne aircraft, regional breakdown, busiest origin countries, and sampled positions for mapping.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Traffic (2 tools) ---
    Tool(
        name="intel_traffic_flow",
        description="Real-time traffic congestion for 20 major world cities via TomTom API. Congestion percentage, speeds, global average. Requires TOMTOM_API_KEY.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_traffic_incidents",
        description="Major traffic incidents across 5 strategic regions (US East/West, Europe, Middle East, East Asia) via TomTom API. Requires TOMTOM_API_KEY.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Webcams (1 tool) ---
    Tool(
        name="intel_webcams",
        description="Public webcam locations and live previews worldwide from Windy Webcams API. Filter by category (traffic, weather, landscape). Requires WINDY_API_KEY.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Webcam category (traffic, weather, landscape, etc.)",
                    "default": "traffic",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max cameras to return (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    # --- Shipping (1 tool) ---
    Tool(
        name="intel_shipping_index",
        description="Compute shipping stress index from dry bulk ETFs (BDRY, SBLK, EGLE, ZIM). Stress score 0-100.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Service Status (1 tool) ---
    Tool(
        name="intel_service_status",
        description="Monitor cloud service provider status (AWS, Azure, GCP, Cloudflare, GitHub). Shows active incidents and recent outages. Optional: provider (aws/azure/gcp/cloudflare/github).",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Filter by provider (aws, azure, gcp, cloudflare, github)",
                },
            },
        },
    ),
    Tool(
        name="intel_bgp_status",
        description="Get BGP routing status for one prefix or ASN from RIPEstat: RIS peer visibility per address family, announced space and neighbour count (ASN queries), observed origin ASNs and per-origin RPKI validation valid/invalid/unknown (prefix queries). A per-resource health check, not global hijack detection - RIPEstat has no target-free incident feed. No API key needed.",
        inputSchema={
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "description": "ASN (AS3333 or 3333) or CIDR prefix (193.0.0.0/21); bare IPs rejected",
                },
            },
            "required": ["resource"],
        },
    ),
    # --- Aircraft cohort early warning (3 tools; approach inspired by kylemcdonald/ews) ---
    Tool(
        name="intel_jet_cohort_snapshot",
        description=f"Live airborne snapshot of a tracked aircraft cohort from adsb.lol (free, no key, ODbL): business jets ({len(BIZJET_TYPES)} ICAO type designators, one request) or military. "
        "Counts by type, PIA/LADD privacy flags, positions. Each call also learns the cohort (hex addresses persisted locally) that intel_jet_activity_anomaly and intel_jet_excess_origins filter on; run it periodically to build the cohort.",
        inputSchema={
            "type": "object",
            "properties": {
                "cohort": {"type": "string", "enum": ["bizjet", "military"], "default": "bizjet"},
                "region": {
                    "type": "string",
                    "description": "global, conus, north_america, europe, middle_east, east_asia, or 'lamin,lomin,lamax,lomax' (filters the summary only; learning is global)",
                    "default": "global",
                },
            },
        },
    ),
    Tool(
        name="intel_jet_activity_anomaly",
        description="Early-warning check: peak concurrent airborne cohort aircraft (business jets or military) in the latest published UTC half-hour (or a given slot) vs the same slot on prior same-weekday dates, from adsb.lol globe_history heatmaps. US federal holiday-adjacent baseline dates are swapped for earlier weeks. Returns robust z-score, alert level 1-5 (normal/watch/elevated/high/alarm), deficit flag, and data gaps. Needs a learned cohort (see intel_jet_cohort_snapshot); downloads ~14 MB per uncached slot, cached on disk.",
        inputSchema={
            "type": "object",
            "properties": {
                "cohort": {"type": "string", "enum": ["bizjet", "military"], "default": "bizjet"},
                "region": {
                    "type": "string",
                    "description": "global, conus, north_america, europe, middle_east, east_asia, or 'lamin,lomin,lamax,lomax'",
                    "default": "global",
                },
                "slot": {
                    "type": "string",
                    "description": "UTC ISO datetime inside the half-hour to score (default: latest published)",
                },
                "baseline_weeks": {"type": "integer", "minimum": 2, "maximum": 8, "default": 4},
                "alarm_sigma": {"type": "number", "default": 5.0, "description": "z at which level 5 (alarm) fires"},
                "min_learning_lead_hours": {
                    "type": "number",
                    "default": 24,
                    "description": "Only use cohort members first seen this long before the window (avoids selection bias). Negative values admit later-learned members for a first look; the result is then marked degraded with a selection-bias data gap.",
                },
            },
        },
    ),
    Tool(
        name="intel_jet_excess_origins",
        description="Where did an excess of cohort departures/arrivals come from? Infers takeoffs and landings from adsb.lol heatmap tracks for a 0.5-2 h window and the same window on prior weeks, density-clusters the endpoints (default 12-mile radius), and reports clusters above their baseline median with a pattern label: departure_anchor, arrival_anchor, regional concentration, diffuse, or no_excess. Optional reference point gives distance-to-event. At most 12 heatmap files (~14 MB each, cached) per call.",
        inputSchema={
            "type": "object",
            "properties": {
                "cohort": {"type": "string", "enum": ["bizjet", "military"], "default": "bizjet"},
                "region": {"type": "string", "default": "global", "description": "Region preset or 'lamin,lomin,lamax,lomax'"},
                "start": {"type": "string", "description": "UTC ISO start of the window (default: ends at the latest published slot)"},
                "slots": {"type": "integer", "minimum": 1, "maximum": 4, "default": 2, "description": "Window length in half-hours"},
                "baseline_weeks": {"type": "integer", "minimum": 1, "maximum": 4, "default": 3},
                "ref_lat": {"type": "number", "description": "Optional event latitude for distance reporting"},
                "ref_lon": {"type": "number", "description": "Optional event longitude for distance reporting"},
                "cluster_radius_mi": {"type": "number", "default": 12, "minimum": 1, "maximum": 50},
                "min_learning_lead_hours": {
                    "type": "number",
                    "default": 24,
                    "description": "Only use cohort members first seen this long before the window; negative admits later-learned members (marked as a selection-bias data gap)",
                },
            },
        },
    ),
]


async def _internet_outages(arguments: dict[str, Any]) -> Any:
    return await infrastructure.fetch_internet_outages(runtime.fetcher)


async def _cable_health(arguments: dict[str, Any]) -> Any:
    return await infrastructure.fetch_cable_health(runtime.fetcher)


async def _nav_warnings(arguments: dict[str, Any]) -> Any:
    return await maritime.fetch_nav_warnings(
        runtime.fetcher, navarea=arguments.get("navarea")
    )


async def _airport_delays(arguments: dict[str, Any]) -> Any:
    return await aviation.fetch_airport_delays(runtime.fetcher)


async def _aviation_domestic(arguments: dict[str, Any]) -> Any:
    return await aviation.fetch_domestic_flights(runtime.fetcher)


async def _traffic_flow(arguments: dict[str, Any]) -> Any:
    from ..sources.traffic import fetch_traffic_flow

    return await fetch_traffic_flow(runtime.fetcher)


async def _traffic_incidents(arguments: dict[str, Any]) -> Any:
    from ..sources.traffic import fetch_traffic_incidents

    return await fetch_traffic_incidents(runtime.fetcher)


async def _webcams(arguments: dict[str, Any]) -> Any:
    from ..sources.webcams import fetch_webcams

    return await fetch_webcams(
        runtime.fetcher,
        category=arguments.get("category", "traffic"),
        limit=arguments.get("limit", 50),
    )


async def _shipping_index(arguments: dict[str, Any]) -> Any:
    return await shipping.fetch_shipping_index(runtime.fetcher)


async def _service_status(arguments: dict[str, Any]) -> Any:
    return await service_status.fetch_service_status(
        runtime.fetcher,
        provider=arguments.get("provider"),
    )


async def _bgp_status(arguments: dict[str, Any]) -> Any:
    from ..sources import bgp

    return await bgp.fetch_bgp_status(
        runtime.fetcher, resource=arguments.get("resource", "")
    )


async def _jet_cohort_snapshot(arguments: dict[str, Any]) -> Any:
    from ..sources.jet_cohort import fetch_cohort_snapshot

    return await fetch_cohort_snapshot(
        runtime.fetcher,
        cohort=arguments.get("cohort", "bizjet"),
        region=arguments.get("region"),
    )


async def _jet_activity_anomaly(arguments: dict[str, Any]) -> Any:
    from ..analysis.jet_activity import fetch_cohort_activity

    return await fetch_cohort_activity(
        runtime.fetcher,
        cohort=arguments.get("cohort", "bizjet"),
        region=arguments.get("region"),
        baseline_weeks=arguments.get("baseline_weeks", 4),
        slot=arguments.get("slot"),
        alarm_sigma=float(arguments.get("alarm_sigma", 5.0)),
        min_learning_lead_hours=float(arguments.get("min_learning_lead_hours", 24)),
    )


async def _jet_excess_origins(arguments: dict[str, Any]) -> Any:
    from ..analysis.jet_activity import fetch_excess_origins

    return await fetch_excess_origins(
        runtime.fetcher,
        cohort=arguments.get("cohort", "bizjet"),
        region=arguments.get("region"),
        start=arguments.get("start"),
        slots=arguments.get("slots", 2),
        baseline_weeks=arguments.get("baseline_weeks", 3),
        ref_lat=arguments.get("ref_lat"),
        ref_lon=arguments.get("ref_lon"),
        cluster_radius_mi=float(arguments.get("cluster_radius_mi", 12)),
        min_learning_lead_hours=float(arguments.get("min_learning_lead_hours", 24)),
    )


HANDLERS = {
    "intel_internet_outages": _internet_outages,
    "intel_cable_health": _cable_health,
    "intel_nav_warnings": _nav_warnings,
    "intel_airport_delays": _airport_delays,
    "intel_aviation_domestic": _aviation_domestic,
    "intel_traffic_flow": _traffic_flow,
    "intel_traffic_incidents": _traffic_incidents,
    "intel_webcams": _webcams,
    "intel_shipping_index": _shipping_index,
    "intel_service_status": _service_status,
    "intel_bgp_status": _bgp_status,
    "intel_jet_cohort_snapshot": _jet_cohort_snapshot,
    "intel_jet_activity_anomaly": _jet_activity_anomaly,
    "intel_jet_excess_origins": _jet_excess_origins,
}
