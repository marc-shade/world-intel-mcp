# World Intel MCP — Feature Parity Roadmap

**Benchmark**: [koala73/worldmonitor](https://github.com/koala73/worldmonitor)
**Updated**: 2026-03-08
**Current tools**: 110 (109 intel + 1 status)

---

## Legend

| Icon | Meaning |
|------|---------|
| :white_check_mark: | We have this |
| :yellow_circle: | Partial — we have the data source but lack the analysis layer |
| :red_circle: | Missing entirely |

---

## 0. Current Assessment / Gap Report

| Area | Finding | Status | Action |
|------|---------|--------|--------|
| MCP tool parity | 110 tools declared in `TOOLS`; 110 routed in `_dispatch()` | :white_check_mark: | Keep as an invariant |
| Optional vector runtime | Missing `qdrant-client` / `fastembed` previously surfaced as runtime failures | :white_check_mark: Fixed | Vector features now degrade cleanly and report availability |
| Base-environment test run | `pytest -q` fails collection without dev extras because `respx` is not installed | :yellow_circle: | Run `pip install -e ".[dev]"` before full-suite validation |
| Core verification | 127 infrastructure/report/vector tests pass in the base environment | :white_check_mark: | `test_reports.py`, `test_cache.py`, `test_analysis.py`, `test_vector_store.py` |
| Documentation drift | Prior roadmap documented 89 tools while the codebase exposed 110 | :white_check_mark: Updated below | Keep roadmap synced with phase increments |
| Maintainability | `src/world_intel_mcp/server.py` is ~2.5k lines and remains the main refactor target | :yellow_circle: | Split tool registry and dispatch by domain |

### Implemented Addendum Missing From Prior Roadmap

#### Financial Intelligence Extensions (12 tools)

| Tool | Purpose | Status |
|------|---------|--------|
| `intel_forex_rates` | Latest FX rates by base + symbol filters | :white_check_mark: |
| `intel_forex_timeseries` | Historical FX series with configurable lookback | :white_check_mark: |
| `intel_major_crosses` | Major crosses + DXY proxy snapshot | :white_check_mark: |
| `intel_yield_curve` | Treasury curve + inversion analysis | :white_check_mark: |
| `intel_bond_indices` | Bond ETF summary (AGG, TLT, HYG, LQD, TIP) | :white_check_mark: |
| `intel_earnings_calendar` | Upcoming earnings calendar | :white_check_mark: |
| `intel_earnings_surprise` | Historical earnings surprise analysis | :white_check_mark: |
| `intel_sec_filings` | Full-text SEC EDGAR filing search | :white_check_mark: |
| `intel_company_filings` | Company-specific 10-K / 10-Q / 8-K retrieval | :white_check_mark: |
| `intel_recent_8k` | Recent material-event 8-K stream | :white_check_mark: |
| `intel_company_profile` | Composite company enrichment profile | :white_check_mark: |
| `intel_macro_composite` | Weighted market regime / macro composite score | :white_check_mark: |

#### Vector & Cross-Domain Analytics (8 tools)

| Tool | Purpose | Status |
|------|---------|--------|
| `intel_semantic_search` | Natural-language search across accumulated intelligence | :white_check_mark: |
| `intel_similar_events` | Similarity search against historical events | :white_check_mark: |
| `intel_timeline` | Chronological timeline from vector store history | :white_check_mark: |
| `intel_vector_stats` | Qdrant collection statistics | :white_check_mark: |
| `intel_collect` | On-demand collection cycle for vector population | :white_check_mark: |
| `intel_cross_correlate` | Cross-category correlation for a topic/query | :white_check_mark: |
| `intel_domain_summary` | Per-category summary of stored intelligence | :white_check_mark: |
| `intel_trend_detection` | Recent-vs-baseline activity surge/drop detection | :white_check_mark: |

#### Intelligence Reports (1 tool)

| Tool | Purpose | Status |
|------|---------|--------|
| `intel_generate_report` | Generate PDF/HTML multi-domain intelligence reports with HTML fallback when `.[pdf]` is unavailable | :white_check_mark: |

---

## 1. Data Sources — Complete Inventory

### Markets & Economics (13 tools)

| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_market_quotes` | `list-market-quotes` | :white_check_mark: |
| `intel_crypto_quotes` | `list-crypto-quotes` | :white_check_mark: |
| `intel_stablecoin_status` | `list-stablecoin-markets` | :white_check_mark: |
| `intel_etf_flows` | `list-etf-flows` | :white_check_mark: |
| `intel_sector_heatmap` | `get-sector-summary` | :white_check_mark: |
| `intel_macro_signals` | `get-macro-signals` | :white_check_mark: |
| `intel_commodity_quotes` | `list-commodity-quotes` | :white_check_mark: |
| `intel_energy_prices` | `get-energy-prices` | :white_check_mark: |
| `intel_fred_series` | `get-fred-series` | :white_check_mark: |
| `intel_world_bank_indicators` | `list-world-bank-indicators` | :white_check_mark: |
| `intel_country_stocks` | Country main index ticker | :white_check_mark: |
| `intel_btc_technicals` | BTC SMA-50/200, Mayer Multiple, cross signals | :white_check_mark: |
| `intel_central_bank_rates` | 15 central bank policy rates (FRED + curated) | :white_check_mark: |

### Natural Disasters & Climate (5 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_earthquakes` | `list-earthquakes` | :white_check_mark: |
| `intel_wildfires` | `list-fire-detections` | :white_check_mark: |
| `intel_climate_anomalies` | `list-climate-anomalies` | :white_check_mark: |
| `intel_environmental_events` | NASA EONET events | :white_check_mark: |
| `intel_disaster_alerts` | GDACS global disaster alerts | :white_check_mark: |

### Conflict & Security (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_acled_events` | `list-acled-events` | :white_check_mark: |
| `intel_ucdp_events` | `list-ucdp-events` | :white_check_mark: |
| `intel_unrest_events` | ACLED protests + GDELT dedup | :white_check_mark: |
| `intel_cyber_threats` | `list-cyber-threats` | :white_check_mark: |

### Military & Defense (8 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_military_flights` | `list-military-flights` | :white_check_mark: |
| `intel_theater_posture` | `get-theater-posture` | :white_check_mark: |
| `intel_aircraft_details` | `get-aircraft-details` | :white_check_mark: |
| `intel_aircraft_batch` | Batch ICAO24 lookup | :white_check_mark: |
| `intel_vessel_snapshot` | `get-vessel-snapshot` | :white_check_mark: |
| `intel_military_surge` | `military-surge.ts` | :white_check_mark: |
| `intel_military_bases` | Static dataset (70 bases) | :white_check_mark: |
| `intel_usni_fleet` | USNI Fleet Tracker weekly disposition | :white_check_mark: |

### Infrastructure & Maritime (6 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_internet_outages` | `list-internet-outages` | :white_check_mark: |
| `intel_cable_health` | `get-cable-health` | :white_check_mark: |
| `intel_nav_warnings` | `list-navigational-warnings` | :white_check_mark: |
| `intel_cascade_analysis` | `infrastructure-cascade.ts` | :white_check_mark: |
| `intel_strategic_ports` | Static dataset (40 ports) | :white_check_mark: |
| `intel_pipelines` | Static dataset (24 pipelines) | :white_check_mark: |

### Humanitarian & Social (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_humanitarian_summary` | `get-humanitarian-summary` | :white_check_mark: |
| `intel_displacement_summary` | `get-displacement-summary` | :white_check_mark: |
| `intel_social_signals` | Reddit public intelligence | :white_check_mark: |
| `intel_disease_outbreaks` | WHO/ProMED/CIDRAP RSS | :white_check_mark: |

### News & Information (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_news_feed` | 100 RSS feeds, 4-tier sources | :white_check_mark: |
| `intel_trending_keywords` | trending-keywords service | :white_check_mark: |
| `intel_gdelt_search` | `search-gdelt-documents` | :white_check_mark: |
| `intel_ai_releases` | AI model/paper tracker | :white_check_mark: |

### Transport & Traffic (6 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_prediction_markets` | `list-prediction-markets` | :white_check_mark: |
| `intel_airport_delays` | `list-airport-delays` | :white_check_mark: |
| `intel_shipping_index` | Yahoo Finance shipping ETFs | :white_check_mark: |
| `intel_traffic_flow` | Real-time congestion in 20 cities (TomTom) | :white_check_mark: |
| `intel_traffic_incidents` | Major incidents in 5 strategic regions (TomTom) | :white_check_mark: |
| `intel_aviation_domestic` | Global air traffic snapshot (OpenSky) | :white_check_mark: |

### Webcams (1 tool)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_webcams` | Public webcam locations worldwide (Windy) | :white_check_mark: |

### Analysis & Intelligence (10 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_risk_scores` | `get-risk-scores` | :white_check_mark: |
| `intel_instability_index` | CII v2 (multi-signal blend) | :white_check_mark: |
| `intel_signal_convergence` | `geo-convergence.ts` | :white_check_mark: |
| `intel_focal_points` | `focal-point-detector.ts` | :white_check_mark: |
| `intel_signal_summary` | `signal-aggregator.ts` | :white_check_mark: |
| `intel_temporal_anomalies` | `temporal-baseline.ts` | :white_check_mark: |
| `intel_hotspot_escalation` | `hotspot-escalation.ts` | :white_check_mark: |
| `intel_alert_digest` | Cross-domain alert synthesis | :white_check_mark: |
| `intel_weekly_trends` | Temporal trend analysis | :white_check_mark: |

### Country & Geopolitical (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_country_brief` | `get-country-intel-brief` | :white_check_mark: |
| `intel_country_dossier` | Comprehensive 6-source country analysis | :white_check_mark: |
| `intel_election_calendar` | Election proximity risk | :white_check_mark: |
| `intel_sanctions_search` | OFAC SDN search | :white_check_mark: |

### Strategic Synthesis (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_strategic_posture` | Composite 9-domain risk assessment | :white_check_mark: |
| `intel_world_brief` | Structured daily intelligence summary | :white_check_mark: |
| `intel_fleet_report` | Naval fleet activity report | :white_check_mark: |
| `intel_population_exposure` | Population near active events | :white_check_mark: |

### Tech & Science (3 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_hacker_news` | Top HN stories (Firebase API) | :white_check_mark: |
| `intel_trending_repos` | GitHub trending repos | :white_check_mark: |
| `intel_arxiv_papers` | Recent AI/ML papers | :white_check_mark: |

### Government (1 tool)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_usa_spending` | USAspending.gov federal data | :white_check_mark: |

### Specialist (3 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_space_weather` | NOAA/SWPC feeds | :white_check_mark: |
| `intel_nuclear_monitor` | USGS seismic near test sites | :white_check_mark: |
| `intel_service_status` | Cloudflare/AWS/Azure/GCP | :white_check_mark: |

### NLP Intelligence (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_extract_entities` | Regex NER (28 leaders, 41 orgs, 36 APTs) | :white_check_mark: |
| `intel_classify_event` | Keyword threat classification (14 categories) | :white_check_mark: |
| `intel_news_clusters` | Jaccard similarity clustering | :white_check_mark: |
| `intel_keyword_spikes` | Welford's algorithm spike detection | :white_check_mark: |

### Extended Geospatial (10 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_undersea_cables` | 34 cables with landing points | :white_check_mark: |
| `intel_ai_datacenters` | 48 global AI/cloud clusters | :white_check_mark: |
| `intel_spaceports` | 27 launch facilities | :white_check_mark: |
| `intel_critical_minerals` | 27 deposit types | :white_check_mark: |
| `intel_stock_exchanges` | 82 global exchanges | :white_check_mark: |
| `intel_trade_routes` | 19 maritime chokepoints/routes | :white_check_mark: |
| `intel_cloud_regions` | 28 AWS/Azure/GCP regions | :white_check_mark: |
| `intel_financial_centers` | 20 GFCI-ranked cities | :white_check_mark: |
| `intel_nuclear_facilities` | 24 power/enrichment/research | :white_check_mark: |

### Financial Intelligence (12 tools)
| Tool | Purpose | Status |
|------|---------|--------|
| `intel_forex_rates` | Latest FX rates by base + symbol filters | :white_check_mark: |
| `intel_forex_timeseries` | Historical FX series with configurable lookback | :white_check_mark: |
| `intel_major_crosses` | Major crosses + DXY proxy snapshot | :white_check_mark: |
| `intel_yield_curve` | Treasury curve + inversion analysis | :white_check_mark: |
| `intel_bond_indices` | Bond ETF summary (AGG, TLT, HYG, LQD, TIP) | :white_check_mark: |
| `intel_earnings_calendar` | Upcoming earnings calendar | :white_check_mark: |
| `intel_earnings_surprise` | Historical earnings surprise analysis | :white_check_mark: |
| `intel_sec_filings` | Full-text SEC EDGAR filing search | :white_check_mark: |
| `intel_company_filings` | Company-specific 10-K / 10-Q / 8-K retrieval | :white_check_mark: |
| `intel_recent_8k` | Recent material-event 8-K stream | :white_check_mark: |
| `intel_company_profile` | Composite company enrichment profile | :white_check_mark: |
| `intel_macro_composite` | Weighted market regime / macro composite score | :white_check_mark: |

### Vector Intelligence (5 tools)
| Tool | Purpose | Status |
|------|---------|--------|
| `intel_semantic_search` | Natural-language search across accumulated intelligence | :white_check_mark: |
| `intel_similar_events` | Similarity search against historical events | :white_check_mark: |
| `intel_timeline` | Chronological timeline from vector store history | :white_check_mark: |
| `intel_vector_stats` | Qdrant collection statistics | :white_check_mark: |
| `intel_collect` | On-demand collection cycle for vector population | :white_check_mark: |

### Cross-Domain Analytics (3 tools)
| Tool | Purpose | Status |
|------|---------|--------|
| `intel_cross_correlate` | Cross-category correlation for a topic/query | :white_check_mark: |
| `intel_domain_summary` | Per-category summary of stored intelligence | :white_check_mark: |
| `intel_trend_detection` | Recent-vs-baseline activity surge/drop detection | :white_check_mark: |

### Reports (1 tool)
| Tool | Purpose | Status |
|------|---------|--------|
| `intel_generate_report` | PDF/HTML multi-domain intelligence reports | :white_check_mark: |

### System (1 tool)
| Tool | Purpose | Status |
|------|---------|--------|
| `intel_status` | Source health, cache stats, tool count | :white_check_mark: |

---

## 2. Static Geospatial Datasets

| Dataset | Records | Query Tool | Status |
|---------|---------|------------|--------|
| Military bases | 70 bases, 9 operators | `intel_military_bases` | :white_check_mark: |
| Strategic ports | 40 ports, 6 types | `intel_strategic_ports` | :white_check_mark: |
| Pipelines | 24 oil/gas/hydrogen | `intel_pipelines` | :white_check_mark: |
| Nuclear facilities | 24 power/enrichment/research | `intel_nuclear_facilities` | :white_check_mark: |
| Intel hotspots | 22 geopolitical hotspots | config/countries.py | :white_check_mark: |
| Conflict zones | Active conflict centers | config/countries.py | :white_check_mark: |
| Strategic waterways | 8 chokepoints | config/countries.py | :white_check_mark: |
| Nuclear test sites | 5 sites with monitoring | config/countries.py | :white_check_mark: |
| Countries config | 22 nations with risk baselines | config/countries.py | :white_check_mark: |
| Major cities | 105 cities (pop > 2M, 1B coverage) | config/population.py | :white_check_mark: |
| Undersea cables | 34 cables with landing points | `intel_undersea_cables` | :white_check_mark: |
| AI datacenters | 48 global clusters | `intel_ai_datacenters` | :white_check_mark: |
| Spaceports | 27 launch facilities | `intel_spaceports` | :white_check_mark: |
| Critical minerals | 27 deposit types | `intel_critical_minerals` | :white_check_mark: |
| Stock exchanges | 82 global exchanges | `intel_stock_exchanges` | :white_check_mark: |
| Trade routes | 19 maritime chokepoints/routes | `intel_trade_routes` | :white_check_mark: |
| Cloud regions | 28 AWS/Azure/GCP regions | `intel_cloud_regions` | :white_check_mark: |
| Financial centers | 20 GFCI-ranked cities | `intel_financial_centers` | :white_check_mark: |

---

## 3. RSS Feed Coverage

Expanded to **119 feeds** across **24 categories** with 4-tier source ranking (wire/major/specialty/aggregator) and propaganda risk labels.

| Category | Count | Status |
|----------|-------|--------|
| Geopolitics | 9 | :white_check_mark: |
| Security/Cyber | 8 | :white_check_mark: |
| Technology | 6 | :white_check_mark: |
| Finance | 6 | :white_check_mark: |
| Defense/Military | 6 | :white_check_mark: |
| Science | 6 | :white_check_mark: |
| Think Tanks | 7 | :white_check_mark: |
| Middle East | 4 | :white_check_mark: |
| Asia-Pacific | 5 | :white_check_mark: |
| Africa | 5 | :white_check_mark: |
| Latin America | 8 | :white_check_mark: |
| Multilingual (ES/FR/DE) | 7 | :white_check_mark: |
| Energy | 5 | :white_check_mark: |
| Government | 4 | :white_check_mark: |
| Crisis/Intl Orgs | 4 | :white_check_mark: |
| Europe | 4 | :white_check_mark: |
| South Asia | 3 | :white_check_mark: |
| Health | 4 | :white_check_mark: |
| Central Asia | 3 | :white_check_mark: |
| Arctic | 3 | :white_check_mark: |
| Maritime | 3 | :white_check_mark: |
| Space | 3 | :white_check_mark: |
| Nuclear | 3 | :white_check_mark: |
| Climate | 3 | :white_check_mark: |

---

## 4. Dashboard

Live Starlette app with SSE streaming at `intel-dashboard --port 8501`.

| Feature | Status |
|---------|--------|
| SSE streaming (30s refresh) | :white_check_mark: 39 data streams |
| Leaflet map (14 layers + 6 static + trade routes) | :white_check_mark: |
| 14 expandable drawer sections | :white_check_mark: |
| USNI Fleet Tracker drawer | :white_check_mark: |
| BTC Technicals drawer (SMA, Mayer, cross signals) | :white_check_mark: |
| Central Bank Rates drawer (15 banks) | :white_check_mark: |
| Data freshness monitoring drawer | :white_check_mark: |
| Per-source circuit breaker health | :white_check_mark: |
| AI situation brief (Ollama-powered) | :white_check_mark: |
| Static HTML reports | Removed (dashboard replaces) |

---

## 5. System Architecture

| Feature | Status | Notes |
|---------|--------|-------|
| SQLite WAL-mode cache | :white_check_mark: | Persistent TTL, stale fallback |
| Per-source circuit breaker | :white_check_mark: | Configurable thresholds |
| Data freshness monitoring | :white_check_mark: | Per-source staleness in dashboard |
| Per-coro timeout (45s) | :white_check_mark: | No single source blocks dashboard |

---

## Completed Phases

### Phase 1-4: Foundation (0 -> 36 tools)
Core data sources: markets, crypto, macro, earthquakes, wildfires, ACLED, UCDP, humanitarian, military flights, theater posture, aircraft, internet outages, cable health, nav warnings, climate, prediction markets, displacement, airport delays, cyber threats, news feeds, GDELT, trending keywords, country briefs, risk scores, instability index, signal convergence.

### Phase 5: Core Analysis Engine (+3 = 39 tools)
`intel_focal_points`, `intel_signal_summary`, `intel_temporal_anomalies`
Countries config with 22 nations, intel hotspots, conflict zones, strategic waterways. CII v2 upgraded with multi-signal weighted blend. Welford's online algorithm for temporal baseline anomaly detection.

### Phase 6: Military & Infrastructure Intelligence (+6 = 45 tools)
`intel_vessel_snapshot`, `intel_military_surge`, `intel_cascade_analysis`, `intel_hotspot_escalation`, `intel_commodity_quotes`, `intel_unrest_events`
AIS vessel tracking, military surge detection in 17 sensitive regions, infrastructure cascade analysis, hotspot escalation scoring for 22 locations.

### Phase 7: Domain Expansion (+10 = 55 tools)
`intel_space_weather`, `intel_ai_releases`, `intel_disease_outbreaks`, `intel_sanctions_search`, `intel_election_calendar`, `intel_shipping_index`, `intel_social_signals`, `intel_nuclear_monitor`, `intel_alert_digest`, `intel_weekly_trends`
80+ RSS feeds with 4-tier source ranking. WHO/ProMED/CIDRAP health monitoring. OFAC sanctions search. Election proximity risk scoring. Reddit social signals. Nuclear test site seismic monitoring. Cross-domain alert digest. Temporal weekly trend analysis.

### Phase 8: Service Status & Geospatial (+5 = 60 tools)
`intel_service_status`, `intel_military_bases`, `intel_strategic_ports`, `intel_pipelines`, `intel_nuclear_facilities`
Cloud service status monitoring (Cloudflare/AWS/Azure/GCP). Static geospatial datasets: 70 military bases from 9 operators, 40 strategic ports across 6 types, 24 oil/gas/hydrogen pipelines, 24 nuclear facilities. All queryable with filters. Dashboard infrastructure map layer.

### Phase 9: NLP Intelligence (+4 = 64 tools)
`intel_extract_entities`, `intel_classify_event`, `intel_news_clusters`, `intel_keyword_spikes`
Regex-based NER (28 leaders, 41 orgs, 25 companies, 36 APT groups, CVE extraction). Keyword-based threat classification into 14 categories with severity scoring. Jaccard similarity news clustering with keyword extraction. Welford's algorithm keyword spike detection against rolling baselines. Entity reference database in config/entities.py. No ML dependencies.

### Phase 10: Strategic Synthesis (+4 = 68 tools)
`intel_strategic_posture`, `intel_world_brief`, `intel_fleet_report`, `intel_population_exposure`
Composite strategic posture assessment from 9 weighted domains (military, political, conflict, infrastructure, economic, cyber, health, climate, space). Structured world intelligence brief aggregating posture, focal points, news clusters, temporal anomalies, and keyword spikes. Naval fleet activity report combining theater posture, vessel snapshots, and surge detections. Population exposure analysis near active events using 105-city dataset (1B pop coverage).

### Phase 11: Extended Data & Geospatial (+12 = 80 tools)
`intel_country_stocks`, `intel_aircraft_batch`, `intel_hacker_news`, `intel_trending_repos`, `intel_arxiv_papers`, `intel_usa_spending`, `intel_environmental_events`, `intel_disaster_alerts`, `intel_undersea_cables`, `intel_ai_datacenters`, `intel_spaceports`, `intel_critical_minerals`, `intel_stock_exchanges`, `intel_usni_fleet`

Static datasets completed: 34 undersea cables, 48 AI datacenters, 27 spaceports, 27 critical mineral deposits, 82 stock exchanges. USNI Fleet Tracker for Navy disposition. Data freshness monitoring added to dashboard. Static HTML report generation removed (live dashboard replaces).

### Phase 12: Financial Intelligence & Geospatial Expansion (+5 = 84 tools)
`intel_btc_technicals`, `intel_central_bank_rates`, `intel_trade_routes`, `intel_cloud_regions`, `intel_financial_centers`

BTC technical analysis with SMA-50/200, Mayer Multiple, golden/death cross signals, and ATH distance via CoinGecko historical data. Central bank policy rates for 15 major banks (Fed, ECB, BoE, BoJ, PBoC, RBI, RBA, BoC, SNB, BCB, BoK, CBRT, SARB, Banxico, BI) — live FRED data when API key set, curated fallback otherwise. Static geospatial datasets: 19 maritime trade routes/chokepoints with oil flow and vessel transit data, 28 cloud provider regions (AWS/Azure/GCP), 20 GFCI-ranked financial centers. Trade route markers added to dashboard infrastructure map layer. BTC technicals and central bank rates added to dashboard drawer.

### Phase 13: Country Dossier, Full Tool Exposure & Feed Expansion (+5 = 89 tools)
`intel_country_dossier`, `intel_traffic_flow`, `intel_traffic_incidents`, `intel_aviation_domestic`, `intel_webcams`

Comprehensive country intelligence dossier aggregating 6 sources in parallel (economy, markets, elections, sanctions, news, security). Exposed 4 previously hidden source functions: TomTom traffic flow (20 cities) and incidents (5 regions), OpenSky global air traffic snapshot, Windy public webcams. RSS feeds expanded from 100 to 119 across 24 categories (+6 new categories: central_asia, arctic, maritime, space, nuclear, climate). 49 CLI commands; the repo test suite has since grown well beyond this phase snapshot.

### Phase 14: Financial Intelligence Extensions (+12 = 101 tools)
`intel_forex_rates`, `intel_forex_timeseries`, `intel_major_crosses`, `intel_yield_curve`, `intel_bond_indices`, `intel_earnings_calendar`, `intel_earnings_surprise`, `intel_sec_filings`, `intel_company_filings`, `intel_recent_8k`, `intel_company_profile`, `intel_macro_composite`

Added business / market-intelligence depth: FX rates and timeseries, bond curves and ETF indices, earnings calendar and surprise analysis, SEC EDGAR search and company filings, composite company enrichment, and a weighted macro-composite market regime layer.

### Phase 15: Vector Intelligence (+5 = 106 tools)
`intel_semantic_search`, `intel_similar_events`, `intel_timeline`, `intel_vector_stats`, `intel_collect`

Qdrant-backed semantic retrieval added across all fetched intelligence, plus timeline reconstruction, store statistics, and on-demand collection. Optional dependencies remain behind `.[vector]` and now degrade cleanly when unavailable.

### Phase 16: Cross-Domain Analytics (+3 = 109 tools)
`intel_cross_correlate`, `intel_domain_summary`, `intel_trend_detection`

Added historical cross-category correlation, stored-data summarization, and recent-vs-baseline trend detection on top of the vector archive for early-warning and activity-shift analysis.

### Phase 17: Intelligence Reports (+1 = 110 tools)
`intel_generate_report`

Added PDF/HTML intelligence report generation over the existing multi-domain data collection stack. PDF output remains optional behind `.[pdf]`, with HTML fallback available when WeasyPrint is not installed.

---

## Summary

| Category | Current | Notes |
|----------|---------|-------|
| Total MCP tools | 110 | 109 intelligence tools + `intel_status` |
| Tool parity | 110 / 110 | `TOOLS` and `_dispatch()` are aligned |
| Static datasets | 18 | Bases, ports, pipelines, nuclear, cables, datacenters, spaceports, minerals, exchanges, trade routes, cloud regions, financial centers |
| RSS feeds | 119 | 24 categories |
| Tests in repo | 344 | 11 test files; full suite requires `.[dev]` |
| Primary remaining gap | Architecture | `server.py` monolith remains the main refactor target |

**Bottom line**: 110 tools across 30+ domains, with the roadmap now aligned to the live MCP registry. The main remaining gaps are full-environment test bootstrapping (`.[dev]`) and continued modularization of the monolithic `server.py` tool registry/dispatcher.
