"""Central bank policy rates from FRED and curated data.

Fetches the Federal Funds Rate, ECB deposit rate, and other major central
bank policy rates.  Uses FRED API when available (free key), falls back to
a curated static dataset for non-FRED banks.
"""

import logging
import os
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.central_banks")


# ---------------------------------------------------------------------------
# FRED series IDs for central bank rates
# ---------------------------------------------------------------------------

_FRED_RATE_SERIES: dict[str, dict] = {
    "fed_funds": {
        "series_id": "DFF",
        "bank": "Federal Reserve",
        "country": "USA",
        "currency": "USD",
        "label": "Federal Funds Rate",
    },
    "ecb_deposit": {
        "series_id": "ECBDFR",
        "bank": "European Central Bank",
        "country": "EUR",
        "currency": "EUR",
        "label": "ECB Deposit Facility Rate",
    },
    "boe_bank_rate": {
        "series_id": "IUDSOIA",
        "bank": "Bank of England",
        "country": "GBR",
        "currency": "GBP",
        "label": "BoE Bank Rate (SONIA)",
    },
}

_FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

# ---------------------------------------------------------------------------
# Curated fallback rates (updated periodically)
# These are the most recent known policy rates for banks not on FRED.
# ---------------------------------------------------------------------------

_CURATED_RATES: list[dict] = [
    {"bank": "Bank of Japan", "country": "JPN", "currency": "JPY",
     "label": "BoJ Policy Rate", "rate": 0.50, "as_of": "2025-01-24",
     "notes": "Short-term policy rate target"},
    {"bank": "People's Bank of China", "country": "CHN", "currency": "CNY",
     "label": "PBoC LPR 1Y", "rate": 3.10, "as_of": "2025-01-20",
     "notes": "1-year Loan Prime Rate"},
    {"bank": "Reserve Bank of India", "country": "IND", "currency": "INR",
     "label": "RBI Repo Rate", "rate": 6.50, "as_of": "2025-02-07",
     "notes": "Policy repo rate"},
    {"bank": "Reserve Bank of Australia", "country": "AUS", "currency": "AUD",
     "label": "RBA Cash Rate", "rate": 4.35, "as_of": "2024-11-05",
     "notes": "Cash rate target"},
    {"bank": "Bank of Canada", "country": "CAN", "currency": "CAD",
     "label": "BoC Overnight Rate", "rate": 3.25, "as_of": "2024-12-11",
     "notes": "Target for the overnight rate"},
    {"bank": "Swiss National Bank", "country": "CHE", "currency": "CHF",
     "label": "SNB Policy Rate", "rate": 0.50, "as_of": "2024-12-12",
     "notes": "SNB policy rate"},
    {"bank": "Central Bank of Brazil", "country": "BRA", "currency": "BRL",
     "label": "BCB SELIC", "rate": 13.25, "as_of": "2025-01-29",
     "notes": "SELIC target rate"},
    {"bank": "Bank of Korea", "country": "KOR", "currency": "KRW",
     "label": "BoK Base Rate", "rate": 3.00, "as_of": "2025-01-16",
     "notes": "Base rate"},
    {"bank": "Central Bank of Turkey", "country": "TUR", "currency": "TRY",
     "label": "CBRT Policy Rate", "rate": 45.00, "as_of": "2025-01-23",
     "notes": "1-week repo rate"},
    {"bank": "South African Reserve Bank", "country": "ZAF", "currency": "ZAR",
     "label": "SARB Repo Rate", "rate": 7.75, "as_of": "2024-11-21",
     "notes": "Repurchase rate"},
    {"bank": "Banco de México", "country": "MEX", "currency": "MXN",
     "label": "Banxico Target Rate", "rate": 10.00, "as_of": "2025-02-06",
     "notes": "Overnight interbank rate target"},
    {"bank": "Bank Indonesia", "country": "IDN", "currency": "IDR",
     "label": "BI Rate", "rate": 5.75, "as_of": "2025-01-15",
     "notes": "BI-Rate"},
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _fetch_fred_rate(fetcher: Fetcher, series_id: str, meta: dict) -> dict | None:
    """Fetch latest observation for a FRED series."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return None

    data = await fetcher.get_json(
        _FRED_API_URL,
        source="fred",
        cache_key=f"central_banks:fred:{series_id}",
        cache_ttl=3600,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "1",
        },
    )

    if data is None:
        return None

    try:
        obs = data["observations"][0]
        value = obs.get("value", ".")
        if value == ".":
            return None
        return {
            "bank": meta["bank"],
            "country": meta["country"],
            "currency": meta["currency"],
            "label": meta["label"],
            "rate": float(value),
            "as_of": obs.get("date"),
            "source": "fred",
        }
    except (KeyError, IndexError, TypeError, ValueError):
        logger.warning("FRED parse error for %s", series_id)
        return None


async def fetch_central_bank_rates(fetcher: Fetcher) -> dict:
    """Fetch policy rates for 15 major central banks.

    Uses FRED API for Fed, ECB, and BoE when FRED_API_KEY is set.
    Falls back to curated static data for all other banks.

    Returns::

        {"rates": [{bank, country, currency, rate, as_of, source}],
         "count": int, "source": "multi", "timestamp": "<iso>"}
    """
    import asyncio

    # Try FRED for the banks we have series for
    fred_tasks = []
    for key, meta in _FRED_RATE_SERIES.items():
        fred_tasks.append(_fetch_fred_rate(fetcher, meta["series_id"], meta))

    fred_results = await asyncio.gather(*fred_tasks)

    rates: list[dict] = []
    fred_banks: set[str] = set()

    for result in fred_results:
        if result is not None:
            rates.append(result)
            fred_banks.add(result["bank"])

    # Add curated rates (skip any that FRED already provided)
    for entry in _CURATED_RATES:
        if entry["bank"] not in fred_banks:
            rates.append({**entry, "source": "curated"})

    # If FRED was unavailable, add curated versions of FRED banks too
    fred_curated_fallback = [
        {"bank": "Federal Reserve", "country": "USA", "currency": "USD",
         "label": "Federal Funds Rate", "rate": 4.50, "as_of": "2025-01-29",
         "notes": "Fed funds target rate (upper bound)"},
        {"bank": "European Central Bank", "country": "EUR", "currency": "EUR",
         "label": "ECB Deposit Facility Rate", "rate": 2.75, "as_of": "2025-01-30",
         "notes": "Deposit facility rate"},
        {"bank": "Bank of England", "country": "GBR", "currency": "GBP",
         "label": "BoE Bank Rate", "rate": 4.50, "as_of": "2025-02-06",
         "notes": "Bank rate"},
    ]
    for entry in fred_curated_fallback:
        if entry["bank"] not in fred_banks:
            rates.append({**entry, "source": "curated"})

    # Sort by rate descending (most hawkish first)
    rates.sort(key=lambda r: r.get("rate", 0), reverse=True)

    return {
        "rates": rates,
        "count": len(rates),
        "fred_available": bool(os.environ.get("FRED_API_KEY")),
        "source": "multi",
        "timestamp": _utc_now_iso(),
    }
