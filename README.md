<img width="1914" height="993" alt="Threat Intelligence MCP Server" src="https://github.com/user-attachments/assets/76ee1cdc-ece2-4b3c-8ffa-a0a127ab4b9b" />

# World Intelligence MCP Server

[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

Real-time global intelligence across **25 domains** with **60 MCP tools**, a live ops-center dashboard, CLI reports, and per-source circuit breakers. All data comes from free, public APIs — no paid subscriptions required.

> **Successor to threat-intel-mcp.** This project evolved from a focused threat intelligence server into a comprehensive world intelligence platform covering markets, geopolitics, climate, military, space weather, AI research, and more.

---

## What You Get

| Domain | Tools | Data Sources |
|--------|-------|-------------|
| **Financial Markets** | 7 | Yahoo Finance, CoinGecko, Polymarket |
| **Economic Indicators** | 3 | EIA energy, FRED macro, World Bank |
| **Seismology** | 1 | USGS earthquake feeds |
| **Wildfires** | 1 | NASA FIRMS satellite hotspots |
| **Conflict & Security** | 4 | ACLED events, UCDP armed conflict, unrest detection |
| **Military & Defense** | 5 | adsb.lol, OpenSky Network, hexdb.io, surge detection |
| **Infrastructure** | 4 | Cloudflare Radar, submarine cables, cascade analysis, cloud service status |
| **Maritime** | 2 | NGA navigation warnings, vessel snapshots |
| **Geospatial Datasets** | 4 | 70 military bases, 40 ports, 24 pipelines, 24 nuclear facilities |
| **Climate** | 1 | Open-Meteo climate anomalies |
| **News & Media** | 3 | 80+ RSS feeds (4-tier), GDELT, trending keywords |
| **Intelligence Analysis** | 8 | Signal convergence, focal points, instability index, risk scores, escalation, surge detection |
| **Prediction Markets** | 1 | Polymarket event contracts |
| **Displacement** | 1 | UNHCR refugee/IDP data |
| **Aviation** | 1 | FAA airport delays |
| **Cyber Threats** | 1 | URLhaus, Feodotracker, CISA KEV, SANS |
| **Space Weather** | 1 | NOAA SWPC (Kp index, solar flares, alerts) |
| **AI/AGI Watch** | 1 | arXiv cs.AI/LG/CL, HuggingFace, newsletters |
| **Health** | 1 | WHO DON, ProMED, CIDRAP disease outbreaks |
| **Sanctions** | 1 | US Treasury OFAC SDN list |
| **Elections** | 1 | Global election calendar with risk scoring |
| **Shipping** | 1 | Dry bulk ETFs, shipping stress index |
| **Social** | 1 | Reddit geopolitical discussion velocity |
| **Nuclear** | 1 | USGS seismics near 5 nuclear test sites |
| **Reports** | 3 | Daily brief, country dossier, threat landscape |
| **Cross-Domain Analysis** | 2 | Alert digest, weekly trends |

**Total: 60 tools** across 25 intelligence domains.

---

## Quick Start

### Install

```bash
# Clone
git clone https://github.com/marc-shade/world-intel-mcp.git
cd world-intel-mcp

# Install (Python 3.11+)
pip install -e .

# With dashboard support
pip install -e ".[dashboard]"

# With dev/test tools
pip install -e ".[dev]"
```

### Run as MCP Server

```bash
# stdio mode (for Claude Code, Cursor, etc.)
world-intel-mcp
```

### Claude Code Configuration

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "world-intel-mcp": {
      "command": "world-intel-mcp",
      "env": {}
    }
  }
}
```

Or if installed in a virtualenv:

```json
{
  "mcpServers": {
    "world-intel-mcp": {
      "command": "/path/to/venv/bin/world-intel-mcp",
      "env": {}
    }
  }
}
```

### Run the Live Dashboard

```bash
# Start the ops-center dashboard (default: http://localhost:8501)
intel-dashboard

# Custom port
intel-dashboard --port 9000
```

The dashboard is a map-first ops center with:
- Full-viewport Leaflet map with 7 toggle-able layers (quakes, military, conflict, fires, convergence, nuclear, infrastructure)
- 35+ live data feeds streaming via SSE (30-second refresh)
- 12 expandable drawer sections (alerts, markets, security, intelligence, AI watch, health, elections, shipping, social, nuclear, trends, infrastructure)
- HUD bar with real-time pills (quakes, aircraft, conflict zones, cyber IOCs, fires, displaced persons, Kp index, AI papers, alerts, shipping stress, outbreaks, services)
- Modal detail system — all external links open in-app, all data items expand to rich detail views
- Glassmorphic floating panels with dark-mode styling
- Per-source circuit breaker health monitoring

### CLI Reports

```bash
# Daily intelligence brief
intel daily-brief

