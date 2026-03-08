"""Intelligence Collector Daemon — continuous vector store population.

Fetches all intelligence sources in parallel and stores results in the
Qdrant vector store. Runs independently of the MCP server and dashboard,
ensuring data accumulates 24/7 for semantic search and historical analysis.

Usage:
    intel-collector                    # Single collection cycle
    intel-collector --daemon           # Run every 5 minutes
    intel-collector --interval 120     # Custom interval (seconds)
    intel-collector --sources markets,conflict  # Specific sources only
"""

import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

logging.basicConfig(
    level=os.environ.get("WORLD_INTEL_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("world-intel-collector")

from .cache import Cache
from .circuit_breaker import CircuitBreaker
from .fetcher import Fetcher
from .vector_store import VectorStore

# All fetchable sources grouped by domain.
# Each entry: (name, module_path, function_name, kwargs)
SOURCES = [
    # Markets (7)
    ("market_quotes", "sources.markets", "fetch_market_quotes", {}),
    ("crypto_quotes", "sources.markets", "fetch_crypto_quotes", {}),
    ("macro_signals", "sources.markets", "fetch_macro_signals", {}),
    ("sector_heatmap", "sources.markets", "fetch_sector_heatmap", {}),
    ("stablecoin_status", "sources.markets", "fetch_stablecoin_status", {}),
    ("etf_flows", "sources.markets", "fetch_etf_flows", {}),
    ("commodity_quotes", "sources.markets", "fetch_commodity_quotes", {}),
    ("btc_technicals", "sources.markets", "fetch_btc_technicals", {}),
    # Economic (3)
    ("energy_prices", "sources.economic", "fetch_energy_prices", {}),
    ("central_bank_rates", "sources.central_banks", "fetch_central_bank_rates", {}),
    # Natural Disasters (2)
    ("earthquakes", "sources.seismology", "fetch_earthquakes", {}),
    ("wildfires", "sources.wildfire", "fetch_wildfires", {}),
    # Conflict & Security (4)
    ("acled_events", "sources.conflict", "fetch_acled_events", {}),
    ("ucdp_events", "sources.conflict", "fetch_ucdp_events", {}),
    ("displacement", "sources.displacement", "fetch_displacement_summary", {}),
    # Military (2)
    ("military_flights", "sources.military", "fetch_military_flights", {}),
    # Infrastructure (4)
    ("internet_outages", "sources.infrastructure", "fetch_internet_outages", {}),
    ("cable_health", "sources.infrastructure", "fetch_cable_health", {}),
    ("service_status", "sources.service_status", "fetch_service_status", {}),
    # Maritime (1)
    ("nav_warnings", "sources.maritime", "fetch_nav_warnings", {}),
    # Climate (1)
    ("climate_anomalies", "sources.climate", "fetch_climate_anomalies", {}),
    # News (2)
    ("news_feed", "sources.news", "fetch_news_feed", {}),
    ("trending_keywords", "sources.news", "fetch_trending_keywords", {}),
    # Prediction (1)
    ("prediction_markets", "sources.prediction", "fetch_prediction_markets", {}),
    # Aviation (2)
    ("airport_delays", "sources.aviation", "fetch_airport_delays", {}),
    ("domestic_flights", "sources.aviation", "fetch_domestic_flights", {}),
    # Cyber (1)
    ("cyber_threats", "sources.cyber", "fetch_cyber_threats", {}),
    # Space Weather (1)
    ("space_weather", "sources.space_weather", "fetch_space_weather", {}),
    # AI/Tech (1)
    ("ai_watch", "sources.ai_watch", "fetch_ai_watch", {}),
    # Health (1)
    ("disease_outbreaks", "sources.health", "fetch_disease_outbreaks", {}),
    # Elections (1)
    ("election_calendar", "sources.elections", "fetch_election_calendar", {}),
    # Shipping (1)
    ("shipping_index", "sources.shipping", "fetch_shipping_index", {}),
    # Social (1)
    ("social_signals", "sources.social", "fetch_social_signals", {}),
    # Nuclear (1)
    ("nuclear_monitor", "sources.nuclear", "fetch_nuclear_monitor", {}),
    # Traffic (2)
    ("traffic_flow", "sources.traffic", "fetch_traffic_flow", {}),
    ("traffic_incidents", "sources.traffic", "fetch_traffic_incidents", {}),
    # Analysis (cross-domain, runs after raw sources)
    ("risk_scores", "sources.intelligence", "fetch_risk_scores", {}),
    ("signal_convergence", "sources.intelligence", "fetch_signal_convergence", {}),
    ("alert_digest", "analysis.alerts", "fetch_alert_digest", {}),
    ("weekly_trends", "analysis.alerts", "fetch_weekly_trends", {}),
    ("strategic_posture", "analysis.posture", "fetch_strategic_posture", {}),
    ("fleet_report", "sources.fleet", "fetch_fleet_report", {}),
    ("usni_fleet", "sources.usni_fleet", "fetch_usni_fleet", {}),
]

# Domain name → list of source names for --sources filtering
DOMAIN_GROUPS = {
    "markets": [
        "market_quotes",
        "crypto_quotes",
        "macro_signals",
        "sector_heatmap",
        "stablecoin_status",
        "etf_flows",
        "commodity_quotes",
        "btc_technicals",
    ],
    "economic": ["energy_prices", "central_bank_rates"],
    "natural": ["earthquakes", "wildfires"],
    "conflict": ["acled_events", "ucdp_events", "displacement"],
    "military": ["military_flights"],
    "infrastructure": ["internet_outages", "cable_health", "service_status"],
    "maritime": ["nav_warnings"],
    "climate": ["climate_anomalies"],
    "news": ["news_feed", "trending_keywords"],
    "prediction": ["prediction_markets"],
    "aviation": ["airport_delays", "domestic_flights"],
    "cyber": ["cyber_threats"],
    "space": ["space_weather"],
    "ai": ["ai_watch"],
    "health": ["disease_outbreaks"],
    "elections": ["election_calendar"],
    "shipping": ["shipping_index"],
    "social": ["social_signals"],
    "nuclear": ["nuclear_monitor"],
    "traffic": ["traffic_flow", "traffic_incidents"],
    "analysis": [
        "risk_scores",
        "signal_convergence",
        "alert_digest",
        "weekly_trends",
        "strategic_posture",
        "fleet_report",
        "usni_fleet",
    ],
}


def _resolve_source_filter(source_filter: str | None) -> set[str] | None:
    """Resolve --sources argument to a set of source names."""
    if not source_filter:
        return None
    names: set[str] = set()
    for part in source_filter.split(","):
        part = part.strip()
        if part in DOMAIN_GROUPS:
            names.update(DOMAIN_GROUPS[part])
        else:
            names.add(part)
    return names


def _import_fetch_fn(module_path: str, fn_name: str):
    """Dynamically import a fetch function from world_intel_mcp."""
    import importlib

    full_module = f"world_intel_mcp.{module_path}"
    mod = importlib.import_module(full_module)
    return getattr(mod, fn_name)


async def collect_once(
    fetcher: Fetcher,
    vector_store: VectorStore,
    source_filter: set[str] | None = None,
    timeout: float = 45.0,
) -> dict:
    """Run one collection cycle across all sources.

    Returns dict with counts of successes, failures, and skipped.
    """
    start = time.time()
    sources_to_run = [
        s for s in SOURCES if source_filter is None or s[0] in source_filter
    ]

    async def _fetch_one(name: str, module_path: str, fn_name: str, kwargs: dict):
        try:
            fn = _import_fetch_fn(module_path, fn_name)
            result = await asyncio.wait_for(fn(fetcher, **kwargs), timeout=timeout)
            return name, result, None
        except asyncio.TimeoutError:
            return name, None, f"timeout ({timeout}s)"
        except Exception as exc:
            return name, None, str(exc)[:120]

    tasks = [_fetch_one(name, mod, fn, kw) for name, mod, fn, kw in sources_to_run]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = 0
    failures = 0
    errors = []

    for item in results:
        if isinstance(item, Exception):
            failures += 1
            errors.append(str(item)[:100])
            continue
        name, data, error = item
        if error:
            failures += 1
            errors.append(f"{name}: {error}")
            logger.warning("Collect %s failed: %s", name, error)
        elif data is not None:
            successes += 1
            # The fetcher already stores in vector_store via its hook,
            # but for sources that return composite data (analysis modules),
            # we also store the high-level result directly.
            if not isinstance(data, dict) or not data.get("error"):
                await vector_store.store(name, data)
        else:
            failures += 1

    elapsed = time.time() - start
    stats = await vector_store.collection_stats()

    summary = {
        "cycle_time_s": round(elapsed, 1),
        "sources_attempted": len(sources_to_run),
        "successes": successes,
        "failures": failures,
        "errors": errors[:10],
        "vector_store_points": stats.get("points_count", 0),
    }

    logger.info(
        "Collection cycle: %d/%d sources in %.1fs, %d vector points",
        successes,
        len(sources_to_run),
        elapsed,
        stats.get("points_count", 0),
    )

    return summary


async def run_daemon(
    interval: int = 300,
    source_filter: str | None = None,
) -> None:
    """Run the collector in daemon mode with a configurable interval."""
    cache = Cache()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=300)
    vector_store = VectorStore(enabled=True)
    await vector_store.start()
    fetcher = Fetcher(cache=cache, breaker=breaker, vector_store=vector_store)

    resolved_filter = _resolve_source_filter(source_filter)
    filter_desc = source_filter or "all"

    logger.info(
        "Collector daemon starting: interval=%ds, sources=%s",
        interval,
        filter_desc,
    )

    stop_event = asyncio.Event()

    def _handle_signal(sig, frame):
        logger.info("Received signal %s, stopping...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    cycle = 0
    while not stop_event.is_set():
        cycle += 1
        logger.info("Starting collection cycle %d", cycle)
        try:
            summary = await collect_once(fetcher, vector_store, resolved_filter)
            logger.info("Cycle %d complete: %s", cycle, summary)
        except Exception as exc:
            logger.error("Cycle %d failed: %s", cycle, exc)

        # Evict expired cache entries periodically
        if cycle % 12 == 0:  # Every ~hour at 5min interval
            evicted = cache.evict_expired()
            if evicted:
                logger.info("Evicted %d expired cache entries", evicted)

        # Wait for next cycle or stop signal
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    await vector_store.stop()
    await fetcher.close()
    logger.info("Collector daemon stopped")


async def run_once(source_filter: str | None = None) -> dict:
    """Run a single collection cycle and exit."""
    cache = Cache()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=300)
    vector_store = VectorStore(enabled=True)
    await vector_store.start()
    fetcher = Fetcher(cache=cache, breaker=breaker, vector_store=vector_store)

    resolved_filter = _resolve_source_filter(source_filter)
    summary = await collect_once(fetcher, vector_store, resolved_filter)

    # Wait for vector store queue to drain
    if vector_store._store_queue:
        await vector_store._store_queue.join()

    await vector_store.stop()
    await fetcher.close()

    return summary


def main():
    """CLI entry point for the collector."""
    import argparse

    parser = argparse.ArgumentParser(
        description="World Intelligence Collector — populate vector store from all sources"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously at --interval seconds",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Collection interval in seconds (default: 300 = 5 minutes)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated source names or domain groups (e.g., 'markets,conflict,cyber')",
    )
    args = parser.parse_args()

    if args.daemon:
        asyncio.run(run_daemon(interval=args.interval, source_filter=args.sources))
    else:
        summary = asyncio.run(run_once(source_filter=args.sources))
        print("Collection complete:")
        print(
            f"  Sources: {summary['successes']}/{summary['sources_attempted']} succeeded"
        )
        print(f"  Time: {summary['cycle_time_s']}s")
        print(f"  Vector store: {summary['vector_store_points']} points")
        if summary["errors"]:
            print(f"  Errors ({len(summary['errors'])}):")
            for e in summary["errors"]:
                print(f"    - {e}")
        sys.exit(0 if summary["failures"] == 0 else 1)


if __name__ == "__main__":
    main()
