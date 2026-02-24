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
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
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
)
from world_intel_mcp.analysis.alerts import fetch_alert_digest, fetch_weekly_trends

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
    }

    gathered = await asyncio.gather(
        *[asyncio.create_task(c) for c in coros.values()],
        return_exceptions=True,
    )

    result: dict = {}
    for name, data in zip(coros.keys(), gathered):
        if isinstance(data, Exception):
            logger.warning("Dashboard fetch %s failed: %s", name, data)
            result[name] = {"error": type(data).__name__ + ": " + str(data)[:120]}
        else:
            result[name] = data

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


async def api_health(request):
    """Health check."""
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/overview", api_overview),
        Route("/api/stream", api_stream),
        Route("/api/health", api_health),
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
