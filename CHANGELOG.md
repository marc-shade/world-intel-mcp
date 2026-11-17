# Changelog

## Unreleased

Tools 139 -> 160. Collector sources 55 -> 61. New MCP surface: 29 prompts and 3
resources (none before).

### Fixed: dead upstream endpoints and feeds
- `intel_airport_delays`: the FAA ASWS host (`soa.smext.faa.gov`) no longer
  resolves. Delays now come from the FAA NAS Status feed
  (`nasstatus.faa.gov/api/airport-status-information`), one national list of
  active ground stops, delay programs and closures. Every airport with an
  active event is listed, not a fixed set of 20; closures are returned in a
  separate `closures` list.
- `intel_internet_outages`: the keyless IODA fallback called a removed route
  (`/v2/outages/overall`, 404). It now reads `/v2/outages/events`.
- `intel_usa_spending` agency list: `/api/v2/agency/list/` returns 404; it now
  reads `/api/v2/references/toptier_agencies/`. A failed fetch returns
  `error` / `degraded` instead of an empty agency list.
- `intel_cyber_threats`: abuse.ch requires an Auth-Key for the URLhaus API
  and has retired the keyless dumps. URLhaus is fetched only when
  `URLHAUS_AUTH_KEY` is set; without it the feed is skipped and reported.
- `intel_social_signals`: Reddit answers unauthenticated JSON with 403. When
  every subreddit fails the tool returns an `error` instead of zero posts.
- `intel_cable_health`: with NGA MSI down, every corridor read as "clear".
  The outage shape now carries `error` / `degraded` / `reason`.
- News: 13 dead RSS URLs replaced (DW x4, CFR, Chatham House, HRW,
  Eurasianet, Daily Maverick, Maritime Executive, Arms Control Association,
  Scientific American, White House).
- CLI: `intel flights` crashed on aircraft whose altitude is the string
  "ground"; `intel space` printed an empty table (it read keys the source
  no longer returns); `intel macro` printed `?` for mempool fees and BTC
  dominance; `intel spending` showed $0.0B obligated (wrong key).

### Fixed: failed fetches log no credentials
- A failed keyed request (FRED, EIA, TomTom and others pass the key as a
  query parameter) logged the full request URL, key included. Fetch
  failure logs, `get_bytes` error strings and stale-cache log lines now mask
  credential-named query parameters (`api_key`, `key`, `token` and similar)
  and any value of a `*_KEY`, `*_TOKEN`, `*_SECRET` or `*_PASSWORD`
  environment variable, which covers the key NASA FIRMS carries in the URL
  path. Keys already written to old log files are not rewritten.

### Added: dashboard research panels (Phase 29)
- RESEARCH in the dashboard top bar (or the `p` key) opens four tabs:
  liquidity board, situations, top stories and collection health. Each tab
  loads from its own route when opened and refreshes every 60 s while the
  panel is open: `/api/liquidity-board`, `/api/situations`,
  `/api/top-stories`, `/api/collection-health`. Each route calls the
  function the MCP tool calls (`fetch_liquidity_board`, `fetch_situations`,
  `fetch_top_stories`, and `HistoryStore.collection_health` on the
  dashboard cache's database) and passes its payload through; the
  liquidity route adds the net liquidity `method` block.
- Failures read as failures: a payload with `error` is a 503 with the
  payload intact, an exception a 503 with the reason, the 90 s budget a
  504, a bad parameter a 400 before anything is fetched. A panel never
  shows figures it has not received: before the first answer it says so, a
  failed first load shows UNAVAILABLE with the reason and the payload's
  diagnostics (unavailable indicators, blocked sources, data gaps), and a
  failed refresh keeps the earlier copy under a REFRESH FAILED banner with
  the time it loaded and its age now. An answer to a query the controls
  have since changed is dropped.
- Top stories cluster headlines in a worker thread, so a 7 d window does
  not stall the dashboard and the 90 s budget can answer 504 with its
  reason. When no feed keeps history back to the prior window, the
  situations and top stories panels say change cannot be measured, not
  that nothing changed.
- The four routes send no `Access-Control-Allow-Origin` header, so another
  site cannot read their answers.
- Liquidity rows keep the units each row states and are grouped by
  measure, amounts outstanding apart from flows. Collection health lists
  failing, degraded, not-attempted-recently and never-run sources and shows
  `cannot_prove` as given; a database with no capture says every source
  reads never_run and why.
- Remote text is escaped by the renderers and sanitized again on
  assignment; only http and https links are kept.
- Reading the collector roster imports the collector module, whose
  `logging.basicConfig` would attach a root handler in the dashboard
  process; the root logger is put back as it was on every path, so the
  first collection-health request does not start printing every upstream
  request. A collector module that cannot be imported is a 503 reading
  "collector roster unavailable: <reason>".

### Fixed: development runs no longer touch user databases
- Temporal and keyword spike databases now follow `XDG_CACHE_HOME` like
  the cache: `$XDG_CACHE_HOME/world-intel-mcp/temporal.db` and
  `$XDG_CACHE_HOME/world-intel-mcp/keyword_spikes.db`. With it unset, they
  remain in `~/.cache/world-intel-mcp/`. Existing baselines are not moved:
  with `XDG_CACHE_HOME` set, the two files already in
  `~/.cache/world-intel-mcp/` stay there unread and new, empty baselines
  start under `$XDG_CACHE_HOME/world-intel-mcp/`. To keep their history,
  move both files there yourself before the next run. Nothing points at
  the old files at runtime; `intel_weekly_trends` reports the new baseline
  as created by that call, then as short of history.
- The cache's default path (`~/.cache/world-intel-mcp/cache.db` when
  neither `WORLD_INTEL_CACHE_DB` nor `XDG_CACHE_HOME` is set) is resolved
  when the cache opens, not at import, so it agrees with the baselines if
  `HOME` changes in between.
- When the cache cannot open at its configured or default path, it now
  falls back to a per-user directory, `world-intel-mcp-<uid>` under the
  system temp directory, created with mode 0700, instead of a shared
  `world-intel-mcp` directory there. It refuses that directory with an
  error naming the reason if it is a symlink or not a directory, is owned
  by another user, gives group or other users access, or holds a symlink
  at `cache.db` or its `-wal`, `-shm` or `-journal` file. A fallback cache
  left in the old shared directory is not read or moved. On Windows the
  fallback keeps its old name and is not checked.
- Importing the package no longer opens databases. The shared cache,
  circuit breaker, AOI store, vector store and fetcher behind the MCP
  tools are built on first use, under a lock, as one set: concurrent first
  uses get the same objects, and a first use that fails binds nothing and
  closes the databases it had opened, so the next use starts over.
- `intel_weekly_trends` no longer reports a failed input as zero. When the
  baseline database is missing or unreadable, `trend_count` is `null` and
  `error` says why; when anomaly detection fails, `current_anomaly_count`
  is `null`. A new `data_gaps` list names each failed input, carries
  anomaly detection's own gaps, and flags a baseline created by the same
  call or with no metric at the 5 observations volatility needs. Reading
  the baselines no longer creates an empty database file.
- The dashboard's Trends panel shows a count that could not be computed as
  a dimmed `?` instead of 0, stays visible when weekly trends report an
  error or time out, and lists the error and every data gap.
- Apply per-source request spacing to every HTTP retry, including JSON,
  text, XML and binary fetches.
- Known open: each retry now waits out its source's spacing and the
  breaker is still checked only before the first attempt, so a full outage
  of a rate-limited source takes longer than before to fall back to its
  stale copy. The registry tests' temp-cache premise still depends on test
  order.

### Fixed: database handles close on every exit path
- The collector (`run_once` and the daemon), standalone report generation
  and the weekly trends query now close their cache, HTTP client and SQLite
  connections when they finish or fail, instead of leaving them to garbage
  collection.
- The test suite closes every cache, fetcher and database it opens. Under
  `--cov` on Python 3.13 it held about 1,550 SQLite descriptors open (each
  unclosed connection's ResourceWarning kept it alive) and failed at the
  default 1,024 open-file limit. Test runs also no longer leave
  `wim-server-test-*` directories in the system temp directory.

### Fixed: simultaneous first opens of a cache database
- Processes opening a new cache database at the same moment (the MCP
  server, the collector and a CLI run, or parallel tests) could crash with
  "database is locked": the switch to WAL needs an exclusive lock, and
  SQLite refuses all but one of the simultaneous requests without waiting.
  A cache at the default path then gave up on that path and fell back to
  the temp directory. Opening now retries the switch for up to 10 seconds.
  Measured with 8 processes on one fresh file: 29 to 67 failed opens in 80
  to 160 before, none in 160 after.

### Fixed: the collector cycle summary separates data from errors
- A source that answers with an upstream error (`{"error": ...}`) still
  counts as a completed fetch, but the cycle summary now lists it under
  `upstream_errors`, and `intel-collector` prints how many of the
  "succeeded" sources stored nothing. Before, such a cycle read as data
  collected.
- A stale cache copy (`_stale`) is no longer stored in the vector store as
  if it were collected this cycle; the summary lists it under
  `stale_not_stored`.

### Added: liquidity and money (Phase 29)
Keyless sources only: the FRED graph CSV (`fred.stlouisfed.org/graph/fredgraph.csv`,
allowed by robots.txt with `Crawl-delay: 1`, honored by a 1 s `fred-graph` rate
floor) and the ECB Data Portal (SDMX-JSON). Every point carries `observed_at`,
`value` and `units`; every series is typed `amount_outstanding`, `flow`,
`growth_rate`, `index` or `unknown` and carries a freshness block that flags data older than
its publication cadence allows (a served stale cache copy or an outage shows up
there). `published_at` is null: neither payload carries release dates, and the
responses say so. `limit=0` returns the full history.
- `intel_net_liquidity`: weekly Fed total assets (WALCL) minus Treasury General
  Account (WDTGAL) minus overnight reverse repo (RRPONTSYD), in USD billions.
  WALCL and WDTGAL are USD millions and are divided by 1,000; RRPONTSYD is already
  USD billions. One point per WALCL Wednesday; the TGA must be reported for that
  Wednesday; RRP comes from that day or, when blank on or after 2013-09-23,
  Tuesday only. Before that date a blank Wednesday has no fallback. Each point
  names the RRP date used. Weeks without aligned components are skipped and counted, never filled
  with zero, and a failed component makes the whole response an error. The TGA
  term is the Wednesday level (WDTGAL), not the week average (WTREGEN). A
  `method` block, returned with errors too, states each term's observation basis
  (WALCL and WDTGAL Wednesday levels in USD millions, RRPONTSYD daily in USD
  billions), its conversion, the RRP alignment and why WTREGEN is not used.
- `intel_liquidity_board`: latest reading and change vs the previous observation
  for the Fed balance sheet, TGA, RRP, net liquidity, US M2, euro area M1/M2/M3
  stocks and Eurosystem total assets, sortable by `biggest_move` or `newest`.
  `biggest_move` ranks absolute changes in billions of each row currency, with
  no FX conversion; observation horizons differ. Percentage changes do not
  affect ranking. A
  failed source becomes an `unavailable` row; net liquidity is dropped, not
  computed with a zero term, when any of its components fails. A `blocked` list
  names each measure not covered with its publisher and the status measured on
  2026-10-17.
- `intel_money_supply`: US M2 (FRED M2SL) and euro area M1, M2 and M3 from the ECB
  BSI dataset (end-of-month stocks, monthly flows, annual growth rates), kept
  separate and never summed. US M3 is reported as discontinued (FRED M3SL ends at
  2006-02-01).
- `intel_fed_liquidity_series`: WALCL, WDTGAL, WTREGEN, RRPONTSYD or M2SL with full
  history; blank source dates (2,833 for RRPONTSYD on 2026-10-17, 2,679 of them
  before 2013-09-23, when daily values begin) are counted, not read as zero.
  Net liquidity therefore starts at 2003-03-19: of 1,244 WALCL weeks, 705 align
  and 539 are skipped and counted (first 2002-12-18, last 2018-12-05): 8 before
  RRPONTSYD begins on 2003-02-07, 530 with a blank Wednesday before 2013-09-23,
  and 2018-12-05, when RRPONTSYD is blank on both the Tuesday and the Wednesday.
  10 points use the Tuesday value, all on holiday Wednesdays (measured
  2026-10-17).
- `intel_ecb_series`: any ECB BSI or ILM series by SDMX key, with units, scale,
  titles and provisional flags taken from the response. A growth rate's change is
  reported in points, not as a percent of a percent.
- Stale cache responses carry `served_from_stale_cache`, `cache_age_seconds` and
  `fetch_failure`, and name the failure in `data_gaps`: the HTTP status, no
  response, an open circuit or an unexpected payload. Each stale copy served
  counts in the circuit breaker's `total_stale_serves` (`intel_status`), and none
  is re-cached as fresh. Only parsed bodies enter the cache. An ECB 404 is a
  final no-data answer, without outage retries, only when its body is the
  portal's JSON problem answer whose detail starts "No Series was returned for
  the query"; any other 404, an empty body or an HTML or plain-text error page
  included, is retried, counted as a breaker failure and takes the outage path.
  An empty ECB response is one only when a start was requested;
  without one it is an unexpected payload and takes the outage path, as does
  JSON that is not an object. An observation value that is not a finite number
  makes the response a parse error.
  Missing ECB roles and board rows are named; index bases, provisional status
  and percentage-point change units are retained. ECB keys must specify every
  dimension, request at most 50 series combinations and be at most 200
  characters long. An ECB start after today (UTC) is refused before any
  request, so a caller's input is never counted as a source failure.
- CLI: `intel liquidity`, `intel net-liquidity`, `intel money-supply`,
  `intel fed-liquidity`, `intel ecb-series`. Collector: `liquidity_board` and
  `net_liquidity` (group `liquidity`). `intel liquidity` prints the ranking
  rule of the chosen sort and each row's status; a terminal too narrow for the
  table gets one entry per indicator instead, so no value, date or unit is cut.
- Live reading 2026-10-17: net liquidity for Wednesday 2026-10-14 was
  USD 5,869.615 billion (WALCL 6,755,639 million, WDTGAL 885,823 million,
  RRPONTSYD 0.201 billion, all observed 2026-10-14).
- Adds 5 tools.

Not added, measured 2026-10-17: ICI money market fund assets and ETF net issuance
(403 on every path, robots.txt included); FINRA margin statistics (the finra.org
Terms of Use, Restrictions d and e, forbid building a database from the site and
data mining, scraping or harvesting tools, robots included); BLS public API (keyless
v1 answers for CPI-U and payrolls, but api.bls.gov robots.txt disallows all paths
and the terms page answers 403). Fund flows and ETF net issuance therefore have no
source here, and no proxy is substituted for any of these measures.
### Added: news vs market reaction
- `intel_news_market_reaction` (CLI: `intel news-reaction`): the companies and
  countries named in recent story clusters, mapped to a listing (the entity
  table's ticker; a US ticker is annotated with its registrant when SEC's
  company_tickers.json lists it) or to the country's primary index (the table
  `intel_country_stocks` uses), with the move on the story's market session
  from Yahoo daily bars. Company rows give the stock's close-to-close return
  (adjusted closes), the benchmark's return over the same two dates (SPY for
  US listings, the exchange country's index otherwise) and the excess return;
  country rows give the index return and a z-score against its previous
  up-to-20 sessions.
