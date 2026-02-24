"""World Intelligence Dashboard — live real-time intelligence overview.

Starlette app serving a self-contained HTML dashboard with SSE streaming.
All data pulled from the same source modules used by the MCP server.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher
from world_intel_mcp.sources import (
    markets,
    seismology,
    military,
    infrastructure,
    maritime,
    economic,
    wildfire,
    cyber,
    news,
    prediction,
    displacement,
    aviation,
    climate,
    conflict,
    intelligence,
    space_weather,
    ai_watch,
    health,
    elections,
    shipping,
    social,
    nuclear,
    service_status,
)
from world_intel_mcp.analysis.alerts import fetch_alert_digest, fetch_weekly_trends
from world_intel_mcp.analysis.posture import fetch_strategic_posture
from world_intel_mcp.analysis.exposure import fetch_population_exposure
from world_intel_mcp.sources.fleet import fetch_fleet_report
from world_intel_mcp.config.countries import INTEL_HOTSPOTS
from world_intel_mcp.config.geospatial import MILITARY_BASES, STRATEGIC_PORTS, PIPELINES, NUCLEAR_FACILITIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared infrastructure — lazily initialised
# ---------------------------------------------------------------------------
_fetcher: Fetcher | None = None
_cache: Cache | None = None
_breaker: CircuitBreaker | None = None


def _ensure_fetcher() -> Fetcher:
    global _fetcher, _cache, _breaker
    if _fetcher is None:
        _cache = Cache()
        _breaker = CircuitBreaker()
        _fetcher = Fetcher(cache=_cache, breaker=_breaker)
    return _fetcher


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

async def _fetch_overview() -> dict:
    """Fetch all dashboard domains in parallel, return unified dict."""
    fetcher = _ensure_fetcher()

    coros = {
        "market_quotes": markets.fetch_market_quotes(fetcher),
        "crypto_quotes": markets.fetch_crypto_quotes(fetcher),
        "macro_signals": markets.fetch_macro_signals(fetcher),
        "sector_heatmap": markets.fetch_sector_heatmap(fetcher),
        "earthquakes": seismology.fetch_earthquakes(fetcher),
        "military_flights": military.fetch_military_flights(fetcher),
        "cyber_threats": cyber.fetch_cyber_threats(fetcher),
        "news_feed": news.fetch_news_feed(fetcher),
        "trending_keywords": news.fetch_trending_keywords(fetcher),
        "nav_warnings": maritime.fetch_nav_warnings(fetcher),
        "internet_outages": infrastructure.fetch_internet_outages(fetcher),
        "cable_health": infrastructure.fetch_cable_health(fetcher),
        "wildfires": wildfire.fetch_wildfires(fetcher),
        "prediction_markets": prediction.fetch_prediction_markets(fetcher),
        "airport_delays": aviation.fetch_airport_delays(fetcher),
        "climate_anomalies": climate.fetch_climate_anomalies(fetcher),
        "energy_prices": economic.fetch_energy_prices(fetcher),
        "stablecoin_status": markets.fetch_stablecoin_status(fetcher),
        "etf_flows": markets.fetch_etf_flows(fetcher),
        "acled_events": conflict.fetch_acled_events(fetcher),
        "ucdp_events": conflict.fetch_ucdp_events(fetcher),
        "displacement": displacement.fetch_displacement_summary(fetcher),
        "risk_scores": intelligence.fetch_risk_scores(fetcher),
        "signal_convergence": intelligence.fetch_signal_convergence(fetcher),
        "space_weather": space_weather.fetch_space_weather(fetcher),
        "ai_watch": ai_watch.fetch_ai_watch(fetcher),
        "disease_outbreaks": health.fetch_disease_outbreaks(fetcher),
        "election_calendar": elections.fetch_election_calendar(fetcher),
        "shipping_index": shipping.fetch_shipping_index(fetcher),
        "social_signals": social.fetch_social_signals(fetcher),
        "nuclear_monitor": nuclear.fetch_nuclear_monitor(fetcher),
        "alert_digest": fetch_alert_digest(fetcher),
        "weekly_trends": fetch_weekly_trends(fetcher),
        "service_status": service_status.fetch_service_status(fetcher),
        "strategic_posture": fetch_strategic_posture(fetcher),
        "fleet_report": fetch_fleet_report(fetcher),
        "population_exposure": fetch_population_exposure(fetcher),
    }

    # Per-coro timeout so no single slow source blocks the entire dashboard.
    # Without this, 80+ RSS feeds timing out sequentially can delay the
    # first SSE frame for minutes, leaving the dashboard stuck at all-zeros.
    async def _with_timeout(name: str, coro, timeout: float = 45.0):
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Dashboard fetch %s timed out after %.0fs", name, timeout)
            return {"error": f"timeout after {timeout}s", "_timeout": True}

    gathered = await asyncio.gather(
        *[_with_timeout(name, c) for name, c in zip(coros.keys(), coros.values())],
        return_exceptions=True,
    )

    result: dict = {}
    for name, data in zip(coros.keys(), gathered):
        if isinstance(data, Exception):
            logger.warning("Dashboard fetch %s failed: %s", name, data)
            result[name] = {"error": type(data).__name__ + ": " + str(data)[:120]}
        else:
            result[name] = data

    # Conflict zone fallback: when both ACLED and UCDP fail, provide
    # static hotspot data so the conflict layer is never empty.
    acled = result.get("acled_events", {})
    ucdp = result.get("ucdp_events", {})
    acled_ok = not acled.get("error") and (acled.get("count") or 0) > 0
    ucdp_ok = not ucdp.get("error") and (ucdp.get("count") or 0) > 0
    if not acled_ok and not ucdp_ok:
        escalation_labels = {1: "low", 2: "low", 3: "moderate", 4: "high", 5: "critical"}
        hotspot_events = [
            {
                "latitude": h["lat"],
                "longitude": h["lon"],
                "country": name.replace("_", " ").title(),
                "event_type": "conflict zone",
                "type_of_violence_label": "active hotspot",
                "fatalities": 0,
                "best": 0,
                "escalation": h["baseline_escalation"],
                "severity": escalation_labels.get(h["baseline_escalation"], "unknown"),
                "associated_countries": h.get("associated_countries", []),
            }
            for name, h in INTEL_HOTSPOTS.items()
        ]
        result["conflict_zones"] = {
            "events": hotspot_events,
            "count": len(hotspot_events),
            "source": "intel-hotspots",
        }

    # Static geospatial datasets (no API calls)
    result["military_bases"] = {"bases": MILITARY_BASES, "count": len(MILITARY_BASES)}
    result["strategic_ports"] = {"ports": STRATEGIC_PORTS, "count": len(STRATEGIC_PORTS)}
    result["pipelines"] = {"pipelines": PIPELINES, "count": len(PIPELINES)}
    result["nuclear_facilities"] = {"facilities": NUCLEAR_FACILITIES, "count": len(NUCLEAR_FACILITIES)}

    # Attach source health + timestamp
    result["source_health"] = _breaker.status() if _breaker else {}
    result["cache_stats"] = _cache.stats() if _cache else {}
    result["timestamp"] = datetime.now(timezone.utc).isoformat()

    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

async def index(request):
    """Serve the dashboard HTML page (reloads on each request during dev)."""
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())


async def api_overview(request):
    """REST endpoint — full snapshot of all intelligence domains."""
    data = await _fetch_overview()
    return JSONResponse(data, headers={"Access-Control-Allow-Origin": "*"})


async def api_stream(request):
    """SSE endpoint — pushes full overview every 30 seconds."""

    async def event_generator():
        while True:
            try:
                data = await _fetch_overview()
                payload = json.dumps(data, default=str)
                yield f"data: {payload}\n\n"
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.exception("SSE tick failed")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def api_static(request):
    """Return static geospatial datasets instantly (no API calls).

    The dashboard fetches this on boot so the infrastructure layer
    populates immediately without waiting for the full SSE gather.
    """
    return JSONResponse({
        "military_bases": {"bases": MILITARY_BASES, "count": len(MILITARY_BASES)},
        "strategic_ports": {"ports": STRATEGIC_PORTS, "count": len(STRATEGIC_PORTS)},
        "pipelines": {"pipelines": PIPELINES, "count": len(PIPELINES)},
        "nuclear_facilities": {"facilities": NUCLEAR_FACILITIES, "count": len(NUCLEAR_FACILITIES)},
    }, headers={"Access-Control-Allow-Origin": "*"})


async def api_health(request):
    """Health check."""
    return JSONResponse({"status": "ok"})


async def api_report_pdf(request):
    """Generate a PDF daily brief report.

    Renders the daily_brief.html template with live data, then converts
    to PDF via weasyprint.  Requires ``pip install world-intel-mcp[pdf]``.
    """
    try:
        from weasyprint import HTML as WeasyHTML
    except ImportError:
        return JSONResponse(
            {"error": "weasyprint not installed — run: pip install world-intel-mcp[pdf]"},
            status_code=501,
        )

    from world_intel_mcp.reports.html_report import render_template

    data = await _fetch_overview()

    context = {
        "title": "Daily Intelligence Brief",
        "generated_at": data.get("timestamp", ""),
        "market_quotes": data.get("market_quotes", {}),
        "crypto_quotes": data.get("crypto_quotes", {}),
        "macro_signals": data.get("macro_signals", {}),
        "earthquakes": data.get("earthquakes", {}),
        "cyber_threats": data.get("cyber_threats", {}),
        "news_feed": data.get("news_feed", {}),
        "military_flights": data.get("military_flights", {}),
        "internet_outages": data.get("internet_outages", {}),
        "climate_anomalies": data.get("climate_anomalies", {}),
        "displacement": data.get("displacement", {}),
        "risk_scores": data.get("risk_scores", {}),
        "alert_digest": data.get("alert_digest", {}),
    }

    html_str = render_template("daily_brief.html", context)
    pdf_bytes = WeasyHTML(string=html_str).write_pdf()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="intel-brief-{now_str}.pdf"',
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/overview", api_overview),
        Route("/api/stream", api_stream),
        Route("/api/static", api_static),
        Route("/api/health", api_health),
        Route("/api/report/pdf", api_report_pdf),
    ],
)


def run(host: str = "127.0.0.1", port: int = 8501) -> None:
    """Launch the dashboard server."""
    import uvicorn

    logger.info("Starting Intelligence Dashboard on http://%s:%d", host, port)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