# Country dossier
intel country-dossier --country "Ukraine"

# Threat landscape overview
intel threat-landscape
```

---

## Architecture

```
src/world_intel_mcp/
  server.py              # MCP server (stdio) — 60 tool definitions
  fetcher.py             # Async HTTP client with retries, stale-data fallback
  cache.py               # SQLite TTL cache with stale-data recovery
  circuit_breaker.py     # Per-source circuit breakers (3 failures -> 5min cooldown)
  cli.py                 # Click CLI for reports

  sources/               # One module per intelligence domain (25 modules)
    markets.py           # Stock indices, crypto, stablecoins, ETFs, sectors, commodities
    economic.py          # Energy prices, FRED macro, World Bank indicators
    seismology.py        # USGS earthquakes
    wildfire.py          # NASA FIRMS satellite fire hotspots (9 global regions)
    conflict.py          # ACLED, UCDP armed conflict events
    military.py          # adsb.lol + OpenSky military flights, aircraft details
    infrastructure.py    # Internet outages, submarine cable health, cloud service status
    maritime.py          # NGA navigation warnings, vessel snapshots
    climate.py           # Open-Meteo climate anomalies by zone
    news.py              # 80+ RSS feeds with per-feed circuit breakers, 4-tier source ranking
    intelligence.py      # GDELT, country briefs, signal convergence, risk scores
    prediction.py        # Polymarket prediction markets
    displacement.py      # UNHCR refugee/IDP statistics
    aviation.py          # FAA airport delays
    cyber.py             # URLhaus, Feodotracker, CISA KEV, SANS
    space_weather.py     # NOAA SWPC: Kp index, solar flares, alerts
    ai_watch.py          # arXiv AI papers, HuggingFace, lab trending
    health.py            # WHO DON, ProMED, CIDRAP disease outbreaks
    sanctions.py         # US Treasury OFAC SDN list search
    elections.py         # Global election calendar with proximity risk scoring
    shipping.py          # Dry bulk shipping stress index (BDRY, SBLK, EGLE, ZIM)
    social.py            # Reddit geopolitical discussion velocity
    nuclear.py           # USGS seismic monitoring near 5 nuclear test sites
    geospatial.py        # Query wrappers for static geospatial datasets
    service_status.py    # Cloudflare, AWS, Azure, GCP service health

  analysis/              # Cross-domain analysis engines
    signals.py           # Signal convergence detection
    instability.py       # Country instability index (CII v2)
    focal_points.py      # Multi-signal focal point detection
    temporal.py          # Temporal anomaly detection with SQLite baselines
    alerts.py            # Cross-domain alert digest + weekly trends
    escalation.py        # Dynamic hotspot escalation scoring
    surge.py             # Military surge anomaly detection
    cascade.py           # Infrastructure cascade simulation

  config/                # Static configuration data
    countries.py         # 22 intel hotspots, election calendar, nuclear test sites
    geospatial.py        # 70 military bases, 40 ports, 24 pipelines, 24 nuclear facilities

  reports/               # Report generation
    generator.py         # Report orchestrator
    markdown_report.py   # Markdown output
    html_report.py       # HTML output (Jinja2 templates)
    templates/           # HTML report templates

  dashboard/             # Live ops-center dashboard
    app.py               # Starlette app with SSE streaming (35+ feeds)
    index.html           # Map-first dashboard UI (7 map layers, 12 drawer sections)

  tests/                 # Test suite
    conftest.py          # Shared fixtures (mock fetcher, circuit breaker)
    test_sources.py      # Source module tests
    test_cache.py        # Cache TTL tests
    test_analysis.py     # Analysis engine tests
```

### Circuit Breakers

Every external API call goes through a circuit breaker. After 3 consecutive failures, the source is "tripped" for 5 minutes, preventing cascading timeouts. Each RSS feed gets its own breaker (e.g., `rss:bbc_world`, `rss:ars_technica`), so a single broken feed doesn't kill all news.

### Data Flow

```
External APIs -> Fetcher (httpx + retries) -> Circuit Breaker -> Cache (TTL) -> MCP Tool Response
                                                                              -> Dashboard (SSE)
                                                                              -> CLI Report
