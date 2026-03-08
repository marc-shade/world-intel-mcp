#!/usr/bin/env python3
"""
World Intelligence MCP Server
==============================

Real-time global intelligence across 30 domains:
financial markets, economic indicators, earthquakes, wildfires,
conflict, military flights, infrastructure, and more.

Phase 1: Markets, Economic, Seismology, Wildfire (14 tools).
Phase 2: Conflict, Military, Infrastructure, Maritime, Climate (+10 = 24 tools).
Phase 3: News, Intelligence, Prediction, Displacement, Aviation, Cyber (+9 = 33 tools).
Phase 4: (reports removed — use live dashboard instead).
Phase 5: Analysis — focal points, signal summary, temporal anomalies, CII v2 (+3 = 39 tools).
Phase 6: Military & infrastructure intelligence (+6 = 45 tools).
Phase 7: Health, sanctions, elections, shipping, social, nuclear, alerts, trends (+10 = 55 tools).
Phase 8: Service status monitoring, RSS expansion (80+ feeds, 14 categories) (+1 = 56 tools).
Phase 9: Geospatial datasets — military bases, ports, pipelines, nuclear facilities (+4 = 60 tools).
Phase 10: NLP intelligence — entity extraction, event classification, news clustering, keyword spikes (+4 = 64 tools).
Phase 11: Strategic synthesis — strategic posture, world brief, fleet report, population exposure (+4 = 68 tools).
Phase 12: Extended geospatial (cables, datacenters, spaceports, minerals, exchanges), country stocks,
          aircraft batch, Hacker News, GitHub trending, arXiv papers, USA spending,
          NASA EONET, GDACS disaster alerts (+14 = 82 tools).
Phase 13: USNI fleet tracker, RSS expansion, report removal.
Phase 14: BTC technicals, central bank rates, trade routes, cloud regions, financial centers (+5 = 87 tools).
Phase 15: Business intelligence — forex (3), bonds/yields (2), earnings (2), SEC filings (3),
          company enrichment (1), macro composite (1) (+12 = 99 tools).
Phase 16: Vector intelligence — semantic search, similar events, timeline, vector stats,
          on-demand collection (+5 = 104 tools). Qdrant vector store auto-populates from all fetches.
          Collector daemon for 24/7 data accumulation. Enterprise-grade semantic retrieval.
Phase 17: Cross-domain analytics — cross-domain correlation, domain summary, trend detection
          (+3 = 109 tools). Historical analysis and early warning from accumulated vector data.
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
from .sources import (
    markets,
    economic,
    seismology,
    wildfire,
    conflict,
    military,
    infrastructure,
    maritime,
    climate,
    news,
    intelligence,
    prediction,
    displacement,
    aviation,
    cyber,
    space_weather,
    ai_watch,
    health,
    sanctions,
    elections,
    shipping,
    social,
    nuclear,
    service_status,
    geospatial,
    hacker_news,
    github_trending,
    arxiv_papers,
    usa_spending,
    environmental,
    usni_fleet,
    central_banks,
)

logging.basicConfig(
    level=os.environ.get("WORLD_INTEL_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("world-intel-mcp")

server = Server("world-intel-mcp")
cache = Cache()
breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=300)

# Vector store — optional, degrades gracefully if Qdrant unavailable.
_vector_store = None
try:
    from .vector_store import VectorStore, vector_dependencies_available

    if vector_dependencies_available():
        _vector_store = VectorStore(enabled=True)
    else:
        logger.info("Vector store unavailable (qdrant_client / fastembed not installed)")
except Exception as exc:
    logger.info("Vector store unavailable: %s", exc)

fetcher = Fetcher(cache=cache, breaker=breaker, vector_store=_vector_store)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    # --- Markets (7 tools) ---
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
                "limit": {
                    "type": "integer",
                    "description": "Number of coins (default 20)",
                    "default": 20,
                },
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
    Tool(
        name="intel_commodity_quotes",
        description="Get commodity futures quotes: gold, silver, crude oil (WTI & Brent), natural gas, corn, wheat, soybeans from Yahoo Finance.",
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
                "series_id": {
                    "type": "string",
                    "description": "FRED series ID (e.g., 'UNRATE')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of observations",
                    "default": 30,
                },
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
                "country": {
                    "type": "string",
                    "description": "ISO country code (default: USA)",
                    "default": "USA",
                },
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
                "min_magnitude": {
                    "type": "number",
                    "description": "Minimum magnitude (default 4.5)",
                    "default": 4.5,
                },
                "hours": {
                    "type": "integer",
                    "description": "Lookback hours (default 24)",
                    "default": 24,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
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
                        "north_america",
                        "south_america",
                        "europe",
                        "africa",
                        "middle_east",
                        "south_asia",
                        "east_asia",
                        "southeast_asia",
                        "oceania",
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
                "days": {
                    "type": "integer",
                    "description": "Lookback days (default 7)",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 100)",
                    "default": 100,
                },
            },
        },
    ),
    Tool(
        name="intel_ucdp_events",
        description="Get state-based violence events from UCDP GED. No API key needed. Optional: days (default 30).",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Lookback days (default 30)",
                    "default": 30,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 100)",
                    "default": 100,
                },
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
                "bbox": {
                    "type": "string",
                    "description": "Bounding box: lamin,lomin,lamax,lomax",
                },
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
                "navarea": {
                    "type": "string",
                    "description": "NAVAREA number (e.g., IV, XII)",
                },
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
                "limit": {
                    "type": "integer",
                    "description": "Number of markets (default 20)",
                    "default": 20,
                },
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
                "year": {
                    "type": "integer",
                    "description": "Reporting year (default: last year)",
                },
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
                "limit": {
                    "type": "integer",
                    "description": "Max threats (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    # --- News (3 tools) ---
    Tool(
        name="intel_news_feed",
        description="Get aggregated intelligence news from 119 RSS feeds across 24 categories. Covers geopolitics, security, tech, finance, military, science, think tanks, regional, energy, space, nuclear, climate, maritime, arctic, and more.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category filter (24 categories available)",
                    "enum": [
                        "geopolitics",
                        "security",
                        "technology",
                        "finance",
                        "military",
                        "science",
                        "think_tanks",
                        "middle_east",
                        "asia_pacific",
                        "africa",
                        "latin_america",
                        "multilingual",
                        "energy",
                        "government",
                        "crisis",
                        "europe",
                        "south_asia",
                        "health",
                        "central_asia",
                        "arctic",
                        "maritime",
                        "space",
                        "nuclear",
                        "climate",
                    ],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    Tool(
        name="intel_trending_keywords",
        description="Detect trending keywords from recent news headlines. Keyword spike detection across 20+ feeds.",
        inputSchema={
            "type": "object",
            "properties": {
                "min_count": {
                    "type": "integer",
                    "description": "Minimum occurrences (default 3)",
                    "default": 3,
                },
            },
        },
    ),
    Tool(
        name="intel_gdelt_search",
        description="Search GDELT 2.0 for global news articles or volume timelines. No API key needed.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (default: 'conflict')",
                    "default": "conflict",
                },
                "mode": {
                    "type": "string",
                    "description": "artlist (articles) or timelinevol (volume timeline)",
                    "enum": ["artlist", "timelinevol"],
                    "default": "artlist",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max records (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    # --- Intelligence (13 tools) ---
    Tool(
        name="intel_country_brief",
        description="Generate a country intelligence brief using Ollama LLM + World Bank + ACLED data. Falls back to data-only if LLM unavailable.",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {
                    "type": "string",
                    "description": "ISO country code (default: US)",
                    "default": "US",
                },
            },
        },
    ),
    Tool(
        name="intel_country_dossier",
        description="Comprehensive country intelligence dossier: economy (GDP/inflation), stock market, elections, sanctions, news mentions, hotspots, and conflict zones. Aggregates 6 sources in parallel.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "ISO-2 or ISO-3 country code (e.g. US, USA, UA, UKR)",
                    "default": "US",
                },
            },
        },
    ),
    Tool(
        name="intel_risk_scores",
        description="Get country risk scores computed from ACLED conflict data vs historical baselines. Requires ACLED_ACCESS_TOKEN.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Top N countries (default 20)",
                    "default": 20,
                },
            },
        },
    ),
    Tool(
        name="intel_instability_index",
        description="Compute Country Instability Index v2 (0-100) from 4 weighted domains: unrest, conflict, security, information. Applies country-specific multipliers and UCDP floors.",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {
                    "type": "string",
                    "description": "ISO alpha-3 code (e.g., UKR). Omit for top-10 focus countries.",
                },
            },
        },
    ),
    Tool(
        name="intel_signal_convergence",
        description="Detect geographic convergence of multi-domain signals (earthquakes, conflict, military) in hotspot regions.",
        inputSchema={
            "type": "object",
            "properties": {
                "lat": {
                    "type": "number",
                    "description": "Center latitude (omit for 5 global hotspots)",
                },
                "lon": {"type": "number", "description": "Center longitude"},
                "radius_deg": {
                    "type": "number",
                    "description": "Radius in degrees (default 5.0)",
                    "default": 5.0,
                },
            },
        },
    ),
    Tool(
        name="intel_focal_points",
        description="Detect focal points where multiple intelligence signals converge on the same entity (country, organization, leader). Cross-references news, military, protests, and infrastructure signals.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_signal_summary",
        description="Aggregate all intelligence signals by country with convergence scoring. Combines conflict, displacement, earthquakes, fires, outages, military, and protests.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "Country name filter (optional)",
                },
            },
        },
    ),
    Tool(
        name="intel_temporal_anomalies",
        description="Detect temporal anomalies — activity levels that deviate from historical baselines using Welford's algorithm. Reports z-score deviations like 'Military flights 3.2x normal for Thursday'.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_unrest_events",
        description="Get social unrest events (protests + riots) from ACLED with Haversine deduplication. Optional: country (name), days (default 7), limit (default 100).",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Country name filter"},
                "days": {
                    "type": "integer",
                    "description": "Lookback days (default 7)",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 100)",
                    "default": 100,
                },
            },
        },
    ),
    Tool(
        name="intel_hotspot_escalation",
        description="Dynamic escalation scores for 22 intel hotspots combining news, military, conflict, and convergence signals. Each hotspot scored 0-100.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_military_surge",
        description="Detect military surge anomalies — foreign aircraft concentration above baselines in 8 sensitive regions (Persian Gulf, Taiwan Strait, Baltic Sea, etc.).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_vessel_snapshot",
        description="Naval activity snapshot at 9 strategic waterways (Hormuz, Malacca, Suez, etc.) from NGA navigational warnings. Each waterway scored clear/advisory/elevated/critical.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_cascade_analysis",
        description="Simulate infrastructure cascade — 'what if cable corridor X is disrupted?' Impact scoring across dependent countries. Optional: corridor name (default: simulate at-risk corridors).",
        inputSchema={
            "type": "object",
            "properties": {
                "corridor": {
                    "type": "string",
                    "description": "Cable corridor to simulate (e.g., red_sea, transpacific, asia_europe)",
                    "enum": [
                        "transatlantic_north",
                        "transatlantic_south",
                        "asia_europe",
                        "red_sea",
                        "transpacific",
                        "mediterranean",
                    ],
                },
            },
        },
    ),
    # --- Space Weather (1 tool) ---
    Tool(
        name="intel_space_weather",
        description="Get solar activity: Kp geomagnetic index, X-ray flare class, solar wind, and SWPC alerts from NOAA.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- AI Watch (1 tool) ---
    Tool(
        name="intel_ai_releases",
        description="Track AI/AGI developments from arXiv, HuggingFace, and AI news feeds. Lab mention trending.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max items (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    # --- Health (1 tool) ---
    Tool(
        name="intel_disease_outbreaks",
        description="Aggregate disease outbreak alerts from WHO DON, ProMED, and CIDRAP. Flags high-concern pathogens (Ebola, H5N1, mpox, etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max items (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    # --- Sanctions (1 tool) ---
    Tool(
        name="intel_sanctions_search",
        description="Search the US Treasury OFAC Specially Designated Nationals (SDN) sanctions list. Substring match on name, country, program.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name substring to search"},
                "country": {"type": "string", "description": "Country filter"},
                "program": {
                    "type": "string",
                    "description": "Sanctions program filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    # --- Elections (1 tool) ---
    Tool(
        name="intel_election_calendar",
        description="Get upcoming global election calendar with proximity-based instability risk scoring. Covers 2025-2029.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "ISO-3 code or country name filter",
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
    # --- Social (1 tool) ---
    Tool(
        name="intel_social_signals",
        description="Monitor geopolitical discussion velocity on Reddit (r/worldnews, r/geopolitics). Engagement metrics and trending posts.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max posts per subreddit (default 25)",
                    "default": 25,
                },
            },
        },
    ),
    # --- Nuclear (1 tool) ---
    Tool(
        name="intel_nuclear_monitor",
        description="Monitor seismic activity near 5 known nuclear test sites (Punggye-ri, Lop Nur, Novaya Zemlya, Nevada NTS, Semipalatinsk). Concern scoring based on depth, magnitude, distance.",
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Lookback hours (default 72)",
                    "default": 72,
                },
            },
        },
    ),
    # --- Alert Digest (1 tool) ---
    Tool(
        name="intel_alert_digest",
        description="Cross-domain alert aggregation from 7 intelligence sources: space weather, instability, military surge, cable health, hotspot escalation, internet outages, shipping stress. Threshold-based prioritized alerts.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Weekly Trends (1 tool) ---
    Tool(
        name="intel_weekly_trends",
        description="Analyze weekly trends from temporal baselines. Reports volatility (coefficient of variation) and current anomalies across all tracked metrics.",
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
    # --- Geospatial Datasets (4 tools) ---
    Tool(
        name="intel_military_bases",
        description="Query 120+ military bases worldwide from 9 operators (USA, Russia, China, UK, France, NATO, India, Turkey, Israel, Iran, UAE). Filterable by operator, host country, base type, branch.",
        inputSchema={
            "type": "object",
            "properties": {
                "operator": {
                    "type": "string",
                    "description": "Filter by operating country (USA, RUS, CHN, GBR, FRA, NATO, IND, TUR, ISR, IRN, ARE)",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by host country name or ISO-3 code",
                },
                "base_type": {
                    "type": "string",
                    "description": "Filter by type: air_base, naval_base, army_base, marine_base, training, space_base, missile_defense, expeditionary",
                },
                "branch": {
                    "type": "string",
                    "description": "Filter by branch (USAF, US Navy, PLA Navy, RAF, etc.)",
                },
            },
        },
    ),
    Tool(
        name="intel_strategic_ports",
        description="Query 40+ strategic ports worldwide: container mega-ports, oil/LNG terminals, naval bases, bulk ports. Filterable by type and country.",
        inputSchema={
            "type": "object",
            "properties": {
                "port_type": {
                    "type": "string",
                    "description": "Filter by type: container, oil, lng, naval, bulk, mixed",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country name or ISO-3 code",
                },
            },
        },
    ),
    Tool(
        name="intel_pipelines",
        description="Query 25+ strategic oil, gas, and hydrogen pipelines with routes, capacity, and status. Includes Nord Stream, Druzhba, Power of Siberia, BTC, TAPS, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "pipeline_type": {
                    "type": "string",
                    "description": "Filter by type: oil, gas, hydrogen",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, destroyed, proposed, stalled, reduced, cancelled, construction, intermittent, terminated",
                },
            },
        },
    ),
    Tool(
        name="intel_nuclear_facilities",
        description="Query 25+ nuclear power plants, enrichment sites, research reactors, and reprocessing facilities worldwide. Includes Zaporizhzhia, Natanz, Fordow, Yongbyon, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "facility_type": {
                    "type": "string",
                    "description": "Filter by type: power, enrichment, research, reprocessing, decommissioned",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country name or ISO-3 code",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: operational, construction, shutdown, occupied, commissioning, decommissioning, exclusion_zone",
                },
            },
        },
    ),
    # --- NLP Intelligence (4 tools) ---
    Tool(
        name="intel_extract_entities",
        description="Extract named entities (countries, leaders, organizations, companies, CVEs, APT groups) from text or recent news headlines.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to analyze. If omitted, analyzes recent news headlines.",
                },
            },
        },
    ),
    Tool(
        name="intel_classify_event",
        description="Classify text into threat categories (military, terrorism, cyber, political, economic, health, climate, nuclear, etc.) with severity scoring (1-10).",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Event text or headline to classify.",
                },
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="intel_news_clusters",
        description="Cluster recent news articles by topic similarity using Jaccard coefficient. Groups related stories and extracts top keywords per cluster.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "RSS feed category filter (geopolitics, security, military, etc.)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max news items to cluster (default: 100)",
                },
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold 0.0-1.0 (default: 0.25)",
                },
            },
        },
    ),
    Tool(
        name="intel_keyword_spikes",
        description="Detect trending keyword spikes against historical baselines using Welford's algorithm. Extracts CVE identifiers and APT group mentions.",
        inputSchema={
            "type": "object",
            "properties": {
                "min_count": {
                    "type": "integer",
                    "description": "Minimum keyword frequency to consider (default: 3)",
                },
                "z_threshold": {
                    "type": "number",
                    "description": "Z-score threshold for spike detection (default: 2.0)",
                },
            },
        },
    ),
    # --- Strategic Synthesis (4 tools) ---
    Tool(
        name="intel_strategic_posture",
        description="Composite global risk assessment from 9 intelligence domains: military, political, conflict, infrastructure, economic, cyber, health, climate, space. Weighted composite score 0-100 with per-domain breakdown and top threats.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_world_brief",
        description="Structured daily intelligence summary: risk overview, focal areas, top story clusters, temporal anomalies, and trending threats. Comprehensive situational awareness in one call.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_fleet_report",
        description="Naval fleet activity report aggregating theater posture (5 theaters), vessel snapshot (9 waterways), military surge detections, and naval base count. Readiness scoring.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_population_exposure",
        description="Estimate population at risk near active events (earthquakes, wildfires, conflict). Finds major cities within radius and sums exposed population.",
        inputSchema={
            "type": "object",
            "properties": {
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in km (default: 200)",
                    "default": 200,
                },
                "event_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["earthquake", "wildfire", "conflict"],
                    },
                    "description": "Event types to include (default: all three)",
                },
            },
        },
    ),
    # --- Extended Geospatial (5 tools) ---
    Tool(
        name="intel_undersea_cables",
        description="Query 30+ undersea fiber-optic cable routes with landing points, owners, capacity (Tbps), and length (km). Filterable by status, country, owner, min capacity.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, planned, construction, decommissioned",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country in landing points",
                },
                "owner": {
                    "type": "string",
                    "description": "Filter by cable owner (Google, Meta, Microsoft, etc.)",
                },
                "min_capacity_tbps": {
                    "type": "number",
                    "description": "Minimum cable capacity in Tbps",
                },
            },
        },
    ),
    Tool(
        name="intel_ai_datacenters",
        description="Query 48+ AI datacenter clusters worldwide with power capacity (MW), operators, and locations. Covers hyperscalers and sovereign AI.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "Filter by country name or ISO-3 code",
                },
                "operator": {
                    "type": "string",
                    "description": "Filter by operator (AWS, Google, Microsoft, Meta, etc.)",
                },
                "min_power_mw": {
                    "type": "integer",
                    "description": "Minimum power capacity in MW",
                },
                "region": {
                    "type": "string",
                    "description": "Filter by region (North America, Europe, Asia-Pacific, etc.)",
                },
            },
        },
    ),
    Tool(
        name="intel_spaceports",
        description="Query 27+ launch facilities and spaceports worldwide. Filterable by country, status, type (orbital/suborbital), and operator.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "Filter by country name or ISO-3 code",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, limited, planned, decommissioned",
                },
                "spaceport_type": {
                    "type": "string",
                    "description": "Filter by type: orbital, suborbital",
                },
                "operator": {
                    "type": "string",
                    "description": "Filter by operator (SpaceX, NASA, CNSA, Roscosmos, etc.)",
                },
            },
        },
    ),
    Tool(
        name="intel_critical_minerals",
        description="Query 28+ critical mineral deposits worldwide: lithium, cobalt, rare earths, nickel, copper, graphite, manganese, PGM, tungsten, uranium, tin, gallium, germanium.",
        inputSchema={
            "type": "object",
            "properties": {
                "mineral": {
                    "type": "string",
                    "description": "Filter by mineral (lithium, cobalt, rare_earths, nickel, copper, graphite, manganese, platinum_group, tungsten, uranium, tin, gallium, germanium)",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country name or ISO-3 code",
                },
                "mineral_type": {
                    "type": "string",
                    "description": "Filter by type: battery, electronic, structural, energy, industrial, strategic",
                },
                "operator": {"type": "string", "description": "Filter by operator"},
            },
        },
    ),
    Tool(
        name="intel_stock_exchanges",
        description="Query 80+ stock exchanges across 4 tiers (mega >$3T, major, emerging, frontier) with market cap, index tickers, currencies, timezones.",
        inputSchema={
            "type": "object",
            "properties": {
                "tier": {
                    "type": "string",
                    "description": "Filter by tier: mega, major, emerging, frontier",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country name or ISO-3 code",
                },
                "currency": {
                    "type": "string",
                    "description": "Filter by currency (USD, EUR, GBP, JPY, CNY, etc.)",
                },
            },
        },
    ),
    # --- Markets Extended (1 tool) ---
    Tool(
        name="intel_country_stocks",
        description="Get real-time stock index quote for any country by ISO-3 code. Maps country to its primary exchange index ticker and fetches via Yahoo Finance.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "ISO-3 country code (USA, GBR, JPN, CHN, DEU, etc.)",
                    "default": "USA",
                },
            },
        },
    ),
    # --- Military Extended (1 tool) ---
    Tool(
        name="intel_aircraft_batch",
        description="Batch lookup of aircraft details by ICAO24 hex codes (max 20). Returns registration, type, operator from hexdb.io.",
        inputSchema={
            "type": "object",
            "properties": {
                "icao24_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ICAO24 hex addresses (max 20)",
                },
            },
            "required": ["icao24_list"],
        },
    ),
    # --- Tech & Science (3 tools) ---
    Tool(
        name="intel_hacker_news",
        description="Get top stories from Hacker News (Firebase API). Returns title, score, URL, author, comment count. Optional: limit (default 30).",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of stories (default 30, max 100)",
                    "default": 30,
                },
            },
        },
    ),
    Tool(
        name="intel_trending_repos",
        description="Get trending GitHub repositories (recently created, most starred). Optional: language filter, time window, limit.",
        inputSchema={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "Programming language filter (python, rust, typescript, etc.)",
                },
                "since_days": {
                    "type": "integer",
                    "description": "Look back N days for new repos (default 7)",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of repos (default 25)",
                    "default": 25,
                },
            },
        },
    ),
    Tool(
        name="intel_arxiv_papers",
        description="Search recent arXiv papers in AI/ML (cs.AI, cs.LG, cs.CL). Optional custom query. Returns title, authors, abstract, categories, PDF link.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "arXiv search query (default: cs.AI OR cs.LG OR cs.CL)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of papers (default 25)",
                    "default": 25,
                },
            },
        },
    ),
    # --- Government (1 tool) ---
    Tool(
        name="intel_usa_spending",
        description="Federal agency spending data from USAspending.gov. Shows top agencies by budget for current fiscal year. Optional: agency filter.",
        inputSchema={
            "type": "object",
            "properties": {
                "agency": {
                    "type": "string",
                    "description": "Filter by agency name substring",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of agencies (default 25)",
                    "default": 25,
                },
            },
        },
    ),
    # --- USNI Fleet (1 tool) ---
    Tool(
        name="intel_usni_fleet",
        description="US Navy fleet disposition from USNI News Fleet Tracker. Extracts ships, hull numbers, carrier strike groups, regional deployment, and force totals from the latest weekly report.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Environmental (2 tools) ---
    Tool(
        name="intel_environmental_events",
        description="Natural events from NASA EONET: wildfires, severe storms, volcanoes, floods, icebergs, drought. Includes geolocation and source links.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Look back N days (default 30)",
                    "default": 30,
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category: wildfires, severeStorms, volcanoes, floods, earthquakes, drought, seaLakeIce",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max events (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    Tool(
        name="intel_disaster_alerts",
        description="Global disaster alerts from GDACS (UN): earthquakes, floods, cyclones, droughts, wildfires. Severity levels (green/orange/red) with affected populations.",
        inputSchema={
            "type": "object",
            "properties": {
                "alert_level": {
                    "type": "string",
                    "description": "Filter by level: green, orange, red",
                },
                "event_type": {
                    "type": "string",
                    "description": "Filter by type: EQ, FL, TC, DR, WF, VO",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max alerts (default 30)",
                    "default": 30,
                },
            },
        },
    ),
    # --- BTC Technicals (1 tool) ---
    Tool(
        name="intel_btc_technicals",
        description="Bitcoin technical indicators: SMA-50, SMA-200, Mayer Multiple, golden/death cross, distance from ATH, 7d/30d changes.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Central Banks (1 tool) ---
    Tool(
        name="intel_central_bank_rates",
        description="Policy rates for 15 major central banks: Fed, ECB, BoE, BoJ, PBoC, RBI, RBA, BoC, SNB, BCB, BoK, CBRT, SARB, Banxico, BI. Live FRED data when API key set, curated fallback otherwise.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Trade Routes (1 tool) ---
    Tool(
        name="intel_trade_routes",
        description="19 critical maritime chokepoints and trade routes with oil flow (mbd), daily vessel transits, trade value share. Optional: route_type (chokepoint/canal/route), country (ISO-3).",
        inputSchema={
            "type": "object",
            "properties": {
                "route_type": {
                    "type": "string",
                    "description": "Filter: chokepoint, canal, route",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by ISO-3 country code",
                },
            },
        },
    ),
    # --- Cloud Regions (1 tool) ---
    Tool(
        name="intel_cloud_regions",
        description="28 major cloud provider regions (AWS, Azure, GCP) with coordinates, zone counts, and launch dates. Optional: provider, country.",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Filter: AWS, Azure, GCP",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by region name substring",
                },
            },
        },
    ),
    # --- Financial Centers (1 tool) ---
    Tool(
        name="intel_financial_centers",
        description="GFCI top 20 global financial centers with rankings, ratings, specializations, and exchange info. Optional: country (ISO-3), min_rank.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "Filter by ISO-3 country code",
                },
                "min_rank": {
                    "type": "integer",
                    "description": "Only include centers ranked this or better",
                },
            },
        },
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
    # --- Aviation domestic (1 tool) ---
    Tool(
        name="intel_aviation_domestic",
        description="Global air traffic snapshot from OpenSky Network: total airborne aircraft, regional breakdown, busiest origin countries, and sampled positions for mapping.",
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
    # --- Forex (3 tools) ---
    Tool(
        name="intel_forex_rates",
        description="Get latest foreign exchange rates from ECB via Frankfurter API. Optional: base currency (default USD), target symbols list.",
        inputSchema={
            "type": "object",
            "properties": {
                "base": {
                    "type": "string",
                    "description": "Base currency code (default: USD)",
                    "default": "USD",
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target currency codes (e.g., ['EUR', 'GBP', 'JPY'])",
                },
            },
        },
    ),
    Tool(
        name="intel_forex_timeseries",
        description="Get historical FX rate timeseries with trend analysis. Optional: base, symbol, days.",
        inputSchema={
            "type": "object",
            "properties": {
                "base": {
                    "type": "string",
                    "description": "Base currency (default: USD)",
                    "default": "USD",
                },
                "symbol": {
                    "type": "string",
                    "description": "Target currency (default: EUR)",
                    "default": "EUR",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of history (default: 30)",
                    "default": 30,
                },
            },
        },
    ),
    Tool(
        name="intel_major_crosses",
        description="Get all 8 major FX currency pairs (EUR/USD, USD/JPY, GBP/USD, etc.) with cross rates and DXY proxy.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Bonds & Yields (2 tools) ---
    Tool(
        name="intel_yield_curve",
        description="Get US Treasury yield curve (2Y-30Y maturities), 2s10s and 3m10y spreads, and inversion detection. Uses FRED or Yahoo Finance fallback.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_bond_indices",
        description="Get major bond ETF prices and performance: AGG (total bond), TLT (20Y+ Treasury), HYG (high yield), LQD (investment grade), TIP (TIPS).",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Earnings (2 tools) ---
    Tool(
        name="intel_earnings_calendar",
        description="Get upcoming earnings announcements for top 20 mega-cap stocks (AAPL, MSFT, GOOGL, etc.) with EPS estimates and days until report.",
        inputSchema={
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Days to look ahead for 'this_week' filter (default: 7)",
                    "default": 7,
                },
            },
        },
    ),
    Tool(
        name="intel_earnings_surprise",
        description="Get recent earnings surprises for a specific stock — past quarter actual vs estimate, surprise %, and forward estimates.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL')",
                },
            },
            "required": ["symbol"],
        },
    ),
    # --- SEC Filings (3 tools) ---
    Tool(
        name="intel_sec_filings",
        description="Search SEC EDGAR filings via full-text search. Filter by form type (10-K, 10-Q, 8-K) and date range.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (company name, keyword, etc.)",
                },
                "form_type": {
                    "type": "string",
                    "description": "Comma-separated form types (e.g., '10-K,10-Q,8-K')",
                },
                "date_range": {
                    "type": "string",
                    "description": "Date range as 'YYYY-MM-DD,YYYY-MM-DD' (default: last 30 days)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 25, max: 100)",
                    "default": 25,
                },
            },
        },
    ),
    Tool(
        name="intel_company_filings",
        description="Get recent SEC filings for a company by ticker symbol (10-K, 10-Q, 8-K). Resolves ticker to CIK automatically.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'AAPL')",
                },
                "form_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Form types to include (default: ['10-K', '10-Q', '8-K'])",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max filings (default: 10)",
                    "default": 10,
                },
            },
            "required": ["ticker"],
        },
    ),
    Tool(
        name="intel_recent_8k",
        description="Get most recent 8-K filings (material corporate events: M&A, executive changes, earnings releases) across all companies.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max filings (default: 25, max: 100)",
                    "default": 25,
                },
            },
        },
    ),
    # --- Company Enrichment (1 tool) ---
    Tool(
        name="intel_company_profile",
        description="Get comprehensive company profile: stock quote, financials, sector/industry, recent news, SEC filings, and GitHub repos (for tech companies). Accepts ticker or company name.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., 'AAPL') or company name",
                },
            },
            "required": ["query"],
        },
    ),
    # --- Macro Composite (1 tool) ---
    Tool(
        name="intel_macro_composite",
        description="Get weighted macro market composite score (0-100) synthesizing Fear & Greed, VIX, sector breadth, DXY, BTC technicals, and 10Y yield into an actionable verdict (RISK_ON / CONSTRUCTIVE / NEUTRAL / CAUTIOUS / STRONG_CAUTION).",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Vector Search (3 tools) ---
    Tool(
        name="intel_semantic_search",
        description="Semantic search across all stored intelligence data using natural language. Searches historical data accumulated from all 101+ tools. Filters: domain (e.g., 'markets', 'conflict'), category (e.g., 'Financial Markets', 'Cyber Threats'), hours (last N hours). Returns ranked results by relevance.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g., 'military activity near Taiwan', 'oil price disruptions')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
                "domain": {
                    "type": "string",
                    "description": "Filter by source domain (e.g., 'markets', 'conflict', 'military')",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g., 'Financial Markets', 'Conflict & Security', 'Cyber Threats')",
                },
                "hours": {
                    "type": "number",
                    "description": "Only results from last N hours",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="intel_similar_events",
        description="Find historically similar intelligence events or data. Given a text description, finds the most similar stored entries across all domains. Useful for pattern matching and precedent analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Reference text to find similar events for",
                },
                "domain": {
                    "type": "string",
                    "description": "Source domain of the reference text",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10)",
                    "default": 10,
                },
                "hours": {
                    "type": "number",
                    "description": "Only results from last N hours",
                },
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="intel_timeline",
        description="Get chronological timeline of stored intelligence data. Returns recent entries sorted by time. Filter by domain or category to focus on specific intelligence areas.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Filter by source domain",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                },
                "hours": {
                    "type": "number",
                    "description": "Time window in hours (default 24)",
                    "default": 24,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries (default 50)",
                    "default": 50,
                },
            },
        },
    ),
    Tool(
        name="intel_vector_stats",
        description="Get vector store statistics: total points, collection status, embedding model info. Shows how much intelligence data has been accumulated.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="intel_collect",
        description="Trigger an immediate collection cycle to populate the vector store. Fetches all intelligence sources and stores them. Optional: sources (comma-separated domain groups like 'markets,conflict,cyber').",
        inputSchema={
            "type": "object",
            "properties": {
                "sources": {
                    "type": "string",
                    "description": "Comma-separated domain groups (e.g., 'markets,conflict,cyber'). Default: all sources.",
                },
            },
        },
    ),
    Tool(
        name="intel_cross_correlate",
        description="Cross-domain intelligence correlation. Given a topic, finds related signals across ALL intelligence domains (military, financial, cyber, conflict, etc.) and groups them by category. Shows how events ripple across domains — e.g., how a military buildup correlates with market movements and news coverage.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic to correlate across domains (e.g., 'Taiwan strait tensions', 'oil supply disruption')",
                },
                "hours": {
                    "type": "number",
                    "description": "Time window in hours (default 24)",
                    "default": 24,
                },
                "limit_per_domain": {
                    "type": "integer",
                    "description": "Max signals per domain category (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="intel_domain_summary",
        description="Summary of all intelligence data stored in the vector database. Shows per-category data point counts, unique sources, latest/earliest timestamps, and total events tracked. Answers: what intelligence do we have and how recent is it?",
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "number",
                    "description": "Time window in hours (default 24)",
                    "default": 24,
                },
            },
        },
    ),
    Tool(
        name="intel_trend_detection",
        description="Detect activity trends by comparing recent intelligence activity against a baseline. Identifies SURGE (>50% increase), ELEVATED (>20%), DECLINING (<-20%), and DROP (<-50%) patterns. Useful for early warning when a domain suddenly spikes or goes quiet.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Focus on one category (e.g., 'Conflict & Security'). Default: all categories.",
                },
                "recent_hours": {
                    "type": "number",
                    "description": "Recent window to measure (default 6 hours)",
                    "default": 6,
                },
                "baseline_hours": {
                    "type": "number",
                    "description": "Baseline window for comparison (default 48 hours)",
                    "default": 48,
                },
            },
        },
    ),
    # --- System (1 tool) ---
    Tool(
        name="intel_status",
        description="Get data source health, circuit breaker status, cache freshness, vector store stats, and system statistics.",
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
            return await markets.fetch_market_quotes(
                fetcher, symbols=arguments.get("symbols")
            )
        case "intel_crypto_quotes":
            return await markets.fetch_crypto_quotes(
                fetcher, limit=arguments.get("limit", 20)
            )
        case "intel_stablecoin_status":
            return await markets.fetch_stablecoin_status(fetcher)
        case "intel_etf_flows":
            return await markets.fetch_etf_flows(fetcher)
        case "intel_sector_heatmap":
            return await markets.fetch_sector_heatmap(fetcher)
        case "intel_macro_signals":
            return await markets.fetch_macro_signals(fetcher)
        case "intel_commodity_quotes":
            return await markets.fetch_commodity_quotes(fetcher)

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
            return await wildfire.fetch_wildfires(
                fetcher, region=arguments.get("region")
            )

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
                fetcher,
                country=arguments.get("country"),
            )

        # Military
        case "intel_military_flights":
            return await military.fetch_military_flights(
                fetcher, bbox=arguments.get("bbox")
            )
        case "intel_theater_posture":
            return await military.fetch_theater_posture(fetcher)
        case "intel_aircraft_details":
            return await military.fetch_aircraft_details(
                fetcher, icao24=arguments["icao24"]
            )

        # Infrastructure
        case "intel_internet_outages":
            return await infrastructure.fetch_internet_outages(fetcher)
        case "intel_cable_health":
            return await infrastructure.fetch_cable_health(fetcher)

        # Maritime
        case "intel_nav_warnings":
            return await maritime.fetch_nav_warnings(
                fetcher, navarea=arguments.get("navarea")
            )

        # Climate
        case "intel_climate_anomalies":
            return await climate.fetch_climate_anomalies(
                fetcher, zones=arguments.get("zones")
            )

        # Prediction
        case "intel_prediction_markets":
            return await prediction.fetch_prediction_markets(
                fetcher, limit=arguments.get("limit", 20)
            )

        # Displacement
        case "intel_displacement_summary":
            return await displacement.fetch_displacement_summary(
                fetcher, year=arguments.get("year")
            )

        # Aviation
        case "intel_airport_delays":
            return await aviation.fetch_airport_delays(fetcher)

        # Cyber
        case "intel_cyber_threats":
            return await cyber.fetch_cyber_threats(
                fetcher, limit=arguments.get("limit", 50)
            )

        # News
        case "intel_news_feed":
            return await news.fetch_news_feed(
                fetcher,
                category=arguments.get("category"),
                limit=arguments.get("limit", 50),
            )
        case "intel_trending_keywords":
            return await news.fetch_trending_keywords(
                fetcher, min_count=arguments.get("min_count", 3)
            )
        case "intel_gdelt_search":
            return await news.fetch_gdelt_search(
                fetcher,
                query=arguments.get("query", "conflict"),
                mode=arguments.get("mode", "artlist"),
                limit=arguments.get("limit", 50),
            )

        # Intelligence
        case "intel_country_brief":
            return await intelligence.fetch_country_brief(
                fetcher, country_code=arguments.get("country_code", "US")
            )
        case "intel_country_dossier":
            from .analysis.dossier import fetch_country_dossier

            return await fetch_country_dossier(
                fetcher, country=arguments.get("country", "US")
            )
        case "intel_risk_scores":
            return await intelligence.fetch_risk_scores(
                fetcher, limit=arguments.get("limit", 20)
            )
        case "intel_instability_index":
            return await intelligence.fetch_instability_index(
                fetcher, country_code=arguments.get("country_code")
            )
        case "intel_signal_convergence":
            return await intelligence.fetch_signal_convergence(
                fetcher,
                lat=arguments.get("lat"),
                lon=arguments.get("lon"),
                radius_deg=arguments.get("radius_deg", 5.0),
            )
        case "intel_focal_points":
            return await intelligence.fetch_focal_points(fetcher)
        case "intel_signal_summary":
            return await intelligence.fetch_signal_summary(
                fetcher, country=arguments.get("country")
            )
        case "intel_temporal_anomalies":
            return await intelligence.fetch_temporal_anomalies(fetcher)
        case "intel_unrest_events":
            return await intelligence.fetch_unrest_events(
                fetcher,
                country=arguments.get("country"),
                days=arguments.get("days", 7),
                limit=arguments.get("limit", 100),
            )
        case "intel_hotspot_escalation":
            return await intelligence.fetch_hotspot_escalation(fetcher)
        case "intel_military_surge":
            return await intelligence.fetch_military_surge(fetcher)
        case "intel_vessel_snapshot":
            return await intelligence.fetch_vessel_snapshot(fetcher)
        case "intel_cascade_analysis":
            return await intelligence.fetch_cascade_analysis(
                fetcher,
                corridor=arguments.get("corridor"),
            )

        # Space Weather
        case "intel_space_weather":
            return await space_weather.fetch_space_weather(fetcher)

        # AI Watch
        case "intel_ai_releases":
            return await ai_watch.fetch_ai_watch(
                fetcher, limit=arguments.get("limit", 50)
            )

        # Health
        case "intel_disease_outbreaks":
            return await health.fetch_disease_outbreaks(
                fetcher, limit=arguments.get("limit", 50)
            )

        # Sanctions
        case "intel_sanctions_search":
            return await sanctions.fetch_sanctions_search(
                fetcher,
                query=arguments.get("query", ""),
                country=arguments.get("country"),
                program=arguments.get("program"),
                limit=arguments.get("limit", 50),
            )

        # Elections
        case "intel_election_calendar":
            return await elections.fetch_election_calendar(
                fetcher,
                country=arguments.get("country"),
            )

        # Shipping
        case "intel_shipping_index":
            return await shipping.fetch_shipping_index(fetcher)

        # Social
        case "intel_social_signals":
            return await social.fetch_social_signals(
                fetcher,
                limit=arguments.get("limit", 25),
            )

        # Nuclear
        case "intel_nuclear_monitor":
            return await nuclear.fetch_nuclear_monitor(
                fetcher,
                hours=arguments.get("hours", 72),
            )

        # Alert Digest
        case "intel_alert_digest":
            from .analysis.alerts import fetch_alert_digest

            return await fetch_alert_digest(fetcher)

        # Weekly Trends
        case "intel_weekly_trends":
            from .analysis.alerts import fetch_weekly_trends

            return await fetch_weekly_trends(fetcher)

        # Service Status
        case "intel_service_status":
            return await service_status.fetch_service_status(
                fetcher,
                provider=arguments.get("provider"),
            )

        # Geospatial datasets
        case "intel_military_bases":
            return await geospatial.fetch_military_bases(
                operator=arguments.get("operator"),
                country=arguments.get("country"),
                base_type=arguments.get("base_type"),
                branch=arguments.get("branch"),
            )
        case "intel_strategic_ports":
            return await geospatial.fetch_strategic_ports(
                port_type=arguments.get("port_type"),
                country=arguments.get("country"),
            )
        case "intel_pipelines":
            return await geospatial.fetch_pipelines(
                pipeline_type=arguments.get("pipeline_type"),
                status=arguments.get("status"),
            )
        case "intel_nuclear_facilities":
            return await geospatial.fetch_nuclear_facilities(
                facility_type=arguments.get("facility_type"),
                country=arguments.get("country"),
                status=arguments.get("status"),
            )

        # Strategic Synthesis
        case "intel_strategic_posture":
            from .analysis.posture import fetch_strategic_posture

            return await fetch_strategic_posture(fetcher)
        case "intel_world_brief":
            from .analysis.world_brief import fetch_world_brief

            return await fetch_world_brief(fetcher)
        case "intel_fleet_report":
            from .sources.fleet import fetch_fleet_report

            return await fetch_fleet_report(fetcher)
        case "intel_population_exposure":
            from .analysis.exposure import fetch_population_exposure

            return await fetch_population_exposure(
                fetcher,
                radius_km=arguments.get("radius_km", 200),
                event_types=arguments.get("event_types"),
            )

        # Extended Geospatial
        case "intel_undersea_cables":
            return await geospatial.fetch_undersea_cables(
                status=arguments.get("status"),
                country=arguments.get("country"),
                owner=arguments.get("owner"),
                min_capacity_tbps=arguments.get("min_capacity_tbps"),
            )
        case "intel_ai_datacenters":
            return await geospatial.fetch_ai_datacenters(
                country=arguments.get("country"),
                operator=arguments.get("operator"),
                min_power_mw=arguments.get("min_power_mw"),
                region=arguments.get("region"),
            )
        case "intel_spaceports":
            return await geospatial.fetch_spaceports(
                country=arguments.get("country"),
                status=arguments.get("status"),
                spaceport_type=arguments.get("spaceport_type"),
                operator=arguments.get("operator"),
            )
        case "intel_critical_minerals":
            return await geospatial.fetch_critical_minerals(
                mineral=arguments.get("mineral"),
                country=arguments.get("country"),
                mineral_type=arguments.get("mineral_type"),
                operator=arguments.get("operator"),
            )
        case "intel_stock_exchanges":
            return await geospatial.fetch_stock_exchanges(
                tier=arguments.get("tier"),
                country=arguments.get("country"),
                currency=arguments.get("currency"),
            )

        # Markets Extended
        case "intel_country_stocks":
            return await markets.fetch_country_stocks(
                fetcher,
                country=arguments.get("country", "USA"),
            )

        # Military Extended
        case "intel_aircraft_batch":
            return await military.fetch_aircraft_details_batch(
                fetcher,
                icao24_list=arguments["icao24_list"],
            )

        # Tech & Science
        case "intel_hacker_news":
            return await hacker_news.fetch_hacker_news(
                fetcher,
                limit=arguments.get("limit", 30),
            )
        case "intel_trending_repos":
            return await github_trending.fetch_trending_repos(
                fetcher,
                language=arguments.get("language"),
                since_days=arguments.get("since_days", 7),
                limit=arguments.get("limit", 25),
            )
        case "intel_arxiv_papers":
            return await arxiv_papers.fetch_arxiv_papers(
                fetcher,
                query=arguments.get("query"),
                limit=arguments.get("limit", 25),
            )

        # Government
        case "intel_usa_spending":
            return await usa_spending.fetch_usa_spending(
                fetcher,
                agency=arguments.get("agency"),
                limit=arguments.get("limit", 25),
            )

        # USNI Fleet
        case "intel_usni_fleet":
            return await usni_fleet.fetch_usni_fleet(fetcher)

        # BTC Technicals
        case "intel_btc_technicals":
            return await markets.fetch_btc_technicals(fetcher)

        # Central Bank Rates
        case "intel_central_bank_rates":
            return await central_banks.fetch_central_bank_rates(fetcher)

        # Trade Routes
        case "intel_trade_routes":
            return await geospatial.fetch_trade_routes(
                route_type=arguments.get("route_type"),
                country=arguments.get("country"),
            )

        # Cloud Regions
        case "intel_cloud_regions":
            return await geospatial.fetch_cloud_regions(
                provider=arguments.get("provider"),
                country=arguments.get("country"),
            )

        # Financial Centers
        case "intel_financial_centers":
            return await geospatial.fetch_financial_centers(
                country=arguments.get("country"),
                min_rank=arguments.get("min_rank"),
            )

        # Environmental
        case "intel_environmental_events":
            return await environmental.fetch_environmental_events(
                fetcher,
                days=arguments.get("days", 30),
                category=arguments.get("category"),
                limit=arguments.get("limit", 50),
            )
        case "intel_disaster_alerts":
            return await environmental.fetch_disaster_alerts(
                fetcher,
                alert_level=arguments.get("alert_level"),
                event_type=arguments.get("event_type"),
                limit=arguments.get("limit", 30),
            )

        # NLP Intelligence
        case "intel_extract_entities":
            from .analysis.entities import fetch_entity_extraction

            return await fetch_entity_extraction(fetcher, text=arguments.get("text"))
        case "intel_classify_event":
            from .analysis.classifier import fetch_classify_event

            return await fetch_classify_event(fetcher, text=arguments["text"])
        case "intel_news_clusters":
            from .analysis.clustering import fetch_news_clusters

            return await fetch_news_clusters(
                fetcher,
                category=arguments.get("category"),
                limit=arguments.get("limit", 100),
                threshold=arguments.get("threshold", 0.25),
            )
        case "intel_keyword_spikes":
            from .analysis.spikes import fetch_keyword_spikes

            return await fetch_keyword_spikes(
                fetcher,
                min_count=arguments.get("min_count", 3),
                z_threshold=arguments.get("z_threshold", 2.0),
            )

        # Traffic
        case "intel_traffic_flow":
            from .sources.traffic import fetch_traffic_flow

            return await fetch_traffic_flow(fetcher)
        case "intel_traffic_incidents":
            from .sources.traffic import fetch_traffic_incidents

            return await fetch_traffic_incidents(fetcher)

        # Aviation domestic
        case "intel_aviation_domestic":
            return await aviation.fetch_domestic_flights(fetcher)

        # Webcams
        case "intel_webcams":
            from .sources.webcams import fetch_webcams

            return await fetch_webcams(
                fetcher,
                category=arguments.get("category", "traffic"),
                limit=arguments.get("limit", 50),
            )

        # Forex
        case "intel_forex_rates":
            from .sources.forex import fetch_forex_rates

            return await fetch_forex_rates(
                fetcher,
                base=arguments.get("base", "USD"),
                symbols=arguments.get("symbols"),
            )
        case "intel_forex_timeseries":
            from .sources.forex import fetch_forex_timeseries

            return await fetch_forex_timeseries(
                fetcher,
                base=arguments.get("base", "USD"),
                symbol=arguments.get("symbol", "EUR"),
                days=arguments.get("days", 30),
            )
        case "intel_major_crosses":
            from .sources.forex import fetch_major_crosses

            return await fetch_major_crosses(fetcher)

        # Bonds & Yields
        case "intel_yield_curve":
            from .sources.bonds import fetch_yield_curve

            return await fetch_yield_curve(fetcher)
        case "intel_bond_indices":
            from .sources.bonds import fetch_bond_indices

            return await fetch_bond_indices(fetcher)

        # Earnings
        case "intel_earnings_calendar":
            from .sources.earnings import fetch_earnings_calendar

            return await fetch_earnings_calendar(
                fetcher, days_ahead=arguments.get("days_ahead", 7)
            )
        case "intel_earnings_surprise":
            from .sources.earnings import fetch_earnings_surprise

            return await fetch_earnings_surprise(fetcher, symbol=arguments["symbol"])

        # SEC Filings
        case "intel_sec_filings":
            from .sources.sec_edgar import fetch_sec_filings

            return await fetch_sec_filings(
                fetcher,
                query=arguments.get("query"),
                form_type=arguments.get("form_type"),
                date_range=arguments.get("date_range"),
                limit=arguments.get("limit", 25),
            )
        case "intel_company_filings":
            from .sources.sec_edgar import fetch_company_filings

            return await fetch_company_filings(
                fetcher,
                ticker=arguments["ticker"],
                form_types=arguments.get("form_types"),
                limit=arguments.get("limit", 10),
            )
        case "intel_recent_8k":
            from .sources.sec_edgar import fetch_recent_8k

            return await fetch_recent_8k(fetcher, limit=arguments.get("limit", 25))

        # Company Enrichment
        case "intel_company_profile":
            from .analysis.company import fetch_company_profile

            return await fetch_company_profile(fetcher, query=arguments["query"])

        # Macro Composite
        case "intel_macro_composite":
            from .analysis.macro_composite import fetch_macro_composite

            return await fetch_macro_composite(fetcher)

        # Vector Search
        case "intel_semantic_search":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.semantic_search(
                query=arguments["query"],
                limit=arguments.get("limit", 20),
                domain=arguments.get("domain"),
                category=arguments.get("category"),
                hours=arguments.get("hours"),
            )
        case "intel_similar_events":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.find_similar(
                domain=arguments.get("domain", "unknown"),
                text=arguments["text"],
                limit=arguments.get("limit", 10),
                hours=arguments.get("hours"),
            )
        case "intel_timeline":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.timeline(
                domain=arguments.get("domain"),
                category=arguments.get("category"),
                hours=arguments.get("hours", 24.0),
                limit=arguments.get("limit", 50),
            )

        case "intel_vector_stats":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.collection_stats()

        case "intel_collect":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            from .collector import collect_once

            return await collect_once(
                fetcher,
                _vector_store,
                source_filter=(
                    None
                    if not arguments.get("sources")
                    else set(arguments["sources"].split(","))
                ),
            )

        case "intel_cross_correlate":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.cross_domain_correlate(
                query=arguments["query"],
                hours=arguments.get("hours", 24.0),
                limit_per_domain=arguments.get("limit_per_domain", 5),
            )
        case "intel_domain_summary":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.domain_summary(
                hours=arguments.get("hours", 24.0),
            )
        case "intel_trend_detection":
            if _vector_store is None:
                return {"error": "Vector store not available (Qdrant not running?)"}
            return await _vector_store.trend_detection(
                category=arguments.get("category"),
                recent_hours=arguments.get("recent_hours", 6.0),
                baseline_hours=arguments.get("baseline_hours", 48.0),
            )

        # System
        case "intel_status":
            vs_stats = {
                "enabled": False,
                "error": 'Vector store dependencies not installed. Install with `pip install -e ".[vector]"`.',
            }
            if _vector_store:
                vs_stats = await _vector_store.collection_stats()
            return {
                "circuit_breakers": breaker.status(),
                "cache": cache.stats(),
                "cache_freshness": cache.freshness(),
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
                    "prediction": ["polymarket"],
                    "displacement": ["unhcr"],
                    "aviation": ["faa"],
                    "cyber": ["feodo-tracker", "cisa-kev", "sans-dshield", "urlhaus"],
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
    if _vector_store:
        await _vector_store.start()
        logger.info("Vector store worker started")
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
    finally:
        if _vector_store:
            await _vector_store.stop()


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
