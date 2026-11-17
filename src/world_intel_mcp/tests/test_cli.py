"""Tests for cli.py — every user-facing command via click.testing.CliRunner.

Fetch functions are faked at their module boundaries (the test_aoi.py /
test_world_brief.py pattern), so no network happens; assertions check that
rendered Rich output contains values derived from the fakes and that CLI
options reach the fetch functions with the right names.

Two former cli.py bug classes are now covered by honest-contract tests
(they were pinned here as characterization tests until fixed):

1. Error surfacing: every data command — the ``report`` command
   included — bails via ``cli._bail_on_error``, so an upstream
   {"error": ...} prints one consistent red ``Error:`` line in table
   mode instead of rendering as a healthy-looking empty table ("0
   earthquakes") or dumping raw JSON at a table-mode user. In
   --json-output mode the raw dict (error included) is printed
   unchanged with no extra rendering. An outage must never be
   shape-identical to a quiet world. See the *_error_dict tests and the
   parametrized test_error_dict_reaches_table_output sweep, which now
   covers the 17 commands that used to dump raw JSON in table mode.

2. Rich markup escaping: values interpolated into ``[...]`` label
   constructs (news category, sanctions entity_type, ai-watch source,
   gh-trending language) and remote free text (titles, descriptions,
   feed names, the report command's literal ``[pdf]`` install hint) are
   escaped with rich.markup.escape, and remote values rendered inside
   Rich Table cells go through ``cli._cell`` (rich.text.Text), so
   bracketed sequences inside remote data render literally instead of
   being swallowed as markup tags or raising MarkupError. See the
   *_label_renders tests, test_report_error_with_fallback_hint,
   test_news_bracketed_remote_title_survives, and the "Markup injection
   via table cells" section.
"""

import pytest
from click.testing import CliRunner

import world_intel_mcp.analysis.dossier as dossier_analysis
import world_intel_mcp.reports as reports_mod
import world_intel_mcp.sources.traffic as traffic_src
import world_intel_mcp.sources.webcams as webcams_src
from world_intel_mcp import cli