```

---

## MCP Tools Reference

### Financial Markets (7 tools)
| Tool | Description |
|------|-------------|
| `intel_market_quotes` | Stock index quotes (S&P 500, Dow, Nasdaq, FTSE, Nikkei) |
| `intel_crypto_quotes` | Top crypto prices and market caps from CoinGecko |
| `intel_stablecoin_status` | Stablecoin peg health (USDT, USDC, DAI, FDUSD) |
| `intel_etf_flows` | Bitcoin spot ETF prices and volumes (IBIT, FBTC, GBTC, ARKB) |
| `intel_sector_heatmap` | US equity sector performance (11 SPDR sector ETFs) |
| `intel_macro_signals` | Macro indicators (Fear & Greed, VIX, DXY, gold, 10Y, BTC mempool) |
| `intel_commodity_quotes` | Commodity futures (gold, silver, crude oil, natural gas) |

### Economic (3 tools)
| Tool | Description |
|------|-------------|
| `intel_energy_prices` | Brent/WTI crude oil and natural gas from EIA |
| `intel_fred_series` | FRED economic data series (GDP, CPI, unemployment, rates) |
| `intel_world_bank_indicators` | World Bank development indicators by country |

### Natural Disasters (2 tools)
| Tool | Description |
|------|-------------|
| `intel_earthquakes` | Recent earthquakes from USGS (configurable magnitude/time) |
| `intel_wildfires` | NASA FIRMS satellite fire hotspots (9 global regions) |

### Security & Conflict (4 tools)
| Tool | Description |
|------|-------------|
| `intel_acled_events` | Armed conflict events from ACLED |
| `intel_ucdp_events` | Uppsala Conflict Data Program events |
| `intel_unrest_events` | Social unrest (protests + riots) with Haversine dedup |
| `intel_cyber_threats` | Aggregated cyber intel (URLhaus, Feodotracker, CISA KEV, SANS) |

### Military & Defense (5 tools)
| Tool | Description |
|------|-------------|
| `intel_military_flights` | Military aircraft via adsb.lol (fallback: OpenSky) |
| `intel_theater_posture` | Military activity across 5 theaters (EU, Indo-Pacific, ME, Arctic, Korea) |
| `intel_aircraft_details` | Aircraft lookup by ICAO24 hex code (hexdb.io) |
| `intel_military_surge` | Foreign aircraft concentration anomaly detection |
| `intel_military_bases` | Query 70 military bases from 9 operators (USA, RUS, CHN, GBR, FRA, NATO, IND, TUR, ISR) |

### Infrastructure (4 tools)
| Tool | Description |
|------|-------------|
| `intel_internet_outages` | Cloudflare Radar internet disruptions |
| `intel_cable_health` | Submarine cable corridor health (6 corridors) |
| `intel_cascade_analysis` | Infrastructure cascade simulation ("what if corridor X fails?") |
| `intel_service_status` | Cloud platform health (Cloudflare, AWS, Azure, GCP) |

### Maritime (2 tools)
| Tool | Description |
|------|-------------|
| `intel_nav_warnings` | Maritime navigation warnings from NGA |
| `intel_vessel_snapshot` | Naval activity at 9 strategic waterways |

### Geospatial Datasets (4 tools)
| Tool | Description |
|------|-------------|
| `intel_military_bases` | 70 military bases from 9 operators — filter by operator, country, type, branch |
| `intel_strategic_ports` | 40 strategic ports across 6 types — filter by type, country |
| `intel_pipelines` | 24 oil/gas/hydrogen pipelines — filter by type, status |
| `intel_nuclear_facilities` | 24 nuclear power/enrichment/research facilities — filter by type, country, status |

### News & Media (3 tools)
| Tool | Description |
|------|-------------|
| `intel_news_feed` | Aggregated news from 80+ global RSS feeds with 4-tier source ranking |
| `intel_trending_keywords` | Trending terms with spike detection |
| `intel_gdelt_search` | GDELT 2.0 global news search and timelines |

### Geopolitical (2 tools)
| Tool | Description |
|------|-------------|
| `intel_prediction_markets` | Polymarket prediction contract prices |
| `intel_election_calendar` | Global election calendar with proximity risk scoring |

### Humanitarian (2 tools)
| Tool | Description |
|------|-------------|
| `intel_displacement_summary` | UNHCR refugee/IDP statistics by country |
| `intel_humanitarian_summary` | HDX humanitarian crisis datasets |

### Environment & Space (2 tools)
| Tool | Description |
|------|-------------|
| `intel_climate_anomalies` | Temperature/precipitation anomalies (15 global zones) |
| `intel_space_weather` | Solar activity: Kp index, X-ray flux, SWPC alerts |

### Health & Social (3 tools)
| Tool | Description |
|------|-------------|
| `intel_disease_outbreaks` | WHO DON, ProMED, CIDRAP outbreak alerts |
| `intel_social_signals` | Reddit geopolitical discussion velocity |
| `intel_sanctions_search` | US Treasury OFAC SDN list search |

### AI/AGI Research (1 tool)
| Tool | Description |
|------|-------------|
| `intel_ai_releases` | arXiv AI papers, HuggingFace models, lab tracking |

### Shipping & Transport (2 tools)
| Tool | Description |
|------|-------------|
| `intel_shipping_index` | Dry bulk shipping stress index (BDRY, SBLK, EGLE, ZIM) |
| `intel_airport_delays` | FAA airport delay status (20 major US airports) |

### Nuclear (1 tool)
| Tool | Description |
|------|-------------|
| `intel_nuclear_monitor` | Seismic monitoring near 5 nuclear test sites |

### Intelligence Analysis (8 tools)
| Tool | Description |
|------|-------------|
| `intel_signal_convergence` | Geographic convergence of multi-domain signals |
| `intel_focal_points` | Multi-signal focal point detection on entities |
| `intel_signal_summary` | Country-level signal aggregation with convergence scoring |
| `intel_temporal_anomalies` | Activity deviations from historical baselines |
| `intel_instability_index` | Country Instability Index v2 (0-100, 4 weighted domains) |
| `intel_risk_scores` | ACLED-based conflict risk scoring vs baselines |
| `intel_hotspot_escalation` | Dynamic escalation scores for 22 intel hotspots |
| `intel_military_surge` | Foreign aircraft concentration anomaly detection |

### Cross-Domain Alerts (2 tools)
| Tool | Description |
|------|-------------|
| `intel_alert_digest` | Aggregated alerts from 7 intelligence sources |
| `intel_weekly_trends` | Weekly trend analysis from temporal baselines |

### Reports (3 tools)
| Tool | Description |
|------|-------------|
| `intel_daily_brief` | Daily intelligence briefing (HTML report) |
| `intel_country_dossier` | Comprehensive country intelligence report |
| `intel_threat_landscape` | Current threat landscape overview |

### System (2 tools)
| Tool | Description |
|------|-------------|
| `intel_country_brief` | Quick country situation summary (Ollama LLM) |
| `intel_status` | Server health, cache stats, circuit breaker status |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ACLED_ACCESS_TOKEN` | No | ACLED API token (enables conflict event data) |
| `NASA_FIRMS_API_KEY` | No | NASA FIRMS key (enables satellite wildfire data) |
| `EIA_API_KEY` | No | EIA key (enables energy price data) |
| `CLOUDFLARE_API_TOKEN` | No | Cloudflare Radar (enables internet outage data) |
| `FRED_API_KEY` | No | FRED key (enables macro economic data) |
| `OPENSKY_CLIENT_ID` | No | OpenSky Network credentials (military flight fallback) |
| `OPENSKY_CLIENT_SECRET` | No | OpenSky Network credentials (military flight fallback) |
| `WORLD_INTEL_LOG_LEVEL` | No | Logging level (default: INFO) |

All other data sources (CoinGecko, USGS, adsb.lol, UCDP, NGA, FAA, Polymarket, UNHCR, NOAA SWPC, arXiv, Reddit, hexdb.io, WHO, OFAC, etc.) use free, unauthenticated public APIs.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=world_intel_mcp

# Type checking (if configured)
mypy src/
```

### Adding a New Source

1. Create `src/world_intel_mcp/sources/your_source.py`
2. Implement `async def fetch_your_data(fetcher: Fetcher, **kwargs) -> dict`
3. Use `fetcher.get_json()` / `fetcher.get_xml()` for HTTP calls (includes caching + circuit breakers)
4. Import in `server.py`, add a `Tool` definition, and wire up the `call_tool` handler
5. Add to `dashboard/app.py` if you want it on the live dashboard
6. Add tests in `tests/`

---

## License

MIT
