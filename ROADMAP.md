# World Intel MCP — Feature Parity Roadmap

**Benchmark**: [koala73/worldmonitor](https://github.com/koala73/worldmonitor)
**Updated**: 2026-02-24
**Current tools**: 68 (67 intel + 1 status)

---

## Legend

| Icon | Meaning |
|------|---------|
| :white_check_mark: | We have this |
| :yellow_circle: | Partial — we have the data source but lack the analysis layer |
| :red_circle: | Missing entirely |

---

## 1. Data Sources — Complete Inventory (59 intel tools)

### Markets & Economics (10 tools)
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

### Natural Disasters & Climate (3 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_earthquakes` | `list-earthquakes` | :white_check_mark: |
| `intel_wildfires` | `list-fire-detections` | :white_check_mark: |
| `intel_climate_anomalies` | `list-climate-anomalies` | :white_check_mark: |

### Conflict & Security (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_acled_events` | `list-acled-events` | :white_check_mark: |
| `intel_ucdp_events` | `list-ucdp-events` | :white_check_mark: |
| `intel_unrest_events` | ACLED protests + GDELT dedup | :white_check_mark: |
| `intel_cyber_threats` | `list-cyber-threats` | :white_check_mark: |

### Military & Defense (6 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_military_flights` | `list-military-flights` | :white_check_mark: |
| `intel_theater_posture` | `get-theater-posture` | :white_check_mark: |
| `intel_aircraft_details` | `get-aircraft-details` | :white_check_mark: |
| `intel_vessel_snapshot` | `get-vessel-snapshot` | :white_check_mark: |
| `intel_military_surge` | `military-surge.ts` | :white_check_mark: |
| `intel_military_bases` | Static dataset (70 bases) | :white_check_mark: |

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
| `intel_news_feed` | 80+ RSS feeds, 4-tier sources | :white_check_mark: |
| `intel_trending_keywords` | trending-keywords service | :white_check_mark: |
| `intel_gdelt_search` | `search-gdelt-documents` | :white_check_mark: |
| `intel_ai_releases` | AI model/paper tracker | :white_check_mark: |

### Transport (3 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_prediction_markets` | `list-prediction-markets` | :white_check_mark: |
| `intel_airport_delays` | `list-airport-delays` | :white_check_mark: |
| `intel_shipping_index` | Yahoo Finance shipping ETFs | :white_check_mark: |

### Analysis & Intelligence (11 tools)
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
| `intel_daily_brief` | — | :white_check_mark: |
| `intel_threat_landscape` | `StrategicPosturePanel` | :white_check_mark: |

### Country & Geopolitical (5 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_country_brief` | `get-country-intel-brief` | :white_check_mark: |
| `intel_country_dossier` | CountryBriefPage | :white_check_mark: |
| `intel_election_calendar` | Election proximity risk | :white_check_mark: |
| `intel_sanctions_search` | OFAC SDN search | :white_check_mark: |
| `intel_nuclear_facilities` | Static dataset (24 facilities) | :white_check_mark: |

### Strategic Synthesis (4 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_strategic_posture` | Composite 9-domain risk assessment | :white_check_mark: |
| `intel_world_brief` | Structured daily intelligence summary | :white_check_mark: |
| `intel_fleet_report` | Naval fleet activity report | :white_check_mark: |
| `intel_population_exposure` | Population near active events | :white_check_mark: |

### Specialist (3 tools)
| Tool | WM Equivalent | Status |
|------|---------------|--------|
| `intel_space_weather` | NOAA/SWPC feeds | :white_check_mark: |
| `intel_nuclear_monitor` | USGS seismic near test sites | :white_check_mark: |
| `intel_service_status` | Cloudflare/AWS/Azure/GCP | :white_check_mark: |

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
| Undersea cables | Cable routes with landing points | — | :red_circle: |
| AI datacenters | Major clusters globally | — | :red_circle: |
| Spaceports | Launch facilities worldwide | — | :red_circle: |
| Critical minerals | Strategic mineral locations | — | :red_circle: |
| Stock exchanges | 92 global exchanges | — | :red_circle: |

---

## 3. RSS Feed Coverage

Expanded from 20 to **80+ feeds** across **15+ categories** with 4-tier source ranking (wire/major/specialty/aggregator) and propaganda risk labels.

| Category | Count | Status |
|----------|-------|--------|
| Wire services | 8+ | :white_check_mark: |
| Politics/World | 15+ | :white_check_mark: |
| Middle East | 8+ | :white_check_mark: |
| Defense/Military | 8+ | :white_check_mark: |
| Think Tanks | 10+ | :white_check_mark: |
| Government (US) | 6+ | :white_check_mark: |
| Crisis/Intl Orgs | 4+ | :white_check_mark: |
| Africa regional | 4+ | :white_check_mark: |
| Asia regional | 6+ | :white_check_mark: |
| Energy | 4+ | :white_check_mark: |
| Cyber/Infosec | 6+ | :white_check_mark: |
| Health (WHO/ProMED) | 3+ | :white_check_mark: |
| Space weather | 2+ | :white_check_mark: |
| AI/ML releases | 3+ | :white_check_mark: |
| Latin America | 0 | :red_circle: |
| Multilingual feeds | 0 | :red_circle: |

---

## 4. What's Still Missing

### Data Sources (P2-P3)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 1 | **Country stock index lookup** — ticker for any country's main index | P2 | S |
| 2 | **Aircraft details batch** — batch lookup by multiple ICAO24 codes | P3 | S |
| 3 | **USNI fleet tracker** — US Navy fleet disposition from USNI News | P2 | M |
| 4 | **Wingbits ADS-B** — crowd-sourced ADS-B coverage | P3 | S |
| 5 | ~~**Population exposure**~~ — :white_check_mark: `intel_population_exposure` | — | — |
| 6 | **Hacker News items** — top HN stories | P3 | S |
| 7 | **Trending repos** — GitHub trending repos | P3 | S |
| 8 | **arXiv papers** — recent AI/ML papers | P3 | S |
| 9 | **PizzInt indicator** — pizza delivery patterns as OSINT proxy | P3 | S |

### Analysis Layers (P2-P3)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 10 | ~~**Strategic Posture Assessment**~~ — :white_check_mark: `intel_strategic_posture` | — | — |
| 11 | ~~**World Brief**~~ — :white_check_mark: `intel_world_brief` (structured, data-driven) | — | — |
| 12 | **USA Spending Tracker** — Federal contract data from USAspending.gov | P3 | S |

### Static Datasets (P3)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 17 | **Undersea cable routes** — landing points (we have health, not routes) | P2 | M |
| 18 | **AI datacenters** — 111 major clusters globally | P3 | S |
| 19 | **Spaceports** — launch facilities worldwide | P3 | S |
| 20 | **Critical mineral deposits** — strategic mineral locations | P3 | S |
| 21 | **Stock exchanges** — 92 global exchanges with coordinates | P3 | M |

### System Architecture (P2)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 22 | **Redis caching backend** — persistent TTL cache (currently in-memory) | P1 | M |
| 23 | **Circuit breaker per-source** — configurable thresholds per API | P2 | S |
| 24 | **Data freshness monitoring** — per-source staleness tracking | P2 | S |

---

## Completed Phases

### Phase 1-4: Foundation (0 -> 39 tools)
Core data sources: markets, crypto, macro, earthquakes, wildfires, ACLED, UCDP, humanitarian, military flights, theater posture, aircraft, internet outages, cable health, nav warnings, climate, prediction markets, displacement, airport delays, cyber threats, news feeds, GDELT, trending keywords, country briefs, risk scores, instability index, signal convergence, daily brief, country dossier, threat landscape.

### Phase 5: Core Analysis Engine (+3 = 42 tools)
`intel_focal_points`, `intel_signal_summary`, `intel_temporal_anomalies`
Countries config with 22 nations, intel hotspots, conflict zones, strategic waterways. CII v2 upgraded with multi-signal weighted blend. Welford's online algorithm for temporal baseline anomaly detection.

### Phase 6: Military & Infrastructure Intelligence (+6 = 48 tools)
`intel_vessel_snapshot`, `intel_military_surge`, `intel_cascade_analysis`, `intel_hotspot_escalation`, `intel_commodity_quotes`, `intel_unrest_events`
AIS vessel tracking, military surge detection in 17 sensitive regions, infrastructure cascade analysis, hotspot escalation scoring for 22 locations.

### Phase 7: Domain Expansion (+10 = 58 tools)
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

---

## Next Phase

### Phase 11: Data Expansion
**Goal**: Fill remaining data gaps and static datasets.

1. **Country stock index lookup** — ticker for any country's main stock index
2. **USNI fleet tracker** — US Navy fleet disposition scraping
3. **Hacker News** — top HN stories via public API
4. **Trending repos** — GitHub trending repositories

New tools: `intel_country_stocks`, `intel_usni_fleet`, `intel_hacker_news`, `intel_trending_repos`

---

## Summary

| Category | Have | Benchmark | Coverage |
|----------|------|-----------|----------|
| Data source tools | 68 | 42 | **162%** |
| Analysis engines | 19 | 15 | **127%** |
| Static datasets | 10 | 12 | 83% |
| RSS feeds | 80+ | 150+ | 53% |
| Strategic synthesis | Strategic posture + world brief + fleet report + population exposure | Dashboard-only | **Exceeds** |

**Bottom line**: 68 tools across 27 domains, exceeding WorldMonitor benchmark by 62% in tool count and 27% in analysis engines. Strategic synthesis layer complete — composite risk assessment, structured intelligence briefs, fleet reporting, and population exposure analysis. Remaining gaps: RSS feed breadth (80+ vs 150+), static datasets (10 vs 12), a few niche data sources.
