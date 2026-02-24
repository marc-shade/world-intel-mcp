#!/usr/bin/env python3
"""
World Intelligence MCP Server
==============================

Real-time global intelligence across 23 domains:
financial markets, economic indicators, earthquakes, wildfires,
conflict, military flights, infrastructure, and more.

Phase 1: Markets, Economic, Seismology, Wildfire (14 tools).
Phase 2: Conflict, Military, Infrastructure, Maritime, Climate (+10 = 24 tools).
Phase 3: News, Intelligence, Prediction, Displacement, Aviation, Cyber (+9 = 33 tools).
Phase 4: Reports — daily brief, country dossier, threat landscape (+3 = 36 tools).
Phase 5: Analysis — focal points, signal summary, temporal anomalies, CII v2 (+3 = 39 tools).
Phase 6: Military & infrastructure intelligence (+6 = 45 tools).
Phase 7: Health, sanctions, elections, shipping, social, nuclear, alerts, trends (+10 = 55 tools).
Phase 8: Service status monitoring, RSS expansion (80+ feeds, 14 categories) (+1 = 56 tools).
Phase 9: Geospatial datasets — military bases, ports, pipelines, nuclear facilities (+4 = 60 tools).
Phase 10: NLP intelligence — entity extraction, event classification, news clustering, keyword spikes (+4 = 64 tools).
Phase 11: Strategic synthesis — strategic posture, world brief, fleet report, population exposure (+4 = 68 tools).
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
from .sources import markets, economic, seismology, wildfire, conflict, military, infrastructure, maritime, climate, news, intelligence, prediction, displacement, aviation, cyber, space_weather, ai_watch, health, sanctions, elections, shipping, social, nuclear, service_status, geospatial
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
    # --- Intelligence (12 tools) ---
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
        description="Compute Country Instability Index v2 (0-100) from 4 weighted domains: unrest, conflict, security, information. Applies country-specific multipliers and UCDP floors.",
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
                "country": {"type": "string", "description": "Country name filter (optional)"},
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
                "days": {"type": "integer", "description": "Lookback days (default 7)", "default": 7},
                "limit": {"type": "integer", "description": "Max results (default 100)", "default": 100},
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
                        "transatlantic_north", "transatlantic_south",
                        "asia_europe", "red_sea", "transpacific", "mediterranean",
                    ],
                },
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
                "limit": {"type": "integer", "description": "Max items (default 50)", "default": 50},
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
                "limit": {"type": "integer", "description": "Max items (default 50)", "default": 50},
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
                "program": {"type": "string", "description": "Sanctions program filter"},
                "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50},
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
                "country": {"type": "string", "description": "ISO-3 code or country name filter"},
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
                "limit": {"type": "integer", "description": "Max posts per subreddit (default 25)", "default": 25},
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
                "hours": {"type": "integer", "description": "Lookback hours (default 72)", "default": 72},
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
                "provider": {"type": "string", "description": "Filter by provider (aws, azure, gcp, cloudflare, github)"},
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
                "operator": {"type": "string", "description": "Filter by operating country (USA, RUS, CHN, GBR, FRA, NATO, IND, TUR, ISR, IRN, ARE)"},
                "country": {"type": "string", "description": "Filter by host country name or ISO-3 code"},
                "base_type": {"type": "string", "description": "Filter by type: air_base, naval_base, army_base, marine_base, training, space_base, missile_defense, expeditionary"},
                "branch": {"type": "string", "description": "Filter by branch (USAF, US Navy, PLA Navy, RAF, etc.)"},
            },
        },
    ),
    Tool(
        name="intel_strategic_ports",
        description="Query 40+ strategic ports worldwide: container mega-ports, oil/LNG terminals, naval bases, bulk ports. Filterable by type and country.",
        inputSchema={
            "type": "object",
            "properties": {
                "port_type": {"type": "string", "description": "Filter by type: container, oil, lng, naval, bulk, mixed"},
                "country": {"type": "string", "description": "Filter by country name or ISO-3 code"},
            },
        },
    ),
    Tool(
        name="intel_pipelines",
        description="Query 25+ strategic oil, gas, and hydrogen pipelines with routes, capacity, and status. Includes Nord Stream, Druzhba, Power of Siberia, BTC, TAPS, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "pipeline_type": {"type": "string", "description": "Filter by type: oil, gas, hydrogen"},
                "status": {"type": "string", "description": "Filter by status: active, destroyed, proposed, stalled, reduced, cancelled, construction, intermittent, terminated"},
            },
        },
    ),
    Tool(
        name="intel_nuclear_facilities",
        description="Query 25+ nuclear power plants, enrichment sites, research reactors, and reprocessing facilities worldwide. Includes Zaporizhzhia, Natanz, Fordow, Yongbyon, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "facility_type": {"type": "string", "description": "Filter by type: power, enrichment, research, reprocessing, decommissioned"},
                "country": {"type": "string", "description": "Filter by country name or ISO-3 code"},
                "status": {"type": "string", "description": "Filter by status: operational, construction, shutdown, occupied, commissioning, decommissioning, exclusion_zone"},
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
                "text": {"type": "string", "description": "Text to analyze. If omitted, analyzes recent news headlines."},
            },
        },
    ),
    Tool(
        name="intel_classify_event",
        description="Classify text into threat categories (military, terrorism, cyber, political, economic, health, climate, nuclear, etc.) with severity scoring (1-10).",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Event text or headline to classify."},
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
                "category": {"type": "string", "description": "RSS feed category filter (geopolitics, security, military, etc.)"},
                "limit": {"type": "integer", "description": "Max news items to cluster (default: 100)"},
                "threshold": {"type": "number", "description": "Similarity threshold 0.0-1.0 (default: 0.25)"},
            },
        },
    ),
    Tool(
        name="intel_keyword_spikes",
        description="Detect trending keyword spikes against historical baselines using Welford's algorithm. Extracts CVE identifiers and APT group mentions.",
        inputSchema={
            "type": "object",
            "properties": {
                "min_count": {"type": "integer", "description": "Minimum keyword frequency to consider (default: 3)"},
                "z_threshold": {"type": "number", "description": "Z-score threshold for spike detection (default: 2.0)"},
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
                "radius_km": {"type": "number", "description": "Search radius in km (default: 200)", "default": 200},
                "event_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["earthquake", "wildfire", "conflict"]},
                    "description": "Event types to include (default: all three)",
                },
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
        case "intel_focal_points":
            return await intelligence.fetch_focal_points(fetcher)
        case "intel_signal_summary":
            return await intelligence.fetch_signal_summary(fetcher, country=arguments.get("country"))
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
                fetcher, corridor=arguments.get("corridor"),
            )

        # Space Weather
        case "intel_space_weather":
            return await space_weather.fetch_space_weather(fetcher)

        # AI Watch
        case "intel_ai_releases":
            return await ai_watch.fetch_ai_watch(fetcher, limit=arguments.get("limit", 50))

        # Health
        case "intel_disease_outbreaks":
            return await health.fetch_disease_outbreaks(fetcher, limit=arguments.get("limit", 50))

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
                fetcher, country=arguments.get("country"),
            )

        # Shipping
        case "intel_shipping_index":
            return await shipping.fetch_shipping_index(fetcher)

        # Social
        case "intel_social_signals":
            return await social.fetch_social_signals(
                fetcher, limit=arguments.get("limit", 25),
            )

        # Nuclear
        case "intel_nuclear_monitor":
            return await nuclear.fetch_nuclear_monitor(
                fetcher, hours=arguments.get("hours", 72),
            )

        # Alert Digest
        case "intel_alert_digest":
            from .analysis.alerts import fetch_alert_digest
            return await fetch_alert_digest(fetcher)

        # Weekly Trends
        case "intel_weekly_trends":
            from .analysis.alerts import fetch_weekly_trends
            return await fetch_weekly_trends(fetcher)

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

        # Service Status
        case "intel_service_status":
            return await service_status.fetch_service_status(
                fetcher, provider=arguments.get("provider"),
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
                    "geospatial": ["static-datasets (bases, ports, pipelines, nuclear)"],
                    "nlp": ["regex-ner", "keyword-classifier", "jaccard-clustering", "keyword-spike-detector"],
                    "synthesis": ["strategic-posture", "world-brief", "fleet-report", "population-exposure"],
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
