# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

World Intelligence MCP Server — 106 tools across 30+ domains providing real-time global intelligence from free public APIs. Serves four interfaces: MCP stdio (for Claude Code/Cursor), a live Starlette dashboard with SSE, a Click CLI with Rich output, and a collector daemon for 24/7 vector store population. Python 3.11+, built with hatchling.

## Commands

```bash
# Install
pip install -e ".[dev,dashboard]"

# Run MCP server (stdio mode)
world-intel-mcp

# Run tests (pytest-asyncio, auto mode)
pytest
pytest --cov=world_intel_mcp
pytest src/world_intel_mcp/tests/test_sources.py::test_fetch_market_quotes -v  # single test

# CLI
intel markets                    # stock indices
intel earthquakes --min-mag 5.0  # USGS quakes
intel status                     # cache + circuit breaker health

# Dashboard (requires [dashboard] extra)
intel-dashboard --port 8501
# Or with .env auto-loaded:
./run-dashboard.sh
```

## Architecture

Three consumers share the same source modules and infrastructure stack:

```
server.py (MCP stdio)  ─┐                                              ┌─ VectorStore (Qdrant)
cli.py (Click CLI)      ├─> sources/*.py ─> Fetcher ─> CircuitBreaker ─┤
dashboard/app.py (SSE)  ─┘    analysis/*.py                            └─ Cache (SQLite)
collector.py (daemon)  ──┘
```

**Infrastructure layer** (`fetcher.py`, `cache.py`, `circuit_breaker.py`):
- `Fetcher`: Centralized async HTTP client (httpx). All external calls go through `get_json()`, `get_text()`, or `get_xml()`. Handles retries (2 max), per-source rate limiting, and stale-data fallback (never returns blank if old data exists).
- `CircuitBreaker`: Per-source tracking. 3 consecutive failures trips the breaker for 5 minutes. Each RSS feed gets its own breaker (`rss:bbc_world`).
- `Cache`: SQLite WAL-mode TTL cache. `get()` returns live data, `get_stale()` returns expired data for fallback.

**Source modules** (`sources/*.py`): Each module exports `async def fetch_*(fetcher: Fetcher, **kwargs) -> dict`. Pure data fetching — no MCP awareness. 30 modules covering markets, seismology, military, cyber, health, tech, environmental, etc.

**Analysis modules** (`analysis/*.py`): Cross-domain intelligence that consumes outputs from multiple sources. Includes signal aggregation, instability indexing, NLP (entity extraction, classification, clustering, spike detection via Welford's algorithm), and strategic synthesis.

**Static config** (`config/*.py`): Curated datasets — 22 intel hotspots, 70+ military bases, 40 ports, 24 pipelines, 24 nuclear facilities, 34 undersea cables, 48 AI datacenters, 27 spaceports, 27 mineral deposits, 82 stock exchanges, 105 major cities, 28 world leaders, 36 APT groups.

**Vector store** (`vector_store.py`): Optional Qdrant + FastEmbed (BAAI/bge-small-en-v1.5, 384-dim ONNX). Async background worker queue (`asyncio.Queue` + `asyncio.to_thread()`) for non-blocking storage. Fetcher auto-stores on fresh HTTP fetches. 65+ source name → category mappings for filtered search.

**Collector** (`collector.py`): Standalone daemon for 24/7 vector store population. 43 sources organized by domain, with `--daemon`, `--interval`, `--sources` CLI args. Dynamic import via `_import_fetch_fn()`. Entry point: `intel-collector`.

**Dashboard** (`dashboard/`): Self-contained Starlette app with a single `index.html` template (no frontend build step). SSE endpoint streams all domains in parallel via `asyncio.gather()`, refreshes every 30 seconds. Loads `.env` from project root on startup.

## Adding a New Tool

1. Create `sources/your_source.py` with `async def fetch_your_data(fetcher: Fetcher, **kwargs) -> dict`
2. Use `fetcher.get_json(url, source="your-source", cache_key=..., cache_ttl=300)` — this gives you caching, retries, circuit breaking, and rate limiting automatically
3. In `server.py`: import the module, add a `Tool(...)` to the `TOOLS` list, add a `case` to `_dispatch()`
4. Optionally add to `dashboard/app.py` (SSE endpoint) and `cli.py` (Click command)
5. Add tests using `respx` to mock HTTP (see `tests/test_sources.py` for pattern)

## Key Patterns

- **Source name string**: The `source` parameter in `fetcher.get_json()` identifies the API for circuit breaking and rate limiting. Must match entries in `_SOURCE_RATE_LIMITS` if rate-limited (e.g., `"yahoo-finance"`, `"coingecko"`, `"adsblol"`).
- **Tool dispatch**: `server.py` uses Python `match/case` to route tool names to source functions. Tool names follow `intel_*` convention.
- **All source functions take `fetcher` as first arg** — never construct your own httpx client.
- **Tests strip proxy env vars** automatically via `conftest.py` fixture (prevents SOCKS proxy interference). The conftest also resets global fetcher rate-limit locks between tests to avoid cross-event-loop binding.

## Environment Variables

Only these unlock additional data sources (everything else works unauthenticated):
- `ACLED_ACCESS_TOKEN` — conflict events
- `NASA_FIRMS_API_KEY` — satellite wildfire data
- `EIA_API_KEY` — energy prices
- `CLOUDFLARE_API_TOKEN` — internet outage data
- `FRED_API_KEY` — macro economic data
- `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET` — military flight fallback

## Testing

Tests use `respx` to mock httpx responses. Fixtures in `conftest.py` provide `cache` (tmp_path SQLite) and `fetcher` (with clean breaker). Tests are async (`pytest-asyncio` in auto mode). Proxy env vars are stripped automatically.