@pytest.fixture(autouse=True)
def _cli_isolation(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the lazily-built Fetcher's Cache at a tmp SQLite file, widen
    Rich's non-tty console so table cells don't truncate, and reset the
    module-global fetcher so each test builds a fresh one."""
    monkeypatch.setenv("WORLD_INTEL_CACHE_DB", str(tmp_path / "cli-cache.db"))
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(cli, "_fetcher", None)
    monkeypatch.setattr(cli, "_aoi_store", None, raising=False)


def _invoke(*args: str):
    return CliRunner().invoke(cli.main, list(args), catch_exceptions=False)


def _fake(payload, calls: list | None = None):
    """Async fake fetch fn; records call kwargs when given a list."""

    async def _f(*args, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        return payload

    return _f


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_command_registry() -> None:
    names = set(cli.main.commands)
    assert {
        "markets",
        "crypto",
        "macro",
        "energy",
        "gas-prices",
        "natgas",
        "electricity",
        "fred",
        "earthquakes",
        "fires",
        "conflicts",
        "flights",
        "posture",
        "outages",
        "cables",
        "warnings",
        "climate",
        "news",
        "trending",
        "gdelt",
        "hostility",
        "situations",
        "top-stories",
        "predictions",
        "displacement",
        "migration-flows",
        "migration-surges",
        "migration-history",
        "net-migration",
        "delays",
        "threats",
        "brief",
        "dossier",
        "risk",
        "instability",
        "btc",
        "central-banks",
        "shipping",
        "social",
        "disease",
        "elections",
        "nuclear",
        "space",
        "sanctions",
        "ai-watch",
        "fleet",
        "hn",
        "gh-trending",
        "arxiv",
        "spending",
        "bases",
        "exchanges",
        "traffic",
        "incidents",
        "air-traffic",
        "status",
        "sync",
        "dashboard",
        "report",
        "aoi",
        "news-reaction",
        "history",
        "guide",
        "liquidity",
        "net-liquidity",
        "money-supply",
        "fed-liquidity",
        "ecb-series",
        "kalshi",
        "prediction-compare",
        "prediction-settled",
    } <= names
    # webcams_cmd has no explicit name=, but click >= 8.1 strips the
    # `_cmd` suffix when deriving default command names, so the
    # user-facing name still comes out right.
    assert "webcams" in names
    assert len(names) == 72


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------

_QUOTES = {
    "quotes": [
        {"symbol": "TSTX", "price": 1234.5, "change_pct": 2.34, "currency": "USD"},
        {"symbol": "DOWN", "price": 99.5, "change_pct": -1.2, "currency": "EUR"},
    ]
}


def test_markets_renders_quotes_and_passes_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    monkeypatch.setattr(cli.markets, "fetch_market_quotes", _fake(_QUOTES, calls))
    result = _invoke("markets", "-s", "AAA", "-s", "BBB")
    assert result.exit_code == 0
    assert calls == [{"symbols": ["AAA", "BBB"]}]
    assert "TSTX" in result.output
    assert "1,234.50" in result.output
    assert "+2.34%" in result.output
    assert "-1.20%" in result.output
    assert "USD" in result.output


def test_markets_no_symbols_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(cli.markets, "fetch_market_quotes", _fake(_QUOTES, calls))
    assert _invoke("markets").exit_code == 0
    assert calls == [{"symbols": None}]


def test_markets_empty_prints_no_data_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.markets, "fetch_market_quotes", _fake({"quotes": []}))
    result = _invoke("markets")
    assert result.exit_code == 0
    assert "No market data available" in result.output


def test_markets_json_flag_prints_raw_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.markets, "fetch_market_quotes", _fake(_QUOTES))
    result = _invoke("--json-output", "markets")
    assert result.exit_code == 0
    assert '"TSTX"' in result.output
    assert '"change_pct"' in result.output


def test_markets_error_dict_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    # An upstream failure must print the error text, not the
    # healthy-looking empty state.
    monkeypatch.setattr(
        cli.markets, "fetch_market_quotes", _fake({"error": "yahoo down"})
    )
    result = _invoke("markets")
    assert result.exit_code == 0
    assert "yahoo down" in result.output
    assert "No market data available" not in result.output


def test_markets_error_dict_json_mode_passes_raw_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --json-output stays machine-honest: the raw dict, error included,
    # with no separate error rendering.
    monkeypatch.setattr(
        cli.markets, "fetch_market_quotes", _fake({"error": "yahoo down"})
    )
    result = _invoke("--json-output", "markets")
    assert result.exit_code == 0
    assert '"error"' in result.output
    assert '"yahoo down"' in result.output
    assert "Error:" not in result.output


def test_crypto_renders_and_passes_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    payload = {
        "coins": [
            {
                "symbol": "btc",
                "current_price": 65_000.0,
                "price_change_percentage_24h": 3.5,
                "market_cap": 1_280_000_000,
            }
        ]
    }
    monkeypatch.setattr(cli.markets, "fetch_crypto_quotes", _fake(payload, calls))
    result = _invoke("crypto", "--limit", "5")
    assert result.exit_code == 0
    assert calls == [{"limit": 5}]
    assert "Top 5 Cryptocurrencies" in result.output
    assert "BTC" in result.output
    assert "$65,000.00" in result.output
    assert "+3.50%" in result.output
    assert "$1,280,000,000" in result.output


def test_macro_renders_dict_none_and_scalar_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "signals": {
            "vix": {"value": 18.2, "classification": "calm"},
            "dxy": None,
            "spread": 4.2,
        }
    }
    monkeypatch.setattr(cli.markets, "fetch_macro_signals", _fake(payload))
    result = _invoke("macro")
    assert result.exit_code == 0
    assert "18.2" in result.output
    assert "calm" in result.output
    assert "unavailable" in result.output  # None signal
    assert "4.2" in result.output  # bare scalar signal


def test_btc_technicals_values_and_na_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "price": 64_250.5,
        "sma_50": 61_000.0,
        "sma_200": None,
        "mayer_multiple": None,
        "cross_signal": "golden_cross",
        "ath_distance_pct": -12.5,
        "change_7d_pct": 4.2,
        "change_30d_pct": None,
    }
    monkeypatch.setattr(cli.markets, "fetch_btc_technicals", _fake(payload))
    result = _invoke("btc")
    assert result.exit_code == 0
    assert "$64,250.50" in result.output
    assert "$61,000.00" in result.output
    assert "golden_cross" in result.output
    assert "-12.5%" in result.output
    assert "+4.20%" in result.output
    assert "N/A" in result.output  # sma_200 / mayer / 30d all None


def test_btc_error_dict_prints_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.markets, "fetch_btc_technicals", _fake({"error": "coingecko down"})
    )
    result = _invoke("btc")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "coingecko down" in result.output
    assert '"error"' not in result.output  # no raw JSON dump at a table-mode user


# ---------------------------------------------------------------------------
# Economic
# ---------------------------------------------------------------------------


def test_energy_renders_oil_and_gas(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "oil": {
            "brent": {"price": 82.5, "date": "2026-08-29"},
            "wti": {"price": 78.1, "date": "2026-08-29"},
        },
        "natural_gas": {"price": 2.9, "date": "2026-08-29"},
    }
    monkeypatch.setattr(cli.economic, "fetch_energy_prices", _fake(payload))
    result = _invoke("energy")
    assert result.exit_code == 0
    assert "Brent Crude" in result.output
    assert "$82.5" in result.output
    assert "$2.9" in result.output


def test_energy_error_dict_prints_error_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli.economic, "fetch_energy_prices", _fake({"error": "EIA_API_KEY missing"})
    )
    result = _invoke("energy")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "EIA_API_KEY missing" in result.output
    assert '"error"' not in result.output


def test_gas_prices_renders_changes_and_em_dash_for_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "prices": {
            "regular": {
                "price_per_gallon": 3.199,
                "change_pct": 0.5,
                "week_ago_pct": -1.2,
            },
            "diesel": {
                "price_per_gallon": 3.899,
                "change_pct": None,
                "week_ago_pct": None,
            },
        }
    }
    monkeypatch.setattr(cli.economic, "fetch_gas_prices", _fake(payload))
    result = _invoke("gas-prices")
    assert result.exit_code == 0
    assert "$3.199" in result.output
    assert "+0.50%" in result.output
    assert "-1.20%" in result.output
    assert "$3.899" in result.output
    assert "—" in result.output  # None change renders as em dash


def test_natgas_renders_period_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"prices": [{"period": "2026-06", "price": 14.23}]}
    monkeypatch.setattr(cli.economic, "fetch_residential_natgas_prices", _fake(payload))
    result = _invoke("natgas")
    assert result.exit_code == 0
    assert "2026-06" in result.output
    assert "$14.23" in result.output


def test_electricity_passes_state_and_renders_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "state": "CA",
        "rates": {"residential": {"price_cents_kwh": 16.44, "period": "2026-05"}},
    }
    monkeypatch.setattr(cli.economic, "fetch_electricity_rates", _fake(payload, calls))
    result = _invoke("electricity", "--state", "CA")
    assert result.exit_code == 0
    assert calls == [{"state": "CA"}]
    assert "Electricity Rates — CA" in result.output
    assert "Residential" in result.output
    assert "16.44" in result.output


def test_fred_passes_series_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    # Single-word title: the Rich table sizes to its (narrow) content and
    # wraps longer titles across lines, which would defeat substring asserts.
    payload = {
        "title": "Jobless",
        "observations": [{"date": "2026-07-01", "value": "4.2"}],
    }
    monkeypatch.setattr(cli.economic, "fetch_fred_series", _fake(payload, calls))
    result = _invoke("fred", "UNRATE", "--limit", "5")
    assert result.exit_code == 0
    assert calls == [{"series_id": "UNRATE", "limit": 5}]
    assert "FRED: Jobless" in result.output
    assert "2026-07-01" in result.output
    assert "4.2" in result.output


def test_fred_error_dict_prints_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.economic, "fetch_fred_series", _fake({"error": "series not found"})
    )
    result = _invoke("fred", "NOPE")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "series not found" in result.output
    assert '"error"' not in result.output


def test_central_banks_renders_rates_and_fred_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 2,
        "fred_available": True,
        "rates": [
            {
                "bank": "Federal Reserve",
                "country": "US",
                "rate": 4.25,
                "as_of": "2026-08-01",
            },
            {"bank": "TCMB", "country": "TR", "rate": 42.0, "as_of": "2026-08-01"},
        ],
    }
    monkeypatch.setattr(cli, "fetch_central_bank_rates", _fake(payload))
    result = _invoke("central-banks")
    assert result.exit_code == 0
    assert "2 Central Banks" in result.output
    assert "FRED" in result.output
    assert "Federal Reserve" in result.output
    assert "4.25" in result.output
    assert "42.00" in result.output


# ---------------------------------------------------------------------------
# Natural
# ---------------------------------------------------------------------------


def test_earthquakes_passes_options_and_renders_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "count": 2,
        "earthquakes": [
            {
                "magnitude": 6.1,
                "place": "Off Honshu",
                "depth_km": 10.0,
                "time": "2026-08-31T12:00:00.000Z",
                "alert_level": "red",
            },
            {
                "magnitude": 4.6,
                "place": "Nevada",
                "depth_km": 5.2,
                "time": "2026-08-31T13:00:00.000Z",
                "alert_level": None,
            },
        ],
    }
    monkeypatch.setattr(cli.seismology, "fetch_earthquakes", _fake(payload, calls))
    result = _invoke("earthquakes", "--min-mag", "5.0", "--hours", "48")
    assert result.exit_code == 0
    assert calls == [{"min_magnitude": 5.0, "hours": 48}]
    assert "2 earthquakes" in result.output
    assert "M5.0+ in last 48h" in result.output
    assert "6.1" in result.output
    assert "Off Honshu" in result.output
    assert "2026-08-31T12:00:00" in result.output  # time truncated to 19 chars
    assert "red" in result.output
    assert "Nevada" in result.output


def test_earthquakes_error_dict_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    # A USGS failure must print the error text — never "0 earthquakes"
    # over an empty table, indistinguishable from a genuinely quiet day.
    monkeypatch.setattr(
        cli.seismology, "fetch_earthquakes", _fake({"error": "USGS unreachable"})
    )
    result = _invoke("earthquakes")
    assert result.exit_code == 0
    assert "USGS unreachable" in result.output
    assert "0 earthquakes" not in result.output


def test_fires_renders_regions_and_skips_zero_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "total_fires": 12,
        "fires_by_region": {
            "north_america": {
                "count": 12,
                "top_clusters": [
                    {"lat": 39.1, "lon": -120.3, "fire_count": 8, "max_frp": 250.0}
                ],
            },
            "europe": {"count": 0},
        },
    }
    monkeypatch.setattr(cli.wildfire, "fetch_wildfires", _fake(payload, calls))
    result = _invoke("fires", "-r", "north_america")
    assert result.exit_code == 0
    assert calls == [{"region": "north_america"}]
    assert "12 high-confidence fires detected" in result.output
    assert "(39.1, -120.3)" in result.output
    assert "8 fires" in result.output
    assert "FRP max 250" in result.output
    assert "europe" not in result.output  # zero-count regions skipped


def test_fires_error_dict_prints_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.wildfire, "fetch_wildfires", _fake({"error": "FIRMS key missing"})
    )
    result = _invoke("fires")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "FIRMS key missing" in result.output
    assert '"error"' not in result.output


def test_climate_renders_anomalies_and_sig_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "zones": {
            "arctic": {
                "name": "Arctic",
                "temp_anomaly_c": 4.2,
                "precip_anomaly_pct": -10.0,
            },
            "sahel": {
                "name": "Sahel",
                "temp_anomaly_c": 0.5,
                "precip_anomaly_pct": 25.0,
            },
        },
        "significant_anomalies": ["arctic"],
    }
    monkeypatch.setattr(cli.climate, "fetch_climate_anomalies", _fake(payload))
    result = _invoke("climate")
    assert result.exit_code == 0
    assert "Arctic" in result.output
    assert "+4.2C" in result.output
    assert "-10%" in result.output
    assert "SIG" in result.output
    assert "Sahel" in result.output
    assert "+0.5C" in result.output


def test_climate_degraded_partial_renders_data_and_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Partial degradation (some zones failed, no top-level "error") must
    # render the usable zones AND a visible warning naming the failed
    # ones — not bail, and not silently show a shrunken table.
    payload = {
        "zones": {
            "arctic": {
                "name": "Arctic",
                "temp_anomaly_c": 4.2,
                "precip_anomaly_pct": -10.0,
            },
        },
        "significant_anomalies": [],
        "unavailable_zones": ["sahel", "amazon"],
        "degraded": True,
    }
    monkeypatch.setattr(cli.climate, "fetch_climate_anomalies", _fake(payload))
    result = _invoke("climate")
    assert result.exit_code == 0
    assert "Arctic" in result.output
    assert "Warning" in result.output
    assert "sahel, amazon" in result.output


# ---------------------------------------------------------------------------
# Conflict / Military
# ---------------------------------------------------------------------------


def test_conflicts_passes_options_and_renders_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "count": 1,
        "events": [
            {
                "event_date": "2026-08-30",
                "event_type": "Battles",
                "country": "Ukraine",
                "location": "Kharkiv",
                "fatalities": 12,
            }
        ],
    }
    monkeypatch.setattr(cli.conflict, "fetch_acled_events", _fake(payload, calls))
    result = _invoke("conflicts", "-c", "Ukraine", "-d", "30")
    assert result.exit_code == 0
    assert calls == [{"country": "Ukraine", "days": 30}]
    assert "1 conflict events" in result.output
    assert "(last 30d)" in result.output
    assert "Battles" in result.output
    assert "Kharkiv" in result.output
    assert "12" in result.output


def test_conflicts_error_dict_prints_error_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli.conflict, "fetch_acled_events", _fake({"error": "ACLED token missing"})
    )
    result = _invoke("conflicts")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "ACLED token missing" in result.output
    assert '"error"' not in result.output


def test_flights_passes_bbox_and_renders_aircraft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "count": 1,
        "aircraft": [
            {
                "callsign": "RCH123",
                "icao24": "ae1234",
                "origin_country": "United States",
                "altitude_m": 10_000,
                "velocity_ms": 250.0,
            }
        ],
    }
    monkeypatch.setattr(cli.military, "fetch_military_flights", _fake(payload, calls))
    result = _invoke("flights", "-b", "1,2,3,4")
    assert result.exit_code == 0
    assert calls == [{"bbox": "1,2,3,4"}]
    assert "1 military aircraft detected" in result.output
    assert "RCH123" in result.output
    assert "ae1234" in result.output
    assert "10,000" in result.output


def test_posture_renders_theaters(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "total_military_aircraft": 25,
        "theaters": {
            "eastern_europe": {
                "count": 22,
                "countries": ["United States", "Poland"],
                "sample_callsigns": ["RCH1", "LAGR2"],
            }
        },
    }
    monkeypatch.setattr(cli.military, "fetch_theater_posture", _fake(payload))
    result = _invoke("posture")
    assert result.exit_code == 0
    assert "25 total military aircraft" in result.output
    assert "Eastern Europe" in result.output
    assert "22" in result.output
    assert "United States, Poland" in result.output
    assert "RCH1, LAGR2" in result.output


def test_nuclear_passes_hours_and_renders_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "total_flagged_events": 1,
        "critical_flags": 0,
        "sites": [
            {"name": "Punggye-ri", "events": [{"m": 4.1}]},
            {"name": "Lop Nur", "events": []},
        ],
    }
    monkeypatch.setattr(cli.nuclear, "fetch_nuclear_monitor", _fake(payload, calls))
    result = _invoke("nuclear", "--hours", "48")
    assert result.exit_code == 0
    assert calls == [{"hours": 48}]
    assert "1 flagged events" in result.output
    assert "in last 48h" in result.output
    assert "Punggye-ri: 1 events" in result.output
    assert "Lop Nur: 0 events" in result.output


# ---------------------------------------------------------------------------
# Infrastructure / Maritime
# ---------------------------------------------------------------------------


def test_outages_renders_ongoing(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "ongoing_count": 2,
        "total_7d": 5,
        "outages": [
            {
                "start": "2026-08-31T05:00",
                "is_ongoing": True,
                "countries": ["Sudan"],
                "description": "Nationwide internet blackout",
            }
        ],
    }
    monkeypatch.setattr(cli.infrastructure, "fetch_internet_outages", _fake(payload))
    result = _invoke("outages")
    assert result.exit_code == 0
    assert "2 ongoing outages" in result.output
    assert "5 in last 7 days" in result.output
    assert "Sudan" in result.output
    assert "Nationwide internet blackout" in result.output
    assert "ONGOING" in result.output


def test_cables_maps_status_scores_to_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "corridors": {
            "red_sea": {
                "status_score": 2,
                "cables": ["AAE-1", "SEACOM"],
                "relevant_warnings": [1, 2],
            }
        }
    }
    monkeypatch.setattr(cli.infrastructure, "fetch_cable_health", _fake(payload))
    result = _invoke("cables")
    assert result.exit_code == 0
    assert "Red Sea" in result.output
    assert "At Risk" in result.output  # score 2 label
    assert "AAE-1, SEACOM" in result.output


def test_warnings_passes_navarea_and_renders_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "count": 3,
        "by_navarea": {"IV": 2, "XII": 1},
        "warnings": [
            {"navarea": "IV", "id": "NAV 0417", "text": "GUNNERY EXERCISES IN AREA"}
        ],
    }
    monkeypatch.setattr(cli.maritime, "fetch_nav_warnings", _fake(payload, calls))
    result = _invoke("warnings", "-n", "IV")
    assert result.exit_code == 0
    assert calls == [{"navarea": "IV"}]
    assert "3 active warnings" in result.output
    assert "IV:2" in result.output
    assert "XII:1" in result.output
    assert "NAV 0417" in result.output
    assert "GUNNERY EXERCISES" in result.output


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


def test_news_passes_options_and_category_label_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "count": 1,
        "categories_fetched": ["security"],
        "items": [
            {
                "category": "geopolitics",
                "title": "Summit convened on maritime security",
                "feed_name": "BBC World",
                "published": "2026-08-31T10:00:00Z",
            }
        ],
    }
    monkeypatch.setattr(cli.news, "fetch_news_feed", _fake(payload, calls))
    result = _invoke("news", "-c", "security", "--limit", "5")
    assert result.exit_code == 0
    assert calls == [{"category": "security", "limit": 5}]
    assert "1 items" in result.output
    assert "Summit convened on maritime security" in result.output
    assert "BBC World" in result.output
    assert "2026-08-31T10:00" in result.output
    # The per-item category label must render literally; before the
    # escape fix Rich parsed "[geopolitics]" as an unknown lowercase
    # markup tag and silently dropped it.
    assert "[geopolitics]" in result.output


def test_news_bracketed_remote_title_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Remote data is a markup-injection surface: "[/]" inside a feed
    # title is a Rich closing tag that used to unbalance the [bold]
    # wrapper and raise MarkupError, crashing the command. Escaped, the
    # title must render verbatim and the command must exit 0.
    payload = {
        "count": 1,
        "categories_fetched": ["security"],
        "items": [
            {
                "category": "security",
                "title": "Ceasefire [/] holds in region",
                "feed_name": "Feed [with] brackets",
                "published": "2026-08-31T10:00:00Z",
            }
        ],
    }
    monkeypatch.setattr(cli.news, "fetch_news_feed", _fake(payload))
    result = _invoke("news")
    assert result.exit_code == 0
    assert "Ceasefire [/] holds in region" in result.output
    assert "Feed [with] brackets" in result.output


def test_news_rejects_invalid_category() -> None:
    result = _invoke("news", "-c", "bogus")
    assert result.exit_code == 2
    assert "Invalid value" in result.stderr
    assert "bogus" in result.stderr


def test_news_empty_prints_no_items_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.news, "fetch_news_feed", _fake({"count": 0, "items": []}))
    result = _invoke("news")
    assert result.exit_code == 0
    assert "No news items available" in result.output


def test_trending_passes_min_count_and_renders_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "total_items_analyzed": 200,
        "keywords": [{"word": "ceasefire", "count": 14}],
    }
    monkeypatch.setattr(cli.news, "fetch_trending_keywords", _fake(payload, calls))
    result = _invoke("trending", "-m", "5")
    assert result.exit_code == 0
    assert calls == [{"min_count": 5}]
    assert "200 items" in result.output
    assert "ceasefire" in result.output
    assert "14" in result.output


def test_gdelt_artlist_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    payload = {"articles": [{"title": "Protests spread", "domain": "example.com"}]}
    monkeypatch.setattr(cli.news, "fetch_gdelt_search", _fake(payload, calls))
    result = _invoke("gdelt", "protest")
    assert result.exit_code == 0
    assert calls == [{"query": "protest", "mode": "artlist", "limit": 20}]
    assert "1 articles" in result.output
    assert "'protest'" in result.output
    assert "Protests spread" in result.output
    assert "(example.com)" in result.output


def test_gdelt_timelinevol_mode_prints_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"timeline": [{"date": "2026-08-31", "value": 42}]}
    monkeypatch.setattr(cli.news, "fetch_gdelt_search", _fake(payload))
    result = _invoke("gdelt", "protest", "-m", "timelinevol")
    assert result.exit_code == 0
    assert "Timeline volume for 'protest'" in result.output
    assert "2026-08-31" in result.output


# ---------------------------------------------------------------------------
# Prediction / Displacement / Aviation / Cyber
# ---------------------------------------------------------------------------


def test_predictions_renders_probability_and_sentiment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "markets": [
            {
                "question": "Will X happen by year end",
                "yes_probability": 0.62,
                "sentiment": "likely_yes",
                "volume_24h": 1_500_000,
            }
        ]
    }
    monkeypatch.setattr(
        cli.prediction, "fetch_prediction_markets", _fake(payload, calls)
    )
    result = _invoke("predictions", "--limit", "10")
    assert result.exit_code == 0
    assert calls == [{"limit": 10}]
    assert "Will X happen by year end" in result.output
    assert "62%" in result.output
    assert "likely_yes" in result.output
    assert "$1,500,000" in result.output


def test_displacement_passes_year_and_renders_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "year": 2025,
        "global_totals": {"grand_total": 120_000_000},
        "by_origin": [
            {
                "country": "Syria",
                "total_displaced": 13_000_000,
                "refugees": 6_500_000,
                "internally_displaced": 6_500_000,
            }
        ],
    }
    monkeypatch.setattr(
        cli.displacement, "fetch_displacement_summary", _fake(payload, calls)
    )
    result = _invoke("displacement", "-y", "2025")
    assert result.exit_code == 0
    assert calls == [{"year": 2025}]
    assert "Global Displacement (2025)" in result.output
    assert "120,000,000" in result.output
    assert "Syria" in result.output
    assert "13,000,000" in result.output


def test_displacement_outage_shape_bails_not_zero_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # UNHCR's honest outage shape carries "error" alongside a zeroed
    # structure. The CLI must surface the error, never render
    # "Grand total: 0" as if there were zero displaced persons worldwide.
    payload = {
        "error": "UNHCR API unavailable (no live or cached data)",
        "degraded": True,
        "reason": "unhcr_fetch_failed",
        "by_origin": [],
        "global_totals": {"grand_total": 0},
        "year": 2025,
        "count": 0,
    }
    monkeypatch.setattr(cli.displacement, "fetch_displacement_summary", _fake(payload))
    result = _invoke("displacement")
    assert result.exit_code == 0
    assert "UNHCR API unavailable" in result.output
    assert "Grand total: 0" not in result.output


def test_migration_flows_passes_filters_and_renders_corridors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "year": 2025,
        "origin_filter": {"kind": "country", "name": "Sudan"},
        "destination_filter": None,
        "total_people": 1_334_595,
        "corridor_count": 1,
        "corridors": [
            {"origin": "Sudan", "destination": "Chad", "people": 1_334_595, "change": 222_134},
        ],
    }
    monkeypatch.setattr(cli.migration, "fetch_migration_flows", _fake(payload, calls))
    result = _invoke("migration-flows", "-o", "SDN", "-y", "2025", "-n", "5", "--min-people", "1000")
    assert result.exit_code == 0
    assert calls == [{"year": 2025, "origin": "SDN", "destination": None, "limit": 5, "min_people": 1000}]
    assert "Displacement corridors (2025) from Sudan" in result.output
    assert "Chad" in result.output
    assert "1,334,595" in result.output
    assert "+222,134" in result.output


def test_migration_flows_unknown_prior_year_is_not_zero_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # change=None means UNHCR had no prior year to compare; rendering "+0"
    # would claim a measured standstill.
    payload = {"year": 2025, "total_people": 10, "corridor_count": 1,
               "corridors": [{"origin": "A", "destination": "B", "people": 10, "change": None}]}
    monkeypatch.setattr(cli.migration, "fetch_migration_flows", _fake(payload))
    result = _invoke("migration-flows")
    assert "n/a" in result.output
    assert "+0" not in result.output


def test_migration_surges_renders_levels_flags_and_unranked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "year": 2025, "compared_with": 2024, "min_change": 100_000,
        "origin_outflow_increases": [
            {"origin": "Sudan", "people_abroad": 3_761_034, "change_abroad": 984_126,
             "change_abroad_pct_of_population": 1.9, "level": "mass"},
        ],
        "origin_outflow_decreases": [
            {"origin": "Afghanistan", "people_abroad": 3_972_525, "change_abroad": -2_178_793,
             "change_abroad_pct_of_population": -4.97, "level": None},
        ],
        "internal_displacement_increases": [
            {"origin": "Guatemala", "idps": 573_000, "change_idps": 573_000, "idps_first_reported": True},
        ],
        "corridor_increases": [
            {"origin": "Sudan", "destination": "Libya", "people": 639_166, "change": 383_518},
        ],
        "unattributed_origin_changes": [{"origin": "Unknown", "change_abroad": 1_548_961}],
        "levels": {"basis": "heuristic thresholds of this tool"},
    }
    monkeypatch.setattr(cli.migration, "fetch_migration_surges", _fake(payload, calls))
    result = _invoke("migration-surges", "--min-change", "100000", "-n", "3")
    assert result.exit_code == 0
    assert calls == [{"year": None, "min_change": 100_000, "limit": 3}]
    assert "2024 -> 2025" in result.output
    assert "+984,126" in result.output and "mass" in result.output
    assert "-2,178,793" in result.output
    assert "none reported prior year" in result.output
    assert "Libya" in result.output
    assert "Not ranked: Unknown" in result.output


def test_migration_history_passes_role_and_renders_waves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "country": "Syrian Arab Rep.", "role": "origin", "meaning": "people FROM this country",
        "years": 4, "first_year": 2011,
        "latest": {"year": 2014, "people": 3_887_000, "idps": 7_600_000},
        "peak": {"year": 2014, "people": 3_887_000},
        "largest_waves": [{"year": 2013, "people": 2_400_000, "increase": 1_671_000, "pct_change": 229.2}],
    }
    monkeypatch.setattr(cli.migration, "fetch_migration_history", _fake(payload, calls))
    result = _invoke("migration-history", "Syria", "--from", "2011", "--to", "2014")
    assert result.exit_code == 0
    assert calls == [{"country": "Syria", "role": "origin", "year_from": 2011, "year_to": 2014}]
    assert "7,600,000 IDPs" in result.output
    assert "Peak 2014: 3,887,000" in result.output
    assert "+1,671,000" in result.output
    assert "+229.2%" in result.output


def test_net_migration_ranking_and_country_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    ranking = {
        "region_filter": None,
        "top_net_immigration": [{"name": "Germany", "year": 2024, "net_migration": 700_000, "per_1000": 8.4}],
        "top_net_emigration": [{"name": "Chad", "year": 2024, "net_migration": -120_000, "per_1000": None}],
    }
    monkeypatch.setattr(cli.migration, "fetch_net_migration", _fake(ranking, calls))
    result = _invoke("net-migration", "-n", "5")
    assert result.exit_code == 0
    assert calls == [{"country": None, "region": None, "limit": 5}]
    assert "Germany" in result.output and "+700,000" in result.output and "+8.40" in result.output
    assert "-120,000" in result.output

    series = {
        "country": "Germany", "region": "Europe & Central Asia",
        "latest": {"year": 2024, "net_migration": 700_000, "per_1000": 8.4},
        "largest_net_inflow_years": [{"year": 2015, "net_migration": 1_175_000, "per_1000": 14.33}],
        "largest_net_outflow_years": [],
    }
    monkeypatch.setattr(cli.migration, "fetch_net_migration", _fake(series))
    result = _invoke("net-migration", "-c", "DEU")
    assert result.exit_code == 0
    assert "Net migration: Germany" in result.output
    assert "+1,175,000" in result.output and "+14.33" in result.output


def test_delays_all_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"delayed_count": 0, "total_checked": 30, "delayed": []}
    monkeypatch.setattr(cli.aviation, "fetch_airport_delays", _fake(payload))
    result = _invoke("delays")
    assert result.exit_code == 0
    assert "No major airport delays!" in result.output


def test_delays_renders_delayed_airports(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "delayed_count": 1,
        "total_checked": 30,
        "delayed": [
            {
                "code": "EWR",
                "name": "Newark Liberty",
                "status": [
                    {"type": "Ground Delay", "reason": "weather", "avg_delay": "45 min"}
                ],
            }
        ],
    }
    monkeypatch.setattr(cli.aviation, "fetch_airport_delays", _fake(payload))
    result = _invoke("delays")
    assert result.exit_code == 0
    assert "1 airports with delays" in result.output
    assert "EWR" in result.output
    assert "Newark Liberty" in result.output
    assert "Ground Delay - weather (45 min)" in result.output


def test_threats_renders_severity_summary_and_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 5,
        "feeds_successful": 3,
        "feeds_attempted": 4,
        "by_severity": {"critical": 1, "high": 2, "medium": 1, "low": 1},
        "threats": [
            {
                "severity": "critical",
                "type": "ip",
                "indicator": "203.0.113.7",
                "threat": "botnet C2",
                "source_feed": "feodo",
            }
        ],
    }
    monkeypatch.setattr(cli.cyber, "fetch_cyber_threats", _fake(payload))
    result = _invoke("threats")
    assert result.exit_code == 0
    assert "5 threats" in result.output
    assert "3/4 feeds" in result.output
    assert "Critical: 1" in result.output
    assert "203.0.113.7" in result.output
    assert "botnet C2" in result.output
    assert "feodo" in result.output


# ---------------------------------------------------------------------------
# Intelligence
# ---------------------------------------------------------------------------


def test_brief_data_only_tag_and_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    payload = {
        "llm_available": False,
        "brief": "Country brief text here.",
        "data": {"gdp": [1, 2], "recent_events": 3},
    }
    monkeypatch.setattr(cli.intelligence, "fetch_country_brief", _fake(payload, calls))
    result = _invoke("brief", "DE")
    assert result.exit_code == 0
    assert calls == [{"country_code": "DE"}]
    assert "Intelligence Brief: DE" in result.output
    assert "data-only" in result.output
    assert "Country brief text here." in result.output
    assert "GDP data points: 2" in result.output
    assert "Recent conflict events: 3" in result.output


def test_risk_renders_country_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "countries": [
            {
                "country": "Sudan",
                "events_30d": 300,
                "risk_score": 88.0,
                "risk_level": "critical",
            }
        ]
    }
    monkeypatch.setattr(cli.intelligence, "fetch_risk_scores", _fake(payload))
    result = _invoke("risk")
    assert result.exit_code == 0
    assert "Sudan" in result.output
    assert "300" in result.output
    assert "88" in result.output
    assert "critical" in result.output


def test_instability_single_country_renders_component_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "instability_index": 72,
        "risk_level": "high",
        "components": {"conflict_intensity": 18.5},
    }
    monkeypatch.setattr(cli.intelligence, "fetch_instability_index", _fake(payload))
    result = _invoke("instability", "UKR")
    assert result.exit_code == 0
    assert "UKR Instability Index: 72/100 (high)" in result.output
    assert "conflict_intensity" in result.output
    assert "18.5/20" in result.output
    assert "█" in result.output


def test_instability_all_countries_renders_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "countries": [
            {
                "country_name": "Sudan",
                "country_code": "SDN",
                "instability_index": 81,
                "events_30d": 240,
                "risk_level": "critical",
            }
        ]
    }
    monkeypatch.setattr(cli.intelligence, "fetch_instability_index", _fake(payload))
    result = _invoke("instability")
    assert result.exit_code == 0
    assert "Sudan (SDN)" in result.output
    assert "81" in result.output
    assert "240" in result.output
    assert "critical" in result.output


def test_dossier_renders_all_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.analysis.dossier as dossier_mod

    calls: list = []
    payload = {
        "overview": {
            "country": "Ukraine",
            "iso2": "UA",
            "iso3": "UKR",
            "baseline_risk": 78,
        },
        "economy": {
            "gdp": [{"year": 2025, "value": 178e9}],
            "conflict_events_30d": 450,
        },
        "markets": {"ticker": "^UX", "quote": {"price": 1200, "change_pct": 1.5}},
        "elections": {
            "upcoming": [
                {
                    "election_type": "parliamentary",
                    "date": "2026-10-01",
                    "risk_score": 4.0,
                }
            ]
        },
        "sanctions": {"match_count": 2},
        "news": {
            "mention_count": 5,
            "mentions": [{"title": "Article about grid strikes"}],
        },
        "security": {"hotspot_count": 2, "conflict_count": 1},
    }
    monkeypatch.setattr(dossier_mod, "fetch_country_dossier", _fake(payload, calls))
    result = _invoke("dossier", "-c", "UA")
    assert result.exit_code == 0
    assert calls == [{"country": "UA"}]
    assert "Country Dossier: Ukraine" in result.output
    assert "(UA/UKR)" in result.output
    assert "GDP 2025: $178.0B" in result.output
    assert "Conflict events (30d): 450" in result.output
    assert "^UX = 1200 (1.5%)" in result.output
    assert "parliamentary on 2026-10-01" in result.output
    assert "risk: 4" in result.output
    assert "2 OFAC matches" in result.output
    assert "5 recent mentions" in result.output
    assert "Article about grid strikes" in result.output
    assert "Hotspots: 2" in result.output
    assert "Conflicts: 1" in result.output
    assert "Baseline risk: 78/100" in result.output


def test_dossier_error_dict_prints_error_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dossier_analysis,
        "fetch_country_dossier",
        _fake({"error": "unknown country XX"}),
    )
    result = _invoke("dossier", "-c", "XX")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "unknown country XX" in result.output
    assert '"error"' not in result.output


# ---------------------------------------------------------------------------
# Shipping / Social / Health / Elections / Space / Sanctions / AI
# ---------------------------------------------------------------------------


def test_shipping_renders_stress_and_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "assessment": "elevated",
        "stress_score": 62.0,
        "quotes": [{"symbol": "BDRY", "price": 12.34, "change_pct": -3.1}],
    }
    monkeypatch.setattr(cli.shipping, "fetch_shipping_index", _fake(payload))
    result = _invoke("shipping")
    assert result.exit_code == 0
    assert "Shipping Stress: elevated" in result.output
    assert "score: 62/100" in result.output
    assert "BDRY" in result.output
    assert "$12.34" in result.output
    assert "-3.10%" in result.output


def test_social_renders_metrics_and_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "velocity_metrics": {"total_posts": 50, "high_engagement_count": 7},
        "top_posts": [{"score": 4521, "title": "Major escalation reported"}],
    }
    monkeypatch.setattr(cli.social, "fetch_social_signals", _fake(payload))
    result = _invoke("social")
    assert result.exit_code == 0
    assert "50 posts" in result.output
    assert "7 high engagement" in result.output
    assert "4521" in result.output
    assert "Major escalation reported" in result.output


def test_disease_renders_outbreaks_with_high_concern_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 3,
        "high_concern_count": 1,
        "items": [
            {
                "is_high_concern": True,
                "title": "H5N1 cluster investigated",
                "feed_name": "WHO",
            }
        ],
    }
    monkeypatch.setattr(cli.health, "fetch_disease_outbreaks", _fake(payload))
    result = _invoke("disease")
    assert result.exit_code == 0
    assert "3 outbreak reports" in result.output
    assert "1 high concern" in result.output
    assert "HC" in result.output
    assert "H5N1 cluster investigated" in result.output
    assert "(WHO)" in result.output


def test_elections_passes_country_and_renders_calendar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "elections": [
            {
                "date": "2026-10-04",
                "country": "Brazil",
                "type": "presidential",
                "days_until": 33,
                "risk_score": 4.5,
            }
        ]
    }
    monkeypatch.setattr(cli.elections, "fetch_election_calendar", _fake(payload, calls))
    result = _invoke("elections", "-c", "BRA")
    assert result.exit_code == 0
    assert calls == [{"country": "BRA"}]
    assert "2026-10-04" in result.output
    assert "Brazil" in result.output
    assert "presidential" in result.output
    assert "33" in result.output
    assert "4.5" in result.output


def test_space_renders_metrics_null_as_unknown_and_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "current_kp": 0.67,
        "kp_level": "Quiet",
        "latest_flare_class": "B6.5",
        "solar_wind_speed_km_s": None,
        "alerts": [
            {
                "issue_datetime": "2026-11-16 06:28:16.430",
                "product_id": "EF3A",
                "message": "Space Weather Message Code: ALTEF3\r\nSerial Number: 1\r\n"
                "Issue Time: 2026 Nov 16 0628 UTC\r\n\r\nCONTINUED ALERT: Electron flux",
            }
        ],
    }
    monkeypatch.setattr(cli.space_weather, "fetch_space_weather", _fake(payload))
    result = _invoke("space")
    assert result.exit_code == 0
    assert "0.67" in result.output
    assert "Quiet" in result.output
    assert "B6.5" in result.output
    assert "unknown" in result.output  # null solar wind
    assert "1 alerts" in result.output
    assert "CONTINUED ALERT: Electron flux" in result.output


def test_flights_on_ground_string_altitude_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 2,
        "aircraft": [
            {"callsign": "UP1", "icao24": "aaaaaa", "origin_country": "US",
             "altitude_m": 22000, "velocity_ms": 286.0, "on_ground": False},
            {"callsign": "DOWN1", "icao24": "bbbbbb", "origin_country": "US",
             "altitude_m": "ground", "velocity_ms": 0.0, "on_ground": True},
        ],
    }
    monkeypatch.setattr(cli.military, "fetch_military_flights", _fake(payload))
    result = _invoke("flights")
    assert result.exit_code == 0
    assert "22,000" in result.output
    assert "ground" in result.output


def test_macro_renders_mempool_and_btc_dominance_dicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "signals": {
            "mempool_fees": {
                "fastest_fee": 2, "half_hour_fee": 1, "hour_fee": 1,
                "economy_fee": 1, "minimum_fee": 1, "source": "mempool",
            },
            "btc_dominance": {"btc_dominance_pct": 58.56, "source": "coingecko"},
            "vix": {"price": 22.91},
        }
    }
    monkeypatch.setattr(cli.markets, "fetch_macro_signals", _fake(payload))
    result = _invoke("macro")
    assert result.exit_code == 0
    assert "2 sat/vB" in result.output
    assert "30m 1 / 1h 1 / eco 1" in result.output
    assert "58.56%" in result.output
    assert "22.91" in result.output
    assert "?" not in result.output


def test_sanctions_passes_query_and_entity_type_label_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "count": 1,
        "total_entities": 12_000,
        "matches": [
            {
                "entity_type": "org",
                "name": "WAGNER GROUP",
                "programs": ["RUSSIA-EO14024"],
            }
        ],
    }
    monkeypatch.setattr(cli.sanctions, "fetch_sanctions_search", _fake(payload, calls))
    result = _invoke("sanctions", "Wagner")
    assert result.exit_code == 0
    assert calls == [{"query": "Wagner", "country": None}]
    assert "1 matches" in result.output
    assert "'Wagner'" in result.output
    assert "12000 total" in result.output
    assert "WAGNER GROUP" in result.output
    assert "RUSSIA-EO14024" in result.output
    # The entity-type label must render literally; before the escape fix
    # Rich parsed "[org]" as a markup tag and silently dropped it.
    assert "[org]" in result.output


def test_ai_watch_source_label_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "total_items": 2,
        "items": [{"title": "New frontier model released", "source": "arxiv"}],
    }
    monkeypatch.setattr(cli.ai_watch, "fetch_ai_watch", _fake(payload))
    result = _invoke("ai-watch")
    assert result.exit_code == 0
    assert "2 items" in result.output
    assert "New frontier model released" in result.output
    # The per-item source label must render literally; before the escape
    # fix Rich parsed "[arxiv]" as a markup tag and silently dropped it.
    assert "[arxiv]" in result.output


# ---------------------------------------------------------------------------
# Fleet / Tech & Science
# ---------------------------------------------------------------------------


def test_fleet_renders_totals_and_ships(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "report_title": "USNI Fleet Tracker update",
        "force_totals": {
            "battle_force": {"total": 296, "uss": 238, "usns": 58},
            "deployed": {"total": 110, "uss": 70, "usns": 40},
        },
        "ships": [
            {
                "name": "USS Gerald R. Ford",
                "hull_number": "CVN-78",
                "type": "carrier",
                "region": "Mediterranean",
            }
        ],
    }
    monkeypatch.setattr(cli, "fetch_usni_fleet", _fake(payload))
    result = _invoke("fleet")
    assert result.exit_code == 0
    assert "USNI Fleet Tracker update" in result.output
    assert "Battle Force: 296 ships (238 USS, 58 USNS)" in result.output
    assert "Deployed: 110 (70 USS, 40 USNS)" in result.output
    assert "1 ships identified" in result.output
    assert "USS Gerald R. Ford" in result.output
    assert "CVN-78" in result.output


def test_fleet_error_dict_prints_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "fetch_usni_fleet", _fake({"error": "USNI page structure changed"})
    )
    result = _invoke("fleet")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "USNI page structure changed" in result.output
    assert '"error"' not in result.output


def test_hn_renders_stories(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    payload = {"stories": [{"score": 512, "title": "Show HN: Something"}]}
    monkeypatch.setattr(cli, "fetch_hacker_news", _fake(payload, calls))
    result = _invoke("hn", "--limit", "5")
    assert result.exit_code == 0
    assert calls == [{"limit": 5}]
    assert "512" in result.output
    assert "Show HN: Something" in result.output


def test_gh_trending_renders_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "repos": [
            {
                "stars": 3200,
                "name": "acme/widget",
                "language": "Rust",
                "description": "A widget framework",
            }
        ]
    }
    monkeypatch.setattr(cli, "fetch_trending_repos", _fake(payload))
    result = _invoke("gh-trending")
    assert result.exit_code == 0
    assert "3200" in result.output
    assert "acme/widget" in result.output
    # The language label is escaped, so it renders literally regardless
    # of case (an unescaped lowercase language used to be swallowed as a
    # markup tag; "[Rust]" only survived by failing Rich's tag regex).
    assert "[Rust]" in result.output
    assert "A widget framework" in result.output


def test_gh_trending_lowercase_language_label_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "repos": [
            {
                "stars": 900,
                "name": "acme/gadget",
                "language": "zig",
                "description": "A gadget toolkit",
            }
        ]
    }
    monkeypatch.setattr(cli, "fetch_trending_repos", _fake(payload))
    result = _invoke("gh-trending")
    assert result.exit_code == 0
    assert "[zig]" in result.output


def test_arxiv_passes_query_and_renders_papers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "papers": [
            {
                "title": "Attention Is Still All You Need",
                "authors": ["A. One", "B. Two"],
            }
        ]
    }
    monkeypatch.setattr(cli, "fetch_arxiv_papers", _fake(payload, calls))
    result = _invoke("arxiv", "-q", "cs.CR", "--limit", "3")
    assert result.exit_code == 0
    assert calls == [{"query": "cs.CR", "limit": 3}]
    assert "Attention Is Still All You Need" in result.output
    assert "A. One, B. Two" in result.output


def test_spending_renders_agency_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "agencies": [
            {
                "name": "Department of Defense",
                "budget_authority": 850e9,
                "obligated_amount": 600e9,
            }
        ]
    }
    monkeypatch.setattr(cli, "fetch_usa_spending", _fake(payload))
    result = _invoke("spending")
    assert result.exit_code == 0
    assert "Department of Defense" in result.output
    assert "$850.0B" in result.output
    assert "$600.0B" in result.output


# ---------------------------------------------------------------------------
# Geospatial (no fetcher argument)
# ---------------------------------------------------------------------------


def test_bases_passes_filters_and_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    payload = {
        "count": 1,
        "total_in_database": 70,
        "bases": [
            {
                "name": "Ramstein AB",
                "operator": "USA",
                "country": "Germany",
                "type": "air",
                "branch": "USAF",
            }
        ],
    }
    monkeypatch.setattr(cli.geospatial, "fetch_military_bases", _fake(payload, calls))
    result = _invoke("bases", "-o", "USA")
    assert result.exit_code == 0
    assert calls == [{"operator": "USA", "country": None}]
    assert "1 bases" in result.output
    assert "of 70" in result.output
    assert "Ramstein AB" in result.output
    assert "Germany" in result.output


def test_exchanges_passes_tier_and_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    payload = {
        "count": 1,
        "total_market_cap_usd_t": 30.5,
        "exchanges": [
            {
                "name": "NYSE",
                "country": "USA",
                "tier": "mega",
                "market_cap_usd_t": 28.33,
            }
        ],
    }
    monkeypatch.setattr(cli.geospatial, "fetch_stock_exchanges", _fake(payload, calls))
    result = _invoke("exchanges", "-t", "mega")
    assert result.exit_code == 0
    assert calls == [{"tier": "mega", "country": None}]
    assert "$30.5T" in result.output
    assert "NYSE" in result.output
    assert "28.33" in result.output


def test_exchanges_rejects_invalid_tier() -> None:
    result = _invoke("exchanges", "-t", "huge")
    assert result.exit_code == 2
    assert "Invalid value" in result.stderr


# ---------------------------------------------------------------------------
# Traffic / Aviation extras / Webcams
# ---------------------------------------------------------------------------


def test_traffic_renders_cities(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.sources.traffic as traffic_mod

    payload = {
        "count": 2,
        "global_avg_congestion": 45.0,
        "cities": [
            {
                "name": "Lagos",
                "country": "NGA",
                "congestion_pct": 72,
                "current_speed_kmh": 18,
            }
        ],
    }
    monkeypatch.setattr(traffic_mod, "fetch_traffic_flow", _fake(payload))
    result = _invoke("traffic")
    assert result.exit_code == 0
    assert "avg congestion 45%" in result.output
    assert "Lagos" in result.output
    assert "72%" in result.output
    assert "18" in result.output


def test_traffic_error_dict_prints_error_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        traffic_src, "fetch_traffic_flow", _fake({"error": "TOMTOM key missing"})
    )
    result = _invoke("traffic")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "TOMTOM key missing" in result.output
    assert '"error"' not in result.output


def test_incidents_renders_delays_and_dash_for_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import world_intel_mcp.sources.traffic as traffic_mod

    payload = {
        "total_count": 3,
        "regions_checked": 5,
        "incidents": [
            {
                "region": "LA",
                "description": "Overturned truck",
                "delay_seconds": 600,
                "from_road": "I-405",
            },
            {
                "region": "NYC",
                "description": "Lane closure",
                "delay_seconds": 0,
                "from_road": "FDR Drive",
            },
        ],
    }
    monkeypatch.setattr(traffic_mod, "fetch_traffic_incidents", _fake(payload))
    result = _invoke("incidents")
    assert result.exit_code == 0
    assert "3 across" in result.output
    assert "5 regions" in result.output
    assert "Overturned truck" in result.output
    assert "10" in result.output  # 600s -> 10 min
    assert "I-405" in result.output
    assert "Lane closure" in result.output


def test_air_traffic_renders_regions_and_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "total_aircraft": 9000,
        "by_region": {"europe": {"count": 4000, "commercial": 3500, "general": 500}},
        "busiest_origins": [{"country": "United States", "count": 2500}],
    }
    monkeypatch.setattr(cli.aviation, "fetch_domestic_flights", _fake(payload))
    result = _invoke("air-traffic")
    assert result.exit_code == 0
    assert "9000 airborne" in result.output
    assert "europe" in result.output
    assert "4000" in result.output
    assert "3500" in result.output
    assert "Busiest Origins:" in result.output
    assert "United States: 2500" in result.output


def test_webcams_passes_options_and_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.sources.webcams as webcams_mod

    calls: list = []
    payload = {
        "count": 1,
        "cameras": [
            {
                "title": "Harbor Cam",
                "city": "Rotterdam",
                "country": "Netherlands",
                "status": "active",
            }
        ],
    }
    monkeypatch.setattr(webcams_mod, "fetch_webcams", _fake(payload, calls))
    result = _invoke("webcams", "-c", "ports", "--limit", "5")
    assert result.exit_code == 0
    assert calls == [{"category": "ports", "limit": 5}]
    assert "1 cameras (ports)" in result.output
    assert "Harbor Cam" in result.output
    assert "Rotterdam" in result.output


# ---------------------------------------------------------------------------
# System: status / sync / report
# ---------------------------------------------------------------------------


def test_status_without_requests_shows_empty_breaker_note() -> None:
    result = _invoke("status")
    assert result.exit_code == 0
    assert "World Intelligence Status" in result.output
    assert "Cache:" in result.output
    assert "No circuit breaker data yet" in result.output


def test_status_renders_breaker_table_after_failure() -> None:
    # Seed the shared fetcher's breaker, then render status through the CLI.
    f = cli._get_fetcher()
    f.breaker.record_failure("test-src")
    result = _invoke("status")
    assert result.exit_code == 0
    assert "Circuit Breakers" in result.output
    assert "test-src" in result.output
    assert "closed" in result.output  # single failure does not trip


def test_status_json_output() -> None:
    result = _invoke("--json-output", "status")
    assert result.exit_code == 0
    assert '"circuit_breakers"' in result.output
    assert '"cache"' in result.output


def test_sync_without_source_evicts_expired() -> None:
    result = _invoke("sync")
    assert result.exit_code == 0
    assert "Evicted 0 expired cache entries" in result.output


def test_sync_with_source_reports_not_implemented() -> None:
    result = _invoke("sync", "yahoo")
    assert result.exit_code == 0
    assert "Force sync not yet implemented for specific source 'yahoo'" in result.output


def test_report_success_panel_and_option_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    payload = {
        "path": "/tmp/r.html",
        "format": "html",
        "size_bytes": 123_456,
        "sections_included": ["markets", "cyber"],
        "sections_failed": ["fleet"],
        "generation_seconds": 4.2,
    }
    monkeypatch.setattr(reports_mod, "generate_report", _fake(payload, calls))
    result = _invoke(
        "report", "--format", "html", "--sections", "markets,cyber", "-t", "Daily"
    )
    assert result.exit_code == 0
    assert calls == [
        {
            "output_path": None,
            "title": "Daily",
            "sections": ["markets", "cyber"],
            "fmt": "html",
        }
    ]
    assert "Report generated" in result.output
    assert "/tmp/r.html" in result.output
    assert "123,456 bytes" in result.output
    assert "markets, cyber" in result.output
    assert "4.2s" in result.output
    assert "Failed: fleet" in result.output


def test_report_error_with_fallback_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "error": "WeasyPrint not installed",
        "fallback": "pip install -e '.[pdf]'",
    }
    monkeypatch.setattr(reports_mod, "generate_report", _fake(payload))
    result = _invoke("report")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "WeasyPrint not installed" in result.output
    # The fallback hint must print the runnable command verbatim; before
    # the escape fix Rich ate the literal "[pdf]" as a markup tag and the
    # printed command would NOT have installed the pdf extra.
    assert "pip install -e '.[pdf]'" in result.output


def test_report_error_json_mode_passes_raw_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # report joins the shared _bail_on_error contract: --json-output gets
    # the raw dict (fallback hint included as data), no error rendering.
    payload = {
        "error": "WeasyPrint not installed",
        "fallback": "pip install -e '.[pdf]'",
    }
    monkeypatch.setattr(reports_mod, "generate_report", _fake(payload))
    result = _invoke("--json-output", "report")
    assert result.exit_code == 0
    assert '"error"' in result.output
    assert '"fallback"' in result.output
    assert "Error:" not in result.output


def test_report_success_json_mode_passes_raw_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "path": "/tmp/r.html",
        "format": "html",
        "size_bytes": 123_456,
        "sections_included": ["markets"],
        "sections_failed": [],
        "generation_seconds": 4.2,
    }
    monkeypatch.setattr(reports_mod, "generate_report", _fake(payload))
    result = _invoke("--json-output", "report")
    assert result.exit_code == 0
    assert '"path"' in result.output
    assert "Report generated" not in result.output


# ---------------------------------------------------------------------------
# Markup injection via table cells: remote data must render literally
# ---------------------------------------------------------------------------

# Two failure modes, both must be dead: a well-formed tag pair like
# "[red]fake[/red]" is silently swallowed (styled, tags eaten), and a
# stray closing tag like "[/]" raises MarkupError and crashes the
# command. Remote values inside Rich Table cells go through cli._cell
# (rich.text.Text), which renders content literally while column-level
# style/justify still apply.


def test_earthquakes_bracketed_place_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 2,
        "earthquakes": [
            {
                "magnitude": 5.1,
                "place": "Coast of [/] Chile",
                "depth_km": 10.0,
                "time": "2026-08-31T12:00:00.000Z",
                "alert_level": None,
            },
            {
                "magnitude": 4.6,
                "place": "[red]fake[/red] quake zone",
                "depth_km": 5.2,
                "time": "2026-08-31T13:00:00.000Z",
                "alert_level": None,
            },
        ],
    }
    monkeypatch.setattr(cli.seismology, "fetch_earthquakes", _fake(payload))
    result = _invoke("earthquakes")
    assert result.exit_code == 0
    assert "Coast of [/] Chile" in result.output
    assert "[red]fake[/red] quake zone" in result.output


def test_threats_bracketed_indicator_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 1,
        "feeds_successful": 1,
        "feeds_attempted": 1,
        "by_severity": {"critical": 1, "high": 0, "medium": 0, "low": 0},
        "threats": [
            {
                "severity": "critical",
                "type": "ip",
                "indicator": "[red]fake[/red] indicator",
                "threat": "botnet [/] C2",
                "source_feed": "feodo",
            }
        ],
    }
    monkeypatch.setattr(cli.cyber, "fetch_cyber_threats", _fake(payload))
    result = _invoke("threats")
    assert result.exit_code == 0
    assert "[red]fake[/red] indicator" in result.output
    assert "botnet [/] C2" in result.output


def test_conflicts_bracketed_location_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 1,
        "events": [
            {
                "event_date": "2026-08-30",
                "event_type": "[bold]Battles[/bold]",
                "country": "Ukraine",
                "location": "Kharkiv [/] oblast",
                "fatalities": 0,
            }
        ],
    }
    monkeypatch.setattr(cli.conflict, "fetch_acled_events", _fake(payload))
    result = _invoke("conflicts")
    assert result.exit_code == 0
    assert "[bold]Battles[/bold]" in result.output
    assert "Kharkiv [/] oblast" in result.output


def test_flights_bracketed_callsign_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 1,
        "aircraft": [
            {
                "callsign": "[dim]RCH123[/dim]",
                "icao24": "ae1234",
                "origin_country": "Neverland [/]",
                "altitude_m": 10_000,
                "velocity_ms": 250.0,
            }
        ],
    }
    monkeypatch.setattr(cli.military, "fetch_military_flights", _fake(payload))
    result = _invoke("flights")
    assert result.exit_code == 0
    assert "[dim]RCH123[/dim]" in result.output
    assert "Neverland [/]" in result.output


def test_predictions_bracketed_question_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "markets": [
            {
                "question": "Will [/] X happen",
                "yes_probability": 0.62,
                "sentiment": "likely_yes",
                "volume_24h": 1_000,
            }
        ]
    }
    monkeypatch.setattr(cli.prediction, "fetch_prediction_markets", _fake(payload))
    result = _invoke("predictions")
    assert result.exit_code == 0
    assert "Will [/] X happen" in result.output


def test_elections_bracketed_country_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "elections": [
            {
                "date": "2026-10-04",
                "country": "[green]Fake[/green]land",
                "type": "general [/] vote",
                "days_until": 33,
                "risk_score": 1.0,
            }
        ]
    }
    monkeypatch.setattr(cli.elections, "fetch_election_calendar", _fake(payload))
    result = _invoke("elections")
    assert result.exit_code == 0
    assert "[green]Fake[/green]land" in result.output
    assert "general [/] vote" in result.output


def test_central_banks_bracketed_bank_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 1,
        "fred_available": False,
        "rates": [
            {
                "bank": "Bank [/] of Testland",
                "country": "[red]TL[/red]",
                "rate": 4.25,
                "as_of": "2026-08-01",
            }
        ],
    }
    monkeypatch.setattr(cli, "fetch_central_bank_rates", _fake(payload))
    result = _invoke("central-banks")
    assert result.exit_code == 0
    assert "Bank [/] of Testland" in result.output
    assert "[red]TL[/red]" in result.output


def test_fleet_bracketed_ship_name_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "report_title": "Fleet Report",
        "force_totals": {},
        "ships": [
            {
                "name": "USS [red]Fake[/red]",
                "hull_number": "CVN-00",
                "type": "carrier",
                "region": "Pacific [/] Fleet",
            }
        ],
    }
    monkeypatch.setattr(cli, "fetch_usni_fleet", _fake(payload))
    result = _invoke("fleet")
    assert result.exit_code == 0
    assert "USS [red]Fake[/red]" in result.output
    assert "Pacific [/] Fleet" in result.output


def test_webcams_bracketed_title_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "count": 1,
        "cameras": [
            {
                "title": "Harbor [/] Cam",
                "city": "[red]Rotterdam[/red]",
                "country": "Netherlands",
                "status": "active",
            }
        ],
    }
    monkeypatch.setattr(webcams_src, "fetch_webcams", _fake(payload))
    result = _invoke("webcams")
    assert result.exit_code == 0
    assert "Harbor [/] Cam" in result.output
    assert "[red]Rotterdam[/red]" in result.output


def test_macro_bracketed_signal_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "signals": {
            "vix [/] proxy": {"value": 18.2, "classification": "regime [/] shift"},
        }
    }
    monkeypatch.setattr(cli.markets, "fetch_macro_signals", _fake(payload))
    result = _invoke("macro")
    assert result.exit_code == 0
    assert "vix [/] proxy" in result.output
    assert "regime [/] shift" in result.output


def test_fred_bracketed_series_title_renders_literally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The table TITLE is a markup surface too: FRED series titles are
    # remote free text.
    payload = {
        "title": "Rate[/]s",
        "observations": [{"date": "2026-07-01", "value": "4.2"}],
    }
    monkeypatch.setattr(cli.economic, "fetch_fred_series", _fake(payload))
    result = _invoke("fred", "UNRATE")
    assert result.exit_code == 0
    assert "Rate[/]s" in result.output


# ---------------------------------------------------------------------------
# Error-surfacing sweep: every data command converted to _bail_on_error
# ---------------------------------------------------------------------------

# (cli args, module holding the fetch fn, fetch fn attribute name). One row
# per command that used to branch only on ctx.obj["json"] and rendered an
# upstream {"error": ...} as a healthy empty state.
_ERROR_SWEEP = [
    (("markets",), cli.markets, "fetch_market_quotes"),
    (("crypto",), cli.markets, "fetch_crypto_quotes"),
    (("macro",), cli.markets, "fetch_macro_signals"),
    (("earthquakes",), cli.seismology, "fetch_earthquakes"),
    (("flights",), cli.military, "fetch_military_flights"),
    (("posture",), cli.military, "fetch_theater_posture"),
    (("outages",), cli.infrastructure, "fetch_internet_outages"),
    (("cables",), cli.infrastructure, "fetch_cable_health"),
    (("warnings",), cli.maritime, "fetch_nav_warnings"),
    (("climate",), cli.climate, "fetch_climate_anomalies"),
    (("news",), cli.news, "fetch_news_feed"),
    (("trending",), cli.news, "fetch_trending_keywords"),
    (("gdelt",), cli.news, "fetch_gdelt_search"),
    (("predictions",), cli.prediction, "fetch_prediction_markets"),
    (("displacement",), cli.displacement, "fetch_displacement_summary"),
    (("migration-flows",), cli.migration, "fetch_migration_flows"),
    (("migration-surges",), cli.migration, "fetch_migration_surges"),
    (("migration-history", "Sudan"), cli.migration, "fetch_migration_history"),
    (("net-migration",), cli.migration, "fetch_net_migration"),
    (("delays",), cli.aviation, "fetch_airport_delays"),
    (("threats",), cli.cyber, "fetch_cyber_threats"),
    (("brief",), cli.intelligence, "fetch_country_brief"),
    (("central-banks",), cli, "fetch_central_bank_rates"),
    (("shipping",), cli.shipping, "fetch_shipping_index"),
    (("social",), cli.social, "fetch_social_signals"),
    (("disease",), cli.health, "fetch_disease_outbreaks"),
    (("elections",), cli.elections, "fetch_election_calendar"),
    (("nuclear",), cli.nuclear, "fetch_nuclear_monitor"),
    (("space",), cli.space_weather, "fetch_space_weather"),
    (("sanctions", "Wagner"), cli.sanctions, "fetch_sanctions_search"),
    (("ai-watch",), cli.ai_watch, "fetch_ai_watch"),
    (("hn",), cli, "fetch_hacker_news"),
    (("gh-trending",), cli, "fetch_trending_repos"),
    (("arxiv",), cli, "fetch_arxiv_papers"),
    (("spending",), cli, "fetch_usa_spending"),
    (("bases",), cli.geospatial, "fetch_military_bases"),
    (("exchanges",), cli.geospatial, "fetch_stock_exchanges"),
    # The 17 legacy commands that used to dump raw JSON at table-mode
    # users on upstream error, unified onto _bail_on_error:
    (("energy",), cli.economic, "fetch_energy_prices"),
    (("gas-prices",), cli.economic, "fetch_gas_prices"),
    (("natgas",), cli.economic, "fetch_residential_natgas_prices"),
    (("electricity",), cli.economic, "fetch_electricity_rates"),
    (("fred", "UNRATE"), cli.economic, "fetch_fred_series"),
    (("fires",), cli.wildfire, "fetch_wildfires"),
    (("conflicts",), cli.conflict, "fetch_acled_events"),
    (("dossier",), dossier_analysis, "fetch_country_dossier"),
    (("risk",), cli.intelligence, "fetch_risk_scores"),
    (("instability",), cli.intelligence, "fetch_instability_index"),
    (("btc",), cli.markets, "fetch_btc_technicals"),
    (("fleet",), cli, "fetch_usni_fleet"),
    (("traffic",), traffic_src, "fetch_traffic_flow"),
    (("incidents",), traffic_src, "fetch_traffic_incidents"),
    (("air-traffic",), cli.aviation, "fetch_domestic_flights"),
    (("webcams",), webcams_src, "fetch_webcams"),
    (("report",), reports_mod, "generate_report"),
]


@pytest.mark.parametrize(
    ("args", "module", "attr"),
    _ERROR_SWEEP,
    ids=[" ".join(row[0]) for row in _ERROR_SWEEP],
)
def test_error_dict_reaches_table_output(
    args: tuple[str, ...],
    module: object,
    attr: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, attr, _fake({"error": "upstream exploded"}))
    result = _invoke(*args)
    assert result.exit_code == 0
    # One consistent human-readable surface in table mode: the shared
    # red "Error:" line, never a raw JSON dump.
    assert "Error:" in result.output
    assert "upstream exploded" in result.output
    assert '"error"' not in result.output


# ---------------------------------------------------------------------------
# AOI geofences: intel aoi <define|define-polygon|define-corridor|list|
# update|delete|brief|escalation|changes>
#
# CRUD subcommands exercise the real AOIStore against the tmp SQLite file
# the _cli_isolation fixture points WORLD_INTEL_CACHE_DB at (the
# test_server_registry pattern); the network-bound brief/escalation/changes
# subcommands fake the analysis functions at the cli.aoi_analysis boundary,
# same as every other faked fetch in this file.
# ---------------------------------------------------------------------------


def _define_zone(name: str = "TestZone") -> None:
    result = _invoke(
        "aoi", "define", name, "--lat", "12.5", "--lon", "45.25", "--radius-km", "150"
    )
    assert result.exit_code == 0, result.output


def test_aoi_subcommand_registry() -> None:
    assert set(cli.aoi_group.commands) == {
        "define",
        "define-polygon",
        "define-corridor",
        "list",
        "update",
        "delete",
        "brief",
        "escalation",
        "changes",
    }


def test_aoi_store_shares_the_fetchers_cache_db() -> None:
    # Mirrors runtime.py: the AOIStore must land in the literal SQLite
    # file the process's Cache resolved to, not a fresh default-path
    # computation.
    _define_zone()
    assert cli._aoi_store is not None
    assert cli._fetcher is not None
    assert cli._aoi_store.db_path == cli._fetcher.cache.db_path
    assert cli._aoi_store.db_path.name == "cli-cache.db"


def test_aoi_define_and_list_roundtrip() -> None:
    _define_zone()
    result = _invoke("aoi", "list")
    assert result.exit_code == 0
    assert "TestZone" in result.output
    assert "circle" in result.output
    assert "150" in result.output


def test_aoi_define_ack_names_center_and_radius() -> None:
    result = _invoke(
        "aoi",
        "define",
        "TestZone",
        "--lat",
        "12.5",
        "--lon",
        "45.25",
        "--radius-km",
        "150",
    )
    assert result.exit_code == 0
    assert "TestZone" in result.output
    assert "12.5" in result.output
    assert "45.25" in result.output
    assert "150" in result.output


def test_aoi_define_duplicate_is_error_not_overwrite() -> None:
    _define_zone()
    result = _invoke(
        "aoi",
        "define",
        "testzone",
        "--lat",
        "1.5",
        "--lon",
        "2.5",
        "--radius-km",
        "10",
    )
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "already exists" in result.output


def test_aoi_define_invalid_lat_surfaces_error_dict() -> None:
    result = _invoke(
        "aoi", "define", "Bad", "--lat", "95", "--lon", "0.5", "--radius-km", "50"
    )
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "lat must be between -90 and 90" in result.output


def test_aoi_define_json_mode_passes_raw_dict() -> None:
    result = _invoke(
        "--json-output",
        "aoi",
        "define",
        "TestZone",
        "--lat",
        "12.5",
        "--lon",
        "45.25",
        "--radius-km",
        "150",
    )
    assert result.exit_code == 0
    assert '"aoi"' in result.output
    assert '"TestZone"' in result.output


def test_aoi_list_empty_prints_no_aois_message() -> None:
    result = _invoke("aoi", "list")
    assert result.exit_code == 0
    assert "No AOIs defined" in result.output


def test_aoi_list_json_mode_passes_raw_dict() -> None:
    _define_zone()
    result = _invoke("--json-output", "aoi", "list")
    assert result.exit_code == 0
    assert '"aois"' in result.output
    assert '"count"' in result.output


def test_aoi_define_polygon_and_corridor_kinds_listed() -> None:
    poly = _invoke(
        "aoi",
        "define-polygon",
        "TriZone",
        "--vertex",
        "12.5,45.0",
        "--vertex",
        "13.0,45.5",
        "--vertex",
        "12.0,46.0",
    )
    assert poly.exit_code == 0, poly.output
    assert "TriZone" in poly.output
    assert "3" in poly.output  # vertex count in the ack

    corr = _invoke(
        "aoi",
        "define-corridor",
        "LaneZone",
        "--waypoint",
        "10.5,40.0",
        "--waypoint",
        "11.5,41.0",
        "--width-km",
        "50",
    )
    assert corr.exit_code == 0, corr.output
    assert "LaneZone" in corr.output
    assert "2" in corr.output  # waypoint count in the ack
    assert "50" in corr.output

    listing = _invoke("aoi", "list")
    assert "polygon" in listing.output
    assert "corridor" in listing.output


def test_aoi_define_polygon_bad_vertex_format_is_usage_error() -> None:
    result = _invoke("aoi", "define-polygon", "Bad", "--vertex", "12.5")
    assert result.exit_code == 2
    assert "expected LAT,LON" in result.output


def test_aoi_define_polygon_nonnumeric_vertex_is_usage_error() -> None:
    result = _invoke("aoi", "define-polygon", "Bad", "--vertex", "a,b")
    assert result.exit_code == 2
    assert "expected numeric LAT,LON" in result.output


def test_aoi_define_polygon_too_few_vertices_surfaces_error_dict() -> None:
    # Count/range rules live in the analysis layer; the CLI surfaces its
    # error dict through the shared red Error line.
    result = _invoke(
        "aoi", "define-polygon", "Duo", "--vertex", "12.5,45.0", "--vertex", "13.0,45.5"
    )
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "at least 3" in result.output


def test_aoi_define_corridor_missing_width_is_usage_error() -> None:
    result = _invoke(
        "aoi",
        "define-corridor",
        "Lane",
        "--waypoint",
        "10.5,40.0",
        "--waypoint",
        "11.5,41.0",
    )
    assert result.exit_code == 2
    assert "--width-km" in result.output


def test_aoi_define_corridor_width_out_of_range_surfaces_error_dict() -> None:
    result = _invoke(
        "aoi",
        "define-corridor",
        "Lane",
        "--waypoint",
        "10.5,40.0",
        "--waypoint",
        "11.5,41.0",
        "--width-km",
        "900",
    )
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "width_km must be between" in result.output


def test_aoi_update_rename_keeps_baseline() -> None:
    _define_zone("Alpha")
    result = _invoke("aoi", "update", "Alpha", "--new-name", "Bravo")
    assert result.exit_code == 0
    assert "Bravo" in result.output
    assert "updated" in result.output
    assert "baseline dropped" not in result.output

    listing = _invoke("aoi", "list")
    assert "Bravo" in listing.output
    assert "Alpha" not in listing.output


def test_aoi_update_geometry_change_reports_dropped_baseline() -> None:
    _define_zone("Alpha")
    result = _invoke("aoi", "update", "Alpha", "--radius-km", "300")
    assert result.exit_code == 0
    assert "300" in result.output
    assert "baseline dropped" in result.output


def test_aoi_update_missing_aoi_surfaces_error_dict() -> None:
    result = _invoke("aoi", "update", "Ghost", "--new-name", "Spectre")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "not found" in result.output


def test_aoi_update_polygon_geometry_is_refused() -> None:
    poly = _invoke(
        "aoi",
        "define-polygon",
        "TriZone",
        "--vertex",
        "12.5,45.0",
        "--vertex",
        "13.0,45.5",
        "--vertex",
        "12.0,46.0",
    )
    assert poly.exit_code == 0
    result = _invoke("aoi", "update", "TriZone", "--lat", "20.5")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "cannot be set directly" in result.output


def test_aoi_delete_then_missing() -> None:
    _define_zone()
    result = _invoke("aoi", "delete", "TestZone")
    assert result.exit_code == 0
    assert "Deleted AOI" in result.output
    assert "TestZone" in result.output

    again = _invoke("aoi", "delete", "TestZone")
    assert again.exit_code == 0
    assert "Error:" in again.output
    assert "not found" in again.output


_AOI_BRIEF = {
    "aoi": {
        "name": "TestZone",
        "lat": 12.5,
        "lon": 45.25,
        "radius_km": 150.0,
        "kind": "circle",
    },
    "markdown": (
        "# AOI Brief: TestZone\n"
        "Center: 12.5, 45.25 (radius 150.0 km)\n\n"
        "## Earthquakes\n"
        "- M5.1 near [red]Quaketown[/red] (12 km) [1]\n\n"
        "## Data Gaps\n"
        "- Wildfires: FIRMS key missing"
    ),
    "counts": {"earthquakes": 1},
    "sources": [{"n": 1, "title": "USGS", "url": "https://example.test/eq"}],
    "cited": True,
    "data_gaps": ["Wildfires: FIRMS key missing"],
    "source": "aoi-brief",
    "timestamp": "2026-09-01T00:00:00Z",
}


def test_aoi_brief_renders_markdown_and_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(cli.aoi_analysis, "fetch_aoi_brief", _fake(_AOI_BRIEF, calls))
    result = _invoke("aoi", "brief", "TestZone")
    assert result.exit_code == 0
    assert calls == [{"name": "TestZone"}]
    assert "AOI Brief: TestZone" in result.output
    assert "Wildfires: FIRMS key missing" in result.output
    # Remote free text in the brief renders literally, never as markup.
    assert "[red]Quaketown[/red]" in result.output


def test_aoi_brief_error_dict_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.aoi_analysis, "fetch_aoi_brief", _fake({"error": "AOI 'X' not found."})
    )
    result = _invoke("aoi", "brief", "X")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "not found" in result.output


def test_aoi_brief_json_mode_passes_raw_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.aoi_analysis, "fetch_aoi_brief", _fake(_AOI_BRIEF))
    result = _invoke("--json-output", "aoi", "brief", "TestZone")
    assert result.exit_code == 0
    assert '"markdown"' in result.output
    assert '"data_gaps"' in result.output


_AOI_ESCALATION = {
    "aoi": {
        "name": "TestZone",
        "lat": 12.5,
        "lon": 45.25,
        "radius_km": 150.0,
        "kind": "circle",
    },
    "score": 42.5,
    "components": {
        "baseline": 0.0,
        "news": None,
        "military": 12.0,
        "conflict": 18.5,
        "social_unrest": 0.4,
        "convergence": None,
    },
    "unavailable_components": ["news", "convergence"],
    "level": "elevated",
    "trend_signal": "rising",
    "data_gaps": ["Military flights: partial coverage: adsb window failed"],
    "source": "aoi-escalation",
    "timestamp": "2026-09-01T00:00:00Z",
}


def test_aoi_escalation_renders_score_components_and_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    monkeypatch.setattr(
        cli.aoi_analysis, "fetch_aoi_escalation", _fake(_AOI_ESCALATION, calls)
    )
    result = _invoke("aoi", "escalation", "TestZone")
    assert result.exit_code == 0
    assert calls == [{"name": "TestZone"}]
    assert "42.5" in result.output
    assert "elevated" in result.output
    assert "rising" in result.output
    assert "18.5" in result.output
    # None components render as unmeasured, never a fabricated 0.0.
    assert "not measured" in result.output
    assert "adsb window failed" in result.output


def test_aoi_escalation_error_dict_is_surfaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli.aoi_analysis, "fetch_aoi_escalation", _fake({"error": "AOI 'X' not found."})
    )
    result = _invoke("aoi", "escalation", "X")
    assert result.exit_code == 0
    assert "Error:" in result.output
    assert "not found" in result.output
    assert '"error"' not in result.output


_AOI_CHANGES_BASELINE = {
    "aoi": {
        "name": "TestZone",
        "lat": 12.5,
        "lon": 45.25,
        "radius_km": 150.0,
        "kind": "circle",
    },
    "baseline": True,
    "previous_taken_at": None,
    "changes": {
        "earthquakes": {"new": [], "departed": [], "unchanged": 3, "baseline": True},
        "news": {"new": [], "departed": [], "unchanged": 1, "baseline": True},
    },
    "counts": {"earthquakes": 3, "news": 1},
    "data_gaps": [],
    "source": "aoi-changes",
    "timestamp": "2026-09-01T00:00:00Z",
}

_AOI_CHANGES_DIFF = {
    "aoi": {
        "name": "TestZone",
        "lat": 12.5,
        "lon": 45.25,
        "radius_km": 150.0,
        "kind": "circle",
    },
    "baseline": False,
    "previous_taken_at": "2026-09-01T10:00:00Z",
    "changes": {
        "earthquakes": {
            "new": [{"key": "eq-new", "summary": "M5.1 Quaketown (12 km)"}],
            "departed": [{"key": "eq-old", "summary": "M4.2 Oldplace (99 km)"}],
            "unchanged": 2,
        },
        "military_flights": {
            "new": [],
            "departed": [],
            "unchanged": 0,
            "baseline": True,
        },
    },
    "counts": {"earthquakes": 3, "military_flights": 0},
    "data_gaps": ["News: RSS down"],
    "source": "aoi-changes",
    "timestamp": "2026-09-01T12:00:00Z",
}


def test_aoi_changes_baseline_then_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.aoi_analysis, "fetch_aoi_changes", _fake(_AOI_CHANGES_BASELINE)
    )
    result = _invoke("aoi", "changes", "TestZone")
    assert result.exit_code == 0
    # First sweep is a baseline: nothing may be claimed new or departed.
    assert "Baseline established" in result.output
    assert "M5.1" not in result.output
    assert "departed" not in result.output.lower()

    monkeypatch.setattr(cli.aoi_analysis, "fetch_aoi_changes", _fake(_AOI_CHANGES_DIFF))
    result = _invoke("aoi", "changes", "TestZone")
    assert result.exit_code == 0
    assert "Baseline established" not in result.output
    assert "2026-09-01T10:00:00Z" in result.output
    assert "M5.1 Quaketown (12 km)" in result.output
    assert "M4.2 Oldplace (99 km)" in result.output
    assert "News: RSS down" in result.output
    # A domain first seen this sweep reads as baseline, not as churn.
    assert "military_flights" in result.output


def test_aoi_changes_error_dict_json_mode_passes_raw_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli.aoi_analysis, "fetch_aoi_changes", _fake({"error": "store exploded"})
    )
    result = _invoke("--json-output", "aoi", "changes", "TestZone")
    assert result.exit_code == 0
    assert '"error"' in result.output
    assert "store exploded" in result.output


# ---------------------------------------------------------------------------
# News vs market reaction
# ---------------------------------------------------------------------------

# Rows trimmed from a live run on 2026-10-17 (technology and energy feeds).
_NEWS_REACTION = {
    "company_reactions": [
        {
            "story": {"headline": "British watchdog seeks tougher terms around Microsoft's dominance"},
            "entity": {"type": "company", "name": "Microsoft"},
            "symbol": "MSFT",
            "benchmark": "SPY",
            "session_date": "2026-10-16",
            "status": "measured",
            "stock_return_pct": -1.9261,
            "benchmark_return_pct": -1.1065,
            "excess_return_pct": -0.8196,
        },
        {
            "story": {"headline": "Aramco CEO Warns Oil Squeeze is [red]Serious[/red]"},
            "entity": {"type": "company", "name": "Aramco"},
            "symbol": "2222.SR",
            "benchmark": "^TASI",
            "status": "data_gap",
            "gap": "no daily bars for benchmark ^TASI",
        },
    ],
    "country_reactions": [
        {
            "story": {"headline": "China Adjusts VAT Exemption For Exported Vehicles"},
            "entity": {"type": "country", "iso3": "CHN", "name": "China"},
            "symbol": "000001.SS",
            "session_date": "2026-10-16",
            "status": "measured",
            "index_return_pct": 0.2376,
            "zscore": 0.73,
        },
        {
            "story": {"headline": "India becomes the latest country to report rogue AI agent activity"},
            "entity": {"type": "country", "iso3": "IND", "name": "India"},
            "symbol": "^NSEI",
            "status": "pending",
            "gap": "no ^NSEI session on or after 2026-10-17 yet (last bar 2026-10-16)",
        },
    ],
    "unmapped": [{"story": "x", "entity": {"name": "Openai"}, "reason": "no public listing"}],
    "excluded": [
        {
            "story": "Shell fire hits border town",
            "entity": {"type": "company", "name": "Shell"},
            "reason": "'shell' is also an artillery round",
        }
    ],
    "summary": {"stories_considered": 146, "stories_with_entities": 22, "unmapped": 1, "excluded": 1},
    "data_gaps": ["^TASI: Yahoo chart returned no data (request failed or symbol unknown)"],
    "interpretation": "Same-session co-movement only. This is not a trading signal.",
}


def test_news_reaction_renders_rows_gaps_and_options(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.analysis.news_market as news_market

    calls: list = []
    monkeypatch.setattr(news_market, "fetch_news_market_reaction", _fake(_NEWS_REACTION, calls))
    result = _invoke("news-reaction", "-c", "finance", "--limit", "80", "--min-size", "1")
    assert result.exit_code == 0
    assert calls == [{"category": "finance", "limit": 80, "min_cluster_size": 1, "include_countries": True}]
    out = result.output
    assert "146 stories, 22 naming a company or country; 1 unmapped, 1 excluded as ambiguous" in out
    assert "not a trading signal" in out
    assert "MSFT vs SPY" in out
    assert "-1.93%" in out and "-1.11%" in out and "-0.82%" in out
    assert "+0.24%" in out and "+0.73" in out
    # A gap renders n/a and its reason, never a 0% move
    assert "data_gap: no daily bars for benchmark ^TASI" in out
    assert "pending: no ^NSEI session on or after 2026-10-17" in out
    assert "+0.00%" not in out and "-0.00%" not in out
    assert "n/a" in out
    # Remote headline markup renders literally
    assert "[red]Serious[/red]" in out
    assert "Excluded: Shell" in out
    assert "Gap: ^TASI: Yahoo chart returned no data" in out


def test_news_reaction_lists_unmapped_names(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.analysis.news_market as news_market

    no_listing = "no public listing in the entity table (private or unlisted)"
    no_index = "no primary index mapped for RUS in the table intel_country_stocks uses"
    data = {
        **_NEWS_REACTION,
        "unmapped": [
            {"story": "a", "entity": {"type": "company", "name": "Openai"}, "reason": no_listing},
            {"story": "b", "entity": {"type": "company", "name": "Openai"}, "reason": no_listing},
            {"story": "c", "entity": {"type": "country", "name": "Russia"}, "reason": no_index},
        ],
    }
    monkeypatch.setattr(news_market, "fetch_news_market_reaction", _fake(data))
    result = _invoke("news-reaction")
    assert result.exit_code == 0
    out = " ".join(result.output.split())
    assert f"Unmapped: Openai (2 stories): {no_listing}" in out
    assert f"Unmapped: Russia: {no_index}" in out


def test_news_reaction_no_countries_skips_country_table(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.analysis.news_market as news_market

    calls: list = []
    monkeypatch.setattr(news_market, "fetch_news_market_reaction", _fake(_NEWS_REACTION, calls))
    result = _invoke("news-reaction", "--no-countries")
    assert result.exit_code == 0
    assert calls[0]["include_countries"] is False
    assert "Countries" not in result.output
    assert "China Adjusts VAT" not in result.output


def test_news_reaction_error_dict_and_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import world_intel_mcp.analysis.news_market as news_market

    err = {"error": "news feed returned no items; nothing to measure (feeds down or empty)"}
    monkeypatch.setattr(news_market, "fetch_news_market_reaction", _fake(err))
    result = _invoke("news-reaction")
    assert result.exit_code == 0
    assert "Error: news feed returned no items" in result.output
    assert "Companies" not in result.output

    monkeypatch.setattr(news_market, "fetch_news_market_reaction", _fake(_NEWS_REACTION))
    result = _invoke("--json-output", "news-reaction")
    assert result.exit_code == 0
    assert '"excess_return_pct": -0.8196' in result.output
    assert "Companies" not in result.output


def test_news_reaction_shows_window_story_time_and_age_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    """The prior session and the story's exchange-local time are on the
    row, so a return over more than one session cannot pass unseen."""
    import world_intel_mcp.analysis.news_market as news_market

    apple = {
        "story": {"headline": "Apple foldable iPhones sell out in hours",
                  "first_published": "2026-10-15T20:30:00Z"},
        "entity": {"type": "company", "name": "Apple"},
        "symbol": "AAPL",
        "benchmark": "SPY",
        "published_local": "2026-10-15T16:30:00-04:00",
        "session_date": "2026-10-16",
        "prior_session_date": "2026-10-15",
        "status": "measured",
        "stock_return_pct": 0.4269,
        "benchmark_return_pct": -1.1065,
        "excess_return_pct": 1.5334,
    }
    data = {
        **_NEWS_REACTION,
        "company_reactions": [apple],
        "summary": {**_NEWS_REACTION["summary"], "stories_dropped_by_age": 3, "max_age_hours": 168.0},
    }
    calls: list = []
    monkeypatch.setattr(news_market, "fetch_news_market_reaction", _fake(data, calls))
    result = _invoke("news-reaction", "--max-age-hours", "24")
    assert result.exit_code == 0
    assert calls[0]["max_age_hours"] == 24.0
    out = result.output
    assert "from 2026-10-15" in out
    assert "story 2026-10-15T16:30:00-04:00" in out
    assert "3 stories older than 168 h left out" in out
    assert "+0.43%" in out and "+1.53%" in out