- Session rule, stated in every response: the story time (earliest
  `published` in the cluster; that article also gives the headline and link)
  is converted to the exchange's timezone; before the regular close on a
  trading day it is that session, at or after the close the next one, and a
  weekend or holiday (read from the listing's own bars) maps to the next
  trading day. Each row names the close it used (`close_time_used`). A
  session that has not closed, or whose last bar Yahoo has not finalized
  (its regularMarketTime is before the close), is `pending`.
- Honest gaps: a failed quote, an expired cached chart or SEC file served
  during an outage, a missing benchmark bar, a stock series missing a day its
  benchmark traded (also between the two dates of a return), a cluster whose
  articles map to different sessions, a story timestamp later than the
  collection time and a story older than the bar range are each a `data_gap`
  row or line with the reason and no number, never a 0% move. A bar Yahoo
  fills for a day without trading (open, high, low and close equal to the
  previous close, no volume) is dropped, not read as a 0% session.
  `data_gaps` also names a listing whose Yahoo close differs from its zone's
  standard close, and a chart without adjusted closes. Stories whose earliest
  article is older than `max_age_hours` (default 168) are left out and
  counted. Unmapped names (companies without a ticker in the entity table,
  countries without an index) are listed, not dropped. Company names that are
  also common words (apple, amazon, meta, shell, bp, alphabet, chevron,
  samsung) are excluded with a stated reason unless the headlines carry a
  corroborating term or an article comes from a feed where the company sense
  dominates (a hyphen-joined use such as "meta-analysis" does not count); a
  phrase marking the other sense ("big apple", "amazon rainforest", "chevron
  ruling", "25 bp") excludes the name. A country gets an index row only when
  the headlines use its name; one named only by a demonym, capital or code,
  or inside a longer name such as "Gulf of Mexico", is listed as excluded.
  Responses say they describe same-session co-movement, not causation, and
  are not a trading signal. Adds 1 tool.

### Added: research guide over MCP (prompts and resources)
- The server now answers `resources/list`, `resources/read`, `prompts/list`
  and `prompts/get`, and advertises the resources and prompts capabilities
  at initialize. Before this it exposed tools only. This change adds no
  tools and renames no tool or parameter. Changes to existing tools made
  alongside it (the corrected tool descriptions, the UCDP failure fields,
  `intel_yield_curve` returning `inverted: null` instead of `false` when no
  spread could be computed, and the arXiv, Kp, ACLED, sanctions and
  instability fixes) are listed under the two Fixed sections below.
- At initialize the server sends `instructions` that point a model at
  `intel://guide` before its first tool call.
- `intel://guide` (markdown): how to ask a strong question (period,
  comparison, measure, place), what an answer contains, what this server
  will not do, the worked prompts, and every registered tool grouped by
  domain module, with a `[needs VARIABLE]` mark on each tool that returns
  an error without its API key. Built from the live registry on every
  read; a test fails if a registered tool is missing or listed twice. It
  says plainly that many tools do not mark a failure: when every upstream
  request fails they can return an empty list, a zero count, a neutral
  score, a LOW risk label, an all-clear status or a false flag with no
  error, `degraded` or `data_gaps` field.
- `intel://guide/source-health` (JSON): open circuit breakers, stale
  serves, stale cache prefixes, cache freshness, and which keyed sources
  have their variables set (names only, never values), with a `verdict`
  line that says when there is nothing to go on yet. Reads in-process
  state and the cache database only; reading it starts no fetch. A cache
  that cannot be read becomes `cache.available: false` with the error,
  and the rest of the snapshot is still returned. It says that breaker
  state covers this server process only. The keyed-source list is checked
  against every credential name quoted anywhere in the package.
- `intel://guide/measures` (markdown): stock versus flow, growth versus
  acceleration, percentage points, seasonal adjustment, the three dates
  (observation, publication, collection), revisions, correlation and
  timing offsets, composite scores, missing data versus zero.
- 29 prompts across conflict, markets, hazards, migration, aviation, cyber,
  infrastructure, maritime, areas of interest, news, politics, sanctions,
  health, stored history and country views. Each names the tools to call,
  the arguments to pass and the limits to respect. Arguments are
  validated: numbers and their ranges, listed values, no tool names from
  outside the prompt, whitespace collapsed so a value stays on its line.
  A missing, unknown or invalid one is an `invalid params` error. Tests
  fail if a prompt names a tool that is not registered, passes an argument
  its schema does not take (name, type, listed value or range), cites an
  output field the code does not produce, describes a step in words that
  share nothing with the called tool's description or names a provider
  that tool does not, or states one of the pinned counts or table sizes
  (cities, countries, waterways, corridors, central banks, hotspots,
  airports, Yahoo maturities, election rows and default limits) that the
  code does not match. Counts the tests do not pin are not checked.
- `intel guide` prints the guide markdown; `intel guide --measures` prints
  the glossary.
- Two tests drive initialize, resources/list, resources/read, prompts/list,
  prompts/get and tools/list over stdio: one against the installed
  `world-intel-mcp` console script (or `python -m world_intel_mcp.server`
  where none is installed), one always against the module form. Neither
  is skipped.
- The maritime, hotspot and airspace prompts state the maritime and
  flight outage behaviour fixed below: a warning counts at a waterway only
  within 300 km of a position it states, a naval warning with no readable
  position changes no status, `unknown` is an NGA outage and `stale` a
  frozen feed (`status_as_of`), the `navarea` filter takes NGA area codes,
  and a flight source outage reads `source: "none"` with `reason`
  `military_flights_unavailable` in military flights, `unavailable_theaters`
  in theater posture and `unchecked_regions` in surge detection. The
  hotspot prompt also says that the escalation
  score's military component is 0 at every hotspot whatever the aircraft
  data (measured 2026-10-17 with mocked aircraft over all 22 hotspots), so
  military activity is read from the surge and posture tools instead. Tests
  hold each statement against the code through a real fetcher with every
  upstream mocked.

### Fixed: tool error reporting and server fixes
- `intel_ucdp_events`: a missing token or a refused request (the UCDP API
  answers 401 without a token) now returns `error`, `degraded: true` and
  `reason` (`ucdp_unconfigured` or `ucdp_fetch_failed`) next to the empty
  events list, the same shape as ACLED's fetch failure, instead of reading
  as zero events. The first page shared a cache key with the second, so a
  multi-page result repeated the first page in place of the second; every
  page now has its own key, which also carries the page size.
- Stale serves are counted for dictionary payloads too (before, only lists
  and text were counted), so `total_stale_serves` in breaker status and
  `stale_serves` in source health include every stale copy served.
- The cache records the database path it was asked to use and whether it
  fell back to a temporary one (`requested_path`, `fell_back`); source
  health shows both.
- `serverInfo.version` at initialize is the package version; it was the
  MCP SDK's version.
- Tool descriptions: `intel_acled_events` and `intel_risk_scores` name
  `ACLED_EMAIL` and `ACLED_PASSWORD`; `intel_ucdp_events` names
  `UCDP_ACCESS_TOKEN` and all three violence types and says its limit is a
  page size; `intel_btc_technicals` says its distance is from the highest
  daily price of the last 200 days, not the all-time high.
- README environment table: `ACLED_EMAIL` and `ACLED_PASSWORD` replace
  `ACLED_ACCESS_TOKEN`, which no code reads; added `UCDP_ACCESS_TOKEN`,
  `TOMTOM_API_KEY`, `WINDY_API_KEY`, `OPENSKY_USERNAME` and
  `OPENSKY_PASSWORD`.
- `intel_yield_curve`: `inverted` is null, not `false`, when neither
  spread could be computed, so an outage or one lost maturity no longer
  reads as "not inverted". New `inversion_basis` names the spreads the
  flag rests on (without `FRED_API_KEY` that is `spread_3m10y` alone) and
  `yields_source` says whether the maturities came from FRED or Yahoo. A
  maturity with no rate is listed in `data_gaps` with `degraded: true`, and
  no rate at all is an `error`.
- `intel_arxiv_papers` without `query` raised a TypeError before any
  request; it now searches the default AI, ML and NLP categories. The
  search also goes into the first request: before, the first request was
  sent to the bare API URL and the query only reached a fallback.
- `intel_situation_brief` and `intel_daily_digest` raised a TypeError when
  NOAA SWPC was down, because the space weather source then reports no Kp
  reading. The brief now says "Kp unavailable (no reading)" and
  `metrics_snapshot.kp_index` is null, and the digest lists "Space weather:
  no Kp reading" in `data_gaps`.
- `intel_acled_events` and `intel_unrest_events` keyed their cache on
  country and days only, so a short list cached for a small `limit` came
  back, for 15 minutes, to a call that asked for more rows, and a count
  below the limit then read as complete. `limit` is now part of both keys.
- `intel_ucdp_events` dropped a page that failed after the first one (an
  outage, or the circuit breaker skipping it) and returned the shorter
  list with no marker. Such a result now carries `degraded`, reason
  `ucdp_partial`, `pages_failed`, `pages_total` and a `data_gaps` entry
  saying count and fatalities are lower bounds, and the conflict-trend
  prompt tells the model to report the list as incomplete.
- With `ACLED_EMAIL` and `ACLED_PASSWORD` set but the ACLED sign-in
  request refused or unreachable, every ACLED tool said the credentials
  were not configured. That case now has its own reason,
  `acled_auth_failed`, and the error says the sign-in failed.
- The sanctions section of `intel_country_dossier` was always empty: it
  searched entity names for the ISO-3 code and read a key the search does
  not return, and a failed SDN download read as zero matches. It now lists
  SDN entries whose remarks name the country (by English name), carries
  `total_entities`, `country_searched`, `match_method` and `more_matches`,
  and a failed download sets `match_count` to null with `error`,
  `degraded`, reason `sdn_unavailable` and a `data_gaps` entry. `intel
  dossier` prints "not screened" in that case.
- `intel_instability_index` for one country: a code outside its name
  table was sent upstream as-is and scored from inputs that never matched
  the place, and any string (a name, a typo, lower case) gave a low score
  with no error. Codes are now upper-cased, the 50 codes it can name are
  sent as English names, and any other input returns an error listing
  `accepted_codes`. Every input it could not obtain (ACLED, internet
  outages, military flights, GDELT, or a country with no military bounding
  box) is named in `data_gaps`, a component with no measured input is
  null, `index_is_lower_bound` marks a total that counts missing parts as
  zero, and with nothing measured the index is null and the risk level
  `unknown`. `ucdp_floor_basis` says the floor comes from a static table.
- The source-health verdict counted only open or half-open circuit
  breakers, and a breaker opens after three failures in a row, so after
  one or two failed calls it read "0 with an open or half-open circuit
  breaker" while the source was down. New `failing_sources` lists every
  source whose last call failed, the verdict reads "N sources called by
  this process, M whose last call failed, K with an open or half-open
  circuit breaker" (plus how many served a stale copy), and the scope
  notes explain `failures`, `total_successes` and `total_failures`.
- `intel_internet_outages` returned an empty list with no marker when
  neither Cloudflare Radar nor IODA answered; it now carries `error`,
  `degraded` and reason `outages_unavailable`.

### Fixed: research guide
- The guide did not mark `intel_instability_index` as needing ACLED
  credentials, though without a `country_code` it returns the same
  credentials error as the other ACLED tools. It now carries
  `[needs ACLED_EMAIL, ACLED_PASSWORD]`, and the keyed-source note says a
  `country_code` call still scores without ACLED and lists
  `acled_unconfigured` in `data_gaps`. A new test calls every conflict and
  intelligence tool with no keys set and checks that each one whose error
  names a key is marked.
- story-breadth told the model not to state a unit for GDELT volume
  while the shared answer shape asked for each number with its unit. The
  answer shape now reads "each number with its unit (or say the source
  states none) and date".
- The guide said stored history exists only for the time the collector
  or server ran, which is false after `intel_history_backfill` loads FRED
  or ECB publisher history. The limit now names the backfill, the three
  tools that read it, and that its values are the publisher's current
  vintage.
- sanctions-screen said a count equal to the limit means more names
  matched, and conflict-trend and earthquake-exposure said the same of
  their lists, but a list that ends exactly at the limit returns the same
  count. They now say the list may have been cut off and to call again
  with a higher limit, and sanctions-screen says `total_entities` counts
  the entries read before the search stopped, not the size of the list.
- The guide's tool list cut each description at the first period
  followed by a capital, so `intel_us_border_encounters` read just "U.S.".
  A period that closes an abbreviation (U.S., e.g., i.e.) no longer ends
  the line.
- Domain summaries carried maintainer notes from module docstrings (a
  build phase, a source file path, internal names), and newer domains had
  no written title. Each domain now has one, and a summary is the first
  sentence of its module docstring without build-phase notes.
- Prompt argument values are rendered as one inert value. In a "call
  with" list a value containing a space is quoted, so "Sudan days 9999
  limit 5" cannot read as extra arguments. Control and format characters
  (escape, NUL, zero-width, direction marks) are dropped. The check that
  refuses a value naming another tool now folds case and compatibility
  forms, treats hyphens as underscores and needs no word boundary in
  front. Whole and decimal numbers take ASCII digits only, and a value
  over 200 characters is refused instead of cut.
- A cache file moved, deleted or replaced while the server held it open
  kept answering from the open handle, and source health reported it as
  the shared cache. `cache.moved` now marks it (the path is gone, or is
  not the file source health first read), the verdict says the numbers
  come from a file no other process shares, and the scope notes say a
  replacement made before the first read is not detected.
- Prompts now name the merged tools that answer their questions:
  story-breadth (outlet breadth, ranked situations, per-day hostility
  coverage), election-watch (Kalshi Elections markets and the cross-venue
  comparison), the migration prompts (US border encounters, UK small boat
  arrivals), the AOI prompts (polygon and corridor areas, the all-area
  digest), market-risk-snapshot (liquidity board, net liquidity),
  company-events (news and market reaction), yield-curve-check and
  central-bank-compare (a keyless FRED backfill read back from the history
  store when `FRED_API_KEY` is not set) and history-recall (the history
  store and the collector's run log). The source-health scope points to
  `intel_collection_health` for the run history it does not read.
- election-watch presented `intel_election_calendar` as upcoming
  elections. It is a hand-kept table of 18 rows dated 2025-01 to
  2029-04, most already past; an uncovered country returns an empty list
  with no note; past entries keep a proximity risk; and the country
  filter also matches part of a name (RUS returns Belarus). The step and
  limits now say each of these. The code is unchanged.
- country-overview now says the dossier's elections section reads the
  same hand-kept table: empty means not covered, and its match on part of
  a name can add another country's election (RUS gets Belarus's).
- earthquake-exposure told the model to keep only the cities whose
  `event_detail` names a step-1 quake, but `intel_population_exposure`
  names only the nearest M4.5+ event per city, so a nearer aftershock
  dropped a city that a large quake had reached. The step now says so
  and to compare each city's position with every step-1 event before
  dropping it. The code is unchanged.
- aoi-watch-setup, aoi-review and wildfire-situation describe failed
  fetches as the code now reports them: a total earthquake or wildfire
  outage is an error that the AOI brief and changes list in `data_gaps`
  and leave out of the diff, and a FIRMS region that did not answer is
  named in `failed_regions` (partial coverage in an AOI). Both AOI
  prompts still call a whole domain departing at once with no gap
  unconfirmed and point to `failing_sources`.
- conflict-trend told the model to check the latest UCDP `date_start`
  before reading a thin window as calm, but when the pinned release
  (gedevents/25.1) ends before the window the tool returns count 0 with
  no date and no marker. The limit now names the release and says a
  count of 0, or a newest event well before the window ends, is missing
  data, not zero events. The code is unchanged.
- Claims in the guide text are pinned to the code they describe: the
  failure warning in the server instructions, shared prompt limits, guide
  intro and glossary; the no-observation-date sentence in all three; the
  fx-move direction, checked by running the rate series; the exposure
  step's magnitude, window, limit and radius, read from the code; the ten
  years in history-recall; and the central bank, hotspot, airport and
  Yahoo maturity counts. The test claim above is narrowed to the counts
  the tests pin.
- The check that a prompt step's purpose agrees with its tool let wrong
  tools through on one shared parameter word, or on a tool's own
  disclaimer (internet outages repointed to the cyclone tool passed). A
  second check now requires a shared word with the tool's name or first
  sentence, without generic schema words, and three such swaps are pinned
  as failures. Seven step purposes were reworded to name what their tool
  returns. Measured on 118 steps and 160 tools, 1,141 of 18,762 one-step
  swaps still pass both checks.

### Added: tropical cyclone forecast tracks
- `intel_cyclones` and `intel_jtwc_cyclones` take `include_forecast`
  (boolean, default false). With it, each storm gains a `forecast`: the
  `initial` fix and forecast `points` (forecast hour, UTC valid time,
  latitude and longitude, max wind and gust in knots, status such as
  POST-TROP/REMNT LOW or DISSIPATED, and the agency's section label),
  `track_status`, and the advisory or warning number and issue time.
  Without it, both responses and the collector's NHC call are unchanged.
- NHC points come from the forecast/advisory text that CurrentStorms.json
  links: the one NHC product that states UTC valid times and post-tropical
  status outright (the KMZ track gives local times, and the shapefile
  labels a post-tropical remnant low "Subtropical Depression"). The cone
  comes from the linked CONE.kmz: its one ring, simplified
  (Douglas-Peucker, 0.01 degrees; Hurricane Trudy advisory 17 went from
  1,167 vertices to 56) to `[lat, lon]` vertices, with the source vertex
  count, the tolerance, and a note pointing at the official geometry
  (`cone_url`).
- JTWC points come from each storm's linked warning text (its forecast,
  extended outlook and long range outlook blocks). JTWC links no cone:
  `cone_status` is `not_published`, and `data_gaps` says so.

### Data honesty: forecast tracks
- `data_gaps` names every track or cone not delivered, per storm, with a
  status: `fetch_failed`, `unparsed`, `refused_link`, `not_linked`,
  `not_published`, `not_fetched_cap` (at most 10 storms per call; the rest are named,
  never dropped) or `error` (an unexpected exception while building that one
  product; the storm list and every other product still arrive). A failure
  marks the response `degraded`; a product the agency does not link is a
  gap, not degradation. A quiet basin still answers zero storms, not
  degraded, and makes no product fetches; a feed outage keeps its existing
  degraded shape and makes none either.
- The text pages are per storm bin, not per issuance, and the feeds are
  cached for 600 s, so a text and its feed entry can be out of step either
  way. Its advisory or warning number is compared with the feed's, with one
  rule for both agencies: a text older than the feed, or one whose number
  cannot be read, is `stale_advisory` or `stale_warning` (degraded, with the
  expected number, not kept); a text newer than the feed is
  `feed_lags_text` (named in `data_gaps`, not degraded, kept). Every
  forecast carries both numbers: `advisory_number` / `warning_number` from
  the text, `feed_advisory_number` / `feed_warning_number` from the feed,
  which the storm's other fields also come from.
- Each product is fetched once per issuance (cache keys carry the
  advisory or warning number and the file or issue time; one-hour TTL;
  only an accepted text is kept) under its own circuit breaker
  (`nhc-forecast`, `nhc-gis`, `jtwc-warning`), so a product outage does
  not trip the warning feeds' breakers. A failed text fetch is
  `fetch_failed`; it is not answered from an expired copy.
- Remote KML is parsed with the standard library: strict UTF-8, any
  DOCTYPE refused, the KML member read only when it is stored or deflated
  and declares at most 100:1 expansion, and a cone with more than one ring
  refused, never trimmed. Size caps: text 1 MiB, KMZ 2 MiB, KML member
  8 MiB. Texts and the KMZ are read with `Fetcher.get_bytes`, which stops
  reading once the decoded body passes its cap; one 64 KiB network read of
  gzip can still decode to about 64 MiB before that check.
- A ring of more than 3,000 vertices is refused before simplifying, and
  simplifying stops once the outline passes 500 vertices, which bounds it
  at about 1.5 million distance evaluations. Measured on one machine: a
  zig-zag ring at the cap takes 0.42 s of CPU; the same shape at the old
  10,000-vertex cap took 15 s. An outline of fewer than 3 vertices is
  refused. Simplifying runs off the event loop.
- Product links come from the agencies' feeds and are fetched only when
  they are strings, contain no whitespace or control characters, and are
  https on the agency's own host (www.nhc.noaa.gov, www.metoc.navy.mil).
  Any other link, and a feed record that is not an object, is reported as
  `refused_link` and never requested. No product redirect is followed:
  one is reported as `refused_link` naming its target, so `track_url` and
  `cone_url` are always where the data came from.
- `intel_cyclones` keeps the fetcher's `_stale` and `_stale_age_seconds`
  marker when CurrentStorms.json is served from an expired cached copy,
  with or without `include_forecast` (it was dropped before).
- `Fetcher.get_bytes` takes `follow_redirects` (keyword-only, default
  true); with false, a redirect is returned as its status and resolved
  `location`, never requested, retried or counted as a source failure. It
  also reads a body as it arrives and refuses it as soon as the decoded
  size passes `max_bytes`, where it used to buffer and decode the whole
  body first. Measured on one machine, a 521,844-byte gzip body that
  decodes to 512 MiB, from a local server, with a 64 MiB cap: peak RSS
  went from 40 MiB to 1,120 MiB before, to 176 MiB after (reading stopped
  at 67,244,864 decoded bytes, the first network read). The over-cap
  error now reads "body exceeds cap N: stopped after M decoded bytes".
  `get_text` and `get_json` still read whole bodies, and `get_text` has no
  cap. `Cache.delete` logs and swallows a locked or read-only database, as
  `Cache.set` does.
- Measured 2026-10-17: every product used answered HTTP 200 without a
  key; nhc.noaa.gov robots.txt disallows nothing and the NWS disclaimer
  puts the products in the public domain. The JTWC home page and
  robots.txt answered 403 (CloudFront "Request blocked"), so JTWC's site
  terms could not be read; its RSS and warning texts served 200 to the
  same client. Wind radii and seas are not parsed.

### Added: day timeline (Phase 29)
- `intel_day_timeline` (MCP) and `intel history day YYYY-MM-DD [--by
  collected|observed] [--source NAME] [--limit N] [--per-source N]` (CLI):
  what the history store holds for one UTC calendar day, the half-open
  window `[day 00:00:00Z, next day 00:00:00Z)`. Input is `YYYY-MM-DD` only;
  a malformed or impossible date, or a future day, is an error naming the
  format (the CLI exits 2). Today is allowed and reported as in progress.
- `by=collected` (default) reads the run log. Per source: attempts, ok /
  degraded / error counts with up to 5 distinct reasons, payload changes
  (changed, unchanged, first capture, not stored), first and last capture,
  observations stored and still retained, and how many of the day's
  payload bodies are still kept. Each source gets a `day_state`:
  `changed`, `unchanged`, `answered`, `degraded`, `failed`,
  `not_attempted` (the collector ran that day, not this source),
  `collector_did_not_run` (no capture of any source that day),
  `before_run_log` (the day is before the first capture in this
  database's run log, so whether the source ran cannot be read),
  `never_run` (no capture of it before or after the day in the retained
  run log) or `unknown_past_retention`. A source with an error beside ok or
  degraded captures is flagged `partial_failure`. A collector block gives
  the day's capture count, first and last capture, `covered_from` and the
  longest stretch without any capture; its state is `ran`, `did_not_run`,
  `unknown_past_retention` or `not_recorded` (the run log starts after the
  day or is empty).
- Extractor failures are read from the run log: captures whose history
  extractor raised (nothing stored) and captures whose points the store
  refused are counted per source, their errors appear among the reasons
  (kind `extraction`), and the day gets a gap saying what the observed view
  misses. by=observed checks captures collected from the day to the next
  day for the same failures.
- Coverage: a day partly or wholly past the run-log cutoff is read as
  covered when the run log still holds an older capture (pruning cuts every
  source at one cutoff and captures are stamped on insert), so a day the
  last cycle has not pruned yet keeps its states; otherwise counts, states
  and the longest gap are stated to cover only the first retained capture
  onward.
- `by=observed`: values whose `observed_at` is the day (a date) or a UTC
  instant on it, one item per series and `observed_at` with the latest
  value, how many values were stored for it and the first one when it was
  revised. Month (`YYYY-MM`) and year (`YYYY`) values containing the day
  are listed apart as period values. Observations without `observed_at`
  (Yahoo quotes) are excluded, and those collected that day are counted
  with the reason.
- Every item carries `observed_at`, `published_at` and `collected_at`.
  Retention is stated per record kind for the day (payload bodies, run
  log, observations): a day past the run-log window reads
  `unknown_past_retention`, never as a day on which nothing ran, and pruned
  payload bodies and observations that outlived their capture are counted.
  Output is capped (default 10 per source and 100 in all, at most 1,000
  and 5,000) with matched and returned counts per source; in by=observed
  the day values and period values share one budget. A limit that is not
  an integer (a bool, 2.9, infinity) gets the default.
- One call reads one SQLite snapshot (a single read transaction), so a
  collector cycle committing mid-call cannot mix two states. A store
  missing some history tables is an error naming them, not an empty day.
  Values whose `observed_at` starts with the day but sorts above
  `T23:59:59Z` (fractional seconds, offsets) are counted on the day.
- Read-only: the store is opened with SQLite `mode=ro`, so the tool cannot
  write it, and it never fetches. Queries range-scan
  `idx_history_captures_time` and `idx_history_obs_time` and walk
  `idx_history_obs_series` one key at a time; a test checks every
  statement's query plan for a full scan of a history table. On a
  synthetic store of 475,200 captures and 1.75 million observations
  (10,982 series), one call took 24 to 46 ms (measured before the review
  fixes, not re-measured).
- Adds 1 tool.

### Added: observation history and collection health
- A history store in the cache SQLite file. Every collector source run is a
  capture: source, collected_at, status (ok, degraded or error), duration,
  record count, reason and payload hash. A failed fetch is an error capture
  with its reason and no record count, never an ok capture with zero
  records. An empty payload is degraded, because a quiet period and a
  silent upstream failure look the same.
- A run that any upstream fetch answered from an expired cached copy is a
  stale-cache replay: degraded, with the reason `served stale cache`. The
  reason is the same text on every replay, so replays group; the copy's
  age and the number of stale fetches are the capture fields
  `stale_age_s` and `stale_fetches` (a run log created before them gains
  the columns in place when opened, and the CLI shows them beside the
  reason). The collector reads this from a per-task log the fetcher
  keeps (`fetcher.recording_stale_serves()`, opened once per source task),
  because most source modules rebuild their payload and drop the fetcher's
  `_stale` marker. A replay's observations are counted but not stored: a
  stale replay is not a new observation. A live capture that is degraded
  for another reason (empty, partial, marked degraded) still stores the
  points it has. A capture whose extractor raised is degraded too, with
  the error as its reason; its payload is kept.
- Payload bodies are kept once per distinct payload as compressed JSON
  (top-level fetch-time stamps and the stale markers are ignored when
  hashing, so a fresh and a stale copy of the same data read unchanged).
  A body over `WORLD_INTEL_HISTORY_MAX_BODY_BYTES` (default 4 MiB of
  JSON, 0 = no cap) is not stored: its capture keeps the hash and says
  why. Replay returns at most `WORLD_INTEL_HISTORY_REPLAY_MAX_BYTES`
  (default 256 KiB, 0 = no cap) and an outline of the top-level keys
  beyond that; replaying a capture whose body an earlier capture stored
  names that capture's time. Retention, each
  0 = keep forever: `WORLD_INTEL_HISTORY_PAYLOAD_DAYS` (default 7) for
  bodies, `WORLD_INTEL_HISTORY_CAPTURE_DAYS` (default 30) for the run log,
  `WORLD_INTEL_HISTORY_DAYS` (default 365) for observations. Measured over
  three full 55-source cycles: 90 KB and 193 KB of new compressed bodies in
  the two follow-up cycles (about 70 KB from sources that change every
  cycle, plus the military flight snapshot when it succeeds) and about
  14 KB of capture rows per cycle. At `--interval 300` that is about
  130-340 MB of bodies at the 7-day default and about 100 MB of run log at
  30 days. Quote observations on a trading day were not measured.
- Observations with three dates: `observed_at` (from the payload, or null
  when it has none; never the collection time), `published_at` (when the
  payload names a release time) and `collected_at`. Built-in extractors:
  NOAA Kp, USGS per-event magnitude, FRED-sourced central bank rates
  (curated rows are skipped), Yahoo index and commodity quotes (null
  `observed_at`: the payload carries no quote time). An index level's unit
  is `index points`, with the quote currency in its label (`^GSPC (USD)`);
  a commodity future's unit is its exchange quotation unit (`USD per troy
  ounce`, `US cents per bushel`).
  `history.register_extractor()` is the public API for new sources; its
  `expected=N` declares how many points a complete payload yields. The
  Yahoo quote sources declare one per default symbol, so a run where some
  symbols did not answer is degraded as `partial: X of N expected series`.
  Observation dates must name a real calendar period in ASCII digits
  (`2026-02-30`, `0000` and fullwidth digits are rejected).
- MCP tools `intel_collection_health`, `intel_capture_history`,
  `intel_series_history` and `intel_revisions`, and the CLI group
  `intel history health|captures|series|revisions`. Adds 4 tools. History
  accrues only while the collector runs, except the `backfill:*` series
  that `intel_history_backfill` (`intel history backfill fred|ecb`) loads
  from the publisher's current data.
- Collection health counts a success only from a live capture. A source
  served from stale cache reads `stale`, keeps its last live success time
  and goes overdue on schedule; consecutive failures count errors and
  stale replays since the last live capture. Health also reports the last
  fully ok capture (`last_ok_at`, `last_ok_age_s`; a Last ok column in
  `intel history health`), `data_gaps` (an empty run log names the file
  it read, and a run log at the cache's temp-directory fallback,
  `world-intel-mcp-<uid>/cache.db` under the system temp directory, is named
  as the fallback), lost history writes and what it cannot prove.
  `intel_revisions` reports how many observations and dated series it
  checked, and its data gaps.
- The collector records every source outcome of a cycle in one
  transaction. Its summary gains a `history` key (and the CLI summary a
  History line). A failed history write is retried once; when the retry
  fails too, the lost cycle is appended to
  `<cache db>-history-write-failures.jsonl` beside the DB (newest 500
  kept), and collection health reports it with the sources it covered. A
  history write failure never fails the cycle. The record is rewritten
  through an exclusive temp file (`mkstemp`: random name, mode 0600)
  renamed into place, and is never read or written through a symlink. A
  symlink, FIFO or other non-regular file at its path is not read: the
  collector replaces it (logged, and noted in the new record as
  `replaced_unread`), and health names one it finds in its data gaps.
- Expected cadence for health is 300 s (the shipped plist interval);
  `WORLD_INTEL_HISTORY_CADENCE_S` and
  `WORLD_INTEL_HISTORY_CADENCES=source=seconds,...` override it.

### Fixed: observation history (collector BaseException)
- A collector source task that ended in a `BaseException` that is not an
  `Exception` (for example a cancelled task) made the cycle raise a
  `TypeError` while tallying results, after the fetches finished, so that
  cycle returned no summary and recorded no history. It now counts as a
  failure and is recorded as an error capture.

### Known limits: observation history
- Known limits, stated in `intel_collection_health`'s `cannot_prove` and
  the `history` module docs: stale data are seen only through the
  fetcher's expired-cache fallback or a top-level `_stale` marker (a
  source that awaits a fetch another task started reads live);
  observation retention prunes by collection time, so a value unchanged
  for longer than `WORLD_INTEL_HISTORY_DAYS` is stored again and its first
  sighting reads as that later capture; a collector and a server that
  resolve different cache paths keep different run logs.
- The cycle summary's `successes` still counts a source that returned
  `{"error": ...}` (unchanged, pinned by an existing test); that run's
  history capture is an error.

### Added: connections with timing offsets (Phase 29)
- `intel_lagged_connections` (CLI: `intel history connections`): Pearson
  correlation between 2 to 8 series in the history store (keys as
  `intel_series_history` lists them), aligned on a UTC day, week (Monday to
  Sunday) or month grid and tested at every lag from `-max_lag` to
  `+max_lag` (default 5, at most 30, reduced so one call runs at most 1,000
  tests). Lag +k compares A at period t with B at t+k, so A leads B by k.
- Default transform: period-over-period changes, never taken across a gap;
  `levels` on request. Responses say which ran and why changes are the
  default (levels of trending series correlate spuriously).
- Per pair: the lag with the smallest p, with r, n (overlapping periods
  after the transform and shift), a two-sided p from Student's t (computed
  from the regularized incomplete beta function, standard library only)
  that treats periods as independent, `p_ar1` (p recomputed with an AR(1)
  effective sample size, below), and the Benjamini-Hochberg `q` and `q_ar1`
  across every test in the call, with the Benjamini-Yekutieli `q_by` (of
  `q_ar1`) alongside. `significant` means `q_ar1` <= 0.05 by default
  (allowed 0.001 to 0.25), and `significant_if_independent` applies the
  threshold to `q`; the other significant lags are listed too. The summary
  gives both counts.
- A pair and lag with fewer than 30 overlapping periods (callers may go down
  to 20), or a constant side, is listed as not tested with its n, never
  dropped. 30 points give about 80% power for a true |r| of 0.5 at alpha
  0.05 (module docstring).
- One vintage, the latest collected value for each `observed_at`. Rows
  without `observed_at` (Yahoo quotes) are not used, with the reason: rows
  are stored only on change, so a missing day cannot be told from an
  unchanged one. A period takes its last observation; nothing is averaged.
  On the week and month grids each series reports the shortest and longest
  interval its changes span (`change_interval_days`), and `data_gaps` names
  unequal intervals.
- Serial correlation: each series' lag-1 autocorrelation (phi) after the
  transform, and on every test an AR(1) effective sample size n (1 - phi_a
  phi_b) / (1 + phi_a phi_b), capped at n, with `p_ar1` recomputed from it;
  significance follows `q_ar1`. Below an effective size of 3, or without a
  measurable phi (too few adjacent periods, or adjacent values that do not
  vary, each named as such), `p_ar1` is 1 and the entry says "no evidence"
  or "not assessed"; those tests still count in `q` and `q_ar1`. phi comes
  from each series' whole window, not from each test's overlap, so a series
  whose autocorrelation differs inside the overlap can still have its
  evidence overstated. `serial_correlation_dominates` marks an effective
  size under a fifth of n, and `data_gaps` names those pairs and every
  series that took part in a test with |phi| above 0.3, either sign. The
  CLI prints series keys literally in its gap, note and pair lines (a key
  segment such as `:x:` was turned into an emoji). The strongest lag's p and `p_ar1` are post-selection;
  `q` and `q_ar1` adjust for every test. Nothing is prewhitened. Measured in
  a scratch simulation through the store: two independent random walks of
  300 daily points in levels (seeds 0-99, defaults) have a lag with q <=
  0.05 in 91 seeds and with `q_ar1` <= 0.05 in none; two independent series
  of 200 AR(1) changes (4,000 runs, lag 0) reject at p <= 0.05 in 12.2%
  (phi 0.5) and 35.3% (phi 0.8) of runs, and at `q_ar1` <= 0.05 in 4.5% and
  5.1%.
- `cannot_prove` in every response: correlation is not causation, a lead is
  not a causal direction, serial correlation inflates significance, a
  shared driver produces correlation, the store holds only what the
  collector recorded, BH under dependence is approximate and covers one
  call, and a small q is not a large effect.
- An unknown grid or transform is an error naming the allowed values;
  numeric inputs are clamped and each clamp is reported, in the MCP
  response (`inputs_clamped`) and as a `Clamped:` line in the CLI. A given
  `start` moved later by the 3,000-period window cut is reported the same
  way.
- Measured 2026-10-17 over a live MCP stdio session and the CLI, on four
  real FRED series (WALCL, WDTGAL, WTREGEN, RRPONTSYD) loaded into an
  isolated store as one capture; illustrative, not findings. The figures
  below were recomputed offline on that stored capture (direct, CLI and MCP
  stdio) after `q_ar1` became the significance rule. Week grid, changes: 24
  of 66 tests significant (26 if periods were independent); the Wednesday
  TGA level against its week average gives r 0.61 at lag 0 and 0.59 at lag
  +1, the averaging window rather than a cause. Levels: Fed total assets
  against either TGA series gives r 0.74 at lag 0 (n 1,244) and p near
  1e-214 if the weeks were independent, but AR(1) effective sample sizes of
  5.2 and 3.3 leave `p_ar1` 0.13 and 0.37: not significant, and `data_gaps`
  says serial correlation dominates. Day grid: the weekly series have no
  adjacent-day changes, so nothing is tested and the response says why.
- With the default 365-day observation retention
  (`WORLD_INTEL_HISTORY_DAYS`), a store filled only by the collector spans
  about a year, so the month grid cannot reach the 20-point floor without a
  longer retention or backfilled history.
- Adds 1 tool.

### Added: history backfill and more history extractors (Phase 29)
- `intel history backfill fred SERIES... [--start YYYY-MM-DD]`,
  `intel history backfill ecb DATASET.KEY... [--start YYYY-MM-DD]` and the
  MCP tool `intel_history_backfill` load the history that FRED's keyless graph CSV
  and the ECB Data Portal (BSI and ILM datasets) already serve into the
  history store. Requests reuse the liquidity tools' fetch and parse code,
  so they go through the Fetcher (FRED rate floor, circuit breaker, cache):
  a copy cached by an earlier call (FRED 1 h, ECB 3 h) is reused without a
  request.
- Backfilled rows have their own sources, `backfill:fred` and
  `backfill:ecb` (series `backfill:fred:<ID>` and
  `backfill:ecb:<DATASET>.<KEY>`), so they never read as collector
  captures; `intel_collection_health` and `intel history health` list them
  apart (`backfills`), and a source whose latest call had any failed
  request reads `error` with that request's reason, whatever order the
  requests were named in. Every run is logged in a new table,
  `history_backfills`, created in place with `CREATE TABLE IF NOT EXISTS`
  (existing rows untouched).
- Dates: `observed_at` is the publisher's period (FRED's date; ECB months
  as written, ECB weeks as the Sunday that ends the ISO week);
  `published_at` is NULL, because neither response names a release or
  vintage date; `collected_at` is the backfill time, stamped after the
  call's last fetch. Values are the publisher's vintage on the backfill
  day, already revised, so revisions made before the first backfill are
  invisible. `--start` keeps values dated on or after it: FRED dates as
  written (a month by its first day), ECB weeks and quarters by the period
  end the store keeps, so the ECB is asked from up to one period earlier
  and the boundary period is cut client-side.
- One capture per request (a FRED id, or an ECB key that may match several
  series). Its saved body is a summary (request, start, full-response
  hash, per-series counts and dates), not the response: the values are in
  the observations, and a replay stays small. An ECB '+' alternative that
  matched no series is named in `data_gaps`.
- Values a re-run no longer finds in the response's date span (withdrawn,
  or now a missing cell) are reported as `absent_from_response` with the
  first and last date; the store keeps them as the earlier backfill read
  them.
- Idempotent: a re-run stores only new or changed values, and a changed
  value is a revision in `intel_revisions`. FRED's missing cells (`.` and
  blank) are skipped and counted, never stored as zero. ECB missing values
  cannot be counted (the SDMX-JSON parser drops them) and read `unknown`.
- Failures are errors, never an empty success: an HTTP error, an empty or
  malformed body, a window without values, and a response available only
  as a stale cache copy each record an error capture and store nothing.
  The CLI exits 1 when any request failed. A store write failure names
  the request it failed on, the requests fetched but not written, and the
  upstream failures after it, written as error captures when the store
  accepts them and listed as not logged when it does not.
- Caps per call: 5 FRED series or 2 ECB keys (at most 20 series per key),
  the newest 20,000 points per series and 100,000 per call; `--start`
  narrows the window. Older values past the series cap cannot be loaded
  by a backfill (there is no end bound); values left out by the call
  budget load in a call of their own.
- Retention: a backfill prunes only backfill rows (sources `backfill:*`
  and its own log), with this process's retention settings; collector rows
  are left to the collector. Observations are pruned by `collected_at`, not
  `observed_at`, so a 1962 value is kept as long as any value stored by the
  same backfill (`WORLD_INTEL_HISTORY_DAYS`, default 365, 0 keeps forever).
  A backfill prunes before it stores, so a pruned value is stored again as
  new. The collector's own prune still covers backfill rows, under the
  collector's settings.
- New history extractors (`history_extractors.py`): `liquidity_board`
  (latest and previous value per indicator; the derived net liquidity row
  is left to its own source), `net_liquidity` (net liquidity and its three
  terms per Wednesday, reverse repo dated by the day it was taken from) and
  `net_migration` (World Bank SM.POP.NETM per country and year). Each
  dates a value only from the payload.
- Measured 2026-10-17, live, isolated HOME: WALCL 1,244 values
  (2002-12-18 to 2026-10-14), RRPONTSYD 3,348 (2,833 blank cells skipped),
  DGS10 16,182 (721 skipped; units unknown, it is not in this server's
  FRED catalog), euro area M3 560 months (1980-01 to 2026-08, 1
  provisional). A second run from the cached copies and a refetch of WALCL
  and M3 stored 0.
- FRED's terms of use speak of personal, non-commercial use of FRED data;
  whether a deployment fits them is the operator's call.
- Adds 1 tool; the `intel history` group gains `backfill fred|ecb`.

### Added: news signals (ROADMAP Phase 29)
- `intel_hostility_timeline`: per UTC day, GDELT DOC 2.0 coverage of a
  country or a pair of countries (`timelinevolraw`): matching articles,
  articles that also use threat / sanction / force / criticism terms (one
  GDELT query per category, every term listed in `queries`), GDELT's total
  monitored articles, and average tone (`timelinetone`, weighted by the
  per-bucket article counts). A failed call, or one only an expired cached
  copy answered, leaves its column null for every day (`column_status`
  per call, `stale_age_seconds` per expired column); a day GDELT did not
  return is null in every column, and a day one series lacks is null in
  that column; all are listed in `data_gaps`. Partial days (GDELT answered
  2026-10-17 in 15-minute buckets for 3 days and hourly buckets for 7) are
  flagged `partial` per volume column (`partial_columns`,
  `coverage_by_column`), and today's unfinished UTC day is flagged
  `in_progress`. Failed and expired columns get one retry pass, which
  stops at the first retry that fails again. Countries resolve from the
  22-country table by name, ISO3 or ISO2 code; other names are searched
  verbatim, and other 2- and 3-letter codes are refused.
- `intel_situations`: country pairs ("between": a headline naming two or
  more countries) and single countries ("inside": a headline naming one)
  ranked over a recent RSS window by most covered, most hostile (headline
  keyword heuristic, `classifier.classify_hostility`) or biggest change.
  Change is defined in the response: current minus prior window, counted
  only over feeds whose retained history reaches back past the prior
  window's start; the feeds that do not are named. With no such feed,
  change fields are null and `change_measured` is false, and a change
  sort ranks by coverage (`sort_applied`); a change figure resting on
  under half of the window's items is named a thin sample.
- `intel_top_stories`: story clusters in the window carried by at least
  `min_outlets` distinct outlets, plus attention: the countries and
  organizations whose headline mentions grew most against the prior window
  (empty with `attention_change_measured: false` when no feed spans both
  windows).
- `intel_news_clusters` clusters gain `outlets` and `outlet_count`
  (distinct publishers among all members; sister feeds such as BBC World
  and BBC Mundo count once). Existing keys are unchanged.
- CLI: `intel hostility COUNTRY [OTHER]`, `intel situations`,
  `intel top-stories`. Nulls render as `n/a`, never 0; partial days are
  marked `*` (and each count from a partial column), today `~`, and
  expired columns are named with their age; unmeasured change and
  attention print as not measured.
- Collector: `situations` and `top_stories` join the `news` group.
- Adds 3 tools.

### Changed: news signals (shared feed requests, GDELT spacing)
- Concurrent `fetch_news_feed` reads of the same feed set share one
  request per feed. The collector starts its four news sources in one
  gather, and each used to request every feed itself; measured live
  2026-10-17, a news-group cycle made 119 feed requests for 119 feeds
  (4 of 4 sources ok, 9.8 s). Each caller still gets its own limit and
  its own item copies, and a caller's timeout does not cancel the read
  the others are waiting on.
- Live GDELT calls are spaced at least 5 s apart by the fetcher
  (`_SOURCE_RATE_LIMITS["gdelt"]`), for every GDELT caller: GDELT's 429
  body asks for "one every 5 seconds" (measured 2026-10-17). Cache hits are
  not delayed. The floor holds across the processes that share one cache
  DB (collector, MCP servers, dashboard, CLI): every request that passes
  the fetcher's GDELT floor also reserves a slot in a `source_floor` table
  under `BEGIN IMMEDIATE` (`shared_floor.py`); a reservation that cannot
  be made is logged and the request keeps the in-process floor. A 429 from
  any source with a floor is retried no sooner than that floor
  (`get_json`; it was 1 s, then 2 s). Processes on different cache DB
  paths still do not coordinate. The AOI sweep makes one GDELT call per
  AOI, so the floor bounds it: against a mocked GDELT, 45 AOIs took 220 s
  of the collector's 240 s `aoi_digest` budget and 50 AOIs timed out
  after 48 calls (measured 2026-10-17, every other AOI domain stubbed).

### Fixed: news signals
- RSS outage read as a slow news day (ROADMAP Phase 24.5):
  `fetch_news_feed` returned `count: 0` with no marker when every feed
  failed. It now reports `feeds_attempted`, `feeds_ok`, `feeds_failed` and
  `feeds_stale` on every call, and `error` / `degraded` /
  `reason: all_feeds_failed` when no feed answered live;
  `intel_news_clusters` and `intel_trending_keywords` pass the marker
  through, so `intel trending` prints an error instead of an empty
  keyword table.
- RSS outage behind a warm cache read as healthy news: a feed whose fetch
  failed came back as its expired cached copy (the fetcher's stale
  fallback, which marks only dict payloads), so in a running deployment
  an outage counted every feed as fine until the expired copies were
  evicted (the collector evicts about hourly; a server running without
  the collector keeps them until `intel sync`). Such feeds are now listed
  in `feeds_stale`, never counted in `feeds_ok`, and kept out of
  situation and attention change figures.
  Verified live 2026-10-17: with an expired copy seeded for DW Europe
  (its feed answers 404), the europe category reported
  `feeds_stale: ["DW Europe"]`.
- Cluster `sources` was always empty: the clusterer read `source_name` /
  `source`, but RSS items name their outlet `feed_name` (measured live
  2026-10-17: 23 of 23 clusters had `sources: []`, which also emptied
  `intel_world_brief` top-story sources).
- RSS `published` times were shifted by the host's UTC offset:
  `_parse_published` read feedparser's UTC struct with `time.mktime`
  (local time) instead of `calendar.timegm`. The struct carries
  `tm_isdst=0`, so the shift is the zone's standard offset: on mac-studio
  (US Eastern) an item published 14:43:52 UTC came out `19:43:52Z`, five
  hours ahead (measured 2026-10-17). The amount depends on the host zone
  (none on a UTC host). It skewed every RSS-based time window and any
  ordering against non-RSS times. The regression test sets its own zone,
  so it fails on the old code on a UTC CI runner too.
- Country dossier news was always empty, with no marker (ROADMAP Phase
  24.5), for three reasons: it asked `fetch_news_feed` for
  `category="all"`, which is not a category (the feed answered with an
  error dict); it read `articles` and `source`, while the feed emits
  `items` and `feed_name`; and it checked only its own `_error`, never the
  feed's `error`. It now reads every feed, passes a feed error or outage
  through as `error` / `degraded` / `reason` with `mention_count: null`
  and a `data_gaps` entry, and names failed or stale feeds. A fourth
  quiet zero: 28 of the 50 accepted country codes (GB, DE, JP and others)
  have no headline keywords, so the search could never match; the section
  now says "mentions not searched" instead of reporting zero.
  `intel dossier` prints `News: not measured` and the gaps in that case.
- Review fixes for the news signals (independent review, 2026-10-17):
  - The hostility timeline showed an expired cached GDELT copy (days old
    when no collector evicts it) as current counts, with no marker. Such a
    column is now null, named in `data_gaps` with its age and in
    `column_status`, and the response is `degraded` with
    `reason: gdelt_stale`.
  - A day with no buckets in the series that judged completeness read as
    complete (`partial: false`), and a category series covering half a day
    sat unflagged next to full-day counts. Partial days are now judged per
    column; a half-day count gets no `hostile_share`.
  - With no comparable feed, situations reported change 0 and ratio 1.0
    ("no change"), and the CLI printed `+0`; attention read as "nothing
    grew". Both are now null or empty and marked not measured.
  - A 429 inside one GDELT call was retried after 1 s and 2 s, and the
    timeline's retry pass asked again for every failed column; see the
    GDELT spacing entry under Changed.
  - Dossier headline matching was a substring test ("Tirana" counted as
    Iran, "Indiana" as India) and hid its cap: it now matches whole words,
    removes four compound names first, and reports `matching_items`,
    `mention_count_capped`, `items_searched` and `searched_span`.
  - A near-total RSS outage (118 of 119 feeds down) read as normal:
    `fetch_news_feed` now marks a read where under half of the feeds
    answered live `degraded` with `reason: partial_feeds_failed`, and
    `intel_trending_keywords` passes the feed counts and marker through;
    situations, top stories and the dossier rank or count over the feeds
    that answered and say so.
  - Clustering ran on the event loop the collector and the MCP server
    share; unknown codes such as "GBR" were sent to GDELT as text; a limit
    of 0 or -1 returned nothing or dropped a result, and `min_articles: 0`
    divided by zero; feed links of any scheme (`javascript:`, `data:`)
    were passed on and titles had no length cap (now http(s) only, titles
    capped at 500 characters).
- Second review fixes for the news signals (2026-10-17):
  - The cross-process GDELT floor honoured a reserved slot up to 600 s
    ahead; the bound is now 40 s (eight processes at 5 s), and a row
    further ahead is treated as a clock jump: overwritten with the current
    time and logged. A row that cannot be read as numbers raised on every
    call; it is now overwritten the same way.
  - A cancelled floor wait left the process's own future slot, and its
    next call ignored it and went first; a process now keeps its own
    queued slot. The slot time is taken once the write lock is held, so a
    wait for the lock never shortens the gap.
  - Dossier headline matching stopped counting demonyms such as "North
    Korean(s)" and "Gazan(s)"; each keyword now also matches with an
    `-n`, `-ns` or `-s` ending, the compound exclusions unchanged.
    `searched_span` was sorted as text, so an unparsed date ("Okt 17,
    2026") read as the newest item; it now spans parsed UTC times only,
    and `items_without_parsed_time` counts the rest.
  - `intel_hostility_timeline` refuses an empty, blank or one-letter
    country (it went out as nine GDELT requests).
  - `intel situations` and `intel top-stories` never printed the
    partial-outage line: the results now carry `feeds_attempted` and
    `feeds_ok` at the top level.

### Fixed: vessel snapshot waterway matching
- `intel_vessel_snapshot` counted every NGA warning at all nine waterways,
  so three naval-keyword warnings anywhere on Earth marked Panama and
  Hormuz critical alike. On the live feed of 2026-10-17 the old code marked
  all nine `critical` from 8 such warnings, none within 300 km of any of
  them. A warning now counts only at waterways within 300 km of a position
  its text states, read from the full text (positions past the
  500-character cut used to be lost). A warning that states no readable
  position counts nowhere: its area code names at least a whole NAVAREA.
  Crediting such warnings to the Panama Canal by NAVAREA IV or XII was
  measured and rejected: on the same capture all 5 of those credits were
  wrong (Hawaii, California, "warnings in force" lists), and on the 3,480
  warnings of 2024 they were 200 of Panama's 203, none naming Panama.
  Naval warnings with no readable position are listed in
  `unplaced_naval_warnings` with a reason (`multi_navarea_series`,
  `navarea_too_broad`, `position_unreadable`, `unknown_area_code`) and
  named in `data_gaps` as `<area code>:<id>`, since one id can name
  warnings in two series. The rule is in `matching_rule`.
- Each waterway emits `total_nearby` (warnings of any topic credited to
  it, which the old code computed and dropped) and `status_as_of`;
  `warning_details` entries carry `match`, `distance_km` and `issue_date`.
- With NGA down every waterway read `clear`. It now reads `unknown`, and
  the response carries `error`, `degraded` and `reason`. With the feed past
  its staleness threshold every waterway reads `stale` (its counts kept,
  dated by `status_as_of`) instead of a current threat level. A feed whose
  currency cannot be checked (`feed_stale` null: no parseable issue date,
  or no active warnings) also reads `unknown`, degraded, with a data gap:
  three undated warnings near Hormuz used to read `critical` with
  `status_as_of` null. The fleet report leaves such a snapshot out of its
  score (a lower bound) and the report prints an UNDATED note.
- Positions are read in degrees-minutes, degrees-minutes-seconds and the
  two mixed, with whitespace, a comma or a slash between latitude and
  longitude; a lone latitude or longitude (a band or a meridian) counts as
  a stated but unreadable position. On the 3,866 warnings captured
  2026-10-17 (386 active, 3,480 from 2024) this loses none of the previous
  parser's 21,780 positions and reads 34 more, in HYDROLANT 2024-473, 479
  and 488.
- A position match no longer starts right after a letter: '20-O3-44N'
  (letter O for zero) used to read as 3.73N, about 1,800 km off; it now
  reads as no position. On 3,643 distinct real warnings (2024 and the
  live captures) this changes no position. A lone latitude or longitude
  still counts as a stated position when a letter precedes it, so a
  mistyped coordinate is unplaced as `position_unreadable`.

### Fixed: navigational warnings
- An NGA outage returned `warnings: []` with no marker, the same shape as a
  sea with no active warnings. It now carries `error`, `degraded`,
  `reason` (`nga_msi_fetch_failed`) and `data_gaps`. A payload with no
  warnings list is `nga_msi_unexpected_payload`; a stale cache serve is
  degraded and says how old the copy is.
- The NGA MSI API holds no warning issued after 10 May 2024 (measured
  2026-10-17: `msgYear=2025` with `status=all` and `msgYear=2026` return
  none, `msgYear=2024` with `status=all` ends on 10 May, and
  `/current-warnings` and `/inforce` list the same 2024 state), yet
  responses read as current. `intel_nav_warnings` now reports
  `newest_issue_date`, `newest_issue_age_days` and `feed_stale`; past
  `stale_after_days` (14, twice the slowest series' longest gap between
  issues in 2024) the response is degraded with the age in `data_gaps`. An
  issue date more than a day ahead is left out of the check and named in
  `data_gaps`: one "MAY 2042" among frozen 2024 warnings used to make the
  feed read current. The vessel snapshot and fleet report pass this on,
  and `intel warnings` prints a STALE line and the data gaps.
- The `navarea` filter compared the value with the API's `navArea` field,
  which only ever holds the codes 4, 12, A, P and C, so the documented
  Roman numerals matched nothing: `navarea="IV"` returned 0 of the 71
  code-4 warnings on the live feed, with no marker. It now takes the codes,
  their series names (`HYDROPAC`) and IV or XII for 4 or 12; a value no
  carried area matches (most NAVAREAs arrive inside the A, P and C series)
  returns `error` and `reason` `navarea_not_carried` with a `data_gaps`
  line naming the series that carry it, never a bare 0. The tool schema
  and the CLI `--navarea` help say the same. The freshness fields describe
  the whole active feed, before the filter, so an area with nothing in
  force on a frozen feed reads stale instead of an undated 0.
- `area_codes` maps the codes the API sends in `navArea` (4, 12, A, P, C;
  never the Roman numerals) to the NAVAREAs, with each code's source in
  `sources/maritime.py`. Code 4 also carries Canadian Arctic (NAVAREA
  XVIII) warnings, so it is not a single NAVAREA.
- NGA answering with no active warnings (an empty list, or only cancelled
  ones) read as a quiet sea: count 0, no marker, every waterway `clear`.
  The live feed held 386 active warnings on 2026-10-17, so the response is
  now degraded with a data gap and `feed_stale` null, and the empty answer
  is reused from the cache for at most 5 minutes instead of an hour.

### Fixed: fleet report and theater posture
- `intel_fleet_report` turned a failed component into `{}`, so with all
  three down it read `LOW_ACTIVITY` with no marker. A component that raises
  or reports an error is now named in `unavailable_components` and
  `data_gaps` and the report is degraded; so is a vessel snapshot whose NGA
  feed is stale, which is no longer scored. With all three unavailable the
  report carries `error` and `reason` (`fleet_components_unavailable`),
  `readiness_level` `UNKNOWN` and `readiness_score` null. With some
  missing, `readiness_lower_bound` is true and `data_gaps` says what the
  score leaves out and how high it can still reach (each component adds at
  most 30 of 90). Component `data_gaps` are passed on.
- `intel_military_flights` with adsb.lol and OpenSky both down returned
  zero aircraft, told apart from an empty sky only by `source: "none"`.
  Those keys stay, and the response now also carries `error`, `degraded`
  and `reason` (`military_flights_unavailable`).
- `intel_theater_posture` turned a theater that no flight source answered
  for (adsb.lol and OpenSky both failed) into zero aircraft, so a full
  outage read as an empty sky, and as `LOW_ACTIVITY` with no error in the
  fleet report. Each theater now names its `source`; unanswered ones are
  listed in `unavailable_theaters` and `data_gaps` and the response is
  degraded, with `error` and `reason` (`military_flights_unavailable`)
  when none answered. Only a complete posture is cached.
  `intel_military_surge` turns a posture error into its own error and
  skips regions whose theater had no source (`unchecked_regions`) instead
  of recording zeros in their baselines.
- On a warm cache those markers were bypassed: when adsb.lol failed, the
  fetcher's expired copy (marked `_stale`) came back as current flights,
  source `adsb.lol`, stamped now, and OpenSky was never tried. Measured
  with a 3-day-old copy and both hosts returning 500: posture cached it as
  complete, surge recorded it into its baselines as today's traffic, and
  the fleet report scored it with no data gap. OpenSky is now tried live
  before any copy is considered, and an expired copy from either source is
  an outage (`error`, `degraded`, `reason`): its aircraft go under
  `stale_copy` with their source, `as_of` and `age_seconds`, never under
  `aircraft`. Posture names such theaters in `stale_theaters` and does not
  cache, surge records nothing for them, and the fleet score is a lower
  bound.
- A malformed `bbox` (not four comma-separated numbers, a latitude outside
  -90..90 or longitude outside -180..180, a minimum not below its maximum)
  returned every military aircraft in the world as the box's, or raised a
  bare `ValueError`. It now returns `error` with `reason` `invalid_bbox`
  without fetching; the tool schema carries a pattern.
- `intel posture` printed 0 for theaters no flight source answered, under
  a total that looked complete, and no data gaps. Those theaters now read
  `unknown`, the total says it covers only the theaters that answered, and
  the gaps are printed.

### Fixed: report maritime section
- The PDF/HTML report read `vessels` and `snapshot` for its maritime
  section, keys the vessel snapshot never emits, so every report said "No
  maritime data". It now shows the nine waterways' statuses, a STALE note
  for a frozen feed, the outage error, and the first data gaps.

### Fixed: dashboard nav-warnings and fleet panels
- The nav-warnings panel read `navArea` and `dtg`, so Area was always '?'
  and Issued blank. It now reads `navarea` and `issue_date`, marks a stale
  NGA feed (`feed_stale`) STALE and a degraded one DEGRADED, still renders
  when the payload has `error`, and lists that error and the payload's
  `data_gaps`.
- The fleet panel was hidden when the report had `error` and showed 0 for
  a missing score. It now shows '?' for a null `readiness_score` and for
  the aircraft or surge count of a component listed in
  `unavailable_components`. When `readiness_lower_bound` is set, the score
  and level get a leading >= and the score is never shown in green; the
  aircraft total gets a leading >= when theaters are unavailable. The panel
  lists the error and `data_gaps`, marks DEGRADED and names the
  unavailable components.
- Warn and crit values in mini boxes are now coloured.

### Tests: navigational warnings and fleet
- Failing-first regression tests built on live NGA records captured
  2026-10-17, and `test_maritime_honesty.py` and `test_fleet_honesty.py`
  for the second review round: each finding test fails on the previous
  branch head and passes now, and five tests kill the mutants that survived
  the first round (radius boundary, malformed DMS, notation order,
  staleness boundary, two components down).
- `test_maritime_honesty_r3.py` for the third round: 44 tests, 26 of which
  fail on the previous head; the other 18 pin parser guards and controls
  that no test held. Each of 26 source mutants (stale-copy handling, bbox
  validation, the CLI posture table, undated and empty feeds, the
  short reuse of an empty answer, both lookbehinds, longitude-only tokens,
  decimal minutes followed by seconds) is killed by this file.

### Still open: navigational warnings and fleet
- The collector cycle summary's `successes` still counts a source that
  answered with an upstream error; it is also listed under
  `upstream_errors`.
- Strategic posture and temporal anomalies still read a posture outage as
  zero activity; posture now marks it, but they do not check.
- A naval warning that cannot be placed leaves every waterway's status
  unchanged; it is named only in `unplaced_naval_warnings` and
  `data_gaps`.
- One malformed coordinate the parser does not anticipate can still raise
  inside the NGA parse loop and fail the whole feed; there is no
  per-record guard.
- For up to 5 minutes after an upgrade a posture cached by the previous
  code can still be served.

### Added: AOI escalation news and convergence components
- `intel_aoi_escalation` now scores the news and convergence components it
  used to report as null (ROADMAP Phase 23).
- News: the change in the area's share of all GDELT coverage, the 7 days
  ending with GDELT's current daily step (still filling;
  `current_step_elapsed` says how far) against the 7 days before, for the
  reverse-geocoded settlement and county at the AOI's centre (the query
  the AOI brief already uses, sent as `timelinevolraw`). Expected articles
  = prior share x current GDELT volume; change_pct = 100 x (current -
  expected) / max(expected, 20); component = min(20, 0.2 x max(0,
  change_pct)). Shares rather than raw counts because GDELT's own intake
  has multi-day outages (measured 2026-10-17 for Pittsburgh: no data for
  16 of 85 days), which raw counts would read as a surge on recovery; a
  comparison where one week monitored under half the other's volume is
  refused as a data gap. An area that cannot be geocoded is not scored,
  rather than searched by the AOI's name. An AOI reaching more than 50 km
  from its centre, or a polygon or corridor whose centre cannot be
  placed, gets a data gap saying the query covers only the centre's place.
- Convergence: `analysis/convergence.py`, unmodified, over the
  earthquakes, military flights, ACLED events and wildfires inside the
  AOI's exact shape (circle, polygon or corridor, through the same
  `filter_by_aoi` scoping as the brief). The 1-degree grid is laid at four
  half-degree offsets and the strongest cell is used, so a cluster
  spanning under half a degree in latitude and in longitude is never
  split on a degree line (one spanning 0.5 to 1 degree still can be).
  With an input failed or partial, a convergent cell is reported as a
  lower bound; no cell at all is null, because quiet cannot be told from
  missing.
- An input that did not answer counts as missing, never as quiet: a USGS
  or FIRMS outage, a military answer from neither adsb.lol nor OpenSky
  (`source: "none"`), and an expired cached copy served in place of a
  fresh answer (USGS, ACLED, GDELT, FIRMS), which is refused with the
  copy's age named in `data_gaps`. A global sample that reached its cap
  (USGS newest 50, ACLED 100 worldwide, FIRMS 20 largest clusters per
  region) counts as partial coverage.
- New response keys; existing keys keep their meaning. `computed_from`
  names the components the score was computed from,
  `zero_filled_components` the ones among them that are a 0 only because
  the military or ACLED fetch failed (`score_hotspot` takes no null for
  those, unchanged), and `lower_bound_components` the ones partial data
  can only have understated. An AOI has no curated baseline, so the score
  tops out at 80; `score_ceiling` is the highest score reachable with the
  components this call measured (a zero-filled one held at 0) and
  `score_method` the formula.
  `news_signal` (query, fetch time, both windows' counts and shares,
  change), `news_scoping` and `convergence_signal` (cells, grid offset,
  events per domain, inputs used, failed or partial, each domain's window
  and fetch time) carry the working. A failed news or convergence input
  makes that component null in `components`, listed in
  `unavailable_components` and explained in `data_gaps`, never a 0.

### Fixed: AOI inputs (earthquakes, wildfires, GDELT, geocoding, brief aviation)
- `fetch_earthquakes` and `fetch_wildfires` mark a failed fetch (`error`,
  `degraded`, `reason`; per region for FIRMS, with `failed_regions` and,
  when other regions answered, `partial_errors`) instead of answering a
  well-formed empty. Their list keys stay, so callers that do not check
  still iterate an empty list.
- `fetch_earthquakes`, `fetch_wildfires` (per region), `fetch_acled_events`
  and `fetch_gdelt_search` keep the fetcher's `_stale` /
  `_stale_age_seconds` marks on an expired cached copy and report
  `fetched_at`, when upstream answered: a cached answer reports its
  original fetch, not the time it was served.
- `fetch_gdelt_search`'s cache key holds a digest of every request
  parameter. The old key reduced a non-Latin query to underscores, so
  "Київ" and "Суми" shared one entry and one AOI was scored on the other's
  timeline.
- `fetch_earthquakes`'s cache key now holds the result limit (ACLED's
  change is under Fixed: tool error reporting and server fixes), so a
  short answer cached for one caller is not served to another as complete.
- The FIRMS docstring states what the request asks for: a day range of 2
  (FIRMS's two most recent days), not the last 24 hours.
- A reverse-geocoding failure no longer repeats its prefix ("Reverse
  geocoding failed: Reverse geocoding unavailable: ...").
- The AOI brief's aviation section reads the `positions` list that the
  domestic-flights source returns. It used to read a `sampled` key the
  source never returns, so every live brief showed 0 aircraft in the
  area. It now counts the sampled aircraft inside the area, and reports
  aviation as a data gap only when the fetch fails or its answer has no
  `positions` list.

### Changed: AOI escalation
- The escalation also fetches earthquakes and wildfires (convergence
  inputs) and one GDELT timeline, in parallel with ACLED and military
  flights; their failures are named in `data_gaps`. The brief, the change
  sweep and the escalation now share one AOI scoping helper, which reads
  an answer without its list (an unrecognized shape) as unknown rather
  than as an empty area, and names a failed FIRMS region next to answered
  ones.
- `intel aoi escalation` prints a zero-filled component as not measured,
  marks lower bounds, and shows the score ceiling and `computed_from`.
- `test_aoi.py` stubs every network-bound source by default: its older
  escalation tests stub only ACLED and military flights and would
  otherwise reach Nominatim, GDELT, USGS and FIRMS live.

### Added: border crossings (flows)
- `intel_us_border_encounters`: U.S. CBP encounters per calendar month
  (Border Patrol Title 8 apprehensions, Field Operations Title 8
  inadmissibles, Title 42 expulsions), read from the newest CSV on CBP's
  public dataset page, which spans four fiscal years (October 2022 to
  August 2026 when written). Nationwide or one land border region, all
  components or USBP / OFO, optionally one citizenship as CBP names it;
  with the latest month against the same month a year earlier, fiscal-year
  totals (the year in progress ends at the file's last month and is
  compared with the same months of the prior year, only when every one is
  published), breakdowns by component,
  encounter type and demographic, and the top citizenships with CBP's
  OTHER bucket reported apart and never ranked. CBP's fiscal months are
  mapped to calendar months (FY2026 October is October 2025).
- `intel_uk_small_boat_arrivals`: Home Office daily and weekly counts of
  migrants and boats detected crossing the English Channel in small boats,
  with uncontrolled landings and the weekly migrants and events prevented
  by French authorities; month and year sums of the daily rows, and the
  year to date against the same calendar dates a year earlier, compared
  only when every day of both spans is in the file (`year_to_date` gives
  `complete`, `days_reported` and `days_in_period`). Read through the
  GOV.UK Content API and the published ODS time series, parsed with the
  standard library (zipfile and the expat streaming parser, no new
  dependency). The publisher's numbered notes are quoted from the file on
  every refresh.
- Both are flows (events per period), stated in every response with units,
  date semantics and the publisher's caveats, and kept apart from the
  UNHCR and World Bank year-end stocks. Neither file has a person
  identifier, so neither counts unique people (said in each response as a
  tool note, not as the publisher's words).
- An outage is a degraded error with no figures; a failed refresh serves
  the last good copy marked `stale` with its age. A '-' in the UK file is
  null, never 0; a CBP month with no rows inside the file's coverage is 0,
  because CBP lists only non-zero cells, and months outside it are never
  invented. Weekly UK totals are checked against their seven days and any
  mismatch is named in `data_gaps`.
- Downloaded files are untrusted input. The ODS reader refuses a DTD,
  reads only the sheets the tool uses (SB_01, SB_02 and Notes), and
  refuses a file past one budget for those sheets together (200,000 rows,
  1,000,000 cells, 4,194,304 characters of text), checked before a repeat
  count is expanded, or past 16 MiB of content.xml, 10,000 levels of
  nesting, 2,000 distinct names or a tag (or text run) longer than 1 MiB;
  a member compressed other than stored or deflated is not opened. A file
  that cannot be read, whatever the parser fault, gives a degraded
  response with a reason (or the last good copy, marked stale), and a
  degraded response names its missing figures in `data_gaps` too. Rows
  and cells that cannot be read outside the columns the tool uses are
  named in `data_gaps` instead of failing the file; a CBP row with bytes
  that are not UTF-8 in a column the tool reads is counted as unreadable.
  A UK row dated before 1 January 2018 (where SB_01 starts) or more than
  seven days after today is left out and named. A cached copy written
  under an older layout or rule is refetched, never served.
- Requests use an identifying User-Agent, two per refresh (the listing,
  then the file), cached 12 h (CBP) and 3 h (UK). Only https links on the
  publishers' own hosts (www.cbp.gov; assets.publishing.service.gov.uk, or
  www.gov.uk under /government/uploads/ since its robots.txt disallows
  other paths), on the standard port, without credentials and with no
  backslash, %5C or empty segment in the path, are requested. CBP's
  robots.txt rule is checked on the path as normalized for the request
  (dot segments removed, escapes of unreserved characters decoded), so
  paths it disallows are never requested; a newer-looking CBP file at such
  a path is named in `data_gaps` instead, as is any encounters link the
  tool cannot read (including names with "_" or a space after
  "nationwide"). No redirect is followed: a 3xx from any of the four
  requests reads as a failed refresh naming its Location (degraded, or the
  last good copy marked stale), never as data. Downloads stop as soon as
  the decoded body passes its cap (CBP page 2 MiB, CBP CSV 32 MiB, GOV.UK
  Content API 2 MiB, Home Office ODS 8 MiB), and the refusal names the cap.
- Frontex is not built: its only data file is an XLSX under `/assets/`,
  which its robots.txt disallows (measured 2026-10-17, see ROADMAP Phase 28).
- Adds 2 tools.

### Added: Kalshi and cross-venue prediction markets
- `intel_kalshi_markets`: Kalshi open markets from its public market-data
  API (no account, no key), ranked by 24h then lifetime volume. Prices are
  YES implied probabilities (bid/ask midpoint when the book is two-sided,
  else the last trade, with the basis named); Kalshi's raw dollar quotes
  are kept. Filter by category (the category's highest-volume series) or
  series ticker. The response names the events it scanned and whether the
  scan was complete: Kalshi lists more than 8,000 open events, furthest
  close date first.
- `intel_prediction_compare`: the same event on Kalshi and Polymarket side
  by side. Matching is deterministic: quantities (with their direction,
  so "more than 25 bps" is not "25 bps"), years, end dates, negation and
  the outcome side must all agree, and each pair carries a
  `match_confidence` and its reasons. Below the threshold (default 0.6) a
  pair is not a match. Returns the price gap per pair, the closest
  rejected pairs with the reason, and unmatched counts per venue.
- `intel_prediction_settled`: recently settled markets on both venues with
  the outcome and the YES price at fixed offsets before close (default 24h
  and 168h) from each venue's price-history endpoint, and a Brier score per
  venue and offset with sample size, distinct events, selection and
  exclusions stated. A venue whose price history cannot be read is not
  scored. The two samples are different markets, and the response says so.
- Every number these three tools take has a stated range in its input
  schema: at most 25 Kalshi series or pages per scan, 2,000 Polymarket
  markets, 500 results, 100 settled markets per venue, and 10 offsets of
  at most 8,760 hours, so one call cannot fan out into an unbounded number
  of upstream requests. The MCP server refuses a value outside its range;
  the source functions clamp counts again for the CLI and other callers,
  and refuse a value that is not a number before any request.
- CLI: `intel kalshi`, `intel prediction-compare`, `intel prediction-settled`.
- Collector: `kalshi_markets` and `prediction_compare` (Economics
  category) join the `prediction` domain. Adds 3 tools.

### Fixed: prediction markets outage read as "no markets"
- `intel_prediction_markets` returned `{"markets": [], "count": 0}` with no
  marker when Polymarket was down, the same shape as a quiet market. It now
  adds `error` and `degraded: true` on an outage or an unexpected response,
  and `stale: true` when the list came from an expired cache entry. Keys,
  parameters and the tool name are unchanged.

### Fixed: prediction-market review findings
- Expired-cache serves after a failed fetch are marked on every Kalshi read
  (open markets, settled listing, candlesticks) and on Polymarket's settled
  listing and price histories: `stale` and `degraded` are set and
  `data_gaps` names the count and the oldest age. A price history served
  from expired cache is excluded from Brier scoring, not scored as current.
- Matching: rate actions (cut, raise or hike, hold or no change) and
  directions (above, below) must agree; a four-digit number after `$` or a
  comparator is an amount, not a year; minus signs and ordinals are kept.
  "U.S." matches "US", "$100m" matches "$100 million", and "4.5% or higher"
  matches "above 4.5%" with a flag that the boundary differs. Candidate
  blocking no longer drops a same-event pair whose words many other titles
  share. `match_confidence` (key unchanged) is documented as an ordinal
  score for ranking pairs, not a probability.
- `intel_prediction_compare`: each side carries its price basis, bid, ask,
  spread and last-trade time (Kalshi's public trades endpoint, for pairs
  priced from a last trade; Gamma publishes none). A pair is flagged,
  ranked after comparable pairs and left out of `comparable_count` when
  either side is not a two-sided quote midpoint (a last trade or Gamma's
  listed outcome price), its spread is wider than 0.10, or the thresholds
  differ at the boundary.
- `intel_prediction_settled`: Polymarket markets are scored against the
  earlier of `endDate` and `closedTime` (`closedTime` comes after
  resolution), and each sample entry names which. The comparability text
  states that reference times differ by venue and that samples differ by
  offset; the CLI prints one Brier table per venue. An offset of 0 or below
  is refused, even next to a valid one, instead of being dropped.
- Kalshi requests wait for the pacing interval only on a cache miss.
  Non-finite or out-of-range prices and non-finite volumes are treated as
  unreadable and counted; identifiers must match each venue's measured
  format before they build a URL or a request; titles are capped at 500
  characters. `intel_prediction_markets` names how many markets it left
  out for an unusable price.

### Fixed: prediction-market re-review findings
- Matching rejects a pair when both titles name different days of the
  same month, no shared month, or different clock times; when a quantity
  differs in unit ($, %, bps) or kind (to a level, by a change) or the
  same numbers come in a different order; on opposite wording (rise or
  fall, positive or negative, before or after); and when a listed name
  (chamber, party, country, a qualifier such as core or cash) or another
  capitalized name appears on one venue only. More negation words
  (won't, fail to), rate verbs (tighten, ease, boost, reduce and their
  forms), number words, dash minus signs, "between" ranges and bps read
  as hundredths of a percent. "Hold" counts as a rate action only in a
  rate question.
- `intel_prediction_compare`: a side priced from an expired copy carries
  `stale` and its age and its pair is flagged and not comparable. The
  Kalshi last-trade lookup reads the trade's price with its time, flags a
  pair whose trade price differs from the listing, skips sides priced from
  an expired listing, stops after 10 lookups or 10 s, and says per side
  what a null time means (`last_trade_lookup`). Matching runs in a worker
  thread. A pair with no price is flagged; Kalshi quotes outside 0 to 1
  are left null and counted.
- `intel_prediction_markets` sets `degraded` with `stale`; `intel
  predictions` prints its data gaps and titles an expired list as such.

## 0.11.0 - 2026-10-12

Cross-border migration (MCP tools, CLI, collector and a dashboard
corridor map), aircraft-cohort early warning, and fixes to the
displacement summary and the dashboard AOI detail panel. Tools 132 -> 139.

### Added: migration
- `intel_migration_flows`: every UNHCR origin -> destination corridor for a
  year (about 6,000 with people in them for 2025: refugees, asylum seekers
  and others in need of international protection), filterable by country
  (ISO-3, ISO-2 or name) or region (UNHCR major areas and UN sub-regions),
  with each corridor's change against the prior year and top origins and
  destinations of the selection.
- `intel_migration_surges`: largest year-over-year increases and decreases
  in people abroad, by origin and by corridor, and in internal displacement,
  with each origin's change as a share of its population (World Bank
  SP.POP.TOTL). Levels mass / major / notable are stated heuristics.
  UNHCR's non-country buckets ("Unknown" origin) are reported separately
  and never ranked.
- `intel_migration_history`: one country's yearly UNHCR series since 1951,
  as an origin or as a host, with its peak year and largest annual waves.
- `intel_net_migration`: World Bank net migration (all reasons, economic
  included) and international migrant stock: latest-year ranking in
  absolute and per-1,000 terms with world regions, a World Bank region
  filter, or one country's series since 1960.

### Added: migration corridor map layer
- The dashboard gains a "Migration Flows" layer and `GET /api/migration`
  (`?limit=` 1-150, default 40; `?year=`): the largest UNHCR origin ->
  destination corridors plus the fastest-rising ones, drawn capital to
  capital with weight by people and colour by year-over-year change.
  Coordinates are the capital-city latitude/longitude of the World Bank
  country list (`wb_countries` now returns `capital`, `latitude`,
  `longitude`); the legend says so. Corridors with no coordinates (UNHCR
  "Unknown" origin, Stateless, West Bank and Gaza) are counted in
  `unplotted` and listed, never dropped. An upstream failure is a 503 with
  `error`, shown as `!` and a red legend line, never an empty map.

### Added: migration in the CLI and collector
- `intel migration-flows`, `intel migration-surges`, `intel migration-history`
  and `intel net-migration` render the four tools as tables, with the same
  error surfacing as every other command. A change with no prior-year
  figure renders "n/a", never "+0".
- The collector gains `migration_surges` and `net_migration` (55 sources)
  and a `migration` domain group (`--sources migration`, which also takes
  `displacement`).

### Fixed: migration surges
- A country whose UNHCR rows were all internal (IDPs, nobody abroad) never
  entered the surge comparison, so its IDP jump was dropped.
- Internal-displacement rows now carry `idps_first_reported` when the prior
  year had no IDP figure. Live 2024 -> 2025 ranked Guatemala (+573,000) and
  Cambodia (+517,555) as IDP surges from a prior figure of 0, which can be
  a first report rather than new displacement; the CLI labels those rows.

### Fixed: displacement summary
- `intel_displacement_summary` never sent UNHCR `coo_all=true`, so UNHCR
  answered with one global row and `by_origin` held a single entry named
  "-" (found by a live call 2026-10-11). It now returns the top 30 origins
  with ISO-3 codes. Names prefer the short TIER1 name ("Syria") so
  `intel_country_signals` can join displacement with the conflict sources;
  that join had no displacement input before.

### Fixed: dashboard detail panels
- Clicking an AOI on the map opened an empty detail panel (label only,
  since 0.10.0): the click called `showDetail`, but the AOI branch lived in
  `showDrawerDetail`, which AOIs never reach. The branch now sits in
  `showDetail`; circle, polygon and corridor AOIs show name, shape,
  centre and last-sweep counts.
- Map clicks on pipelines and trade routes opened the same empty panel.
  Pipelines now go to the pipeline renderer the drawer already used; trade
  routes gain one (type, oil flow, vessel transits, share of global trade,
  ISO-3 countries, notes, all from `config/trade_routes.py`).
- Drawer rows for UCDP events and conflict-zone hotspots showed a raw dump
  of the first 12 keys under a JSON title. UCDP rows now show both sides,
  violence type, deaths (best and low-high), dates, coordinates, headline,
  source and UCDP id; conflict-zone rows use the map's conflict renderer.
- UCDP events on the map's conflict layer opened the ACLED-shaped panel:
  "Conflict Event", 0 fatalities, no dates. They now open the UCDP panel.
- The conflict-zone hotspot fallback (used when ACLED and UCDP both have no
  events) was built only by `/api/overview`, which the page never calls,
  so with no conflict feed the map layer and the drawer's "Active Conflict
  Zones" section stayed empty. `/api/stream` now sends it from the same
  builder once both feeds report, or `null` when one has events.
- `test_dashboard_detail_routing.py` fails if any dispatched type lacks a
  branch in the renderer it reaches, or if UCDP map clicks miss the UCDP
  renderer; `test_dashboard_stream_conflict.py` drives one stream tick.

### Docs
- README's per-tool reference listed 126 of the 135 tools while every
  headline count said 135: the 5 newer AOI tools, `intel_bgp_status`,
  `intel_daily_digest`, and the severe-weather, cyclone, launch and
  volcano tools were missing. All 139 are listed now, and
  `test_readme_documents_every_registered_tool` pins the reference and
  each section's count to the live registry. Collector count 51 -> 53 in
  README; pyproject description; ROADMAP phases 27-28; CLAUDE.md
  dispatch note (no `match/case` since Phase 26) and the UNHCR code trap.

### Data honesty: migration
- UNHCR figures are year-end stocks, not border crossings; every response
  carries a `measure` string saying so. World Bank net migration is
  modelled by the UN World Population Prospects, and its latest years can
  be projections.
- UNHCR's own country codes are not ISO ("AUS" is Austria), so requests
  send `cf_type=ISO` and rows are read through `coo_iso` / `coa_iso`.
- Not included: near-real-time displacement (IOM DTM and HDX HAPI need
  keys), regional border-crossing series, and bilateral economic migration
  flows (only national net totals exist in a keyless API).

### Added: aircraft-cohort early warning
Approach inspired by
[kylemcdonald/ews](https://github.com/kylemcdonald/ews) (independent
implementation; no ews code used).

- `intel_jet_cohort_snapshot`: live airborne snapshot of the business-jet
  cohort (69 ICAO type designators in one adsb.lol `/v2/type` request) or
  the military cohort (`/v2/mil`), with per-type counts and PIA/LADD
  flags. Each call learns cohort membership into a `jet_cohort` table in
  the cache DB. The collector gains `bizjet_cohort` and `military_cohort`
  so the cohort keeps learning 24/7 (collector sources 51 -> 53).
- `intel_jet_activity_anomaly`: peak concurrent airborne cohort aircraft
  in a UTC half-hour, from adsb.lol `globe_history` heatmaps, against the
  same slot on 2-8 prior same-weekday dates; dates within a day of a US
  federal holiday are swapped for earlier weeks. Robust z with a counting
  noise floor; a second z on the cohort's share of all tracked aircraft
  guards against feeder-coverage swings, and the level (1-5) uses the
  smaller. Deficits (z <= -3) are flagged too.
- `intel_jet_excess_origins`: takeoff/landing inference (ground/air
  transitions plus low climbs/descents at coverage edges), density
  clustering of endpoints across the current and baseline windows, and a
  departure/arrival anchor, regional, diffuse or no-excess label, with
  optional distance to a reference point.
- `Fetcher.get_bytes` (binary fetch with rate floor, retries, breaker;
  404 reported distinctly) and an on-disk LRU for heatmaps
  (`WORLD_INTEL_HEATMAP_CACHE_MB`, default 1024).

### Data honesty: aircraft cohort
- Cohort selection bias is gated: only members first seen
  `min_learning_lead_hours` (default 24) before the window count. A fresh
  install answers `warming_up`. A negative lead is allowed for a first
  look but marks the result degraded and suppresses the alert level and
  pattern label (bypassing the gate measured 1,002 vs a 206 baseline
  median on 2026-10-11, i.e. pure selection artefact).
- Missing, unpublished or low-coverage heatmaps are listed in
  `data_gaps`; fewer than 3 usable baseline windows is
  `insufficient_baseline`, never a zero-excess "normal".

### Not ported from ews
- FAA / global registry cohort importers: the FAA ReleasableAircraft.zip
  answers 403 to non-browser clients, and the ADS-B Exchange database and
  `globe_history` are under JETNET terms (robots.txt disallows
  `/globe_history/`), so the cohort is learned from adsb.lol instead.
- Year-long backfill, learned holiday profiles and annual ratios,
  non-ICAO (`~hex`) activity stores, and the paid SMS/email/Telegram
  alerting stack.

## 0.10.0 - 2026-09-02

Geofences become visible and their news becomes geographic: the
dashboard draws every AOI with its last-sweep counts, and AOI news is
searched by the place an area sits in rather than by its name. The
roadmap's last planned item ships here; along the way, every live
GDELT fetch was found to have been silently failing and was fixed.

### Added
- Dashboard AOI layer: a toggleable "AOI Geofences" Leaflet layer draws
  every defined area (circle, polygon, corridor) from the shared store,
  with a tooltip and detail panel showing what the last collector sweep
  counted inside it. Backed by a new `/api/aois` endpoint that reads
  the stored change snapshot and never gathers live, so drawing a shape
  costs nothing upstream. An AOI that has never been swept says so
  (`last_sweep: null`) instead of showing zeros; a broken store is a 503
  with the reason, never an empty map that reads as "no areas defined".
  Verified in headless Chromium: 2 shapes rendered, the 50 km circle at
  50,000 m, no console errors. First endpoint tests for the dashboard
  (Starlette TestClient); a real SQLite thread-affinity error surfaced
  during them and was fixed by opening the store per request.

### Changed
- AOI news is now scoped by where the area IS, not what it is named.
  Every other AOI domain was filtered geometrically; news alone was a
  GDELT search for the AOI's name, so an area called "Home" returned a
  Chinese A-share IPO article and "PGH Square" an Indian op-ed on Gaza
  (both measured live 2026-09-02, both for a fence around Pittsburgh).
  New `sources/geocode.py` reverse-geocodes the AOI centre via OSM
  Nominatim (no key; 1 req/s floor and an identifying User-Agent per
  its usage policy; 30-day cache since places do not move) and the
  brief/changes/digest search GDELT for the settlement and county
  (`("Pittsburgh" OR "Allegheny County")`). The brief reports how news
  was scoped in `news_scoping`; when geocoding is unavailable (geocoder
  down, open ocean) it falls back to the AOI name and says so in
  `data_gaps`, because that is exactly when articles may be unrelated.

### Fixed
- Every live GDELT fetch had been failing and hiding behind stale
  cache. Root cause, measured: api.gdeltproject.org TCP-connects in
  0.03 s but its TLS handshake took 19.7 s, 17.4 s, then >45 s across
  three samples (Nominatim and USGS: 0.05 s on the same network), and
  the Fetcher's 15 s default counts TLS inside the connect phase, so
  every request was a `ConnectTimeout`. Both GDELT call sites (news
  search, company profile) now use a shared 45 s `GDELT_TIMEOUT`;
  live-verified afterwards with 10 real articles for the Pittsburgh
  AOI. Handshakes slower than that still degrade to the existing honest
  `error`/`degraded` shape.
- GDELT DOC API requires OR clauses in parentheses: a bare `"a" OR "b"`
  returns nothing at all (measured live). The news query builder wraps
  multi-term queries; a regression test pins the exact form.
- A failed Nominatim request (e.g. HTTP 429) was reported as "returned
  an unexpected response shape", pointing a reader at parsing when the
  cause was rate limiting. A failed fetch and a genuinely odd payload
  now carry distinct messages.

### Testing
- The AOI test suite had briefly become non-hermetic: the shared
  domain stub did not cover the new geocoder, so ~150 tests were each
  making a live Nominatim request (suite time 0.9 s -> 15.8 s, and a
  real 429 from OSM). The stub now covers it (back to 0.7 s), proven by
  temporarily making any live geocode call raise: only the six tests
  that mock Nominatim themselves touched it.

## 0.9.0 - 2026-09-02

AOI geofences become a continuous watch: the collector daemon sweeps
every defined area on its interval, and a webhook fires when something
enters or leaves.

### Added
- Scheduled AOI sweeps: `aoi_digest` is now a collector source
  (`analysis.aoi.fetch_aoi_sweep`, a fetcher-only wrapper that opens
  the AOI store on the fetcher's own cache database), so
  `intel-collector --daemon` advances every defined geofence's change
  snapshot on each cycle - the daemon interval is the watch cadence,
  and the existing launchd wrapper makes it survive reboots. New `aoi`
  domain group for `--sources aoi`. Digests land in the collector log
  and the vector store, and in the webhook below when configured.
- AOI change notifications: set `WORLD_INTEL_AOI_WEBHOOK` and the
  sweep POSTs every non-quiet digest (something entered or left a
  geofence) to that URL - `json` payload by default
  (title/totals/markdown/timestamp), or raw markdown with a `Title`
  header via `WORLD_INTEL_AOI_WEBHOOK_FORMAT=text` for ntfy-style
  sinks. Quiet sweeps never fire; an unreachable sink or non-2xx
  response never fails the sweep (snapshots already advanced) but is
  recorded honestly in the digest's `notification` field. New
  `Fetcher.post()` carries the delivery - deliberately outside the
  caching/retry/breaker machinery, since the target is the operator's
  own endpoint. Live-verified end-to-end against a local sink: a real
  sweep detected a change and the sink received the JSON payload.
- Per-source collector timeout overrides (`SOURCE_TIMEOUTS`): a live
  smoke caught a single 50 km AOI sweep on a cold cache blowing the
  flat 45 s budget (the digest fans out to ~8 domains per AOI, several
  rate-floored); the sweep now gets 240 s and the override path is
  regression-tested.

## 0.8.0 - 2026-09-01

AOIs become operational (one-call sweeps and a full CLI), and the
domain roster reaches Europe, the West Pacific, and the routing table.

### Added
- `intel_aoi_digest` (+1 tool): the change sweep across every defined
  AOI (or a named subset) in one call - per-AOI new/departed items,
  counts, data_gaps, and a combined markdown digest. Each AOI's
  snapshot advances, so a scheduler can call this one tool on an
  interval to learn what entered or left all watched areas. No AOIs is
  a note; unknown requested names are an error; one AOI's failed
  domain stays in that AOI's data_gaps.
- `intel aoi` CLI command group: define, define-polygon,
  define-corridor, list, update, delete, brief, escalation, changes -
  full parity with the MCP tools, sharing the server's store semantics
  (same cache-resolved SQLite file) and the 0.6.0 error and
  markup-safety conventions. Live-smoked through the real entry point.
- `intel_meteoalarm_alerts` (+1): Meteoalarm (EUMETNET) severe-weather
  warnings for 39 European countries. Live verification found there is
  NO Europe-wide feed (per-country only; calling without a country
  returns the roster) and that awareness color lives only in the
  warning title, so the module derives it and says so.
- `intel_jtwc_cyclones` (+1): JTWC warnings for the NW Pacific, North
  Indian Ocean, and Southern Hemisphere, complementing NHC
  (`intel_cyclones`). Storm positions/intensities are in the linked
  warning products, not the feed; the module links rather than
  pretends. A live run caught and fixed a wrong basin guid before
  release.
- `intel_bgp_status` (+1 = 132): per-resource BGP health from RIPEstat
  - RIS visibility, announced space, observed origins, per-origin RPKI
  validation. Deliberately scoped as a health check, not global hijack
  detection: RIPEstat has no target-free incident feed, and the tool
  description says exactly that. A polite 1s rate floor was added for
  the ripestat source.

### Not added, honestly
- FAA NOTAMs: the official API returns 401 without a key and the
  unofficial search backend is POST-only and undocumented; no genuine
  key-free machine-readable path was found (verified live 2026-09-01).
  Tracked in ROADMAP as blocked-on-upstream rather than faked.

## 0.7.0 - 2026-09-01

The monolith splits. No behavior changes.

### Changed
- server.py (2,890 lines: a 128-entry Tool list plus an 800-line
  match/case) is now a 158-line shell over 12 domain modules in
  `world_intel_mcp/tools/` (markets, hazards, conflict,
  infrastructure, society, intelligence, geospatial, synthesis,
  finance, vector, aoi, system), with shared infrastructure (cache,
  circuit breaker, AOI store, vector store, fetcher) in
  `world_intel_mcp/runtime.py`. Each module exports TOOLS and
  HANDLERS; `tools.aggregate()` refuses to import a registry whose
  tools and handlers disagree or collide, so the drift the old
  text-scan parity test could only catch in CI now prevents the
  server from starting at all.
- Pure move, verified three ways: an AST comparison of every
  name/description/inputSchema against the pre-split registry
  (127/127 byte-equal), the full suite (814 passed, 90.8% coverage),
  and a live MCP stdio session (initialize, tools/list returning all
  128, and a real tools/call round-trip).
- Registry/registration tests upgraded from text-scans of server.py
  to import-based assertions against the aggregated registry,
  including a falsifiability test proving `aggregate()` rejects
  drift and collisions.

## 0.6.0 - 2026-09-01

The CLI stops lying about outages, and the new domains join the 24/7
collector.

### Fixed
- 33 CLI commands rendered an upstream `{"error": ...}` as a healthy
  empty state ("0 earthquakes" over an empty table during a USGS
  outage, error text discarded) - the fail-reads-as-success class at
  the CLI layer. One shared bail-on-error path now prints the
  upstream error prominently in table mode and passes the raw dict
  through unchanged in --json-output mode. Partial degradation
  renders data plus a visible warning (climate names its unavailable
  zones); a displacement outage prints the error instead of "Grand
  total: 0". 43 tests failed against the old behavior; 114 pass now.
- Rich markup no longer swallows lowercase bracketed values or lets
  remote feed titles inject markup: news categories, sanctions entity
  types, ai-watch sources, and gh-trending languages render again;
  the `intel report` fallback hint prints its `[pdf]` extra verbatim;
  a feed title containing "[/]" renders literally instead of crashing
  the command with a MarkupError. Escaping is per-site; the CLI's own
  color styling is untouched.
- Remote data inside Rich TABLE cells is injection-safe too: cell
  values from upstream APIs render via rich.text.Text (literal text,
  column styling preserved), with interpolated values escaped where a
  cell deliberately keeps markup. 11 injection tests cover both the
  swallow and the crash mode; static-config columns are documented as
  deliberately unwrapped.
- The two coexisting error styles are unified: the 17 commands that
  dumped raw JSON on error in table mode now use the same red Error:
  line as everyone else, and --json-output passes the raw dict
  through on all 53 commands (intel report previously ignored the
  flag entirely).

### Added
- The four 0.5.0 domains (weather alerts, launch schedule, volcano
  activity, cyclones) joined the collector's 24/7 vector-store
  roster: 46 -> 50 sources, with the roster-count invariant test,
  domain groups, and vector-store category mappings updated together.

### Credits
- Richard Barron (@RichardBarron27, Red Specter Security Research)
  for the external security report (#21) that prompted the
  SECURITY.md threat model and the cache-permissions hardening
  shipped in 0.4.0.

## 0.5.0 - 2026-09-01

Geofences in any shape, four new hazard domains, precise entity
matching, and the last coverage zeros gone.

### Added
- **Polygon AOIs** — `intel_aoi_define_polygon` (+1 tool): a named area
  bounded by 3-64 [lat, lon] vertices, for shapes a radius cannot
  express (a border region, a strait, an EEZ). Every intel_aoi_* tool
  scopes to the exact polygon: an event inside the bounding circle but
  outside the polygon is excluded. Polygons may cross the antimeridian.
  Point infrastructure matches the exact shape; line features
  (pipelines, cables) match the bounding circle, disclosed in
  `data_gaps` rather than silently approximated.
- **Corridor AOIs** — `intel_aoi_define_corridor` (+1 tool): a route of
  waypoints plus a width in km (a shipping lane, a supply road, a cable
  run), built on the great-circle segment distance from 0.4.0.
  Distances in results are measured to the route, not to a center.
  Existing AOI databases migrate in place; old rows read as circles.
- **Four hazard/space domains** (+4 tools = 128), each verified against
  its live API before mocking: `intel_weather_alerts` (NWS CAP, US
  only, honest null coordinates for zone-based alerts),
  `intel_launch_schedule` (Launch Library 2, hour-long cache for the
  free tier), `intel_volcano_activity` (Smithsonian GVP weekly
  report), `intel_cyclones` (NHC active storms - Atlantic/E-C Pacific
  basins only; zero storms is a quiet tropics, not an outage).
- CLI and collector test waves: `cli.py` 0% -> 92% (76 tests driving
  all 52 reachable commands through CliRunner), `collector.py`
  20% -> 97% (run loop, daemon cycle, source-filter resolution). The
  last of the coverage zeros from the 0.4.0 audit.

### Fixed
- Entity extraction no longer substring-matches: "usa" inside
  "thousand" tagged the United States, "hamas" inside "Bahamas",
  "trump" inside "trumpet", "meta" inside "metadata". Countries,
  leaders, organizations, and companies now use the same precompiled
  word-boundary alternation the APT-group matcher always had (with a
  plural allowance for country demonyms). Verified faster per call on
  headline-size inputs.
- Event classification keywords are boundary-anchored stems:
  "launched" still classifies space, but "strike" inside "airstrike"
  no longer adds a social-unrest category and severity bump, "ied"
  inside "denied" no longer fires, "coup" inside "couple" no longer
  fires. A benign sentence that previously triggered four categories
  at severity 7 now classifies as nothing.

### Known issues (pinned by tests, fix planned)
- ~30 CLI commands render an upstream `{"error": ...}` as a
  healthy-looking empty state ("0 earthquakes" on an outage), and
  lowercase bracketed values in Rich output are swallowed as markup
  (the `intel report` fallback hint prints a pip command missing its
  `[pdf]` extra). Both are documented by deliberately-pinning tests
  in `test_cli.py` and tracked in ROADMAP Phase 24.5.

## 0.4.0 - 2026-09-01

Geofences that survive the dateline, notice change, a test suite that
reaches the layers the old one never imported, and outages that say so
instead of reading as good news.

### Added
- `intel_aoi_changes` (+1 tool): geofence change detection — what
  entered or left a user-defined AOI since the last sweep, per domain
  (earthquakes, military flights, ACLED conflict events, wildfire
  clusters, news mentions), built on the same scoped gather as
  `intel_aoi_brief` so the two tools can never disagree about what is
  inside the fence. The first sweep is an explicit `baseline`; a
  domain whose fetch failed goes to `data_gaps`, is excluded from the
  diff (a failed fetch must never read as "everything left the
  area"), and keeps its last real observation for the next successful
  sweep. Sampled aviation is excluded by design: diffing a 1-in-10
  global sample would manufacture fake enter/leave events every run.
- `intel_aoi_update` (+1 tool = 122): rename and/or re-center/resize
  an AOI in place with define-grade validation and collision checks.
  A rename migrates the AOI's change-detection snapshot; a geometry
  change drops it, because the old baseline described a different
  piece of the planet.
- `SECURITY.md`: explicit threat model (prompted by the external
  report in issue #21) — what the trust boundaries are, what
  hardening exists inside them (parameterized SQL throughout, no
  shell/eval/exec, server-generated report paths), and what is out of
  scope for a single-user local OSINT tool.
- Test waves for the previously unexecuted layers: the `analysis/`
  NLP modules (classifier, entities, convergence, spikes, clustering,
  signals, focal points, surge, and more) and the low-coverage
  `sources/` modules (intelligence, cyber, climate, displacement,
  fleet, prediction, service_status, maritime, military parsing) had
  0-30% statement coverage; measured overall coverage was 59% before
  this release despite a green 309-test suite. At release: 597
  non-smoke tests, 81% statement coverage.
- CI coverage ratchet: `--cov-fail-under=80` on the test job
  (measured 81% on 2026-09-01; floor set one point under for platform
  variance). The floor only moves up.

### Fixed
- Antimeridian AOIs: the bounding box derived from an AOI's radius was
  clamped at lon ±180, so a Bering Strait or Fiji geofence silently
  lost everything on the far side of the dateline in the OpenSky
  military-flight path and could report a false "no FIRMS coverage"
  wildfire gap. Circles crossing the dateline now produce two boxes;
  military fetches run per box and merge (icao24 dedup); a one-box
  failure is reported as `partial coverage` in `data_gaps` instead of
  passing half-coverage off as full.
- Pipelines and undersea cables are matched as line features:
  great-circle segment distance (cross-track with endpoint clamping)
  replaces endpoint-only / landing-point-only proximity, so a
  pipeline or cable whose midspan passes through the AOI is detected
  even when its endpoints are hundreds of km away.
- `intel_world_brief` top stories always reported `article_count: 0`:
  the brief read `article_count` from news clusters, but
  `fetch_news_clusters` emits the member count as `size` (the
  silent-zero class again; found by the new analysis-layer tests).
  Reads `size` now, with `article_count` as fallback, plus a
  regression test in the real emitted shape.
- `intel_fleet_report` per-waterway warning counts were always 0: the
  report read `warning_count` but `fetch_vessel_snapshot` emits
  `naval_warnings` (same silent-zero class, also found by the new
  tests). Reads `naval_warnings` now, with `warning_count` fallback,
  plus a regression test in the real emitted shape.
- Cache database files are created with owner-only permissions
  (0600); the `-wal`/`-shm` sidecars inherit the mode (issue #21).
- `__version__` no longer drifts from `pyproject.toml` (it had been
  stuck at 0.1.0 since the first release): it now derives from the
  installed package metadata at runtime.
- A UNHCR outage no longer reads as zero refugees worldwide:
  `intel_displacement_summary`'s failure shape carries `error`,
  `degraded`, and `reason: unhcr_fetch_failed` instead of bare zeroed
  totals (#22).
- Climate zones whose fetch failed are named in `unavailable_zones`
  (with `degraded: true`) instead of silently vanishing; a full
  Open-Meteo outage is an `error` with a reason, and an invalid zone
  filter now says so and lists the valid keys (#23).
- "Resolved: Major outage" post-mortems no longer count as active
  critical incidents (resolution status outranks incident keywords),
  and a provider whose status feed is unreachable is named in
  `unavailable_providers` instead of masquerading as healthy with no
  incidents (#24).

## 0.3.0 - 2026-08-16

Briefs that show their work, and areas you define yourself.

### Added
- User-defined areas of interest (AOIs/geofences): `intel_aoi_define`,
  `intel_aoi_list`, `intel_aoi_delete`, `intel_aoi_brief`, and
  `intel_aoi_escalation` (+5 = 119 tools). Before this, only
  `intel_signal_convergence` accepted a real point-plus-radius,
  `intel_military_flights` took a bbox, and hotspot escalation scoring was
  restricted to the 22 hardcoded `INTEL_HOTSPOTS`. `intel_aoi_define`
  persists a named point-radius area (validated: lat -90..90, lon
  -180..180, radius_km 1..2000) in a dedicated `aois` table inside the
  existing SQLite cache database, rejecting a duplicate (case-insensitive)
  name by echoing the existing definition back instead of overwriting it.
  `intel_aoi_brief` composes a cited view of earthquakes, military flights
  (bbox derived from the radius), wildfires (region-mapped, since NASA
  FIRMS has no point+radius query), ACLED conflict events, sampled
  aviation traffic, nearby static infrastructure (bases, ports, pipelines,
  nuclear facilities, undersea cables, datacenters, spaceports) with
  distances in km, and news headline mentions of the AOI name, all
  filtered to the AOI's radius, with `data_gaps` naming every domain that
  couldn't be geographically scoped. `intel_aoi_escalation` reuses the
  existing `score_hotspot` scoring engine unmodified, scoped to the AOI's
  own radius rather than the fixed 2-degree window used for the 22
  built-in hotspots (#16).
- Situation briefs now cite their sources. `fetch_situation_brief` builds a
  numbered `sources` list while walking the overview data: domain, a short
  description or headline, a URL when the upstream item carries one, and a
  timestamp when available, covering every metric that contributes to the
  brief. The Ollama prompt is instructed to cite claims inline as `[n]`
  using only that list; the structured fallback brief cites mechanically,
  since it is assembled per-metric. The response gains `sources` and
  `cited`: `cited` is true only when the returned text actually contains a
  `[n]` matching a real source number, so a brief where the model ignored
  the citation instruction (or invented an out-of-range number) is
  distinguishable from one that genuinely cited its sources. A metric with
  no traceable upstream item is reported without a citation rather than
  pointing at something that isn't really there (#15).
- `intel_daily_digest`: a cited markdown morning brief composing top
  current events by domain, recent headlines, and, when the optional
  vector store is installed, recent activity trends and a 24-hour
  timeline. Every listed item carries a source reference. When the vector
  store isn't available, the Trends and Timeline sections say so via
  `data_gaps` instead of rendering as an empty, falsely-quiet section
  (#15).
- `intel_situation_brief` (+1 = 120 tools). The cited situation brief
  (#15) was previously reachable only through the dashboard's SSE
  overview; MCP clients, the primary consumer this server exists for,
  couldn't call it at all. The new tool gathers a bounded server-side
  overview (earthquakes, military flights, ACLED conflict events,
  wildfires, cyber threats, disease outbreaks, news, space weather,
  strategic posture, and the alert digest, not the dashboard's full
  47-source fan-out), then delegates to the existing, unmodified
  `fetch_situation_brief` for the AI-generated brief or its
  mechanically-cited fallback when Ollama is unreachable (#18).

### Fixed
- `_extract_metrics` (situation brief) read the earthquake event list under
  the key `events`, but `fetch_earthquakes` returns it under `earthquakes`,
  so the lookup always missed and `max_magnitude` was silently 0 in every
  brief ever generated. Found while wiring earthquake citations off the
  same field.
- Test counts in the docs lagged the 0.2.0 regression tests (claimed 244
  total when 0.2.0 itself shipped 256). Corrected to the live count.
- `fetch_gdelt_search` returned a clean zero-article payload when the
  GDELT API call failed, byte-identical to a genuine zero-hit search:
  same class as the ACLED defect fixed in 0.2.0 (#3). Observed live as a
  429: GDELT asks for one request per 5 seconds. Failure paths now carry
  `error`, `degraded`, and `reason` keys, keeping `articles`/`count` in
  their normal empty shape; `intel_aoi_brief`'s news domain now surfaces
  the failure as a `data_gap` instead of reading as "no news mentions"
  (#17).

## 0.2.0 - 2026-08-16

The honesty release. A full review of the data paths found five ways the
server could present missing or stale data as fresh and real. All five are
fixed, each with a regression test that fails against the old code.

### Fixed
- ACLED-backed tools returned a clean zero-event payload when the API call
  failed, indistinguishable from genuine peace. Failure paths now carry
  `error`, `degraded`, and `reason` keys, and the eight downstream
  conflict/instability tools report `data_gaps` (#3).
- The documented `_stale=True` marker on cached fallback responses never
  actually existed. It does now, along with `_stale_age_seconds`; non-dict
  stale serves are counted in `CircuitBreaker.status()` (#4).
- `intel_gas_prices` restamped days-old cached prices with a fresh
  `fetched_at`. The timestamp now reflects the cached row's real age, and
  the fallback branch is reachable on real outages, which it previously
  was not (#5).
- `intel_hotspot_escalation` hardcoded its news and convergence components
  to zero for every hotspot, so an active war zone could score the lowest
  severity tier. Unmeasured components now report `null` and the score
  renormalizes over what was actually measured. The tool description no
  longer claims signals it cannot compute (#6).
- The circuit breaker stopped enforcing backoff after its first cooldown
  cycle: a failed half-open probe never re-timestamped the trip. Confirmed
  by repro, then fixed (#7).

### Added
- Continuous integration: the test suite (238 passing at this release, 18 live-network
  smoke tests deselected) now runs on every push and pull request, Python
  3.11 and 3.12 (#11).
- CONTRIBUTING.md, bug report and feature request templates (#12).
- This changelog (#14).

### Changed
- The collector launchd plist ships as a template; `collector-daemon.sh`
  resolves the repository root at runtime instead of hardcoding the
  maintainer's machine paths, and gained a `render` subcommand (#8).
- The situation brief's Ollama default is `localhost`, matching the rest
  of the codebase; `OLLAMA_API_URL` and `OLLAMA_MODEL` are documented (#9).
- README counts corrected against live code, all of them undercounts:
  226 passing tests (was "186"), 15 central banks (was "8"), 119 RSS feeds
  (was "80+"), 47 SSE sources (was "35+") (#10).
- `requirements.txt` removed; `pyproject.toml` is the single source of
  dependency truth (#13).

### Response-shape notes for MCP clients
All changes are additive (new keys only), with one exception: inside
`intel_hotspot_escalation`, each hotspot's `components` dict now reports
`social_unrest` and `convergence` as separate entries instead of the
combined `social_convergence`. Top-level shapes are unchanged.

## 0.1.0 - 2026-06-04

Everything before versioning began: 113 tools across 30+ domains built in
eighteen phases, from market data and SEC filings through conflict
tracking, military flights, climate, cyber, news, vector search over
accumulated intelligence, and a live Leaflet dashboard with SSE streaming.
The phase-by-phase history lives in ROADMAP.md.
