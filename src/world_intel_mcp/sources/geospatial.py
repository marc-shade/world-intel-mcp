"""Static geospatial dataset queries for world-intel-mcp.

Pure data lookups — no network I/O. Uses config/geospatial.py datasets.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..config.geospatial import (
    MILITARY_BASES,
    STRATEGIC_PORTS,
    PIPELINES,
    NUCLEAR_FACILITIES,
    query_bases,
    query_ports,
    query_pipelines,
    query_nuclear,
)
from ..config.cables import UNDERSEA_CABLES, query_cables
from ..config.datacenters import AI_DATACENTERS, query_datacenters
from ..config.spaceports import SPACEPORTS, query_spaceports
from ..config.minerals import CRITICAL_MINERALS, query_minerals
from ..config.exchanges import STOCK_EXCHANGES, query_exchanges
from ..config.trade_routes import TRADE_ROUTES, CLOUD_REGIONS, FINANCIAL_CENTERS


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API — each returns dict matching MCP tool output shape
# ---------------------------------------------------------------------------

async def fetch_military_bases(
    operator: str | None = None,
    country: str | None = None,
    base_type: str | None = None,
    branch: str | None = None,
) -> dict:
    """Query military bases worldwide.

    Args:
        operator: Filter by operating country (USA, RUS, CHN, GBR, FRA, etc.)
        country: Filter by host country name or ISO-3 code.
        base_type: Filter by type (air_base, naval_base, army_base, etc.)
        branch: Filter by branch (USAF, US Navy, PLA Navy, etc.)

    Returns:
        Dict with bases[], count, by_operator{}, by_type{}, source, timestamp.
    """
    bases = query_bases(operator=operator, country=country, base_type=base_type, branch=branch)

    by_operator: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for b in bases:
        by_operator[b["operator"]] = by_operator.get(b["operator"], 0) + 1
        by_type[b["type"]] = by_type.get(b["type"], 0) + 1

    return {
        "bases": bases,
        "count": len(bases),
        "total_in_database": len(MILITARY_BASES),
        "by_operator": by_operator,
        "by_type": by_type,
        "filters": {
            "operator": operator,
            "country": country,
            "base_type": base_type,
            "branch": branch,
        },
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_strategic_ports(
    port_type: str | None = None,
    country: str | None = None,
) -> dict:
    """Query strategic ports worldwide.

    Args:
        port_type: Filter by type (container, oil, lng, naval, bulk, mixed).
        country: Filter by country name or ISO-3 code.

    Returns:
        Dict with ports[], count, by_type{}, source, timestamp.
    """
    ports = query_ports(port_type=port_type, country=country)

    by_type: dict[str, int] = {}
    for p in ports:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1

    return {
        "ports": ports,
        "count": len(ports),
        "total_in_database": len(STRATEGIC_PORTS),
        "by_type": by_type,
        "filters": {"port_type": port_type, "country": country},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_pipelines(
    pipeline_type: str | None = None,
    status: str | None = None,
) -> dict:
    """Query oil, gas, and hydrogen pipelines.

    Args:
        pipeline_type: Filter by type (oil, gas, hydrogen).
        status: Filter by status (active, destroyed, proposed, etc.)

    Returns:
        Dict with pipelines[], count, by_type{}, by_status{}, source, timestamp.
    """
    pipes = query_pipelines(pipeline_type=pipeline_type, status=status)

    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for p in pipes:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1

    return {
        "pipelines": pipes,
        "count": len(pipes),
        "total_in_database": len(PIPELINES),
        "by_type": by_type,
        "by_status": by_status,
        "filters": {"pipeline_type": pipeline_type, "status": status},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_nuclear_facilities(
    facility_type: str | None = None,
    country: str | None = None,
    status: str | None = None,
) -> dict:
    """Query nuclear power plants, enrichment sites, and research reactors.

    Args:
        facility_type: Filter by type (power, enrichment, research, reprocessing, decommissioned).
        country: Filter by country name or ISO-3 code.
        status: Filter by status (operational, construction, shutdown, etc.)

    Returns:
        Dict with facilities[], count, total_capacity_mw, by_type{}, by_status{}, source, timestamp.
    """
    facilities = query_nuclear(facility_type=facility_type, country=country, status=status)

    total_cap = sum(f.get("capacity_mw", 0) for f in facilities)
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for f in facilities:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        by_status[f["status"]] = by_status.get(f["status"], 0) + 1

    return {
        "facilities": facilities,
        "count": len(facilities),
        "total_in_database": len(NUCLEAR_FACILITIES),
        "total_capacity_mw": total_cap,
        "by_type": by_type,
        "by_status": by_status,
        "filters": {"facility_type": facility_type, "country": country, "status": status},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_undersea_cables(
    status: str | None = None,
    country: str | None = None,
    owner: str | None = None,
    min_capacity_tbps: float | None = None,
) -> dict:
    """Query undersea cable routes with landing points."""
    cables = query_cables(status=status, country=country, owner=owner, min_capacity_tbps=min_capacity_tbps)
    total_length = sum(c["length_km"] for c in cables)
    total_capacity = sum(c["capacity_tbps"] for c in cables)
    by_status: dict[str, int] = {}
    for c in cables:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    return {
        "cables": cables,
        "count": len(cables),
        "total_in_database": len(UNDERSEA_CABLES),
        "total_length_km": total_length,
        "total_capacity_tbps": total_capacity,
        "by_status": by_status,
        "filters": {"status": status, "country": country, "owner": owner, "min_capacity_tbps": min_capacity_tbps},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_ai_datacenters(
    country: str | None = None,
    operator: str | None = None,
    min_power_mw: int | None = None,
    region: str | None = None,
) -> dict:
    """Query AI datacenter clusters worldwide."""
    dcs = query_datacenters(country=country, operator=operator, min_power_mw=min_power_mw, region=region)
    total_power = sum(d["power_mw"] for d in dcs)
    by_country: dict[str, int] = {}
    for d in dcs:
        by_country[d["country"]] = by_country.get(d["country"], 0) + 1
    return {
        "datacenters": dcs,
        "count": len(dcs),
        "total_in_database": len(AI_DATACENTERS),
        "total_power_mw": total_power,
        "by_country": by_country,
        "filters": {"country": country, "operator": operator, "min_power_mw": min_power_mw, "region": region},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_spaceports(
    country: str | None = None,
    status: str | None = None,
    spaceport_type: str | None = None,
    operator: str | None = None,
) -> dict:
    """Query launch facilities and spaceports worldwide."""
    sps = query_spaceports(country=country, status=status, spaceport_type=spaceport_type, operator=operator)
    by_country: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for s in sps:
        by_country[s["country"]] = by_country.get(s["country"], 0) + 1
        by_type[s["type"]] = by_type.get(s["type"], 0) + 1
    return {
        "spaceports": sps,
        "count": len(sps),
        "total_in_database": len(SPACEPORTS),
        "by_country": by_country,
        "by_type": by_type,
        "filters": {"country": country, "status": status, "spaceport_type": spaceport_type, "operator": operator},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_critical_minerals(
    mineral: str | None = None,
    country: str | None = None,
    mineral_type: str | None = None,
    operator: str | None = None,
) -> dict:
    """Query critical mineral deposits worldwide."""
    deposits = query_minerals(mineral=mineral, country=country, mineral_type=mineral_type, operator=operator)
    by_mineral: dict[str, int] = {}
    by_country: dict[str, int] = {}
    for d in deposits:
        by_mineral[d["mineral"]] = by_mineral.get(d["mineral"], 0) + 1
        by_country[d["country"]] = by_country.get(d["country"], 0) + 1
    return {
        "deposits": deposits,
        "count": len(deposits),
        "total_in_database": len(CRITICAL_MINERALS),
        "by_mineral": by_mineral,
        "by_country": by_country,
        "filters": {"mineral": mineral, "country": country, "mineral_type": mineral_type, "operator": operator},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_stock_exchanges(
    tier: str | None = None,
    country: str | None = None,
    currency: str | None = None,
) -> dict:
    """Query global stock exchanges (92 exchanges, 4 tiers)."""
    exs = query_exchanges(tier=tier, country=country, currency=currency)
    total_mcap = sum(e["market_cap_usd_t"] for e in exs)
    by_tier: dict[str, int] = {}
    for e in exs:
        by_tier[e["tier"]] = by_tier.get(e["tier"], 0) + 1
    return {
        "exchanges": exs,
        "count": len(exs),
        "total_in_database": len(STOCK_EXCHANGES),
        "total_market_cap_usd_t": round(total_mcap, 2),
        "by_tier": by_tier,
        "filters": {"tier": tier, "country": country, "currency": currency},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_trade_routes(
    route_type: str | None = None,
    country: str | None = None,
) -> dict:
    """Query maritime trade routes and chokepoints.

    Args:
        route_type: Filter by type (chokepoint, canal, route).
        country: Filter by ISO-3 country code in the countries list.
    """
    routes = list(TRADE_ROUTES)
    if route_type:
        routes = [r for r in routes if r["type"] == route_type.lower()]
    if country:
        c = country.upper()
        routes = [r for r in routes if c in r.get("countries", [])]

    total_oil = sum(r.get("oil_flow_mbd", 0) for r in routes)
    by_type: dict[str, int] = {}
    for r in routes:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    return {
        "routes": routes,
        "count": len(routes),
        "total_in_database": len(TRADE_ROUTES),
        "total_oil_flow_mbd": round(total_oil, 1),
        "by_type": by_type,
        "filters": {"route_type": route_type, "country": country},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_cloud_regions(
    provider: str | None = None,
    country: str | None = None,
) -> dict:
    """Query major cloud provider regions (AWS, Azure, GCP).

    Args:
        provider: Filter by provider (AWS, Azure, GCP).
        country: Filter by region name substring.
    """
    regions = list(CLOUD_REGIONS)
    if provider:
        p = provider.upper()
        regions = [r for r in regions if r["provider"].upper() == p]
    if country:
        c = country.lower()
        regions = [r for r in regions if c in r["name"].lower()]

    by_provider: dict[str, int] = {}
    for r in regions:
        by_provider[r["provider"]] = by_provider.get(r["provider"], 0) + 1

    return {
        "regions": regions,
        "count": len(regions),
        "total_in_database": len(CLOUD_REGIONS),
        "by_provider": by_provider,
        "filters": {"provider": provider, "country": country},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }


async def fetch_financial_centers(
    country: str | None = None,
    min_rank: int | None = None,
) -> dict:
    """Query global financial centers (GFCI top 20+).

    Args:
        country: Filter by ISO-3 country code.
        min_rank: Only include centers ranked this or better (lower = better).
    """
    centers = list(FINANCIAL_CENTERS)
    if country:
        c = country.upper()
        centers = [fc for fc in centers if fc["iso3"] == c]
    if min_rank is not None:
        centers = [fc for fc in centers if fc["gfci_rank"] <= min_rank]

    by_country: dict[str, int] = {}
    for fc in centers:
        by_country[fc["iso3"]] = by_country.get(fc["iso3"], 0) + 1

    return {
        "centers": centers,
        "count": len(centers),
        "total_in_database": len(FINANCIAL_CENTERS),
        "by_country": by_country,
        "filters": {"country": country, "min_rank": min_rank},
        "source": "static-geospatial",
        "timestamp": _utc_now_iso(),
    }
