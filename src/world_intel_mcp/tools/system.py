"""System tools: server health and source status.

The exemplar domain module for the Phase 26 split. The pattern every
migrated module follows:

- ``TOOLS`` holds the ``Tool`` definitions verbatim from the old
  server.py registry (descriptions and schemas unchanged).
- ``HANDLERS`` maps each tool name to an ``async def h(arguments)``
  whose body is the old ``_dispatch`` case verbatim, with shared
  infrastructure reached via ``runtime`` (``runtime.fetcher``,
  ``runtime.cache``, ``runtime.aoi_store``, ``runtime.vector_store``)
  instead of server.py module globals.
- ``aggregate()`` in the package init refuses to import a module whose
  TOOLS and HANDLERS disagree.
"""

from typing import Any

from mcp.types import Tool

from .. import runtime

TOOLS: list[Tool] = [
    Tool(
        name="intel_status",
        description="Get data source health, circuit breaker status, cache freshness, vector store stats, and system statistics.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def _status(arguments: dict[str, Any]) -> Any:
    vs_stats = {
        "enabled": False,
        "error": 'Vector store dependencies not installed. Install with `pip install -e ".[vector]"`.',
    }
    if runtime.vector_store:
        vs_stats = await runtime.vector_store.collection_stats()
    return {
        "circuit_breakers": runtime.breaker.status(),
        "cache": runtime.cache.stats(),
        "cache_freshness": runtime.cache.freshness(),
        "vector_store": vs_stats,
        "sources": {
            "markets": [
                "yahoo-finance",
                "coingecko",
                "alternative-me",
                "mempool",
            ],
            "economic": ["eia", "fred", "world-bank"],
            "natural": ["usgs", "nasa-firms"],
            "conflict": ["acled", "ucdp", "hdx"],
            "military": ["opensky", "hexdb", "adsblol"],
            "infrastructure": ["cloudflare-radar", "ioda", "nga-msi"],
            "maritime": ["nga-msi"],
            "climate": ["open-meteo"],
            "news": ["rss-aggregator", "gdelt"],
            "intelligence": ["ollama", "acled", "world-bank", "hdx", "usgs"],
            "prediction": ["polymarket", "kalshi"],
            "displacement": ["unhcr"],
            "aviation": ["faa"],
            "cyber": ["feodo-tracker", "cisa-kev", "sans-dshield", "netapi-honeypot"],
            "space_weather": ["noaa-swpc"],
            "ai_watch": ["arxiv", "huggingface", "ai-news-rss"],
            "health": ["who-don", "cdc", "outbreak-news"],
            "sanctions": ["ofac-sdn"],
            "elections": ["election-calendar"],
            "shipping": ["yahoo-finance"],
            "social": ["reddit-public"],
            "nuclear": ["usgs-nuclear-monitor"],
            "service_status": ["aws", "azure", "gcp", "cloudflare", "github"],
            "geospatial": [
                "static-datasets (bases, ports, pipelines, nuclear, cables, datacenters, spaceports, minerals, exchanges, trade-routes, cloud-regions, financial-centers)"
            ],
            "nlp": [
                "regex-ner",
                "keyword-classifier",
                "jaccard-clustering",
                "keyword-spike-detector",
            ],
            "synthesis": [
                "strategic-posture",
                "world-brief",
                "fleet-report",
                "population-exposure",
            ],
            "tech": ["hackernews", "github", "arxiv"],
            "government": ["usaspending-gov"],
            "environmental": ["eonet", "gdacs"],
            "forex": ["ecb-frankfurter"],
            "bonds": ["fred", "yahoo-finance"],
            "earnings": ["yahoo-finance"],
            "sec_filings": ["sec-edgar"],
            "company_enrichment": [
                "yahoo-finance",
                "gdelt",
                "sec-edgar",
                "github",
            ],
            "macro_composite": [
                "yahoo-finance",
                "coingecko",
                "alternative-me",
            ],
        },
    }


HANDLERS = {
    "intel_status": _status,
}
