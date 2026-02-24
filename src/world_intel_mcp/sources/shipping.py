"""Shipping stress index source for world-intel-mcp.

Tracks dry bulk shipping ETFs via Yahoo Finance to compute a freight
stress index. Reuses _fetch_yahoo_quote from markets.py.
No additional API keys required.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher
from .markets import _fetch_yahoo_quote

logger = logging.getLogger("world-intel-mcp.sources.shipping")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SHIPPING_SYMBOLS: dict[str, str] = {
    "BDRY": "Breakwave Dry Bulk Shipping ETF",
    "SBLK": "Star Bulk Carriers",
    "EGLE": "Eagle Bulk Shipping",
    "ZIM": "ZIM Integrated Shipping",
}

# Stress thresholds: if average daily change exceeds these, flag stress
_STRESS_THRESHOLDS: list[tuple[float, str]] = [
    (5.0, "extreme"),
    (3.0, "high"),
    (1.5, "elevated"),
    (0.5, "moderate"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_shipping_index(fetcher: Fetcher) -> dict:
    """Compute a shipping stress index from dry bulk ETF quotes.

    Fetches BDRY, SBLK, EGLE, ZIM from Yahoo Finance, computes an
    aggregate stress score (0-100) based on price volatility.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.

    Returns:
        Dict with quotes, stress_score, assessment, signals, source.
    """
    now = datetime.now(timezone.utc)

    tasks = [
        _fetch_yahoo_quote(fetcher, sym, f"shipping:quote:{sym}", 300)
        for sym in _SHIPPING_SYMBOLS
    ]
    results = await asyncio.gather(*tasks)

    quotes: list[dict] = []
    change_pcts: list[float] = []

    for sym, quote in zip(_SHIPPING_SYMBOLS, results):
        if quote is None:
            continue
        change_pct = quote.get("change_pct")
        quotes.append({
            "symbol": sym,
            "name": _SHIPPING_SYMBOLS[sym],
            "price": quote.get("price"),
            "change_pct": change_pct,
        })
        if change_pct is not None:
            change_pcts.append(abs(change_pct))

    # Compute stress score (0-100)
    if change_pcts:
        avg_change = sum(change_pcts) / len(change_pcts)
        # Scale: 0% change = 0 stress, 10%+ change = 100 stress
        stress_score = min(100, round(avg_change * 10, 1))
    else:
        avg_change = 0.0
        stress_score = 0.0

    # Assessment
    assessment = "low"
    for threshold, label in _STRESS_THRESHOLDS:
        if avg_change >= threshold:
            assessment = label
            break

    # Signals
    signals: list[str] = []
    for q in quotes:
        pct = q.get("change_pct")
        if pct is not None and abs(pct) > 3.0:
            direction = "up" if pct > 0 else "down"
            signals.append(f"{q['symbol']} {direction} {abs(pct):.1f}%")

    return {
        "quotes": quotes,
        "stress_score": stress_score,
        "assessment": assessment,
        "signals": signals,
        "source": "yahoo-finance",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
