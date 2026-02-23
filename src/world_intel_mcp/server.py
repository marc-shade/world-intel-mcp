#!/usr/bin/env python3
"""
World Intelligence MCP Server
==============================

Real-time global intelligence across 17 domains:
financial markets, economic indicators, earthquakes, wildfires,
conflict, military flights, infrastructure, and more.

Phase 1: Markets, Economic, Seismology, Wildfire (12 tools).
Phase 2: Conflict, Military, Infrastructure, Maritime, Climate (+10 = 22 tools).
Phase 3: News, Intelligence, Prediction, Displacement, Aviation, Cyber (+14 = 36 tools).
Phase 4: Reports — daily brief, country dossier, threat landscape (+3 = 39 tools).
"""

import asyncio
import json
import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .cache import Cache
from .circuit_breaker import CircuitBreaker
from .fetcher import Fetcher
from .sources import markets, economic, seismology, wildfire, conflict, military, infrastructure, maritime, climate, news, intelligence, prediction, displacement, aviation, cyber
from .reports import generator as report_gen

logging.basicConfig(
    level=os.environ.get("WORLD_INTEL_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("world-intel-mcp")

server = Server("world-intel-mcp")
cache = Cache()
breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=300)
fetcher = Fetcher(cache=cache, breaker=breaker)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    # --- Markets (6 tools) ---
    Tool(
        name="intel_market_quotes",
        description="Get real-time stock market index quotes (S&P 500, Dow, Nasdaq, FTSE, Nikkei, etc.). Optional: symbols (list of ticker symbols).",
        inputSchema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols (default: major indices)",
                },
            },
        },
    ),
    Tool(
        name="intel_crypto_quotes",
        description="Get top cryptocurrency prices, market caps, and 7-day sparklines from CoinGecko. Optional: limit (int, default 20).",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of coins (default 20)", "default": 20},
            },
        },
    ),
    Tool(
        name="intel_stablecoin_status",
        description="Check stablecoin peg health (USDT, USDC, DAI, FDUSD). Flags depegs >0.5%.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_etf_flows",
        description="Get Bitcoin spot ETF prices and volumes (IBIT, FBTC, GBTC, ARKB, BITB).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_sector_heatmap",
        description="Get US equity sector performance heatmap (11 SPDR sector ETFs).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_macro_signals",
        description="Get 7 key macro signals: Fear & Greed, mempool fees, DXY, VIX, gold, 10Y Treasury, BTC dominance.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Economic (3 tools) ---
    Tool(
        name="intel_energy_prices",
        description="Get crude oil (Brent, WTI) and natural gas prices from EIA. Requires EIA_API_KEY.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_fred_series",
        description="Get Federal Reserve economic data series (GDP, UNRATE, CPIAUCSL, DFF, T10YIE, etc.). Requires FRED_API_KEY.",
        inputSchema={
            "type": "object",
            "properties": {
                "series_id": {"type": "string", "description": "FRED series ID (e.g., 'UNRATE')"},
                "limit": {"type": "integer", "description": "Number of observations", "default": 30},
            },
            "required": ["series_id"],
        },
    ),
    Tool(
        name="intel_world_bank_indicators",
        description="Get World Bank development indicators (GDP, inflation, unemployment) for a country.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "ISO country code (default: USA)", "default": "USA"},
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "World Bank indicator codes",
                },
            },
        },
    ),
    # --- Natural (2 tools) ---
    Tool(
        name="intel_earthquakes",
        description="Get recent earthquakes from USGS. No API key needed.",
        inputSchema={
            "type": "object",
            "properties": {
                "min_magnitude": {"type": "number", "description": "Minimum magnitude (default 4.5)", "default": 4.5},
                "hours": {"type": "integer", "description": "Lookback hours (default 24)", "default": 24},
                "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50},
            },
        },
    ),
    Tool(
        name="intel_wildfires",
        description="Get active wildfires from NASA FIRMS (9 global regions). Requires NASA_FIRMS_API_KEY.",
        inputSchema={
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Specific region (north_america, europe, etc.) or omit for all 9",
                    "enum": [
                        "north_america", "south_america", "europe", "africa",
                        "middle_east", "south_asia", "east_asia", "southeast_asia", "oceania",
                    ],
                },
            },
        },
    ),
    # --- Conflict (3 tools) ---
    Tool(
        name="intel_acled_events",
        description="Get armed conflict events from ACLED. Optional: country (name), days (default 7), limit (default 100). Requires ACLED_ACCESS_TOKEN.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Country name filter"},
                "days": {"type": "integer", "description": "Lookback days (default 7)", "default": 7},
                "limit": {"type": "integer", "description": "Max results (default 100)", "default": 100},
            },
        },
    ),
    Tool(
        name="intel_ucdp_events",
        description="Get state-based violence events from UCDP GED. No API key needed. Optional: days (default 30).",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback days (default 30)", "default": 30},
                "limit": {"type": "integer", "description": "Max results (default 100)", "default": 100},
            },
        },
    ),
    Tool(
        name="intel_humanitarian_summary",
        description="Get humanitarian crisis datasets from HDX. No API key needed. Optional: country code.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "ISO country code filter"},
            },
        },
    ),
    # --- Military (3 tools) ---
    Tool(
        name="intel_military_flights",
        description="Track military aircraft via OpenSky Network (ICAO hex + callsign filtering). Optional: bbox (lamin,lomin,lamax,lomax).",
        inputSchema={
            "type": "object",
            "properties": {
                "bbox": {"type": "string", "description": "Bounding box: lamin,lomin,lamax,lomax"},
            },
        },
    ),
    Tool(
        name="intel_theater_posture",
        description="Get military aircraft presence across 5 theaters: European, Indo-Pacific, Middle East, Arctic, Korean Peninsula.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_aircraft_details",
        description="Get aircraft details from hexdb.io by ICAO24 hex code (free, no API key).",
        inputSchema={
            "type": "object",
            "properties": {
                "icao24": {"type": "string", "description": "ICAO24 hex code"},
            },
            "required": ["icao24"],
        },
    ),
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
        description="Get active navigational warnings from NGA Maritime Safety. Optional: navarea (I-XVI).",
        inputSchema={
            "type": "object",
            "properties": {
                "navarea": {"type": "string", "description": "NAVAREA number (e.g., IV, XII)"},
            },
        },
    ),
    # --- Climate (1 tool) ---
    Tool(
        name="intel_climate_anomalies",
        description="Detect temperature and precipitation anomalies across 15 global climate zones (vs. prior year baseline).",
        inputSchema={
            "type": "object",
            "properties": {
                "zones": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Zone keys to check (default: all 15)",
                },
            },
        },
    ),
    # --- Prediction (1 tool) ---
    Tool(
        name="intel_prediction_markets",
        description="Get active prediction markets from Polymarket (questions, YES probabilities, volumes, sentiment).",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of markets (default 20)", "default": 20},
            },
        },
    ),
    # --- Displacement (1 tool) ---
    Tool(
        name="intel_displacement_summary",
        description="Get UNHCR refugee/displacement statistics by country of origin. No API key needed.",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Reporting year (default: last year)"},
            },
        },
    ),
    # --- Aviation (1 tool) ---
    Tool(
        name="intel_airport_delays",
        description="Get current US airport delays from FAA (20 major airports). No API key needed.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Cyber (1 tool) ---
    Tool(
        name="intel_cyber_threats",
        description="Get aggregated cyber threat intelligence from 4 feeds (Feodo, CISA KEV, SANS, URLhaus). No API key needed.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max threats (default 50)", "default": 50},
            },
        },
    ),
    # --- News (3 tools) ---
    Tool(
        name="intel_news_feed",
        description="Get aggregated intelligence news from 20+ RSS feeds across 6 categories (geopolitics, security, tech, finance, military, science).",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category filter",
                    "enum": ["geopolitics", "security", "technology", "finance", "military", "science"],
                },
                "limit": {"type": "integer", "description": "Max items (default 50)", "default": 50},
            },
        },
    ),
    Tool(
        name="intel_trending_keywords",
        description="Detect trending keywords from recent news headlines. Keyword spike detection across 20+ feeds.",
        inputSchema={
            "type": "object",
            "properties": {
                "min_count": {"type": "integer", "description": "Minimum occurrences (default 3)", "default": 3},
            },
        },
    ),
    Tool(
        name="intel_gdelt_search",
        description="Search GDELT 2.0 for global news articles or volume timelines. No API key needed.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (default: 'conflict')", "default": "conflict"},
                "mode": {
                    "type": "string",
                    "description": "artlist (articles) or timelinevol (volume timeline)",
                    "enum": ["artlist", "timelinevol"],
                    "default": "artlist",
                },
                "limit": {"type": "integer", "description": "Max records (default 50)", "default": 50},
            },
        },
    ),
    # --- Intelligence (4 tools) ---
    Tool(
        name="intel_country_brief",
        description="Generate a country intelligence brief using Ollama LLM + World Bank + ACLED data. Falls back to data-only if LLM unavailable.",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "ISO country code (default: US)", "default": "US"},
            },
        },
    ),
    Tool(
        name="intel_risk_scores",
        description="Get country risk scores computed from ACLED conflict data vs historical baselines. Requires ACLED_ACCESS_TOKEN.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Top N countries (default 20)", "default": 20},
            },
        },
    ),
    Tool(
        name="intel_instability_index",
        description="Compute Country Instability Index (0-100) from conflict, economic, humanitarian, infrastructure, and military signals.",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "ISO alpha-3 code (e.g., UKR). Omit for top-10 focus countries."},
            },
        },
    ),
    Tool(
        name="intel_signal_convergence",
        description="Detect geographic convergence of multi-domain signals (earthquakes, conflict, military) in hotspot regions.",
        inputSchema={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Center latitude (omit for 5 global hotspots)"},
                "lon": {"type": "number", "description": "Center longitude"},
                "radius_deg": {"type": "number", "description": "Radius in degrees (default 5.0)", "default": 5.0},
            },
        },
    ),
    # --- Reports (3 tools) ---
    Tool(
        name="intel_daily_brief",
        description="Generate a daily intelligence brief HTML report (markets, conflict, cyber, natural, predictions, trending). Returns file path.",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "Custom output directory (default: $STORAGE_BASE/reports/intel/)"},
            },
        },
    ),
    Tool(
        name="intel_country_dossier",
        description="Generate a full country dossier HTML report (brief, instability index, conflict, displacement, economic). Returns file path.",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "ISO country code (e.g., UKR, SYR, MMR)"},
                "output_dir": {"type": "string", "description": "Custom output directory"},
            },
            "required": ["country_code"],
        },
    ),
    Tool(
        name="intel_threat_landscape",
        description="Generate a threat landscape HTML report (cyber threats, conflict, military, cable health, outages). Returns file path.",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "Custom output directory"},
            },
        },
    ),
    # --- System (1 tool) ---
    Tool(
        name="intel_status",
        description="Get data source health, circuit breaker status, and cache statistics.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

async def _dispatch(name: str, arguments: dict[str, Any]) -> Any:
    """Route tool call to the appropriate source function."""
    match name:
        # Markets
        case "intel_market_quotes":
            return await markets.fetch_market_quotes(fetcher, symbols=arguments.get("symbols"))
        case "intel_crypto_quotes":
            return await markets.fetch_crypto_quotes(fetcher, limit=arguments.get("limit", 20))
        case "intel_stablecoin_status":
            return await markets.fetch_stablecoin_status(fetcher)
        case "intel_etf_flows":
            return await markets.fetch_etf_flows(fetcher)
        case "intel_sector_heatmap":
            return await markets.fetch_sector_heatmap(fetcher)
        case "intel_macro_signals":
            return await markets.fetch_macro_signals(fetcher)

        # Economic
        case "intel_energy_prices":
            return await economic.fetch_energy_prices(fetcher)
        case "intel_fred_series":
            return await economic.fetch_fred_series(
                fetcher,
                series_id=arguments["series_id"],
                limit=arguments.get("limit", 30),
            )
        case "intel_world_bank_indicators":
            return await economic.fetch_world_bank_indicators(
                fetcher,
                country=arguments.get("country", "USA"),
                indicators=arguments.get("indicators"),
            )

        # Natural
        case "intel_earthquakes":
            return await seismology.fetch_earthquakes(
                fetcher,
                min_magnitude=arguments.get("min_magnitude", 4.5),
                hours=arguments.get("hours", 24),
                limit=arguments.get("limit", 50),
            )
        case "intel_wildfires":
            return await wildfire.fetch_wildfires(fetcher, region=arguments.get("region"))

        # Conflict
        case "intel_acled_events":
            return await conflict.fetch_acled_events(
                fetcher,
                country=arguments.get("country"),
                days=arguments.get("days", 7),
                limit=arguments.get("limit", 100),
            )
        case "intel_ucdp_events":
            return await conflict.fetch_ucdp_events(
                fetcher,
                days=arguments.get("days", 30),
                limit=arguments.get("limit", 100),
            )
        case "intel_humanitarian_summary":
            return await conflict.fetch_humanitarian_summary(
                fetcher, country=arguments.get("country"),
            )

        # Military
        case "intel_military_flights":
            return await military.fetch_military_flights(fetcher, bbox=arguments.get("bbox"))
        case "intel_theater_posture":
            return await military.fetch_theater_posture(fetcher)
        case "intel_aircraft_details":
            return await military.fetch_aircraft_details(fetcher, icao24=arguments["icao24"])

        # Infrastructure
        case "intel_internet_outages":
            return await infrastructure.fetch_internet_outages(fetcher)
        case "intel_cable_health":
            return await infrastructure.fetch_cable_health(fetcher)

        # Maritime
        case "intel_nav_warnings":
            return await maritime.fetch_nav_warnings(fetcher, navarea=arguments.get("navarea"))

        # Climate
        case "intel_climate_anomalies":
            return await climate.fetch_climate_anomalies(fetcher, zones=arguments.get("zones"))

        # Prediction
        case "intel_prediction_markets":
            return await prediction.fetch_prediction_markets(fetcher, limit=arguments.get("limit", 20))

        # Displacement
        case "intel_displacement_summary":
            return await displacement.fetch_displacement_summary(fetcher, year=arguments.get("year"))

        # Aviation
        case "intel_airport_delays":
            return await aviation.fetch_airport_delays(fetcher)

        # Cyber
        case "intel_cyber_threats":
            return await cyber.fetch_cyber_threats(fetcher, limit=arguments.get("limit", 50))

        # News
        case "intel_news_feed":
            return await news.fetch_news_feed(
                fetcher,
                category=arguments.get("category"),
                limit=arguments.get("limit", 50),
            )
        case "intel_trending_keywords":
            return await news.fetch_trending_keywords(fetcher, min_count=arguments.get("min_count", 3))
        case "intel_gdelt_search":
            return await news.fetch_gdelt_search(
                fetcher,
                query=arguments.get("query", "conflict"),
                mode=arguments.get("mode", "artlist"),
                limit=arguments.get("limit", 50),
            )

        # Intelligence
        case "intel_country_brief":
            return await intelligence.fetch_country_brief(fetcher, country_code=arguments.get("country_code", "US"))
        case "intel_risk_scores":
            return await intelligence.fetch_risk_scores(fetcher, limit=arguments.get("limit", 20))
        case "intel_instability_index":
            return await intelligence.fetch_instability_index(fetcher, country_code=arguments.get("country_code"))
        case "intel_signal_convergence":
            return await intelligence.fetch_signal_convergence(
                fetcher,
                lat=arguments.get("lat"),
                lon=arguments.get("lon"),
                radius_deg=arguments.get("radius_deg", 5.0),
            )

        # Reports
        case "intel_daily_brief":
            return await report_gen.generate_daily_brief(output_dir=arguments.get("output_dir"))
        case "intel_country_dossier":
            return await report_gen.generate_country_dossier(
                country_code=arguments["country_code"],
                output_dir=arguments.get("output_dir"),
            )
        case "intel_threat_landscape":
            return await report_gen.generate_threat_landscape(output_dir=arguments.get("output_dir"))

        # System
        case "intel_status":
            return {
                "circuit_breakers": breaker.status(),
                "cache": cache.stats(),
                "sources": {
                    "markets": ["yahoo-finance", "coingecko", "alternative-me", "mempool"],
                    "economic": ["eia", "fred", "world-bank"],
                    "natural": ["usgs", "nasa-firms"],
                    "conflict": ["acled", "ucdp", "hdx"],
                    "military": ["opensky", "hexdb"],
                    "infrastructure": ["cloudflare-radar", "nga-msi"],
                    "maritime": ["nga-msi"],
                    "climate": ["open-meteo"],
                    "news": ["rss-aggregator", "gdelt"],
                    "intelligence": ["ollama", "acled", "world-bank", "hdx", "usgs"],
                    "prediction": ["polymarket"],
                    "displacement": ["unhcr"],
                    "aviation": ["faa"],
                    "cyber": ["feodo-tracker", "cisa-kev", "sans-dshield", "urlhaus"],
                },
            }

        case _:
            return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    args = arguments or {}
    logger.info("Tool call: %s(%s)", name, json.dumps(args, default=str)[:200])
    result = await _dispatch(name, args)
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _run() -> None:
    logger.info("World Intelligence MCP Server starting (%d tools)", len(TOOLS))
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
