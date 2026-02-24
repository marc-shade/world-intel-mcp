"""Financial market data sources for world-intel-mcp.

Provides async functions for equities, crypto, stablecoins, ETF flows,
sector heatmaps, and macro signals.  Every function takes a Fetcher
instance as its first argument and returns a dict (or None-safe partial
results when individual upstream calls fail).
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.markets")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INDEX_SYMBOLS = ["^GSPC", "^DJI", "^IXIC", "^FTSE", "^N225", "^HSI", "^GDAXI"]

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

_COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
_COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

_STABLECOIN_IDS = "tether,usd-coin,dai,first-digital-usd"
_STABLECOIN_DEPEG_THRESHOLD = 0.005  # 0.5%

_BTC_ETF_SYMBOLS = ["IBIT", "FBTC", "GBTC", "ARKB", "BITB"]

_SECTOR_ETFS: dict[str, str] = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLC": "Communication",
    "XLY": "Consumer Disc",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLB": "Materials",
}

_COMMODITY_SYMBOLS: dict[str, str] = {
    "GC=F": "Gold",
    "SI=F": "Silver",
    "CL=F": "Crude Oil WTI",
    "BZ=F": "Brent Crude",
    "NG=F": "Natural Gas",
    "ZC=F": "Corn",
    "ZW=F": "Wheat",
    "ZS=F": "Soybeans",
}

_FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
_MEMPOOL_FEES_URL = "https://mempool.space/api/v1/fees/recommended"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _fetch_yahoo_quote(fetcher: Fetcher, symbol: str, cache_key: str, cache_ttl: int) -> dict | None:
    """Fetch a single Yahoo Finance v8 chart quote and extract meta fields."""
    url = _YAHOO_CHART_URL.format(symbol=symbol)
    data = await fetcher.get_json(
        url,
        source="yahoo-finance",
        cache_key=cache_key,
        cache_ttl=cache_ttl,
        params={"range": "1d", "interval": "5m"},
        yahoo_rate_limit=True,
    )
    if data is None:
        return None

    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        change_pct = meta.get("regularMarketChangePercent")
        # Yahoo v8 chart often omits regularMarketChangePercent — compute from previousClose
        if change_pct is None and price is not None:
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            if prev and prev > 0:
                change_pct = round(((price - prev) / prev) * 100, 4)
        return {
            "symbol": symbol,
            "price": price,
            "change_pct": change_pct,
            "currency": meta.get("currency"),
        }
    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected Yahoo chart structure for %s", symbol)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_market_quotes(fetcher: Fetcher, symbols: list[str] | None = None) -> dict:
    """Fetch major index quotes from Yahoo Finance.

    Returns::

        {"quotes": [...], "source": "yahoo-finance", "timestamp": "<iso>"}
    """
    symbols = symbols or _DEFAULT_INDEX_SYMBOLS

    tasks = [
        _fetch_yahoo_quote(fetcher, sym, f"markets:quotes:{sym}", 120)
        for sym in symbols
    ]
    results = await asyncio.gather(*tasks)

    quotes = [q for q in results if q is not None]
    return {
        "quotes": quotes,
        "source": "yahoo-finance",
        "timestamp": _utc_now_iso(),
    }


async def fetch_crypto_quotes(fetcher: Fetcher, limit: int = 20) -> dict:
    """Fetch top crypto coins by market cap from CoinGecko.

    Returns::

        {"coins": [...], "source": "coingecko", "timestamp": "<iso>"}
    """
    data = await fetcher.get_json(
        _COINGECKO_MARKETS_URL,
        source="coingecko",
        cache_key=f"markets:crypto:{limit}",
        cache_ttl=180,
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": str(limit),
            "sparkline": "true",
            "price_change_percentage": "1h,24h,7d",
        },
    )

    coins: list[dict] = []
    if data is not None and isinstance(data, list):
        for coin in data:
            coins.append({
                "id": coin.get("id"),
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "current_price": coin.get("current_price"),
                "market_cap": coin.get("market_cap"),
                "price_change_percentage_24h": coin.get("price_change_percentage_24h"),
                "sparkline_in_7d": coin.get("sparkline_in_7d"),
            })

    return {
        "coins": coins,
        "source": "coingecko",
        "timestamp": _utc_now_iso(),
    }


async def fetch_stablecoin_status(fetcher: Fetcher) -> dict:
    """Detect stablecoin de-peg events via CoinGecko.

    Returns::

        {"stablecoins": [{id, price, peg_deviation_pct, is_depegged}], ...}
    """
    data = await fetcher.get_json(
        _COINGECKO_MARKETS_URL,
        source="coingecko",
        cache_key="markets:stablecoins",
        cache_ttl=180,
        params={
            "vs_currency": "usd",
            "ids": _STABLECOIN_IDS,
            "sparkline": "false",
        },
    )

    stablecoins: list[dict] = []
    if data is not None and isinstance(data, list):
        for coin in data:
            price = coin.get("current_price")
            if price is not None:
                deviation = abs(price - 1.0) / 1.0
                stablecoins.append({
                    "id": coin.get("id"),
                    "price": price,
                    "peg_deviation_pct": round(deviation * 100, 4),
                    "is_depegged": deviation > _STABLECOIN_DEPEG_THRESHOLD,
                })

    return {
        "stablecoins": stablecoins,
        "source": "coingecko",
        "timestamp": _utc_now_iso(),
    }


async def fetch_etf_flows(fetcher: Fetcher) -> dict:
    """Fetch BTC spot ETF volume and price changes from Yahoo Finance.

    Returns::

        {"etfs": [{symbol, price, change_pct, volume}], ...}
    """
    tasks = [
        _fetch_yahoo_quote(fetcher, sym, f"markets:etf_flows:{sym}", 600)
        for sym in _BTC_ETF_SYMBOLS
    ]
    results = await asyncio.gather(*tasks)

    # Re-fetch with volume info (chart meta includes volume in some responses,
    # but we need the raw data).  We already have price/change from the helper;
    # pull volume from the same cached chart payload.
    etfs: list[dict] = []
    for sym, quote in zip(_BTC_ETF_SYMBOLS, results):
        if quote is None:
            continue
        # Volume: re-read from cache (already populated by _fetch_yahoo_quote)
        cached = fetcher.cache.get(f"markets:etf_flows:{sym}")
        volume = None
        if cached is not None:
            try:
                meta = cached["chart"]["result"][0]["meta"]
                volume = meta.get("regularMarketVolume")
            except (KeyError, IndexError, TypeError):
                pass
        etfs.append({
            "symbol": sym,
            "price": quote["price"],
            "change_pct": quote["change_pct"],
            "volume": volume,
        })

    return {
        "etfs": etfs,
        "source": "yahoo-finance",
        "timestamp": _utc_now_iso(),
    }


async def fetch_commodity_quotes(fetcher: Fetcher) -> dict:
    """Fetch commodity futures quotes from Yahoo Finance.

    Covers gold, silver, crude oil (WTI & Brent), natural gas, corn,
    wheat, and soybeans.  Reuses ``_fetch_yahoo_quote`` for parallel
    fetching with built-in caching.

    Returns::

        {"commodities": [{symbol, name, price, change_pct}], ...}
    """
    tasks = [
        _fetch_yahoo_quote(fetcher, sym, f"markets:commodity:{sym}", 300)
        for sym in _COMMODITY_SYMBOLS
    ]
    results = await asyncio.gather(*tasks)

    commodities: list[dict] = []
    for sym, quote in zip(_COMMODITY_SYMBOLS, results):
        if quote is None:
            continue
        commodities.append({
            "symbol": sym,
            "name": _COMMODITY_SYMBOLS[sym],
            "price": quote["price"],
            "change_pct": quote["change_pct"],
        })

    return {
        "commodities": commodities,
        "count": len(commodities),
        "source": "yahoo-finance",
        "timestamp": _utc_now_iso(),
    }


async def fetch_sector_heatmap(fetcher: Fetcher) -> dict:
    """Fetch sector ETF performance for a market heatmap.

    Returns::

        {"sectors": [{symbol, name, price, change_pct}], ...}
    """
    tasks = [
        _fetch_yahoo_quote(fetcher, sym, f"markets:sector_heatmap:{sym}", 300)
        for sym in _SECTOR_ETFS
    ]
    results = await asyncio.gather(*tasks)

    sectors: list[dict] = []
    for sym, quote in zip(_SECTOR_ETFS, results):
        if quote is None:
            continue
        sectors.append({
            "symbol": sym,
            "name": _SECTOR_ETFS[sym],
            "price": quote["price"],
            "change_pct": quote["change_pct"],
        })

    return {
        "sectors": sectors,
        "source": "yahoo-finance",
        "timestamp": _utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# Macro Signals (aggregated dashboard)
# ---------------------------------------------------------------------------

async def _fetch_fear_greed(fetcher: Fetcher) -> dict | None:
    data = await fetcher.get_json(
        _FEAR_GREED_URL,
        source="alternative-me",
        cache_key="markets:macro:fear_greed",
        cache_ttl=300,
    )
    if data is None:
        return None
    try:
        entry = data["data"][0]
        return {
            "value": int(entry["value"]),
            "classification": entry.get("value_classification"),
            "source": "alternative-me",
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def _fetch_mempool_fees(fetcher: Fetcher) -> dict | None:
    data = await fetcher.get_json(
        _MEMPOOL_FEES_URL,
        source="mempool",
        cache_key="markets:macro:mempool_fees",
        cache_ttl=300,
    )
    if data is None:
        return None
    return {
        "fastest_fee": data.get("fastestFee"),
        "half_hour_fee": data.get("halfHourFee"),
        "hour_fee": data.get("hourFee"),
        "economy_fee": data.get("economyFee"),
        "minimum_fee": data.get("minimumFee"),
        "source": "mempool",
    }


async def _fetch_yahoo_macro_symbol(fetcher: Fetcher, symbol: str, label: str) -> dict | None:
    quote = await _fetch_yahoo_quote(
        fetcher, symbol, f"markets:macro:{label}", 300,
    )
    if quote is None:
        return None
    return {
        "symbol": symbol,
        "price": quote["price"],
        "change_pct": quote["change_pct"],
        "source": "yahoo-finance",
    }


async def _fetch_btc_dominance(fetcher: Fetcher) -> dict | None:
    data = await fetcher.get_json(
        _COINGECKO_GLOBAL_URL,
        source="coingecko",
        cache_key="markets:macro:btc_dominance",
        cache_ttl=300,
    )
    if data is None:
        return None
    try:
        btc_pct = data["data"]["market_cap_percentage"]["btc"]
        return {
            "btc_dominance_pct": round(btc_pct, 2),
            "source": "coingecko",
        }
    except (KeyError, TypeError):
        return None


async def fetch_macro_signals(fetcher: Fetcher) -> dict:
    """Aggregate 7 macro signals into a single dashboard payload.

    Each signal is fetched independently -- a failure in one does not
    affect the others.

    Returns::

        {"signals": {"fear_greed": {...}, "mempool_fees": {...}, ...},
         "source": "multi", "timestamp": "<iso>"}
    """
    (
        fear_greed,
        mempool_fees,
        dxy,
        vix,
        gold,
        treasury_10y,
        btc_dominance,
    ) = await asyncio.gather(
        _fetch_fear_greed(fetcher),
        _fetch_mempool_fees(fetcher),
        _fetch_yahoo_macro_symbol(fetcher, "DX-Y.NYB", "dxy"),
        _fetch_yahoo_macro_symbol(fetcher, "^VIX", "vix"),
        _fetch_yahoo_macro_symbol(fetcher, "GC=F", "gold"),
        _fetch_yahoo_macro_symbol(fetcher, "^TNX", "treasury_10y"),
        _fetch_btc_dominance(fetcher),
    )

    return {
        "signals": {
            "fear_greed": fear_greed,
            "mempool_fees": mempool_fees,
            "dxy": dxy,
            "vix": vix,
            "gold": gold,
            "treasury_10y": treasury_10y,
            "btc_dominance": btc_dominance,
        },
        "source": "multi",
        "timestamp": _utc_now_iso(),
    }
