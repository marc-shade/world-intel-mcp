#!/usr/bin/env python3
"""
intel — CLI for World Intelligence MCP.

Calls source functions directly (no MCP protocol overhead).

Two rendering conventions keep the output honest:

- Every data command routes upstream failures through _bail_on_error:
  one red "Error:" line in table mode, the raw dict in --json-output
  mode. An outage never renders as a healthy empty table or a raw JSON
  dump at a table-mode user.
- Remote free text (names, titles, places, descriptions) is
  injection-safe: table cells go through _cell (rich.text.Text renders
  literally), console lines through rich.markup.escape, and values
  deliberately styled with markup escape only the interpolated part.
  Config/enum-derived scalars (region keys, static dataset fields) and
  numerically formatted values stay as-is.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import click
from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box

from .analysis import aoi as aoi_analysis
from .cache import Cache
from .circuit_breaker import CircuitBreaker
from .fetcher import Fetcher
from .sources import (
    markets,
    economic,
    seismology,
    wildfire,
    conflict,
    military,
    infrastructure,
    maritime,
    climate,
    news,
    intelligence,
    prediction,
    displacement,
    migration,
    aviation,
    cyber,
    shipping,
    social,
    nuclear,
    space_weather,
    ai_watch,
    elections,
    health,
    sanctions,
)
from .sources.central_banks import fetch_central_bank_rates
from .sources.usni_fleet import fetch_usni_fleet
from .sources.hacker_news import fetch_hacker_news
from .sources.github_trending import fetch_trending_repos
from .sources.arxiv_papers import fetch_arxiv_papers
from .sources.usa_spending import fetch_usa_spending
from .sources import geospatial
from .sources import liquidity
from .sources import kalshi as kalshi_src
from .sources import prediction_cross

console = Console()

# Shared infrastructure — lazily initialized
_fetcher: Fetcher | None = None


def _get_fetcher() -> Fetcher:
    global _fetcher
    if _fetcher is None:
        cache = Cache()
        breaker = CircuitBreaker()
        _fetcher = Fetcher(cache=cache, breaker=breaker)
    return _fetcher


def _run(coro: Any) -> Any:
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)


def _print_json(data: dict) -> None:
    """Print raw JSON if --json flag, otherwise formatted."""
    console.print_json(json.dumps(data, default=str))


def _bail_on_error(ctx: click.Context, data: dict) -> bool:
    """True when the command should stop rendering.

    In --json-output mode the raw dict (error included) is printed
    unchanged. In table mode an upstream {"error": ...} is printed in red
    so an outage is never shape-identical to a quiet world ("0
    earthquakes", "No market data available"). Degraded-but-partial
    payloads carry no top-level "error" key and fall through to normal
    rendering.
    """
    if ctx.obj.get("json"):
        _print_json(data)
        return True
    if "error" in data:
        console.print(f"[red]Error:[/red] {escape(str(data['error']))}")
        return True
    return False


def _cell(value: Any) -> Text:
    """Table cell for remote data: renders literally, never as markup.

    A bracketed sequence in an upstream value ("Coast of [/] Chile",
    "[red]fake[/red]") must neither vanish into Rich's markup parser nor
    raise MarkupError. Column-level style/justify still apply to Text
    cells; only content-embedded markup is neutralized. Cells that
    deliberately wrap a remote value in markup keep the markup and
    escape() the interpolated value instead.
    """
    return Text(str(value))


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def main(ctx: click.Context, json_output: bool) -> None:
    """World Intelligence CLI — real-time global intelligence."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------


@main.command(name="markets")
@click.option("--symbols", "-s", multiple=True, help="Ticker symbols")
@click.pass_context
def markets_cmd(ctx: click.Context, symbols: tuple[str, ...]) -> None:
    """Stock market index quotes."""
    f = _get_fetcher()
    sym_list = list(symbols) if symbols else None
    data = _run(markets.fetch_market_quotes(f, symbols=sym_list))

    if _bail_on_error(ctx, data):
        return

    quotes = data.get("quotes", [])
    if not quotes:
        console.print("[yellow]No market data available[/yellow]")
        return

    table = Table(title="Market Indices", box=box.SIMPLE_HEAVY)
    table.add_column("Symbol", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Change %", justify="right")
    table.add_column("Currency")

    for q in quotes:
        chg = q.get("change_pct") or 0
        price = q.get("price") or 0
        style = "green" if chg >= 0 else "red"
        table.add_row(
            _cell(q.get("symbol", "?")),
            f"{price:,.2f}",
            f"[{style}]{chg:+.2f}%[/{style}]",
            _cell(q.get("currency", "")),
        )
    console.print(table)


@main.command()
@click.option("--limit", "-n", default=20, help="Number of coins")
@click.pass_context
def crypto(ctx: click.Context, limit: int) -> None:
    """Top cryptocurrency prices."""
    f = _get_fetcher()
    data = _run(markets.fetch_crypto_quotes(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    coins = data.get("coins", [])
    if not coins:
        console.print("[yellow]No crypto data available[/yellow]")
        return

    table = Table(title=f"Top {limit} Cryptocurrencies", box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Symbol", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("24h %", justify="right")
    table.add_column("Market Cap", justify="right")

    for i, c in enumerate(coins[:limit], 1):
        chg = c.get("price_change_percentage_24h", 0) or 0
        style = "green" if chg >= 0 else "red"
        mcap = c.get("market_cap", 0) or 0
        table.add_row(
            str(i),
            _cell(c.get("symbol", "?").upper()),
            f"${c.get('current_price', 0):,.2f}",
            f"[{style}]{chg:+.2f}%[/{style}]",
            f"${mcap:,.0f}",
        )
    console.print(table)


def _num(v: object, fmt: str) -> str:
    """Format a number; pass strings through (ADS-B altitude is "ground")."""
    if isinstance(v, str):
        return v
    return format(v or 0, fmt)


@main.command()
@click.pass_context
def macro(ctx: click.Context) -> None:
    """7-signal macro dashboard."""
    f = _get_fetcher()
    data = _run(markets.fetch_macro_signals(f))

    if _bail_on_error(ctx, data):
        return

    signals = data.get("signals", {})
    table = Table(title="Macro Signals", box=box.SIMPLE_HEAVY)
    table.add_column("Signal", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Detail")

    for name, info in signals.items():
        if info is None:
            table.add_row(_cell(name), "[dim]unavailable[/dim]", "")
        elif isinstance(info, dict):
            val = info.get("value", info.get("price", "?"))
            detail = info.get("classification", info.get("label", ""))
            if "fastest_fee" in info:
                val = f"{info['fastest_fee']} sat/vB"
                detail = (
                    f"30m {info.get('half_hour_fee', '?')} / "
                    f"1h {info.get('hour_fee', '?')} / "
                    f"eco {info.get('economy_fee', '?')}"
                )
            elif "btc_dominance_pct" in info:
                val = f"{info['btc_dominance_pct']}%"
                detail = "BTC dominance"
            table.add_row(_cell(name), _cell(val), _cell(detail))
        else:
            table.add_row(_cell(name), _cell(info), "")
    console.print(table)


# ---------------------------------------------------------------------------
# Economic
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def energy(ctx: click.Context) -> None:
    """Oil and natural gas prices (EIA)."""
    f = _get_fetcher()
    data = _run(economic.fetch_energy_prices(f))

    if _bail_on_error(ctx, data):
        return

    oil = data.get("oil", {})
    gas = data.get("natural_gas", {})
    table = Table(title="Energy Prices", box=box.SIMPLE_HEAVY)
    table.add_column("Commodity", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Date")

    for name, info in [
        ("Brent Crude", oil.get("brent")),
        ("WTI Crude", oil.get("wti")),
        ("Natural Gas", gas),
    ]:
        if info and isinstance(info, dict):
            table.add_row(
                name, _cell(f"${info.get('price', '?')}"), _cell(info.get("date", ""))
            )
    console.print(table)


@main.command("gas-prices")
@click.pass_context
def gas_prices(ctx: click.Context) -> None:
    """US retail gasoline & diesel prices (AAA, daily)."""
    f = _get_fetcher()
    data = _run(economic.fetch_gas_prices(f))

    if _bail_on_error(ctx, data):
        return

    prices = data.get("prices", {})
    table = Table(title="US Gas Prices — Today (AAA)", box=box.SIMPLE_HEAVY)
    table.add_column("Grade", style="bold")
    table.add_column("$/gallon", justify="right")
    table.add_column("DoD", justify="right")
    table.add_column("WoW", justify="right")

    grade_labels = {
        "regular": "Regular",
        "mid_grade": "Mid-Grade",
        "premium": "Premium",
        "diesel": "Diesel",
    }
    for grade, label in grade_labels.items():
        info = prices.get(grade)
        if info and isinstance(info, dict):
            price = info.get("price_per_gallon", 0)
            dod = info.get("change_pct")
            wow = info.get("week_ago_pct")
            dod_str = (
                f"[{'green' if dod >= 0 else 'red'}]{dod:+.2f}%[/]"
                if dod is not None
                else "—"
            )
            wow_str = (
                f"[{'green' if wow >= 0 else 'red'}]{wow:+.2f}%[/]"
                if wow is not None
                else "—"
            )
            table.add_row(label, f"${price:.3f}", dod_str, wow_str)
    console.print(table)


@main.command("natgas")
@click.pass_context
def natgas(ctx: click.Context) -> None:
    """US residential natural gas prices (EIA)."""
    f = _get_fetcher()
    data = _run(economic.fetch_residential_natgas_prices(f))

    if _bail_on_error(ctx, data):
        return

    prices = data.get("prices", [])
    table = Table(title="US Residential Natural Gas Prices", box=box.SIMPLE_HEAVY)
    table.add_column("Period", style="bold")
    table.add_column("$/MCF", justify="right")

    for entry in prices:
        table.add_row(_cell(entry.get("period", "")), f"${entry.get('price', '?'):.2f}")
    console.print(table)


@main.command("electricity")
@click.option("--state", "-s", default=None, help="2-letter state code (e.g., CA, TX)")
@click.pass_context
def electricity(ctx: click.Context, state: str | None) -> None:
    """US electricity retail rates (EIA)."""
    f = _get_fetcher()
    data = _run(economic.fetch_electricity_rates(f, state=state))

    if _bail_on_error(ctx, data):
        return

    rates = data.get("rates", {})
    label = data.get("state", "US")
    table = Table(
        title=f"Electricity Rates — {escape(str(label))}", box=box.SIMPLE_HEAVY
    )
    table.add_column("Sector", style="bold")
    table.add_column("cents/kWh", justify="right")
    table.add_column("Period")

    for sector in ("residential", "commercial", "industrial", "all_sectors"):
        info = rates.get(sector)
        if info and isinstance(info, dict):
            table.add_row(
                sector.replace("_", " ").title(),
                f"{info.get('price_cents_kwh', '?'):.2f}",
                _cell(info.get("period", "")),
            )
    console.print(table)


@main.command()
@click.argument("series_id")
@click.option("--limit", "-n", default=30, help="Number of observations")
@click.pass_context
def fred(ctx: click.Context, series_id: str, limit: int) -> None:
    """FRED economic data series (e.g., UNRATE, GDP, CPIAUCSL)."""
    f = _get_fetcher()
    data = _run(economic.fetch_fred_series(f, series_id=series_id, limit=limit))

    if _bail_on_error(ctx, data):
        return

    obs = data.get("observations", [])
    title = data.get("title", series_id)
    # FRED series titles are remote free text — the table title is a
    # markup surface too.
    table = Table(title=f"FRED: {escape(str(title))}", box=box.SIMPLE_HEAVY)
    table.add_column("Date", style="bold")
    table.add_column("Value", justify="right")

    for o in obs[:20]:
        table.add_row(_cell(o.get("date", "")), _cell(o.get("value", "")))
    console.print(table)


# ---------------------------------------------------------------------------
# Natural
# ---------------------------------------------------------------------------


@main.command()
@click.option("--min-mag", "-m", default=4.5, help="Minimum magnitude")
@click.option("--hours", "-h", default=24, help="Lookback hours")
@click.pass_context
def earthquakes(ctx: click.Context, min_mag: float, hours: int) -> None:
    """Recent earthquakes (USGS)."""
    f = _get_fetcher()
    data = _run(seismology.fetch_earthquakes(f, min_magnitude=min_mag, hours=hours))

    if _bail_on_error(ctx, data):
        return

    quakes = data.get("earthquakes", [])
    console.print(
        f"[bold]{data.get('count', 0)} earthquakes[/bold] (M{min_mag}+ in last {hours}h)\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Mag", justify="right", style="bold")
    table.add_column("Location")
    table.add_column("Depth (km)", justify="right")
    table.add_column("Time")
    table.add_column("Alert")

    for q in quakes[:25]:
        mag = q.get("magnitude", 0)
        style = "red bold" if mag >= 6.0 else "yellow" if mag >= 5.0 else ""
        alert = q.get("alert_level") or ""
        table.add_row(
            f"[{style}]{mag:.1f}[/{style}]" if style else f"{mag:.1f}",
            _cell(q.get("place", "Unknown")),
            f"{q.get('depth_km', 0):.1f}",
            _cell(q.get("time", "")[:19]),
            _cell(alert),
        )
    console.print(table)


@main.command()
@click.option("--region", "-r", default=None, help="Region name (e.g., north_america)")
@click.pass_context
def fires(ctx: click.Context, region: str | None) -> None:
    """Active wildfires (NASA FIRMS)."""
    f = _get_fetcher()
    data = _run(wildfire.fetch_wildfires(f, region=region))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('total_fires', 0)} high-confidence fires detected[/bold]\n"
    )

    for reg_name, reg_data in data.get("fires_by_region", {}).items():
        count = reg_data.get("count", 0)
        if count == 0:
            continue
        console.print(f"  [bold]{reg_name}[/bold]: {count} fires")
        for cluster in reg_data.get("top_clusters", [])[:5]:
            console.print(
                f"    ({cluster.get('lat', 0):.1f}, {cluster.get('lon', 0):.1f}) "
                f"— {cluster.get('fire_count', 0)} fires, FRP max {cluster.get('max_frp', 0):.0f}"
            )


# ---------------------------------------------------------------------------
# Conflict
# ---------------------------------------------------------------------------


@main.command()
@click.option("--country", "-c", default=None, help="Country name")
@click.option("--days", "-d", default=7, help="Lookback days")
@click.pass_context
def conflicts(ctx: click.Context, country: str | None, days: int) -> None:
    """Armed conflict events (ACLED)."""
    f = _get_fetcher()
    data = _run(conflict.fetch_acled_events(f, country=country, days=days))

    if _bail_on_error(ctx, data):
        return

    events = data.get("events", [])
    console.print(
        f"[bold]{data.get('count', 0)} conflict events[/bold] (last {days}d)\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Date", style="bold")
    table.add_column("Type")
    table.add_column("Country")
    table.add_column("Location")
    table.add_column("Fatalities", justify="right")

    for e in events[:25]:
        fat = e.get("fatalities", 0) or 0
        style = "red bold" if fat >= 10 else "yellow" if fat > 0 else ""
        fat_str = f"[{style}]{fat}[/{style}]" if style else str(fat)
        table.add_row(
            _cell(str(e.get("event_date", ""))[:10]),
            _cell(e.get("event_type", "")),
            _cell(e.get("country", "")),
            _cell(e.get("location", "")),
            fat_str,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Military
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--bbox", "-b", default=None, help="Bounding box: lamin,lomin,lamax,lomax"
)
@click.pass_context
def flights(ctx: click.Context, bbox: str | None) -> None:
    """Military aircraft tracking (OpenSky)."""
    f = _get_fetcher()
    data = _run(military.fetch_military_flights(f, bbox=bbox))

    if _bail_on_error(ctx, data):
        return

    aircraft = data.get("aircraft", [])
    console.print(f"[bold]{data.get('count', 0)} military aircraft detected[/bold]\n")

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Callsign", style="bold")
    table.add_column("ICAO24")
    table.add_column("Country")
    table.add_column("Alt (m)", justify="right")
    table.add_column("Speed (m/s)", justify="right")

    for a in aircraft[:30]:
        table.add_row(
            _cell(a.get("callsign", "?")),
            _cell(a.get("icao24", "")),
            _cell(a.get("origin_country", "")),
            _num(a.get("altitude_m"), ",.0f"),
            _num(a.get("velocity_ms"), ".0f"),
        )
    console.print(table)


@main.command()
@click.pass_context
def posture(ctx: click.Context) -> None:
    """Military theater posture (5 theaters)."""
    f = _get_fetcher()
    data = _run(military.fetch_theater_posture(f))

    if _bail_on_error(ctx, data):
        return

    theaters = data.get("theaters", {})
    # A theater no flight source answered for used to print 0, the reading
    # of an empty sky, under a total that looked complete.
    unknown = set(data.get("unavailable_theaters") or []) | {
        name for name, info in theaters.items() if info.get("source") == "none"
    }
    total = data.get("total_military_aircraft", 0)
    if unknown:
        console.print(
            f"[bold]{total} military aircraft in the theaters that answered[/bold] "
            f"({len(theaters) - len(unknown)} of {len(theaters)}; the rest are unknown)\n"
        )
    else:
        console.print(f"[bold]{total} total military aircraft[/bold]\n")

    table = Table(title="Theater Posture", box=box.SIMPLE_HEAVY)
    table.add_column("Theater", style="bold")
    table.add_column("Aircraft", justify="right")
    table.add_column("Countries")
    table.add_column("Sample Callsigns")

    for name, info in theaters.items():
        count = info.get("count", 0)
        style = "red bold" if count >= 20 else "yellow" if count >= 5 else ""
        count_str = f"[{style}]{count}[/{style}]" if style else str(count)
        if name in unknown:
            count_str = "[yellow]unknown[/yellow]"
        table.add_row(
            name.replace("_", " ").title(),
            count_str,
            _cell(", ".join(info.get("countries", [])[:5])),
            _cell(", ".join(info.get("sample_callsigns", [])[:3])),
        )
    console.print(table)
    _print_data_gaps(data)


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def outages(ctx: click.Context) -> None:
    """Internet outages (Cloudflare Radar)."""
    f = _get_fetcher()
    data = _run(infrastructure.fetch_internet_outages(f))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('ongoing_count', 0)} ongoing outages[/bold], "
        f"{data.get('total_7d', 0)} in last 7 days\n"
    )

    for o in data.get("outages", [])[:15]:
        ongoing = "[red]ONGOING[/red]" if o.get("is_ongoing") else ""
        countries = ", ".join(o.get("countries", [])[:5]) if o.get("countries") else ""
        console.print(
            f"  {o.get('start', '')[:16]}  {escape(countries)}  "
            f"{escape(o.get('description', '')[:80])}  {ongoing}"
        )


@main.command()
@click.pass_context
def cables(ctx: click.Context) -> None:
    """Undersea cable corridor health (NGA)."""
    f = _get_fetcher()
    data = _run(infrastructure.fetch_cable_health(f))

    if _bail_on_error(ctx, data):
        return

    status_labels = {
        0: "[green]Clear[/green]",
        1: "[yellow]Advisory[/yellow]",
        2: "[red]At Risk[/red]",
        3: "[red bold]Disrupted[/red bold]",
    }

    table = Table(title="Undersea Cable Health", box=box.SIMPLE_HEAVY)
    table.add_column("Corridor", style="bold")
    table.add_column("Status")
    table.add_column("Cables")
    table.add_column("Warnings", justify="right")

    for name, info in data.get("corridors", {}).items():
        score = info.get("status_score", 0)
        table.add_row(
            name.replace("_", " ").title(),
            status_labels.get(score, str(score)),
            _cell(", ".join(info.get("cables", [])[:3])),
            str(len(info.get("relevant_warnings", []))),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Maritime
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--navarea",
    "-n",
    default=None,
    help="NGA area code: 4, 12, A, P or C (IV and XII are accepted for 4 and 12)",
)
@click.pass_context
def warnings(ctx: click.Context, navarea: str | None) -> None:
    """Navigational warnings (NGA Maritime Safety)."""
    f = _get_fetcher()
    data = _run(maritime.fetch_nav_warnings(f, navarea=navarea))

    if _bail_on_error(ctx, data):
        if not ctx.obj.get("json"):
            _print_data_gaps(data)
        return

    if data.get("feed_stale"):
        # The live feed's newest warning dates from May 2024; without this
        # line the list read as current conditions.
        console.print(
            "[yellow bold]STALE:[/yellow bold] newest warning issued "
            f"{escape(str(data.get('newest_issue_date')))} "
            f"({data.get('newest_issue_age_days')} days ago; threshold "
            f"{data.get('stale_after_days')} days)"
        )
    console.print(f"[bold]{data.get('count', 0)} active warnings[/bold]\n")
    _print_data_gaps(data)

    by_area = data.get("by_navarea", {})
    if by_area:
        console.print(
            "  By NAVAREA: " + ", ".join(f"{k}:{v}" for k, v in sorted(by_area.items()))
        )
        console.print()

    for w in data.get("warnings", [])[:20]:
        area = escape(f"[{w.get('navarea', '?')}]")
        console.print(
            f"  {area} {escape(w.get('id', ''))}  {escape(w.get('text', '')[:100])}"
        )


# ---------------------------------------------------------------------------
# Climate
# ---------------------------------------------------------------------------


@main.command(name="climate")
@click.pass_context
def climate_cmd(ctx: click.Context) -> None:
    """Climate anomalies (15 global zones vs. prior year)."""
    f = _get_fetcher()
    data = _run(climate.fetch_climate_anomalies(f))

    if _bail_on_error(ctx, data):
        return

    zones = data.get("zones", {})
    sig = data.get("significant_anomalies", [])

    # Degraded-but-partial: some zones failed but the rest are usable.
    # Render the data AND a visible warning naming what is missing.
    unavailable = data.get("unavailable_zones", [])
    if unavailable:
        console.print(
            f"[yellow]Warning:[/yellow] {len(unavailable)} zones unavailable "
            f"(Open-Meteo): {escape(', '.join(unavailable))}\n"
        )

    table = Table(title="Climate Anomalies", box=box.SIMPLE_HEAVY)
    table.add_column("Zone", style="bold")
    table.add_column("Temp Anomaly", justify="right")
    table.add_column("Precip Anomaly", justify="right")
    table.add_column("Flag")

    for key, z in zones.items():
        temp_a = z.get("temp_anomaly_c", 0)
        prec_a = z.get("precip_anomaly_pct", 0)
        t_style = "red" if temp_a > 3 else "blue" if temp_a < -3 else ""
        flag = "[red bold]SIG[/red bold]" if key in sig else ""
        t_str = (
            f"[{t_style}]{temp_a:+.1f}C[/{t_style}]" if t_style else f"{temp_a:+.1f}C"
        )
        table.add_row(_cell(z.get("name", key)), t_str, f"{prec_a:+.0f}%", flag)
    console.print(table)


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


@main.command(name="news")
@click.option(
    "--category",
    "-c",
    default=None,
    type=click.Choice(
        [
            "geopolitics",
            "security",
            "technology",
            "finance",
            "military",
            "science",
            "think_tanks",
            "middle_east",
            "asia_pacific",
            "africa",
            "latin_america",
            "multilingual",
            "energy",
            "government",
            "crisis",
            "europe",
            "south_asia",
            "health",
            "central_asia",
            "arctic",
            "maritime",
            "space",
            "nuclear",
            "climate",
        ]
    ),
    help="Category filter",
)
@click.option("--limit", "-n", default=30, help="Max items")
@click.pass_context
def news_cmd(ctx: click.Context, category: str | None, limit: int) -> None:
    """Intelligence news from 119 RSS feeds across 24 categories."""
    f = _get_fetcher()
    data = _run(news.fetch_news_feed(f, category=category, limit=limit))

    if _bail_on_error(ctx, data):
        return

    _print_partial_feed_outage(data)
    items = data.get("items", [])
    if not items:
        console.print("[yellow]No news items available[/yellow]")
        return

    console.print(
        f"[bold]{data.get('count', 0)} items[/bold] from {', '.join(data.get('categories_fetched', []))}\n"
    )

    for item in items:
        # Remote values are escaped so the category label renders
        # literally instead of parsing as a markup tag, and bracketed
        # sequences inside feed titles can't drop text or raise
        # MarkupError.
        cat = escape(f"[{item.get('category', '')}]")
        title = escape(item.get("title", ""))
        feed = escape(item.get("feed_name", ""))
        pub = (item.get("published") or "")[:16]
        console.print(f"  {cat} [bold]{title}[/bold]")
        console.print(f"         {feed} — {pub}")


@main.command()
@click.option("--min-count", "-m", default=3, help="Minimum keyword occurrences")
@click.pass_context
def trending(ctx: click.Context, min_count: int) -> None:
    """Trending keywords from recent news."""
    f = _get_fetcher()
    data = _run(news.fetch_trending_keywords(f, min_count=min_count))

    if _bail_on_error(ctx, data):
        return

    keywords = data.get("keywords", [])
    console.print(
        f"[bold]Trending keywords[/bold] (from {data.get('total_items_analyzed', 0)} items)\n"
    )
    _print_partial_feed_outage(data)

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Keyword", style="bold")
    table.add_column("Count", justify="right")

    for i, kw in enumerate(keywords[:30], 1):
        table.add_row(str(i), _cell(kw["word"]), str(kw["count"]))
    console.print(table)


@main.command()
@click.argument("query", default="conflict")
@click.option(
    "--mode", "-m", default="artlist", type=click.Choice(["artlist", "timelinevol"])
)
@click.option("--limit", "-n", default=20, help="Max records")
@click.pass_context
def gdelt(ctx: click.Context, query: str, mode: str, limit: int) -> None:
    """Search GDELT 2.0 global news database."""
    f = _get_fetcher()
    data = _run(news.fetch_gdelt_search(f, query=query, mode=mode, limit=limit))

    if _bail_on_error(ctx, data):
        return

    if mode == "artlist":
        articles = data.get("articles", [])
        console.print(f"[bold]{len(articles)} articles[/bold] for '{query}'\n")
        for a in articles[:20]:
            title = escape(a.get("title", "")[:80])
            domain = escape(a.get("domain", ""))
            console.print(f"  [bold]{title}[/bold]  ({domain})")
    else:
        console.print(f"[bold]Timeline volume for '{query}'[/bold]")
        _print_json(data)


def _na(value: Any) -> str:
    """A null measurement renders as n/a, never as 0."""
    return "n/a" if value is None else str(value)


def _print_partial_feed_outage(data: dict) -> None:
    """Say when a result rests on a minority of the RSS feeds.

    fetch_news_feed marks that read degraded with no error (reason
    partial_feeds_failed); a total outage carries an error and never
    reaches here (``_bail_on_error``).
    """
    if data.get("degraded") and "error" not in data and data.get("feeds_attempted"):
        console.print(
            f"[yellow]Partial outage:[/yellow] only {data.get('feeds_ok')} of "
            f"{data.get('feeds_attempted')} RSS feeds answered live"
        )


@main.command(name="hostility")
@click.argument("country")
@click.argument("other", required=False)
@click.option("--days", "-d", default=14, help="Days back including today (max 90)")
@click.pass_context
def hostility_cmd(ctx: click.Context, country: str, other: str | None, days: int) -> None:
    """Daily coverage and hostile coverage of a country or pair (GDELT)."""
    from .analysis import news_signals

    f = _get_fetcher()
    data = _run(news_signals.fetch_hostility_timeline(f, country=country, other=other, days=days))

    if _bail_on_error(ctx, data):
        return

    names = " / ".join(p["name"] for p in data.get("parties", []))
    console.print(
        f"[bold]Hostility timeline: {escape(names)}[/bold] "
        f"({data.get('days_requested')} days, resolution {escape(str(data.get('date_resolution')))})\n"
    )
    table = Table(box=box.SIMPLE_HEAVY)
    for col in ("Date", "Articles", "Threat", "Sanction", "Force", "Criticism", "Tone"):
        table.add_column(col, justify="left" if col == "Date" else "right")
    for d in data.get("days", []):
        h = d.get("hostile", {})
        partial_cols = set(d.get("partial_columns") or [])

        def _count(col: str, value: Any) -> str:
            # A count from a column whose buckets miss an elapsed hour.
            return _na(value) + ("*" if value is not None and col in partial_cols else "")

        date = d["date"] + (" *" if d.get("partial") else "") + (" ~" if d.get("in_progress") else "")
        table.add_row(
            date,
            _count("articles", d.get("articles")),
            _count("threat", h.get("threat")),
            _count("sanction", h.get("sanction")),
            _count("force", h.get("force")),
            _count("criticism", h.get("criticism")),
            _na(d.get("tone")),
        )
    console.print(table)
    console.print(
        "[dim]* after a date: partial day; after a count: that column's buckets miss an "
        "elapsed hour; ~ day in progress; n/a = not measured (fetch failed, expired "
        "copy, or day not returned)[/dim]"
    )
    for col, age in (data.get("stale_age_seconds") or {}).items():
        age_text = f"{age / 3600:.1f} h old" if isinstance(age, (int, float)) else "age unknown"
        console.print(
            f"[yellow]Stale:[/yellow] {escape(str(col))} is an expired cached copy "
            f"({age_text}); shown as n/a"
        )
    _print_data_gaps(data)


@main.command(name="situations")
@click.option("--hours", "-H", default=24.0, help="Window length in hours (1 to 168)")
@click.option(
    "--sort", "-s", default="covered", type=click.Choice(["covered", "hostile", "change"])
)
@click.option(
    "--kind", "-k", default="all", type=click.Choice(["all", "between", "inside"])
)
@click.option("--limit", "-n", default=20, help="Max situations")
@click.pass_context
def situations_cmd(ctx: click.Context, hours: float, sort: str, kind: str, limit: int) -> None:
    """Ranked situations between and inside countries (RSS headlines)."""
    from .analysis import news_signals

    f = _get_fetcher()
    data = _run(news_signals.fetch_situations(f, hours=hours, sort=sort, kind=kind, limit=limit))

    if _bail_on_error(ctx, data):
        return

    win = data.get("window", {})
    console.print(
        f"[bold]Situations[/bold] by {data.get('sort_applied', sort)}, window "
        f"{win.get('current', {}).get('start', '?')} .. {win.get('current', {}).get('end', '?')}\n"
    )
    _print_partial_feed_outage(data)
    if data.get("change_measured") is False:
        # n/a in the Change column, never +0.
        console.print(
            "[yellow]Change not measured[/yellow] (no feed covers both windows); "
            "the Change column shows n/a"
        )
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Kind")
    table.add_column("Countries", style="bold")
    table.add_column("Articles", justify="right")
    table.add_column("Hostile", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Outlets", justify="right")
    table.add_column("Headline")
    for i, s in enumerate(data.get("situations", []), 1):
        heads = s.get("sample_headlines") or [{}]
        table.add_row(
            str(i),
            s["kind"],
            _cell(" / ".join(c["name"] for c in s.get("countries", []))),
            str(s["articles"]),
            str(s["hostile_articles"]),
            _signed(s["change"]),
            str(s["outlet_count"]),
            _cell((heads[0].get("title") or "")[:70]),
        )
    console.print(table)
    _print_data_gaps(data)


@main.command(name="top-stories")
@click.option("--hours", "-H", default=24.0, help="Window length in hours (1 to 168)")
@click.option("--min-outlets", "-m", default=3, help="Minimum distinct outlets per story")
@click.option("--limit", "-n", default=10, help="Max stories")
@click.pass_context
def top_stories_cmd(ctx: click.Context, hours: float, min_outlets: int, limit: int) -> None:
    """Stories carried by many outlets, plus who gained attention."""
    from .analysis import news_signals

    f = _get_fetcher()
    data = _run(
        news_signals.fetch_top_stories(f, hours=hours, min_outlets=min_outlets, limit=limit)
    )

    if _bail_on_error(ctx, data):
        return

    console.print(f"[bold]Top stories[/bold] (>= {min_outlets} outlets)\n")
    _print_partial_feed_outage(data)
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Outlets", justify="right")
    table.add_column("Articles", justify="right")
    table.add_column("Headline", style="bold")
    for i, s in enumerate(data.get("stories", []), 1):
        table.add_row(str(i), str(s["outlet_count"]), str(s["articles"]), _cell(s["headline"][:90]))
    console.print(table)

    attention = data.get("attention", [])
    if attention:
        att = Table(title="Attention (growth vs prior window)", box=box.SIMPLE_HEAVY)
        att.add_column("Name", style="bold")
        att.add_column("Type")
        att.add_column("Now", justify="right")
        att.add_column("Prior", justify="right")
        att.add_column("Change", justify="right")
        for a in attention:
            att.add_row(
                _cell(a["name"]),
                a["type"],
                str(a["current_comparable"]),
                str(a["prior"]),
                _signed(a["change"]),
            )
        console.print(att)
    elif data.get("attention_change_measured") is False:
        # An empty list here is not "nothing grew".
        console.print(
            "[yellow]Attention:[/yellow] not measured (no feed covers both windows)"
        )
    _print_data_gaps(data)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


@main.command()
@click.option("--limit", "-n", default=20, help="Number of markets")
@click.pass_context
def predictions(ctx: click.Context, limit: int) -> None:
    """Prediction market movers (Polymarket)."""
    f = _get_fetcher()
    data = _run(prediction.fetch_prediction_markets(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    _print_data_gaps(data)
    mkts = data.get("markets", [])
    if not mkts:
        console.print("[yellow]No prediction market data available[/yellow]")
        return

    title = "Prediction Markets (expired cached copy)" if data.get("stale") else "Prediction Markets"
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Question", max_width=50)
    table.add_column("YES %", justify="right")
    table.add_column("Sentiment")
    table.add_column("24h Vol", justify="right")

    for m in mkts:
        yes_pct = (m.get("yes_probability", 0) or 0) * 100
        sentiment = m.get("sentiment", "")
        vol = m.get("volume_24h", 0) or 0
        s_style = (
            "green" if "yes" in sentiment else "red" if "no" in sentiment else "yellow"
        )
        table.add_row(
            _cell(m.get("question", "")[:50]),
            f"{yes_pct:.0f}%",
            f"[{s_style}]{escape(str(sentiment))}[/{s_style}]",
            f"${vol:,.0f}",
        )
    console.print(table)


def _pct(value: Any) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _stale_note(m: dict) -> str:
    """" (expired copy, N h old)" for a market priced from expired cache."""
    if not m.get("stale"):
        return ""
    age = m.get("stale_age_seconds")
    return f" (expired copy, {age / 3600:.1f} h old)" if isinstance(age, (int, float)) else " (expired copy)"


def _last_trade_note(side: dict) -> str | None:
    """The Kalshi last-trade lookup result for the Flags column."""
    status = side.get("last_trade_lookup")
    if status is None and not side.get("last_trade_time"):
        return None
    if side.get("last_trade_time"):
        price = side.get("last_trade_price")
        at = f" at {_pct(price)}" if price is not None else ""
        copy = " (expired copy)" if status == "found_in_expired_copy" else ""
        return f"kalshi last trade {side['last_trade_time']}{at}{copy}"
    return f"kalshi last trade: {str(status).replace('_', ' ')}"


# Data gaps print through the shared _print_data_gaps defined with the
# AOI commands below (module-level, resolved at call time).


@main.command()
@click.option("--category", "-c", default=None, help="Kalshi category, e.g. Economics")
@click.option("--series", "-s", default=None, help="Kalshi series ticker, e.g. KXFED")
@click.option("--limit", "-n", default=20, help=f"Number of markets (max {kalshi_src.MAX_RESULTS})")
@click.option(
    "--pages", default=3, help=f"Unfiltered scan: pages of 200 open events (max {kalshi_src.MAX_PAGES})"
)
@click.pass_context
def kalshi(ctx: click.Context, category: str | None, series: str | None, limit: int, pages: int) -> None:
    """Kalshi open markets by volume (public market data)."""
    f = _get_fetcher()
    data = _run(
        kalshi_src.fetch_kalshi_markets(f, category=category, series=series, limit=limit, pages=pages)
    )

    if _bail_on_error(ctx, data):
        return

    _print_data_gaps(data)
    mkts = data.get("markets", [])
    if not mkts:
        console.print(
            f"[yellow]No traded Kalshi markets in the scanned set "
            f"({data.get('scan', {}).get('events_scanned', 0)} events)[/yellow]"
        )
        return

    table = Table(title="Kalshi Markets", box=box.SIMPLE_HEAVY)
    table.add_column("Market", max_width=55)
    table.add_column("YES side", max_width=25)
    table.add_column("YES", justify="right")
    table.add_column("Basis")
    table.add_column("24h Vol", justify="right")
    table.add_column("Volume", justify="right")
    for m in mkts:
        # Wrapped, not sliced: a ladder's rows differ only at the end
        # ("... at their October 2026 meeting?" vs "... December ...").
        table.add_row(
            _cell(m.get("question") or ""),
            _cell(m.get("yes_side") or ""),
            _pct(m.get("probability")),
            _cell(m.get("price_basis", "") + _stale_note(m)),
            f"{m.get('volume_24h', 0):,.0f}",
            f"{m.get('volume', 0):,.0f}",
        )
    console.print(table)
    console.print(f"[dim]{escape(data.get('units', {}).get('price', ''))}[/dim]")


@main.command("prediction-compare")
@click.option("--category", "-c", default=None, help="Kalshi category, e.g. Economics")
@click.option("--series", "-s", default=None, help="Kalshi series ticker")
@click.option(
    "--polymarket-limit", default=300,
    help=f"Polymarket open markets to compare (max {prediction.MAX_OPEN_MARKETS})",
)
@click.option("--min-confidence", default=0.6, help="Match threshold 0..1")
@click.option("--limit", "-n", default=25, help=f"Matched pairs to show (max {prediction_cross.MAX_PAIRS})")
@click.pass_context
def prediction_compare(
    ctx: click.Context,
    category: str | None,
    series: str | None,
    polymarket_limit: int,
    min_confidence: float,
    limit: int,
) -> None:
    """Same event on Kalshi and Polymarket, side by side."""
    f = _get_fetcher()
    data = _run(
        prediction_cross.fetch_prediction_compare(
            f,
            category=category,
            series=series,
            polymarket_limit=polymarket_limit,
            min_confidence=min_confidence,
            limit=limit,
        )
    )

    if _bail_on_error(ctx, data):
        return

    _print_data_gaps(data)
    comparable = data.get("comparable_count")
    console.print(
        f"Compared {data.get('kalshi_markets_compared', 0)} Kalshi / "
        f"{data.get('polymarket_markets_compared', 0)} Polymarket markets: "
        f"{data.get('matched_count', 0)} matched, unmatched Kalshi "
        f"{data.get('unmatched_kalshi')}, unmatched Polymarket {data.get('unmatched_polymarket')}"
        + ("" if comparable is None else f"; {comparable} comparable (both prices live two-sided quotes)")
    )
    pairs = data.get("matched", [])
    if not pairs:
        console.print(
            f"[yellow]No pair reached match confidence {data.get('min_confidence')}[/yellow]"
        )
        return

    table = Table(title="Cross-venue Matches", box=box.SIMPLE_HEAVY)
    table.add_column("Kalshi", max_width=40)
    table.add_column("Polymarket", max_width=40)
    table.add_column("Score", justify="right")
    table.add_column("Kalshi YES", justify="right")
    table.add_column("Poly YES", justify="right")
    table.add_column("Gap", justify="right")
    table.add_column("Flags", max_width=40)
    flagged = False
    for p in pairs:
        gap = p.get("price_gap")
        flags = list(p.get("flags") or [])
        flagged = flagged or bool(flags)
        traded = _last_trade_note(p.get("kalshi") or {})
        if traded:
            flags.append(traded)
        table.add_row(  # wrapped, not sliced (see the kalshi table)
            _cell(p.get("kalshi", {}).get("question") or ""),
            _cell(p.get("polymarket", {}).get("question") or ""),
            f"{p.get('match_confidence', 0):.2f}",
            _pct(p.get("kalshi_yes_probability")),
            _pct(p.get("polymarket_yes_probability")),
            "-" if gap is None else f"{gap * 100:+.1f}pp",
            _cell("; ".join(flags) or "-"),
        )
    console.print(table)
    console.print("Score: ordinal match score for ranking pairs, not a probability.")
    if flagged:
        console.print(
            "Flagged pairs are listed after comparable ones: a flagged gap is not a like-for-like "
            "difference of two live quotes on the same terms."
        )


@main.command("prediction-settled")
@click.option("--limit", "-n", default=25, help=f"Settled markets per venue (max {kalshi_src.MAX_SETTLED})")
@click.option(
    "--offset", "offsets", multiple=True, type=float,
    help=(
        f"Hours before close (repeatable, up to {prediction_cross.MAX_OFFSETS} values of at most "
        f"{prediction_cross.MAX_OFFSET_HOURS}; default 24 and 168)"
    ),
)
@click.option("--kalshi-category", default="Economics", help="Kalshi sample category")
@click.option("--kalshi-series", default=None, help="Kalshi sample series ticker")
@click.pass_context
def prediction_settled(
    ctx: click.Context,
    limit: int,
    offsets: tuple[float, ...],
    kalshi_category: str,
    kalshi_series: str | None,
) -> None:
    """Settled markets scored against pre-close prices (Brier)."""
    f = _get_fetcher()
    data = _run(
        prediction_cross.fetch_prediction_settled(
            f,
            limit=limit,
            offsets_hours=list(offsets) or None,
            kalshi_category=kalshi_category,
            kalshi_series=kalshi_series,
        )
    )

    if _bail_on_error(ctx, data):
        return

    _print_data_gaps(data)
    # One table per venue: the samples are different markets with
    # different reference times, so their rows must not read as comparable.
    for venue, entry in (data.get("venues") or {}).items():
        if not entry.get("scores"):
            reason = entry.get("error") or entry.get("not_scored_reason") or "no scores returned"
            console.print(f"{escape(venue)}: not scored ({escape(reason)})")
            continue
        table = Table(title=f"Brier scores, {escape(venue)} sample only", box=box.SIMPLE_HEAVY)
        table.add_column("Offset")
        table.add_column("n", justify="right")
        table.add_column("Events", justify="right")
        table.add_column("Brier", justify="right")
        table.add_column("YES rate", justify="right")
        table.add_column("Excluded", no_wrap=True)
        for label, sc in entry["scores"].items():
            brier = sc.get("brier")
            excluded = ", ".join(f"{k}: {v}" for k, v in (sc.get("excluded") or {}).items())
            table.add_row(
                _cell(label),
                str(sc.get("n", 0)),
                str(sc.get("distinct_events", 0)),
                "-" if brier is None else f"{brier:.4f}",
                _pct(sc.get("yes_rate")),
                _cell(excluded or "-"),
            )
        console.print(table)
        if entry.get("reference_time"):
            console.print(f"{escape(venue)} reference time: {escape(entry['reference_time'])}")
    console.print(escape(data.get("comparability", "")))


# ---------------------------------------------------------------------------
# Displacement
# ---------------------------------------------------------------------------


@main.command(name="displacement")
@click.option("--year", "-y", default=None, type=int, help="Reporting year")
@click.pass_context
def displacement_cmd(ctx: click.Context, year: int | None) -> None:
    """UNHCR displacement statistics."""
    f = _get_fetcher()
    data = _run(displacement.fetch_displacement_summary(f, year=year))

    if _bail_on_error(ctx, data):
        return

    totals = data.get("global_totals", {})
    console.print(f"[bold]Global Displacement ({data.get('year', '?')})[/bold]")
    console.print(f"  Grand total: {totals.get('grand_total', 0):,}\n")

    by_origin = data.get("by_origin", [])
    table = Table(title="Top Countries of Origin", box=box.SIMPLE_HEAVY)
    table.add_column("Country", style="bold")
    table.add_column("Total Displaced", justify="right")
    table.add_column("Refugees", justify="right")
    table.add_column("IDPs", justify="right")

    for c in by_origin[:15]:
        table.add_row(
            _cell(c.get("country", "")),
            f"{c.get('total_displaced', 0):,}",
            f"{c.get('refugees', 0):,}",
            f"{c.get('internally_displaced', 0):,}",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def _signed(value: Any) -> str:
    return "n/a" if value is None else f"{value:+,}"


@main.command(name="migration-flows")
@click.option("--year", "-y", default=None, type=int, help="Reporting year (default: latest)")
@click.option("--origin", "-o", default=None, help="Origin country, ISO3 code or region")
@click.option("--destination", "-d", default=None, help="Destination country, ISO3 code or region")
@click.option("--limit", "-n", default=25, help="Max corridors")
@click.option("--min-people", default=0, help="Skip corridors smaller than this")
@click.pass_context
def migration_flows_cmd(
    ctx: click.Context,
    year: int | None,
    origin: str | None,
    destination: str | None,
    limit: int,
    min_people: int,
) -> None:
    """Largest UNHCR origin -> destination corridors (year-end stocks)."""
    f = _get_fetcher()
    data = _run(
        migration.fetch_migration_flows(
            f, year=year, origin=origin, destination=destination,
            limit=limit, min_people=min_people,
        )
    )
    if _bail_on_error(ctx, data):
        return

    filters = [
        f"{label} {escape(sel['name'])}"
        for label, sel in (("from", data.get("origin_filter")), ("to", data.get("destination_filter")))
        if sel
    ]
    console.print(
        f"[bold]Displacement corridors ({data.get('year', '?')})[/bold]"
        + (f" {' '.join(filters)}" if filters else "")
    )
    console.print(
        f"  {data.get('corridor_count', 0):,} corridors, "
        f"{data.get('total_people', 0):,} people\n"
    )
    table = Table(title="Corridors", box=box.SIMPLE_HEAVY)
    table.add_column("Origin", style="bold")
    table.add_column("Destination")
    table.add_column("People", justify="right")
    table.add_column("Change vs prior year", justify="right")
    for c in data.get("corridors", []):
        table.add_row(
            _cell(c.get("origin", "")),
            _cell(c.get("destination", "")),
            f"{c.get('people', 0):,}",
            _signed(c.get("change")),
        )
    console.print(table)


@main.command(name="migration-surges")
@click.option("--year", "-y", default=None, type=int, help="Reporting year (default: latest)")
@click.option("--min-change", default=50_000, help="Smallest year-over-year change to report")
@click.option("--limit", "-n", default=20, help="Max rows per ranking")
@click.pass_context
def migration_surges_cmd(
    ctx: click.Context, year: int | None, min_change: int, limit: int
) -> None:
    """Year-over-year jumps in people displaced from each origin."""
    f = _get_fetcher()
    data = _run(
        migration.fetch_migration_surges(f, year=year, min_change=min_change, limit=limit)
    )
    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]Displacement surges {data.get('compared_with', '?')} -> "
        f"{data.get('year', '?')}[/bold] (min change {data.get('min_change', 0):,})\n"
    )
    for key, title in (
        ("origin_outflow_increases", "Rising outflows by origin"),
        ("origin_outflow_decreases", "Falling outflows by origin"),
    ):
        table = Table(title=title, box=box.SIMPLE_HEAVY)
        table.add_column("Origin", style="bold")
        table.add_column("People abroad", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("% of pop.", justify="right")
        table.add_column("Level")
        for o in data.get(key, []):
            pct = o.get("change_abroad_pct_of_population")
            table.add_row(
                _cell(o.get("origin", "")),
                f"{o.get('people_abroad', 0):,}",
                _signed(o.get("change_abroad")),
                "n/a" if pct is None else f"{pct:+.2f}%",
                o.get("level") or "",
            )
        console.print(table)

    idps = data.get("internal_displacement_increases", [])
    if idps:
        table = Table(title="Rising internal displacement", box=box.SIMPLE_HEAVY)
        table.add_column("Country", style="bold")
        table.add_column("IDPs", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("Note")
        for o in idps:
            table.add_row(
                _cell(o.get("origin", "")), f"{o.get('idps', 0):,}", _signed(o.get("change_idps")),
                "none reported prior year" if o.get("idps_first_reported") else "",
            )
        console.print(table)

    table = Table(title="Rising corridors", box=box.SIMPLE_HEAVY)
    table.add_column("Origin", style="bold")
    table.add_column("Destination")
    table.add_column("People", justify="right")
    table.add_column("Change", justify="right")
    for c in data.get("corridor_increases", []):
        table.add_row(
            _cell(c.get("origin", "")), _cell(c.get("destination", "")),
            f"{c.get('people', 0):,}", _signed(c.get("change")),
        )
    console.print(table)

    for o in data.get("unattributed_origin_changes", []):
        console.print(
            f"  [dim]Not ranked: {escape(str(o.get('origin', '')))} "
            f"{_signed(o.get('change_abroad'))} (not a country; often a host reporting change)[/dim]"
        )
    console.print(f"[dim]Levels are {escape(data.get('levels', {}).get('basis', 'heuristic'))}.[/dim]")


@main.command(name="migration-history")
@click.argument("country")
@click.option(
    "--role", "-r", type=click.Choice(["origin", "host"]), default="origin",
    help="origin = people from the country; host = people it hosts",
)
@click.option("--from", "year_from", default=1951, help="First year")
@click.option("--to", "year_to", default=None, type=int, help="Last year")
@click.pass_context
def migration_history_cmd(
    ctx: click.Context, country: str, role: str, year_from: int, year_to: int | None
) -> None:
    """One country's UNHCR displacement series and its largest waves."""
    f = _get_fetcher()
    data = _run(
        migration.fetch_migration_history(
            f, country=country, role=role, year_from=year_from, year_to=year_to
        )
    )
    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{escape(str(data.get('country', country)))} as {role}[/bold]: "
        f"{escape(str(data.get('meaning', '')))}"
    )
    peak, latest = data.get("peak"), data.get("latest")
    if latest:
        idps = f", {latest.get('idps', 0):,} IDPs" if role == "origin" else ""
        console.print(f"  Latest {latest.get('year')}: {latest.get('people', 0):,} people{idps}")
    if peak:
        console.print(f"  Peak {peak.get('year')}: {peak.get('people', 0):,} people")
    console.print(f"  {data.get('years', 0)} years of data since {data.get('first_year', '?')}\n")

    table = Table(title="Largest waves", box=box.SIMPLE_HEAVY)
    table.add_column("Year", style="bold")
    table.add_column("People", justify="right")
    table.add_column("Increase", justify="right")
    table.add_column("% change", justify="right")
    for w in data.get("largest_waves", []):
        pct = w.get("pct_change")
        table.add_row(
            str(w.get("year", "")), f"{w.get('people', 0):,}", _signed(w.get("increase")),
            "n/a" if pct is None else f"{pct:+.1f}%",
        )
    console.print(table)


@main.command(name="net-migration")
@click.option("--country", "-c", default=None, help="One country: its series since 1960")
@click.option("--region", "-r", default=None, help="World Bank region code or name")
@click.option("--limit", "-n", default=20, help="Max rows per ranking")
@click.pass_context
def net_migration_cmd(
    ctx: click.Context, country: str | None, region: str | None, limit: int
) -> None:
    """World Bank net migration, all reasons (immigrants minus emigrants)."""
    f = _get_fetcher()
    data = _run(
        migration.fetch_net_migration(f, country=country, region=region, limit=limit)
    )
    if _bail_on_error(ctx, data):
        return

    if country:
        latest = data.get("latest") or {}
        console.print(
            f"[bold]Net migration: {escape(str(data.get('country', country)))}[/bold] "
            f"({escape(str(data.get('region', '')))})"
        )
        if latest:
            console.print(
                f"  Latest {latest.get('year')}: {_signed(latest.get('net_migration'))}"
                f" ({latest.get('per_1000')} per 1,000)\n"
            )
        for key, title in (
            ("largest_net_inflow_years", "Largest net inflow years"),
            ("largest_net_outflow_years", "Largest net outflow years"),
        ):
            table = Table(title=title, box=box.SIMPLE_HEAVY)
            table.add_column("Year", style="bold")
            table.add_column("Net migration", justify="right")
            table.add_column("Per 1,000", justify="right")
            for e in data.get(key, []):
                table.add_row(
                    str(e.get("year", "")), _signed(e.get("net_migration")),
                    "n/a" if e.get("per_1000") is None else f"{e['per_1000']:+.2f}",
                )
            console.print(table)
    else:
        scope = escape(str(data.get("region_filter") or "all countries"))
        console.print(f"[bold]Net migration, latest year ({scope})[/bold]\n")
        for key, title in (
            ("top_net_immigration", "Largest net immigration"),
            ("top_net_emigration", "Largest net emigration"),
        ):
            table = Table(title=title, box=box.SIMPLE_HEAVY)
            table.add_column("Country", style="bold")
            table.add_column("Year", justify="right")
            table.add_column("Net migration", justify="right")
            table.add_column("Per 1,000", justify="right")
            for r in data.get(key, []):
                table.add_row(
                    _cell(r.get("name", "")), str(r.get("year", "")),
                    _signed(r.get("net_migration")),
                    "n/a" if r.get("per_1000") is None else f"{r['per_1000']:+.2f}",
                )
            console.print(table)
    console.print("[dim]Source: UN WPP via World Bank; recent years can be projections.[/dim]")


# ---------------------------------------------------------------------------
# Aviation
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def delays(ctx: click.Context) -> None:
    """US airport delays (FAA)."""
    f = _get_fetcher()
    data = _run(aviation.fetch_airport_delays(f))

    if _bail_on_error(ctx, data):
        return

    delayed = data.get("delayed", [])
    console.print(
        f"[bold]{data.get('delayed_count', 0)} airports with delays[/bold] "
        f"(checked {data.get('total_checked', 0)})\n"
    )

    if not delayed:
        console.print("[green]No major airport delays![/green]")
        return

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Airport", style="bold")
    table.add_column("Name")
    table.add_column("Delay Info")

    for d in delayed:
        statuses = d.get("status", [])
        info = (
            "; ".join(
                f"{s.get('type', '')} - {s.get('reason', '')} ({s.get('avg_delay', '')})"
                for s in statuses
            )
            if statuses
            else "Details unavailable"
        )
        table.add_row(
            _cell(d.get("code", "")), _cell(d.get("name", "")), _cell(info[:80])
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Cyber
# ---------------------------------------------------------------------------


@main.command()
@click.option("--limit", "-n", default=30, help="Max threats")
@click.pass_context
def threats(ctx: click.Context, limit: int) -> None:
    """Cyber threat intelligence (4 feeds)."""
    f = _get_fetcher()
    data = _run(cyber.fetch_cyber_threats(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    by_sev = data.get("by_severity", {})
    console.print(
        f"[bold]{data.get('count', 0)} threats[/bold] "
        f"({data.get('feeds_successful', 0)}/{data.get('feeds_attempted', 0)} feeds)"
    )
    console.print(
        f"  [red]Critical: {by_sev.get('critical', 0)}[/red]  "
        f"[yellow]High: {by_sev.get('high', 0)}[/yellow]  "
        f"Medium: {by_sev.get('medium', 0)}  "
        f"[dim]Low: {by_sev.get('low', 0)}[/dim]\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Severity")
    table.add_column("Type")
    table.add_column("Indicator", max_width=40)
    table.add_column("Threat")
    table.add_column("Feed")

    for t in data.get("threats", [])[:limit]:
        sev = t.get("severity", "")
        sev_style = {
            "critical": "red bold",
            "high": "yellow",
            "medium": "",
            "low": "dim",
        }.get(sev, "")
        sev_str = (
            f"[{sev_style}]{escape(str(sev))}[/{sev_style}]"
            if sev_style
            else _cell(sev)
        )
        table.add_row(
            sev_str,
            _cell(t.get("type", "")),
            _cell((t.get("indicator", ""))[:40]),
            _cell((t.get("threat", ""))[:30]),
            _cell(t.get("source_feed", "")),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Intelligence
# ---------------------------------------------------------------------------


@main.command()
@click.argument("country_code", default="US")
@click.pass_context
def brief(ctx: click.Context, country_code: str) -> None:
    """Country intelligence brief (LLM + data)."""
    f = _get_fetcher()
    data = _run(intelligence.fetch_country_brief(f, country_code=country_code))

    if _bail_on_error(ctx, data):
        return

    llm_tag = (
        "[green]LLM[/green]"
        if data.get("llm_available")
        else "[yellow]data-only[/yellow]"
    )
    console.print(f"[bold]Intelligence Brief: {country_code}[/bold] ({llm_tag})\n")
    # LLM-generated free text: escape so bracketed sequences render
    # instead of parsing as markup.
    console.print(escape(str(data.get("brief", "No brief available."))))

    d = data.get("data", {})
    if d.get("gdp") or d.get("recent_events"):
        console.print(
            f"\n[dim]GDP data points: {len(d.get('gdp', []))} | "
            f"Recent conflict events: {d.get('recent_events', 0)}[/dim]"
        )


@main.command()
@click.option("--country", "-c", default="US", help="ISO-2 or ISO-3 country code")
@click.pass_context
def dossier(ctx: click.Context, country: str) -> None:
    """Comprehensive country intelligence dossier."""
    from .analysis.dossier import fetch_country_dossier

    f = _get_fetcher()
    data = _run(fetch_country_dossier(f, country=country))

    if _bail_on_error(ctx, data):
        return

    overview = data.get("overview", {})
    console.print(
        f"[bold]Country Dossier: {overview.get('country', country)}[/bold] "
        f"({overview.get('iso2')}/{overview.get('iso3')})\n"
    )

    # Economy
    econ = data.get("economy", {})
    if "_error" not in econ:
        gdp = econ.get("gdp", [])
        if gdp:
            latest = gdp[0]
            console.print(
                f"[cyan]Economy:[/cyan] GDP {latest.get('year')}: ${latest.get('value', 0) / 1e9:,.1f}B"
            )
        if econ.get("conflict_events_30d"):
            console.print(f"  Conflict events (30d): {econ['conflict_events_30d']}")

    # Markets
    mkt = data.get("markets", {})
    if "ticker" in mkt:
        q = mkt.get("quote", {})
        console.print(
            f"[green]Markets:[/green] {mkt['ticker']} = {q.get('price', 'N/A')} ({q.get('change_pct', 'N/A')}%)"
        )

    # Elections
    elec = data.get("elections", {})
    upcoming = elec.get("upcoming", [])
    if upcoming:
        next_e = upcoming[0]
        console.print(
            f"[yellow]Elections:[/yellow] {escape(str(next_e.get('election_type')))} "
            f"on {next_e.get('date')} (risk: {next_e.get('risk_score', 0):.0f})"
        )

    # Sanctions
    sanc = data.get("sanctions", {})
    if "match_count" in sanc and sanc["match_count"] is None:
        # A failed SDN download is not zero matches.
        console.print("[red]Sanctions:[/red] not screened (SDN list unavailable)")
    elif (sanc.get("match_count") or 0) > 0:
        console.print(f"[red]Sanctions:[/red] {sanc['match_count']} OFAC matches")

    # News
    news = data.get("news", {})
    if "mention_count" in news and news["mention_count"] is None:
        # A failed feed (or a country without keywords) is not zero mentions.
        console.print("[blue]News:[/blue] not measured")
    elif news.get("mention_count_capped"):
        # The listed mentions are capped; the match count is not.
        console.print(
            f"[blue]News:[/blue] {news.get('matching_items')} matching headlines in the "
            f"{news.get('items_searched')} newest items ({news.get('mention_count')} listed)"
        )
    else:
        console.print(f"[blue]News:[/blue] {news.get('mention_count', 0)} recent mentions")
    for art in news.get("mentions", [])[:3]:
        console.print(f"  - {escape(art.get('title', 'N/A')[:80])}")
    _print_data_gaps(news)

    # Security
    sec = data.get("security", {})
    if sec.get("hotspot_count", 0):
        console.print(f"[red]Hotspots:[/red] {sec['hotspot_count']} associated")
    if sec.get("conflict_count", 0):
        console.print(f"[red]Conflicts:[/red] {sec['conflict_count']} active")

    br = overview.get("baseline_risk")
    if br is not None:
        console.print(f"\n[dim]Baseline risk: {br}/100[/dim]")


@main.command()
@click.option("--limit", "-n", default=20, help="Top N countries")
@click.pass_context
def risk(ctx: click.Context, limit: int) -> None:
    """Country risk scores (ACLED-based)."""
    f = _get_fetcher()
    data = _run(intelligence.fetch_risk_scores(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    table = Table(title="Country Risk Scores", box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Country", style="bold")
    table.add_column("Events (30d)", justify="right")
    table.add_column("Risk Score", justify="right")
    table.add_column("Level")

    for i, c in enumerate(data.get("countries", []), 1):
        level = c.get("risk_level", "")
        l_style = {
            "critical": "red bold",
            "elevated": "yellow",
            "moderate": "",
            "low": "dim",
        }.get(level, "")
        l_str = (
            f"[{l_style}]{escape(str(level))}[/{l_style}]" if l_style else _cell(level)
        )
        table.add_row(
            str(i),
            _cell(c.get("country", "")),
            _cell(c.get("events_30d", 0)),
            f"{c.get('risk_score', 0):.0f}",
            l_str,
        )
    console.print(table)


@main.command()
@click.argument("country_code", required=False, default=None)
@click.pass_context
def instability(ctx: click.Context, country_code: str | None) -> None:
    """Country Instability Index (0-100)."""
    f = _get_fetcher()
    data = _run(intelligence.fetch_instability_index(f, country_code=country_code))

    if _bail_on_error(ctx, data):
        return

    if country_code:
        idx = data.get("instability_index", 0)
        level = data.get("risk_level", "")
        # A null index or component was not measured; it is not zero.
        idx_text = "not measured" if idx is None else f"{idx}/100"
        console.print(
            f"[bold]{country_code} Instability Index: {idx_text} ({level})[/bold]\n"
        )
        components = data.get("components", {})
        for name, score in components.items():
            if score is None:
                console.print(f"  {name:30s} not measured")
                continue
            bar = "█" * int(score) + "░" * (20 - int(score))
            console.print(f"  {name:30s} {bar} {score:.1f}/20")
        for gap in data.get("data_gaps") or []:
            console.print(f"  [yellow]gap:[/yellow] {escape(str(gap))}")
    else:
        table = Table(title="Instability Index (Focus Countries)", box=box.SIMPLE_HEAVY)
        table.add_column("Country", style="bold")
        table.add_column("Index", justify="right")
        table.add_column("Events (30d)", justify="right")
        table.add_column("Risk Level")

        for c in data.get("countries", []):
            level = c.get("risk_level", "")
            l_style = {
                "critical": "red bold",
                "high": "yellow",
                "medium": "",
                "low": "dim",
            }.get(level, "")
            l_str = (
                f"[{l_style}]{escape(str(level))}[/{l_style}]"
                if l_style
                else _cell(level)
            )
            table.add_row(
                _cell(f"{c.get('country_name', '')} ({c.get('country_code', '')})"),
                f"{c.get('instability_index', 0):.0f}",
                _cell(c.get("events_30d", 0)),
                l_str,
            )
        console.print(table)


# ---------------------------------------------------------------------------
# Finance (additional)
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def btc(ctx: click.Context) -> None:
    """Bitcoin technical indicators (SMA, Mayer, cross signals)."""
    f = _get_fetcher()
    data = _run(markets.fetch_btc_technicals(f))

    if _bail_on_error(ctx, data):
        return

    console.print(f"[bold]BTC Technicals[/bold]  price: ${data.get('price', 0):,.2f}\n")
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Indicator", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("SMA-50", f"${data.get('sma_50', 0):,.2f}")
    table.add_row(
        "SMA-200", f"${data.get('sma_200', 0):,.2f}" if data.get("sma_200") else "N/A"
    )
    table.add_row(
        "Mayer Multiple",
        f"{data.get('mayer_multiple', 0):.4f}" if data.get("mayer_multiple") else "N/A",
    )
    cross = data.get("cross_signal", "neutral")
    c_style = (
        "green" if cross == "golden_cross" else "red" if cross == "death_cross" else ""
    )
    table.add_row(
        "Cross Signal",
        f"[{c_style}]{escape(str(cross))}[/{c_style}]" if c_style else _cell(cross),
    )
    table.add_row("ATH Distance", f"{data.get('ath_distance_pct', 0):.1f}%")
    table.add_row(
        "7d Change",
        f"{data.get('change_7d_pct', 0):+.2f}%"
        if data.get("change_7d_pct") is not None
        else "N/A",
    )
    table.add_row(
        "30d Change",
        f"{data.get('change_30d_pct', 0):+.2f}%"
        if data.get("change_30d_pct") is not None
        else "N/A",
    )
    console.print(table)


@main.command(name="central-banks")
@click.pass_context
def central_banks_cmd(ctx: click.Context) -> None:
    """Central bank policy rates (15 banks)."""
    f = _get_fetcher()
    data = _run(fetch_central_bank_rates(f))

    if _bail_on_error(ctx, data):
        return

    fred_tag = (
        "[green]FRED[/green]"
        if data.get("fred_available")
        else "[yellow]curated[/yellow]"
    )
    console.print(f"[bold]{data.get('count', 0)} Central Banks[/bold] ({fred_tag})\n")

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Bank", style="bold")
    table.add_column("Country")
    table.add_column("Rate %", justify="right")
    table.add_column("As Of")

    for r in data.get("rates", []):
        rate = r.get("rate", 0)
        style = (
            "red bold"
            if rate >= 10
            else "yellow"
            if rate >= 5
            else "green"
            if rate < 1
            else ""
        )
        rate_str = f"[{style}]{rate:.2f}[/{style}]" if style else f"{rate:.2f}"
        table.add_row(
            _cell(r.get("bank", "")),
            _cell(r.get("country", "")),
            rate_str,
            _cell(r.get("as_of", "")),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Liquidity and money (Phase 29)
# ---------------------------------------------------------------------------


def _liq_num(value: Any, signed: bool = False) -> str:
    """Two decimals, rounded half-up on the value as reported: binary
    float formatting would show 5869.615 as 5,869.61."""
    if value is None:
        return "n/a"
    from decimal import ROUND_HALF_UP, Decimal

    d = Decimal(repr(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{d:+,.2f}" if signed else f"{d:,.2f}"


def _liq_points_table(title: str, points: list[dict], extra: tuple[str, ...] = ()) -> Table:
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Observed", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Units")
    for col in extra:
        table.add_column(col.replace("_", " ").title(), justify="right")
    for p in points:
        table.add_row(
            _cell(p.get("observed_at", "")),
            _liq_num(p.get("value")),
            _cell(p.get("units") or ""),
            *(
                _liq_num(p.get(c)) if isinstance(p.get(c), (int, float)) else _cell(p.get(c) or "")
                for c in extra
            ),
        )
    return table


# Board columns: (header, justify, whole). A whole column holds dates,
# numbers or units and is never wrapped or cut; the text columns fold.
_LIQ_BOARD_COLUMNS = (
    ("Indicator", "left", False), ("Observed", "left", True), ("Latest", "right", True),
    ("Units", "left", True), ("Change", "right", True), ("Change %", "right", True),
    ("Measure", "left", False), ("Status", "left", False),
)
_LIQ_TEXT_MIN_WIDTH = 12


def _liq_board_fits(rows: list[list[str]], width: int) -> bool:
    """Whether the board table fits ``width`` with its whole columns intact
    and each text column at least _LIQ_TEXT_MIN_WIDTH wide (or its full
    width). Narrower, Rich would cut cells or drop text columns (at 80
    columns it dropped Indicator), so the board is printed as a list."""
    need = len(_LIQ_BOARD_COLUMNS) + 1  # table edges and column separators
    for i, (header, _, whole) in enumerate(_LIQ_BOARD_COLUMNS):
        natural = max([cell_len(header)] + [cell_len(row[i]) for row in rows])
        need += (natural if whole else min(natural, _LIQ_TEXT_MIN_WIDTH)) + 2  # cell padding
    return need <= width


@main.command(name="liquidity")
@click.option(
    "--sort", type=click.Choice(["biggest_move", "newest"]), default="biggest_move",
    help=(
        "biggest_move: largest absolute change, in billions of each row's currency "
        "(no FX conversion; percent change does not rank); newest: latest period end"
    ),
)
@click.pass_context
def liquidity_cmd(ctx: click.Context, sort: str) -> None:
    """Liquidity board: Fed balance sheet, TGA, RRP, net liquidity, M2, euro M1-M3."""
    data = _run(liquidity.fetch_liquidity_board(_get_fetcher(), sort=sort))
    if _bail_on_error(ctx, data):
        return
    rows, stale = [], []
    for r in data.get("indicators", []):
        measure = r.get("measure", "")
        stale.append(bool((r.get("freshness") or {}).get("stale")))
        rows.append([
            str(r.get("indicator", "")),
            f"{r.get('observed_at')} (stale)" if stale[-1] else str(r.get("observed_at", "")),
            _liq_num(r.get("latest_value")),
            str(r.get("units") or ""),
            _liq_num(r.get("change"), signed=True),
            _liq_num(r.get("change_pct"), signed=True),
            "stock" if measure == "amount_outstanding" else str(measure),
            str(r.get("status") or ""),
        ])
    title = f"Liquidity board (sorted by {sort})"
    if _liq_board_fits(rows, console.width):
        table = Table(title=title, box=box.SIMPLE_HEAVY)
        for header, justify, whole in _LIQ_BOARD_COLUMNS:
            table.add_column(
                header, justify=justify, no_wrap=whole, overflow="fold",
                style="bold" if header == "Indicator" else None,
            )
        for row, is_stale in zip(rows, stale):
            cells = [_cell(value) for value in row]
            if is_stale:
                cells[1].stylize("yellow")
            table.add_row(*cells)
        console.print(table)
    else:
        console.print(Text(title, style="bold"))
        for row, is_stale in zip(rows, stale):
            indicator, observed, latest, units, change, change_pct, measure, status = row
            console.print(Text(indicator, style="bold"))
            console.print(Padding(Text.assemble(
                f"{latest} {units}, observed ", (observed, "yellow" if is_stale else ""),
                f", change {change} ({change_pct}%), {measure}", f", {status}" if status else "",
            ), (0, 0, 0, 2)))
    if data.get("ranking_rule"):
        console.print(f"[dim]Ranking: {escape(str(data['ranking_rule']))}[/dim]")
    for u in data.get("unavailable", []):
        console.print(
            f"[red]Unavailable:[/red] {escape(str(u.get('indicator')))}: {escape(str(u.get('error')))}"
        )
    for b in data.get("blocked", []):
        console.print(
            f"[dim]Not covered: {escape(str(b.get('measure')))} ({escape(str(b.get('publisher')))}): "
            f"{escape(str(b.get('measured')))}[/dim]"
        )
    _print_data_gaps(data)


@main.command(name="net-liquidity")
@click.option("--limit", "-n", default=12, help="Newest weeks (0 = full history)")
@click.option("--start", default=None, help="Only weeks on or after YYYY-MM-DD")
@click.pass_context
def net_liquidity_cmd(ctx: click.Context, limit: int, start: str | None) -> None:
    """US net liquidity = WALCL - WDTGAL - RRPONTSYD, weekly, USD billions."""
    data = _run(liquidity.fetch_net_liquidity(_get_fetcher(), limit=limit, start=start))
    if _bail_on_error(ctx, data):
        return
    console.print(f"[bold]{escape(str(data.get('formula', '')))}[/bold]")
    console.print(f"[dim]{escape(str(data.get('alignment', '')))}[/dim]\n")
    console.print(
        _liq_points_table(
            "US net liquidity",
            data.get("points", []),
            ("fed_total_assets", "treasury_general_account", "reverse_repo", "reverse_repo_observed_at"),
        )
    )
    _print_data_gaps(data)


@main.command(name="money-supply")
@click.option(
    "--region", type=click.Choice(["all", "us", "euro_area"]), default="all",
    help="US M2, euro area M1/M2/M3, or both",
)
@click.option("--limit", "-n", default=6, help="Newest months per series (0 = full history)")
@click.pass_context
def money_supply_cmd(ctx: click.Context, region: str, limit: int) -> None:
    """Money supply: US M2 and euro area M1/M2/M3, never summed."""
    data = _run(liquidity.fetch_money_supply(_get_fetcher(), region=region, limit=limit))
    if _bail_on_error(ctx, data):
        return
    us = data.get("us")
    if us is not None:
        m2 = us.get("M2", {})
        if "error" in m2:
            console.print(f"[red]US M2 unavailable:[/red] {escape(str(m2['error']))}")
        else:
            console.print(_liq_points_table("US M2 (FRED M2SL, seasonally adjusted)", m2.get("points", [])))
        console.print(f"[dim]{escape(str(us.get('M3', {}).get('note', '')))}[/dim]")
    ea = data.get("euro_area")
    if ea is not None:
        if "error" in ea:
            console.print(f"[red]Euro area unavailable:[/red] {escape(str(ea['error']))}")
        else:
            for name, roles in ea.get("aggregates", {}).items():
                for role, s in roles.items():
                    console.print(
                        _liq_points_table(f"Euro area {name} {role}", s.get("points", []), ("status",))
                    )
    console.print(f"[dim]{escape(str(data.get('note', '')))}[/dim]")
    _print_data_gaps(data)


@main.command(name="fed-liquidity")
@click.argument("series_id", type=click.Choice(sorted(liquidity.FRED_SERIES), case_sensitive=False))
@click.option("--limit", "-n", default=20, help="Newest points (0 = full history)")
@click.option("--start", default=None, help="Only points on or after YYYY-MM-DD")
@click.pass_context
def fed_liquidity_cmd(ctx: click.Context, series_id: str, limit: int, start: str | None) -> None:
    """One keyless FRED liquidity series (WALCL, WDTGAL, WTREGEN, RRPONTSYD, M2SL)."""
    data = _run(
        liquidity.fetch_fed_liquidity_series(
            _get_fetcher(), series_id=series_id, limit=limit, start=start
        )
    )
    if _bail_on_error(ctx, data):
        return
    console.print(
        _liq_points_table(
            f"{data.get('label')} ({data.get('series_id')}, {data.get('frequency')}, {data.get('measure')})",
            data.get("points", []),
        )
    )
    _print_data_gaps(data)


@main.command(name="ecb-series")
@click.argument("key")
@click.option("--dataset", "-d", type=click.Choice(sorted(liquidity.ECB_DATASETS)), default="BSI")
@click.option("--limit", "-n", default=12, help="Newest points per series (0 = full history)")
@click.option("--start", default=None, help="Only points on or after YYYY-MM-DD, not after today (UTC)")
@click.pass_context
def ecb_series_cmd(
    ctx: click.Context, key: str, dataset: str, limit: int, start: str | None
) -> None:
    """ECB Data Portal series by SDMX key (BSI money, ILM Eurosystem balance sheet)."""
    data = _run(
        liquidity.fetch_ecb_series(_get_fetcher(), dataset=dataset, key=key, limit=limit, start=start)
    )
    if _bail_on_error(ctx, data):
        return
    for s in data.get("series", []):
        # ECB titles are remote free text: escape them in the table title.
        title = escape(f"{s.get('title') or s.get('key')} ({s.get('measure')})")
        console.print(_liq_points_table(title, s.get("points", []), ("status",)))
    _print_data_gaps(data)


@main.command(name="shipping")
@click.pass_context
def shipping_cmd(ctx: click.Context) -> None:
    """Shipping index (BDI, tanker, container ETFs)."""
    f = _get_fetcher()
    data = _run(shipping.fetch_shipping_index(f))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]Shipping Stress: {data.get('assessment', '?')}[/bold] "
        f"(score: {data.get('stress_score', 0):.0f}/100)\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Symbol", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Change %", justify="right")

    for q in data.get("quotes", []):
        chg = q.get("change_pct") or 0
        style = "green" if chg >= 0 else "red"
        table.add_row(
            _cell(q.get("symbol", "")),
            f"${q.get('price', 0):,.2f}",
            f"[{style}]{chg:+.2f}%[/{style}]",
        )
    console.print(table)


def _signed_pct(value: Any) -> str:
    """A measured percent, coloured; a missing one says so, never 0%."""
    if value is None:
        return "[dim]n/a[/dim]"
    style = "green" if value >= 0 else "red"
    return f"[{style}]{value:+.2f}%[/{style}]"


def _session_cell(row: dict) -> Text:
    """Session date, the prior session the return starts from, and the
    story's exchange-local time, so a return over more than one session
    or a misplaced story time shows on the row."""
    lines = [str(row.get("session_date") or "-")]
    if row.get("prior_session_date"):
        lines.append(f"from {row['prior_session_date']}")
    story_time = row.get("published_local") or row.get("story", {}).get("first_published")
    if story_time:
        lines.append(f"story {story_time}")
    return _cell("\n".join(lines))


@main.command(name="news-reaction")
@click.option("--category", "-c", default=None, help="RSS category (finance, technology, energy, ...)")
@click.option("--limit", "-n", default=150, type=int, help="News items to cluster (max 300)")
@click.option("--min-size", default=2, type=int, help="Minimum articles per story (1 includes single-article stories)")
@click.option("--max-age-hours", default=None, type=float, help="Leave out stories older than this (default 168)")
@click.option("--no-countries", is_flag=True, help="Skip the country-index rows")
@click.pass_context
def news_reaction(
    ctx: click.Context,
    category: str | None,
    limit: int,
    min_size: int,
    max_age_hours: float | None,
    no_countries: bool,
) -> None:
    """Market move on the session of each story naming a company or country."""
    from .analysis.news_market import fetch_news_market_reaction

    kwargs: dict[str, Any] = {}
    if max_age_hours is not None:
        kwargs["max_age_hours"] = max_age_hours
    data = _run(
        fetch_news_market_reaction(
            _get_fetcher(),
            category=category,
            limit=limit,
            min_cluster_size=min_size,
            include_countries=not no_countries,
            **kwargs,
        )
    )
    if _bail_on_error(ctx, data):
        return

    s = data.get("summary", {})
    dropped = s.get("stories_dropped_by_age") or 0
    aged_out = (
        f"; {dropped} stories older than {s.get('max_age_hours', 0):g} h left out" if dropped else ""
    )
    console.print(
        f"[bold]News vs market reaction[/bold]: {s.get('stories_considered', 0)} stories, "
        f"{s.get('stories_with_entities', 0)} naming a company or country; "
        f"{s.get('unmapped', 0)} unmapped, {s.get('excluded', 0)} excluded as ambiguous{aged_out}"
    )
    console.print(f"[dim]{escape(str(data.get('interpretation', '')))}[/dim]\n")

    table = Table(title="Companies", box=box.SIMPLE_HEAVY)
    table.add_column("Story", max_width=48)
    table.add_column("Company", style="bold")
    table.add_column("Ticker")
    table.add_column("Session")
    table.add_column("Stock", justify="right")
    table.add_column("Benchmark", justify="right")
    table.add_column("Excess", justify="right")
    table.add_column("Status")
    for r in data.get("company_reactions", []):
        status = r.get("status", "")
        table.add_row(
            _cell(r.get("story", {}).get("headline", "")),
            _cell(r.get("entity", {}).get("name", "")),
            _cell(f"{r.get('symbol', '')} vs {r.get('benchmark') or 'none'}"),
            _session_cell(r),
            _signed_pct(r.get("stock_return_pct")),
            _signed_pct(r.get("benchmark_return_pct")),
            _signed_pct(r.get("excess_return_pct")),
            _cell(status if status == "measured" else f"{status}: {r.get('gap', '')}"),
        )
    console.print(table)

    if not no_countries:
        table = Table(title="Countries", box=box.SIMPLE_HEAVY)
        table.add_column("Story", max_width=48)
        table.add_column("Country", style="bold")
        table.add_column("Index")
        table.add_column("Session")
        table.add_column("Index move", justify="right")
        table.add_column("z", justify="right")
        table.add_column("Status")
        for r in data.get("country_reactions", []):
            status = r.get("status", "")
            z = r.get("zscore")
            table.add_row(
                _cell(r.get("story", {}).get("headline", "")),
                _cell(r.get("entity", {}).get("name", "")),
                _cell(r.get("symbol", "")),
                _session_cell(r),
                _signed_pct(r.get("index_return_pct")),
                "[dim]n/a[/dim]" if z is None else f"{z:+.2f}",
                _cell(status if status == "measured" else f"{status}: {r.get('gap', '')}"),
            )
        console.print(table)

    # Unmapped names are listed, not dropped; one line per name and reason.
    unmapped: dict[tuple[str, str], int] = {}
    for row in data.get("unmapped", []):
        key = (str(row.get("entity", {}).get("name", "")), str(row.get("reason", "")))
        unmapped[key] = unmapped.get(key, 0) + 1
    for (name, reason), count in unmapped.items():
        stories = f" ({count} stories)" if count > 1 else ""
        console.print(f"[dim]Unmapped:[/dim] {escape(name)}{stories}: {escape(reason)}")
    for row in data.get("excluded", []):
        console.print(
            f"[yellow]Excluded:[/yellow] {escape(str(row.get('entity', {}).get('name', '')))}"
            f" in \"{escape(str(row.get('story', '')))}\": {escape(str(row.get('reason', '')))}"
        )
    _print_data_gaps(data)


# ---------------------------------------------------------------------------
# Social & Health
# ---------------------------------------------------------------------------


@main.command(name="social")
@click.pass_context
def social_cmd(ctx: click.Context) -> None:
    """Reddit social signals (worldnews, geopolitics)."""
    f = _get_fetcher()
    data = _run(social.fetch_social_signals(f))

    if _bail_on_error(ctx, data):
        return

    metrics = data.get("velocity_metrics", {})
    console.print(
        f"[bold]Social Signals[/bold] — {metrics.get('total_posts', 0)} posts, "
        f"{metrics.get('high_engagement_count', 0)} high engagement\n"
    )

    for post in data.get("top_posts", [])[:15]:
        score = post.get("score", 0)
        style = "bold" if score >= 1000 else ""
        title = escape(post.get("title", "")[:80])
        console.print(
            f"  [{style}]{score:>5}[/{style}]  {title}"
            if style
            else f"  {score:>5}  {title}"
        )


@main.command(name="disease")
@click.pass_context
def disease_cmd(ctx: click.Context) -> None:
    """Disease outbreaks (WHO/ProMED/CIDRAP)."""
    f = _get_fetcher()
    data = _run(health.fetch_disease_outbreaks(f))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('count', 0)} outbreak reports[/bold] "
        f"([red]{data.get('high_concern_count', 0)} high concern[/red])\n"
    )

    for item in data.get("items", [])[:20]:
        hc = "[red]HC[/red] " if item.get("is_high_concern") else "    "
        title = escape(item.get("title", "")[:80])
        feed = escape(item.get("feed_name", ""))
        console.print(f"  {hc}{title}  [dim]({feed})[/dim]")


@main.command(name="elections")
@click.option("--country", "-c", default=None, help="Country filter (ISO-3)")
@click.pass_context
def elections_cmd(ctx: click.Context, country: str | None) -> None:
    """Election calendar with risk scoring."""
    f = _get_fetcher()
    data = _run(elections.fetch_election_calendar(f, country=country))

    if _bail_on_error(ctx, data):
        return

    table = Table(title="Election Calendar", box=box.SIMPLE_HEAVY)
    table.add_column("Date", style="bold")
    table.add_column("Country")
    table.add_column("Type")
    table.add_column("Days", justify="right")
    table.add_column("Risk", justify="right")

    for e in data.get("elections", []):
        risk = e.get("risk_score", 0)
        r_style = "red bold" if risk >= 4 else "yellow" if risk >= 2 else ""
        r_str = f"[{r_style}]{risk:.1f}[/{r_style}]" if r_style else f"{risk:.1f}"
        table.add_row(
            _cell(e.get("date", "")),
            _cell(e.get("country", "")),
            _cell(e.get("type", "")),
            _cell(e.get("days_until", "")),
            r_str,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Specialist
# ---------------------------------------------------------------------------


@main.command(name="nuclear")
@click.option("--hours", "-h", default=72, help="Lookback hours")
@click.pass_context
def nuclear_cmd(ctx: click.Context, hours: int) -> None:
    """Nuclear test site seismic monitor."""
    f = _get_fetcher()
    data = _run(nuclear.fetch_nuclear_monitor(f, hours=hours))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('total_flagged_events', 0)} flagged events[/bold] "
        f"([red]{data.get('critical_flags', 0)} critical[/red]) in last {hours}h\n"
    )

    for site in data.get("sites", []):
        n = site.get("name", "")
        events = site.get("events", [])
        count = len(events)
        style = "red bold" if count > 0 else "dim"
        console.print(f"  [{style}]{n}: {count} events[/{style}]")


@main.command(name="space")
@click.pass_context
def space_cmd(ctx: click.Context) -> None:
    """Space weather (NOAA/SWPC)."""
    f = _get_fetcher()
    data = _run(space_weather.fetch_space_weather(f))

    if _bail_on_error(ctx, data):
        return

    table = Table(title="Space Weather", box=box.SIMPLE_HEAVY)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    for key in (
        "current_kp",
        "kp_level",
        "latest_flare_class",
        "solar_wind_speed_km_s",
    ):
        if key in data:
            val = data[key]
            table.add_row(
                key.replace("_", " ").title(), _cell("unknown" if val is None else val)
            )
    console.print(table)
    alerts = data.get("alerts") or []
    if alerts:
        console.print(f"\n[bold]{len(alerts)} alerts[/bold]")
        for al in alerts[:5]:
            lines = [ln for ln in str(al.get("message", "")).splitlines() if ln.strip()]
            head = next(
                (ln for ln in lines if ln.startswith(("ALERT", "WATCH", "WARNING", "SUMMARY", "CONTINUED", "EXTENDED"))),
                lines[0] if lines else "",
            )
            console.print(
                f"  {_cell(str(al.get('issue_datetime', ''))[:16])} "
                f"{_cell(al.get('product_id', ''))} {_cell(head)}"
            )


@main.command(name="sanctions")
@click.argument("query")
@click.option("--country", "-c", default=None, help="Country filter")
@click.pass_context
def sanctions_cmd(ctx: click.Context, query: str, country: str | None) -> None:
    """Search OFAC SDN sanctions list."""
    f = _get_fetcher()
    data = _run(sanctions.fetch_sanctions_search(f, query=query, country=country))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('count', 0)} matches[/bold] for '{query}' "
        f"(from {data.get('total_entities', 0)} total)\n"
    )

    for m in data.get("matches", [])[:20]:
        etype = escape(f"[{m.get('entity_type', '')}]")
        name = escape(m.get("name", ""))
        programs = escape(", ".join(m.get("programs", [])[:3]))
        console.print(f"  {etype} [bold]{name}[/bold]  ({programs})")


@main.command(name="ai-watch")
@click.pass_context
def ai_watch_cmd(ctx: click.Context) -> None:
    """AI model and paper releases tracker."""
    f = _get_fetcher()
    data = _run(ai_watch.fetch_ai_watch(f))

    if _bail_on_error(ctx, data):
        return

    console.print(f"[bold]AI Watch[/bold] — {data.get('total_items', 0)} items\n")
    for item in data.get("items", [])[:20]:
        title = escape(item.get("title", "")[:80])
        src = escape(f"[{item.get('source', '')}]")
        console.print(f"  {src} {title}")


# ---------------------------------------------------------------------------
# Navy
# ---------------------------------------------------------------------------


@main.command(name="fleet")
@click.pass_context
def fleet_cmd(ctx: click.Context) -> None:
    """USNI Fleet Tracker (Navy disposition)."""
    f = _get_fetcher()
    data = _run(fetch_usni_fleet(f))

    if _bail_on_error(ctx, data):
        return

    console.print(f"[bold]{escape(data.get('report_title', 'Fleet Report'))}[/bold]\n")

    totals = data.get("force_totals", {})
    if totals.get("battle_force"):
        bf = totals["battle_force"]
        console.print(
            f"  Battle Force: {bf.get('total', 0)} ships ({bf.get('uss', 0)} USS, {bf.get('usns', 0)} USNS)"
        )
    if totals.get("deployed"):
        dp = totals["deployed"]
        console.print(
            f"  Deployed: {dp.get('total', 0)} ({dp.get('uss', 0)} USS, {dp.get('usns', 0)} USNS)"
        )

    ships = data.get("ships", [])
    if ships:
        console.print(f"\n  [bold]{len(ships)} ships identified[/bold]")
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Ship", style="bold")
        table.add_column("Hull")
        table.add_column("Type")
        table.add_column("Region")
        for s in ships[:20]:
            table.add_row(
                _cell(s.get("name", "")),
                _cell(s.get("hull_number", "")),
                _cell(s.get("type", "")),
                _cell(s.get("region", "")),
            )
        console.print(table)


# ---------------------------------------------------------------------------
# Tech & Science
# ---------------------------------------------------------------------------


@main.command(name="hn")
@click.option("--limit", "-n", default=20, help="Number of stories")
@click.pass_context
def hn_cmd(ctx: click.Context, limit: int) -> None:
    """Top Hacker News stories."""
    f = _get_fetcher()
    data = _run(fetch_hacker_news(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    for s in data.get("stories", []):
        score = s.get("score", 0)
        title = escape(s.get("title", "")[:80])
        console.print(f"  {score:>5}  {title}")


@main.command(name="gh-trending")
@click.option("--limit", "-n", default=15, help="Number of repos")
@click.pass_context
def gh_trending_cmd(ctx: click.Context, limit: int) -> None:
    """Trending GitHub repositories."""
    f = _get_fetcher()
    data = _run(fetch_trending_repos(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    for r in data.get("repos", []):
        stars = r.get("stars", 0)
        name = escape(r.get("name", ""))
        lang = escape(f"[{r.get('language') or ''}]")
        desc = escape((r.get("description") or "")[:60])
        console.print(f"  {stars:>6} [bold]{name}[/bold] {lang}  {desc}")


@main.command(name="arxiv")
@click.option("--query", "-q", default="cs.AI", help="arXiv category or query")
@click.option("--limit", "-n", default=10, help="Number of papers")
@click.pass_context
def arxiv_cmd(ctx: click.Context, query: str, limit: int) -> None:
    """Recent arXiv papers."""
    f = _get_fetcher()
    data = _run(fetch_arxiv_papers(f, query=query, limit=limit))

    if _bail_on_error(ctx, data):
        return

    for p in data.get("papers", []):
        title = escape(p.get("title", "")[:80])
        authors = escape(", ".join(p.get("authors", [])[:3]))
        console.print(f"  [bold]{title}[/bold]")
        console.print(f"    {authors}")


@main.command(name="spending")
@click.option("--limit", "-n", default=15, help="Top N agencies")
@click.pass_context
def spending_cmd(ctx: click.Context, limit: int) -> None:
    """US federal spending (USAspending.gov)."""
    f = _get_fetcher()
    data = _run(fetch_usa_spending(f, limit=limit))

    if _bail_on_error(ctx, data):
        return

    table = Table(title="Federal Agencies by Budget", box=box.SIMPLE_HEAVY)
    table.add_column("Agency", style="bold")
    table.add_column("Budget Auth", justify="right")
    table.add_column("Obligated", justify="right")

    for a in data.get("agencies", []):
        budget = a.get("budget_authority", 0) or 0
        obligated = a.get("obligated_amount", 0) or 0
        table.add_row(
            _cell(a.get("name", "")),
            f"${budget / 1e9:,.1f}B",
            f"${obligated / 1e9:,.1f}B",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Geospatial (static datasets)
# ---------------------------------------------------------------------------


@main.command(name="bases")
@click.option("--operator", "-o", default=None, help="Operator country (USA, RUS, CHN)")
@click.option("--country", "-c", default=None, help="Host country")
@click.pass_context
def bases_cmd(ctx: click.Context, operator: str | None, country: str | None) -> None:
    """Military bases worldwide (70 bases)."""
    data = _run(geospatial.fetch_military_bases(operator=operator, country=country))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('count', 0)} bases[/bold] (of {data.get('total_in_database', 0)})\n"
    )
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Name", style="bold")
    table.add_column("Operator")
    table.add_column("Country")
    table.add_column("Type")
    table.add_column("Branch")

    for b in data.get("bases", [])[:30]:
        table.add_row(
            b.get("name", ""),
            b.get("operator", ""),
            b.get("country", ""),
            b.get("type", ""),
            b.get("branch", ""),
        )
    console.print(table)


@main.command(name="exchanges")
@click.option(
    "--tier", "-t", default=None, type=click.Choice(["mega", "major", "mid", "small"])
)
@click.option("--country", "-c", default=None, help="Country filter")
@click.pass_context
def exchanges_cmd(ctx: click.Context, tier: str | None, country: str | None) -> None:
    """Global stock exchanges (82 exchanges)."""
    data = _run(geospatial.fetch_stock_exchanges(tier=tier, country=country))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]{data.get('count', 0)} exchanges[/bold] "
        f"(${data.get('total_market_cap_usd_t', 0):.1f}T total market cap)\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Exchange", style="bold")
    table.add_column("Country")
    table.add_column("Tier")
    table.add_column("Market Cap ($T)", justify="right")

    for e in data.get("exchanges", [])[:30]:
        table.add_row(
            e.get("name", ""),
            e.get("country", ""),
            e.get("tier", ""),
            f"{e.get('market_cap_usd_t', 0):.2f}",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Traffic, Aviation, Webcams
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def traffic(ctx: click.Context) -> None:
    """Real-time traffic congestion for 20 major cities (TomTom)."""
    from .sources.traffic import fetch_traffic_flow

    f = _get_fetcher()
    data = _run(fetch_traffic_flow(f))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]Global Traffic[/bold] — {data.get('count', 0)} cities, "
        f"avg congestion {data.get('global_avg_congestion', 0):.0f}%\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("City", style="bold")
    table.add_column("Country")
    table.add_column("Congestion %", justify="right")
    table.add_column("Speed (km/h)", justify="right")

    for c in data.get("cities", [])[:20]:
        cong = c.get("congestion_pct", 0)
        style = "red" if cong > 60 else "yellow" if cong > 30 else "green"
        table.add_row(
            c.get("name", ""),
            c.get("country", ""),
            f"[{style}]{cong}%[/{style}]",
            _cell(c.get("current_speed_kmh", "")),
        )
    console.print(table)


@main.command()
@click.pass_context
def incidents(ctx: click.Context) -> None:
    """Major traffic incidents across strategic regions (TomTom)."""
    from .sources.traffic import fetch_traffic_incidents

    f = _get_fetcher()
    data = _run(fetch_traffic_incidents(f))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]Traffic Incidents[/bold] — {data.get('total_count', 0)} across "
        f"{data.get('regions_checked', 0)} regions\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Region")
    table.add_column("Description", max_width=40)
    table.add_column("Delay (min)", justify="right")
    table.add_column("Road")

    for inc in data.get("incidents", [])[:20]:
        delay_min = round(inc.get("delay_seconds", 0) / 60)
        table.add_row(
            inc.get("region", ""),
            _cell(inc.get("description", "")[:40]),
            str(delay_min) if delay_min else "-",
            _cell(inc.get("from_road", "")[:30]),
        )
    console.print(table)


@main.command(name="air-traffic")
@click.pass_context
def air_traffic_cmd(ctx: click.Context) -> None:
    """Global air traffic snapshot (OpenSky)."""
    f = _get_fetcher()
    data = _run(aviation.fetch_domestic_flights(f))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]Air Traffic[/bold] — {data.get('total_aircraft', 0)} airborne\n"
    )

    table = Table(box=box.SIMPLE_HEAVY, title="By Region")
    table.add_column("Region", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Commercial", justify="right")
    table.add_column("General", justify="right")

    for region, stats in sorted(
        data.get("by_region", {}).items(), key=lambda x: -x[1]["count"]
    ):
        table.add_row(
            region, str(stats["count"]), str(stats["commercial"]), str(stats["general"])
        )
    console.print(table)

    if data.get("busiest_origins"):
        console.print("\n[bold]Busiest Origins:[/bold]")
        for o in data["busiest_origins"][:10]:
            console.print(f"  {escape(str(o['country']))}: {o['count']}")


@main.command()
@click.option("--category", "-c", default="traffic", help="Webcam category")
@click.option("--limit", "-n", default=20, help="Max cameras")
@click.pass_context
def webcams_cmd(ctx: click.Context, category: str, limit: int) -> None:
    """Public webcam locations worldwide (Windy)."""
    from .sources.webcams import fetch_webcams

    f = _get_fetcher()
    data = _run(fetch_webcams(f, category=category, limit=limit))

    if _bail_on_error(ctx, data):
        return

    console.print(
        f"[bold]Webcams[/bold] — {data.get('count', 0)} cameras ({category})\n"
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Title", style="bold", max_width=30)
    table.add_column("City")
    table.add_column("Country")
    table.add_column("Status")

    for cam in data.get("cameras", []):
        table.add_row(
            _cell(cam.get("title", "")[:30]),
            _cell(cam.get("city", "")),
            _cell(cam.get("country", "")),
            _cell(cam.get("status", "")),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Data source health and cache stats."""
    f = _get_fetcher()
    breaker_status = f.breaker.status()
    cache_stats = f.cache.stats()

    if ctx.obj.get("json"):
        _print_json({"circuit_breakers": breaker_status, "cache": cache_stats})
        return

    console.print(Panel("[bold]World Intelligence Status[/bold]"))

    # Cache
    console.print(
        f"\n[bold]Cache:[/bold] {cache_stats.get('active_entries', 0)} active, "
        f"{cache_stats.get('expired_entries', 0)} expired"
    )

    # Circuit breakers
    if breaker_status:
        table = Table(title="Circuit Breakers", box=box.SIMPLE_HEAVY)
        table.add_column("Source", style="bold")
        table.add_column("Status")
        table.add_column("Failures", justify="right")
        table.add_column("Cooldown", justify="right")

        for source, info in sorted(breaker_status.items()):
            s = info.get("status", "closed")
            style = (
                "green" if s == "closed" else "yellow" if s == "half-open" else "red"
            )
            table.add_row(
                source,
                f"[{style}]{s}[/{style}]",
                str(info.get("failures", 0)),
                f"{info.get('cooldown_remaining_s', 0):.0f}s"
                if info.get("cooldown_remaining_s")
                else "",
            )
        console.print(table)
    else:
        console.print("\n[dim]No circuit breaker data yet (no requests made)[/dim]")


@main.command(name="guide")
@click.option(
    "--measures", is_flag=True, help="Print the measures glossary instead of the guide"
)
@click.pass_context
def guide_cmd(ctx: click.Context, measures: bool) -> None:
    """Print the research guide the MCP server serves as intel://guide."""
    from . import guide

    if measures:
        uri, text = guide.MEASURES_URI, guide.MEASURES
    else:
        uri, text = guide.GUIDE_URI, guide.render_guide()
    if ctx.obj.get("json"):
        _print_json({"uri": uri, "mime_type": "text/markdown", "text": text})
        return
    # click.echo, not console.print: tool descriptions contain brackets
    # that Rich would parse as markup, and the output is meant to pipe.
    click.echo(text, nl=False)


@main.command(name="sync")
@click.argument("source", required=False)
def sync_cmd(source: str | None) -> None:
    """Force refresh a data source cache."""
    f = _get_fetcher()
    if source:
        # Delete all cache entries matching this source prefix
        # Simple approach: evict expired, then note we can't selectively clear yet
        console.print(
            f"[yellow]Force sync not yet implemented for specific source '{source}'[/yellow]"
        )
        console.print(
            "[dim]Workaround: cache entries expire naturally based on TTL[/dim]"
        )
    else:
        removed = f.cache.evict_expired()
        console.print(f"Evicted {removed} expired cache entries")


@main.command()
@click.option("--port", default=8501, type=int, help="Port to listen on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
def dashboard(port: int, host: str) -> None:
    """Launch the live intelligence dashboard."""
    from .dashboard.app import run as run_dashboard

    console.print(
        f"[bold]Starting Intelligence Dashboard[/bold] on http://{host}:{port}"
    )
    run_dashboard(host=host, port=port)


@main.command()
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Output file path"
)
@click.option("--title", "-t", default=None, help="Report title")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["pdf", "html"]),
    default="pdf",
    help="Output format",
)
@click.option(
    "--sections", "-s", default=None, help="Comma-separated section names to include"
)
@click.pass_context
def report(
    ctx: click.Context,
    output: str | None,
    title: str | None,
    fmt: str,
    sections: str | None,
) -> None:
    """Generate a PDF or HTML intelligence report."""
    from .reports import generate_report

    f = _get_fetcher()
    section_list = [s.strip() for s in sections.split(",")] if sections else None

    with console.status("[bold]Generating report..."):
        result = asyncio.run(
            generate_report(
                f, output_path=output, title=title, sections=section_list, fmt=fmt
            )
        )

    if _bail_on_error(ctx, result):
        if "fallback" in result and not ctx.obj.get("json"):
            # escape keeps the literal "[pdf]" in the install hint from
            # being eaten as a markup tag — the printed command must be
            # runnable verbatim.
            console.print(f"[yellow]{escape(str(result['fallback']))}[/yellow]")
        return

    console.print(
        Panel(
            f"[bold green]Report generated[/bold green]\n\n"
            f"Path: {result['path']}\n"
            f"Format: {result['format']}\n"
            f"Size: {result['size_bytes']:,} bytes\n"
            f"Sections: {', '.join(result['sections_included'])}\n"
            f"Time: {result['generation_seconds']}s"
            + (
                f"\n[yellow]Failed: {', '.join(result['sections_failed'])}[/yellow]"
                if result["sections_failed"]
                else ""
            ),
            title="Intelligence Report",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# AOI geofences
# ---------------------------------------------------------------------------

# AOI store — lazily initialized against the same physical SQLite file the
# CLI's Cache resolved to (fallback path included), mirroring how
# runtime.py builds the MCP server's store from its own cache.db_path.
_aoi_store: aoi_analysis.AOIStore | None = None


def _get_aoi_store() -> aoi_analysis.AOIStore:
    global _aoi_store
    if _aoi_store is None:
        _aoi_store = aoi_analysis.AOIStore(_get_fetcher().cache.db_path)
    return _aoi_store


def _parse_latlon_pairs(
    ctx: click.Context, param: click.Parameter, value: tuple[str, ...]
) -> list[list[float]]:
    """Parse repeated LAT,LON option values into [[lat, lon], ...].

    Only the syntax is checked here (a malformed pair is a usage error,
    exit 2); range and count rules belong to the analysis layer, which
    reports them as {"error": ...} dicts through _bail_on_error.
    """
    pairs: list[list[float]] = []
    for raw in value:
        parts = raw.split(",")
        if len(parts) != 2:
            raise click.BadParameter(f"expected LAT,LON (got {raw!r})")
        try:
            pairs.append([float(parts[0]), float(parts[1])])
        except ValueError:
            raise click.BadParameter(
                f"expected numeric LAT,LON (got {raw!r})"
            ) from None
    return pairs


def _print_data_gaps(data: dict) -> None:
    # emoji=False: series keys such as "src:x:..." would otherwise render ":x:" as an emoji.
    for gap in data.get("data_gaps", []):
        console.print(f"[yellow]Gap:[/yellow] {escape(str(gap))}", emoji=False)


@main.group(name="aoi")
def aoi_group() -> None:
    """User-defined areas of interest (AOIs/geofences)."""


@aoi_group.command(name="define")
@click.argument("name")
@click.option("--lat", type=float, required=True, help="Center latitude, -90..90")
@click.option("--lon", type=float, required=True, help="Center longitude, -180..180")
@click.option(
    "--radius-km", type=float, required=True, help="Radius in kilometers, 1..2000"
)
@click.pass_context
def aoi_define(
    ctx: click.Context, name: str, lat: float, lon: float, radius_km: float
) -> None:
    """Define a point-radius AOI."""
    data = aoi_analysis.define_aoi(
        _get_aoi_store(), name=name, lat=lat, lon=lon, radius_km=radius_km
    )
    if _bail_on_error(ctx, data):
        return
    a = data["aoi"]
    console.print(
        f"AOI [bold]{escape(str(a['name']))}[/bold] defined: "
        f"center {a['lat']}, {a['lon']} (radius {a['radius_km']:g} km)"
    )


@aoi_group.command(name="define-polygon")
@click.argument("name")
@click.option(
    "--vertex",
    "vertices",
    multiple=True,
    metavar="LAT,LON",
    callback=_parse_latlon_pairs,
    help="Polygon vertex as LAT,LON; repeat 3-64 times",
)
@click.pass_context
def aoi_define_polygon(
    ctx: click.Context, name: str, vertices: list[list[float]]
) -> None:
    """Define a polygon AOI from repeated --vertex LAT,LON."""
    data = aoi_analysis.define_polygon_aoi(
        _get_aoi_store(), name=name, vertices=vertices
    )
    if _bail_on_error(ctx, data):
        return
    a = data["aoi"]
    n_vertices = len((a.get("geometry") or {}).get("vertices", []))
    console.print(
        f"Polygon AOI [bold]{escape(str(a['name']))}[/bold] defined: "
        f"{n_vertices} vertices, bounding radius {a['radius_km']:.0f} km "
        f"around {a['lat']:.4f}, {a['lon']:.4f}"
    )


@aoi_group.command(name="define-corridor")
@click.argument("name")
@click.option(
    "--waypoint",
    "waypoints",
    multiple=True,
    metavar="LAT,LON",
    callback=_parse_latlon_pairs,
    help="Route waypoint as LAT,LON; repeat 2-64 times",
)
@click.option(
    "--width-km", type=float, required=True, help="Total corridor width in km, 1..500"
)
@click.pass_context
def aoi_define_corridor(
    ctx: click.Context, name: str, waypoints: list[list[float]], width_km: float
) -> None:
    """Define a corridor AOI from repeated --waypoint LAT,LON plus a width."""
    data = aoi_analysis.define_corridor_aoi(
        _get_aoi_store(), name=name, waypoints=waypoints, width_km=width_km
    )
    if _bail_on_error(ctx, data):
        return
    a = data["aoi"]
    geometry = a.get("geometry") or {}
    console.print(
        f"Corridor AOI [bold]{escape(str(a['name']))}[/bold] defined: "
        f"{len(geometry.get('waypoints', []))} waypoints, width "
        f"{geometry.get('width_km', width_km):g} km, bounding radius "
        f"{a['radius_km']:.0f} km"
    )


@aoi_group.command(name="list")
@click.pass_context
def aoi_list_cmd(ctx: click.Context) -> None:
    """List defined AOIs."""
    data = aoi_analysis.list_aois(_get_aoi_store())
    if _bail_on_error(ctx, data):
        return

    aois = data.get("aois", [])
    if not aois:
        console.print("[yellow]No AOIs defined[/yellow]")
        return

    table = Table(title=f"Areas of Interest ({len(aois)})", box=box.SIMPLE_HEAVY)
    table.add_column("Name", style="bold")
    table.add_column("Kind")
    table.add_column("Center", justify="right")
    table.add_column("Radius km", justify="right")
    table.add_column("Created")

    for a in aois:
        created = datetime.fromtimestamp(
            a.get("created_at", 0), tz=timezone.utc
        ).strftime("%Y-%m-%d")
        table.add_row(
            _cell(a.get("name", "")),
            _cell(a.get("kind", "circle")),
            f"{a.get('lat', 0):.4f}, {a.get('lon', 0):.4f}",
            f"{a.get('radius_km', 0):,.0f}",
            created,
        )
    console.print(table)


@aoi_group.command(name="update")
@click.argument("name")
@click.option("--new-name", default=None, help="New name (must not collide)")
@click.option("--lat", type=float, default=None, help="New center latitude")
@click.option("--lon", type=float, default=None, help="New center longitude")
@click.option("--radius-km", type=float, default=None, help="New radius in km")
@click.pass_context
def aoi_update(
    ctx: click.Context,
    name: str,
    new_name: str | None,
    lat: float | None,
    lon: float | None,
    radius_km: float | None,
) -> None:
    """Rename an AOI and/or change a circle's center or radius."""
    data = aoi_analysis.update_aoi(
        _get_aoi_store(),
        name=name,
        new_name=new_name,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    if _bail_on_error(ctx, data):
        return
    a = data["aoi"]
    console.print(
        f"AOI [bold]{escape(str(a['name']))}[/bold] updated: "
        f"center {a['lat']}, {a['lon']} (radius {a['radius_km']:g} km)"
    )
    if data.get("snapshot_dropped"):
        console.print(
            "[yellow]Change-detection baseline dropped (geometry changed); "
            "the next 'intel aoi changes' sweep re-baselines.[/yellow]"
        )


@aoi_group.command(name="delete")
@click.argument("name")
@click.pass_context
def aoi_delete(ctx: click.Context, name: str) -> None:
    """Delete a defined AOI."""
    data = aoi_analysis.delete_aoi(_get_aoi_store(), name=name)
    if _bail_on_error(ctx, data):
        return
    console.print(f"Deleted AOI [bold]{escape(str(data.get('deleted', name)))}[/bold]")


@aoi_group.command(name="brief")
@click.argument("name")
@click.pass_context
def aoi_brief(ctx: click.Context, name: str) -> None:
    """Cited brief for a defined AOI (data gaps included)."""
    data = _run(
        aoi_analysis.fetch_aoi_brief(_get_fetcher(), _get_aoi_store(), name=name)
    )
    if _bail_on_error(ctx, data):
        return
    # The brief's markdown embeds remote free text (news titles, place
    # names); Text renders it literally, never through the markup parser.
    # Its Data Gaps section is part of the markdown itself.
    console.print(Text(str(data.get("markdown", ""))))


@aoi_group.command(name="escalation")
@click.argument("name")
@click.pass_context
def aoi_escalation(ctx: click.Context, name: str) -> None:
    """Escalation score (0-100) for a defined AOI."""
    data = _run(
        aoi_analysis.fetch_aoi_escalation(_get_fetcher(), _get_aoi_store(), name=name)
    )
    if _bail_on_error(ctx, data):
        return

    a = data.get("aoi", {})
    level = data.get("level", "")
    l_style = {
        "critical": "red bold",
        "elevated": "yellow",
        "watch": "dim",
    }.get(level, "")
    level_str = (
        f"[{l_style}]{escape(str(level))}[/{l_style}]"
        if l_style
        else escape(str(level))
    )
    console.print(
        f"[bold]{escape(str(a.get('name', name)))}[/bold] escalation: "
        f"{data.get('score', 0)} on a 0-100 scale ({level_str}, "
        f"trend {escape(str(data.get('trend_signal', '')))})"
    )
    if data.get("score_ceiling") is not None:
        console.print(
            f"[dim]Highest score reachable with the components measured: "
            f"{data['score_ceiling']} (an AOI has no curated baseline)[/dim]"
        )
    if data.get("computed_from"):
        console.print(
            "[dim]Computed from: "
            f"{escape(', '.join(str(c) for c in data['computed_from']))}[/dim]"
        )

    # A zero-filled component is a 0 only because its fetch failed; a
    # lower bound could only rise with the data that is missing.
    zero_filled = set(data.get("zero_filled_components") or [])
    lower_bound = set(data.get("lower_bound_components") or [])
    table = Table(title="Components", box=box.SIMPLE_HEAVY)
    table.add_column("Component", style="bold")
    table.add_column("Points", justify="right")
    for comp, points in data.get("components", {}).items():
        if points is None:
            table.add_row(_cell(comp), "[dim]not measured[/dim]")
        elif comp in zero_filled:
            table.add_row(
                _cell(comp), "[yellow]not measured (fetch failed; scored as 0)[/yellow]"
            )
        elif comp in lower_bound:
            table.add_row(_cell(comp), f"{points:.1f} (lower bound)")
        else:
            table.add_row(_cell(comp), f"{points:.1f}")
    console.print(table)
    _print_data_gaps(data)


@aoi_group.command(name="changes")
@click.argument("name")
@click.pass_context
def aoi_changes(ctx: click.Context, name: str) -> None:
    """What entered or left a defined AOI since the last sweep."""
    data = _run(
        aoi_analysis.fetch_aoi_changes(_get_fetcher(), _get_aoi_store(), name=name)
    )
    if _bail_on_error(ctx, data):
        return

    a = data.get("aoi", {})
    changes = data.get("changes", {})
    if data.get("baseline"):
        console.print(
            f"Baseline established for [bold]{escape(str(a.get('name', name)))}[/bold]"
            ": nothing is claimed to have entered or left; run again to diff."
        )
        table = Table(title="Baseline Observations", box=box.SIMPLE_HEAVY)
        table.add_column("Domain", style="bold")
        table.add_column("Observed", justify="right")
        for domain, info in changes.items():
            table.add_row(_cell(domain), str(info.get("unchanged", 0)))
        console.print(table)
        _print_data_gaps(data)
        return

    prev = data.get("previous_taken_at")
    if prev:
        console.print(f"[dim]Previous sweep: {escape(str(prev))}[/dim]")

    table = Table(
        title=f"AOI Changes — {escape(str(a.get('name', name)))}",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Domain", style="bold")
    table.add_column("New", justify="right")
    table.add_column("Departed", justify="right")
    table.add_column("Unchanged", justify="right")
    for domain, info in changes.items():
        if info.get("baseline"):
            # A domain first seen this sweep: a baseline, not churn.
            table.add_row(
                _cell(domain),
                "[dim]baseline[/dim]",
                "[dim]baseline[/dim]",
                str(info.get("unchanged", 0)),
            )
        else:
            table.add_row(
                _cell(domain),
                str(len(info.get("new", []))),
                str(len(info.get("departed", []))),
                str(info.get("unchanged", 0)),
            )
    console.print(table)

    for domain, info in changes.items():
        for item in info.get("new", []):
            console.print(
                f"  [green]+[/green] {escape(str(domain))}: "
                f"{escape(str(item.get('summary', '')))}"
            )
        for item in info.get("departed", []):
            console.print(
                f"  [red]-[/red] {escape(str(domain))}: "
                f"{escape(str(item.get('summary', '')))}"
            )
    _print_data_gaps(data)


# ---------------------------------------------------------------------------
# History (collector run log, captures, series, revisions)
# ---------------------------------------------------------------------------


def _with_history_store(fn: Any) -> dict:
    from .history import HistoryStore

    store = HistoryStore(_get_fetcher().cache.db_path)
    try:
        return fn(store)
    finally:
        store.close()


def _reason_text(reason: str | None, stale_age: Any = None, stale_fetches: Any = None) -> str:
    """A run-log reason for display, with a stale-cache replay's copy age
    and fetch count beside it (stored apart, so the reason itself is the
    same text on every replay)."""
    from .history import STALE_REASON

    text = reason or ""
    if not text.startswith(STALE_REASON):
        return text
    if stale_fetches and stale_fetches > 1:
        detail = f"{stale_fetches} fetches" + (
            f", oldest {stale_age} s" if stale_age is not None else ""
        )
    elif stale_age is not None:
        detail = f"age {stale_age} s"
    else:
        return text
    return f"{STALE_REASON} ({detail}){text[len(STALE_REASON):]}"


@main.group(name="history")
def history_group() -> None:
    """Saved collector history: health, captures, series, revisions.

    History accrues only while the collector (intel-collector) runs, except
    series that intel history backfill loads from FRED or the ECB Data Portal.
    """


@history_group.command(name="health")
@click.option("--source", default=None, help="One collector source name")
@click.pass_context
def history_health(ctx: click.Context, source: str | None) -> None:
    """Per-source collection health from the collector's run log."""
    from .collector import SOURCES

    roster = [name for name, _, _, _ in SOURCES]
    data = _with_history_store(
        lambda s: s.collection_health(roster, source=source)
    )
    if _bail_on_error(ctx, data):
        return

    table = Table(
        title=f"Collection health (cadence {data['default_cadence_s']:g} s, "
        f"overdue past {data['overdue_multiple']:g}x)",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Source", style="bold")
    table.add_column("State")
    table.add_column("Last attempt")
    table.add_column("Last success")
    table.add_column("Last ok")
    table.add_column("Fails", justify="right")
    table.add_column("Latest observed")
    table.add_column("Reason")
    styles = {"ok": "green", "degraded": "yellow", "never_run": "dim"}
    for row in data["sources"]:
        state = row["state"]
        overdue = state in ("failing", "stale") and row.get("overdue")
        label = f"{state}, overdue" if overdue else state
        table.add_row(
            _cell(row["source"]),
            Text(label, style=styles.get(state, "red")),
            _cell(row.get("last_attempt_at") or "-"),
            _cell(row.get("last_success_at") or "-"),
            _cell(row.get("last_ok_at") or "-"),
            str(row.get("consecutive_failures", "-")),
            _cell(row.get("latest_observed_at") or "-"),
            _cell(_reason_text(row.get("last_reason"), row.get("last_stale_age_s"),
                               row.get("last_stale_fetches"))),
        )
    if data["sources"]:
        console.print(table)
    for row in data.get("backfills", []):
        console.print(
            f"Backfill [bold]{escape(row['source'])}[/bold]: {row['captures']} capture(s), "
            f"last {row['last_run_at']} ({row['last_status']}"
            + (
                f", {row['last_run_failed']} of {row['last_run_requests']} request(s) failed"
                if row.get("last_run_failed") else ""
            )
            + f"), {row['observations']} "
            f"observations in {row['series']} series, observed "
            f"{escape(str(row['first_observed_at'] or '-'))} to "
            f"{escape(str(row['latest_observed_at'] or '-'))}."
        )
        if row.get("last_run_failed"):
            console.print(f"  Last run failed: {escape(str(row['last_reason']))}")
    counts = ", ".join(f"{k} {v}" for k, v in sorted(data["state_counts"].items())) or "none"
    storage = data["storage"]
    console.print(
        f"States: {counts}. Stored: {storage['captures']} captures, "
        f"{storage['payload_bodies']} payload bodies "
        f"({storage['payload_bytes_compressed']:,} bytes compressed), "
        f"{storage['observations']} observations in {storage['series']} series."
    )
    _print_data_gaps(data)
    for line in data["cannot_prove"]:
        console.print(f"[yellow]Cannot prove:[/yellow] {escape(line)}")


@history_group.command(name="captures")
@click.argument("source")
@click.option("--limit", default=20, type=int, help="Captures to show")
@click.option(
    "--capture-id", default=None, type=int, help="Show one capture with its payload"
)
@click.pass_context
def history_captures(
    ctx: click.Context, source: str, limit: int, capture_id: int | None
) -> None:
    """A source's earlier captures, newest first."""
    data = _with_history_store(
        lambda s: s.capture_history(source, limit=limit, capture_id=capture_id)
    )
    if _bail_on_error(ctx, data):
        return

    if "capture" in data:
        cap = data["capture"]
        console.print(
            f"Capture {cap['capture_id']} of [bold]{escape(source)}[/bold] at "
            f"{cap['collected_at']}: {cap['status']} ({cap['change'] or 'no payload'})"
        )
        if cap.get("reason"):
            reason = _reason_text(str(cap["reason"]), cap.get("stale_age_s"),
                                  cap.get("stale_fetches"))
            console.print(f"[yellow]Reason:[/yellow] {escape(reason)}")
        if cap.get("payload_note"):
            console.print(f"[yellow]Gap:[/yellow] {escape(cap['payload_note'])}")
        if cap.get("payload") is not None:
            _print_json(cap["payload"])
        elif cap.get("payload_outline") is not None:
            _print_json(cap["payload_outline"])
        return

    captures = data["captures"]
    if not captures:
        _print_data_gaps(data)
        return
    table = Table(
        title=f"Captures of {escape(source)} ({data['total_captures']} total, "
        f"{data['changed_captures']} changed, {data['distinct_payloads']} distinct)",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("ID", justify="right")
    table.add_column("Collected")
    table.add_column("Status")
    table.add_column("Duration s", justify="right")
    table.add_column("Records", justify="right")
    table.add_column("Change")
    table.add_column("Reason")
    for cap in captures:
        table.add_row(
            str(cap["capture_id"]),
            cap["collected_at"],
            cap["status"],
            "-" if cap["duration_s"] is None else f"{cap['duration_s']:.2f}",
            "-" if cap["record_count"] is None else str(cap["record_count"]),
            cap["change"] or "-",
            _cell(_reason_text(cap.get("reason"), cap.get("stale_age_s"),
                               cap.get("stale_fetches"))),
        )
    console.print(table)
    console.print(f"[dim]{escape(data['note'])}[/dim]")


@history_group.command(name="series")
@click.argument("series_key", required=False)
@click.option("--source", default=None, help="Filter the listing to one source")
@click.option("--limit", default=None, type=int, help="Rows to show")
@click.pass_context
def history_series(
    ctx: click.Context, series_key: str | None, source: str | None, limit: int | None
) -> None:
    """One series' observations (three dates), or the list of series."""
    default_limit = 100 if series_key else 200
    data = _with_history_store(
        lambda s: s.series_history(
            series_key, source=source, limit=limit or default_limit
        )
    )
    if _bail_on_error(ctx, data):
        return

    if series_key is None:
        if not data["series"]:
            _print_data_gaps(data)
            return
        table = Table(
            title=f"Series ({data['total_series']})", box=box.SIMPLE_HEAVY
        )
        table.add_column("Series", style="bold")
        table.add_column("Label")
        table.add_column("Points", justify="right")
        table.add_column("Observed from")
        table.add_column("Observed to")
        table.add_column("Last collected")
        for row in data["series"]:
            table.add_row(
                _cell(row["series_key"]),
                _cell(row.get("label") or ""),
                str(row["points"]),
                _cell(row.get("first_observed_at") or "unknown"),
                _cell(row.get("last_observed_at") or "unknown"),
                row["last_collected_at"],
            )
        console.print(table)
        return

    table = Table(title=escape(series_key), box=box.SIMPLE_HEAVY)
    table.add_column("Observed")
    table.add_column("Published")
    table.add_column("Collected")
    table.add_column("Value", justify="right")
    table.add_column("Unit")
    for obs in data["observations"]:
        table.add_row(
            _cell(obs["observed_at"] or "unknown"),
            _cell(obs["published_at"] or "unknown"),
            obs["collected_at"],
            f"{obs['value']:g}",
            _cell(obs.get("unit") or ""),
        )
    console.print(table)
    _print_data_gaps(data)


@history_group.command(name="revisions")
@click.option("--source", default=None, help="Filter to one source")
@click.option("--series", "series_key", default=None, help="Filter to one series")
@click.option("--limit", default=100, type=int, help="Revisions to show")
@click.pass_context
def history_revisions(
    ctx: click.Context, source: str | None, series_key: str | None, limit: int
) -> None:
    """Values a later capture changed for the same observed_at."""
    data = _with_history_store(
        lambda s: s.revisions(source=source, series_key=series_key, limit=limit)
    )
    if _bail_on_error(ctx, data):
        return

    if not data["revisions"]:
        console.print("[yellow]No revisions seen between saved captures[/yellow]")
    else:
        table = Table(title=f"Revisions ({data['count']})", box=box.SIMPLE_HEAVY)
        table.add_column("Series", style="bold")
        table.add_column("Observed")
        table.add_column("Was", justify="right")
        table.add_column("Now", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Revised at")
        for rev in data["revisions"]:
            table.add_row(
                _cell(rev["series_key"]),
                _cell(rev["observed_at"]),
                f"{rev['previous_value']:g}",
                f"{rev['revised_value']:g}",
                f"{rev['delta']:+g}",
                rev["revised_collected_at"],
            )
        console.print(table)
    _print_data_gaps(data)
    for line in data["cannot_prove"]:
        console.print(f"[yellow]Cannot prove:[/yellow] {escape(line)}")


from .analysis import lagged_connections as _lagged  # noqa: E402


def _p_text(value: float) -> str:
    return "<1e-300" if value == 0 else f"{value:.2g}"


@history_group.command(name="connections")
@click.argument("series_keys", nargs=-1, required=True)
@click.option("--grid", type=click.Choice(_lagged.GRIDS), default=_lagged.DEFAULT_GRID,
              show_default=True, help="UTC calendar grid (weeks run Monday to Sunday)")
@click.option("--transform", type=click.Choice(_lagged.TRANSFORMS),
              default=_lagged.DEFAULT_TRANSFORM, show_default=True,
              help="changes (period-over-period) or levels")
@click.option("--max-lag", type=int, default=_lagged.DEFAULT_MAX_LAG, show_default=True,
              help=f"Largest lead or lag in grid periods (0 to {_lagged.MAX_LAG_CAP})")
@click.option("--min-overlap", type=int, default=_lagged.DEFAULT_MIN_OVERLAP, show_default=True,
              help=f"Fewest overlapping periods a test needs (at least {_lagged.MIN_OVERLAP_FLOOR})")
@click.option("--q", "q", type=float, default=_lagged.DEFAULT_Q, show_default=True,
              help="False discovery rate threshold (Benjamini-Hochberg, applied to q_ar1)")
@click.option("--start", default=None, help="First date YYYY-MM-DD")
@click.option("--end", default=None, help="Last date YYYY-MM-DD")
@click.pass_context
def history_connections(
    ctx: click.Context, series_keys: tuple[str, ...], grid: str, transform: str,
    max_lag: int, min_overlap: int, q: float, start: str | None, end: str | None,
) -> None:
    """Correlation between stored series at leads and lags.

    Lag +k compares the first series of a pair at period t with the second
    at t+k, so the first leads by k. A connection is not a cause.
    """
    data = _with_history_store(
        lambda s: _lagged.lagged_connections(
            s, list(series_keys), grid=grid, transform=transform, max_lag=max_lag,
            min_overlap=min_overlap, q=q, start=start, end=end,
        )
    )
    if _bail_on_error(ctx, data):
        return

    method = data["method"]
    lo, hi = method["lags"]
    table = Table(
        title=f"Connections ({method['grid']} grid, {method['transform']}, lags {lo:+d} to "
        f"{hi:+d}, {data['tests_run']} tests, BH q_ar1 <= {method['q_threshold']:g})",
        box=box.SIMPLE_HEAVY,
    )
    numeric = ("Lag", "r", "n", "n_eff", "p", "q", "p_ar1", "q_ar1")
    for name in ("A", "B", "Lag", "Timing", "r", "n", "n_eff", "p", "q", "p_ar1", "q_ar1",
                 "Significant"):
        table.add_column(name, justify="right" if name in numeric else "left")
    for pair in data["pairs"]:
        if not pair["strongest"]:
            table.add_row(_cell(pair["a"]), _cell(pair["b"]), "-",
                          Text("not tested", style="dim"), *["-"] * 8)
        for entry in pair["strongest"]:
            n_eff = entry["n_effective_ar1"]
            table.add_row(
                _cell(pair["a"]), _cell(pair["b"]), f"{entry['lag']:+d}", entry["timing"],
                f"{entry['r']:+.3f}", str(entry["n"]), "-" if n_eff is None else f"{n_eff:g}",
                _p_text(entry["p"]), _p_text(entry["q"]), _p_text(entry["p_ar1"]),
                _p_text(entry["q_ar1"]),
                Text("yes", style="green") if entry["significant"] else Text("no"),
            )
    console.print(table)
    console.print(escape(data["summary"]))
    console.print(
        "n_eff: AR(1) effective sample size from the two series' lag-1 autocorrelations. "
        "p and q use n (periods treated as independent); p_ar1 and q_ar1 use n_eff, and "
        f"Significant means q_ar1 <= {method['q_threshold']:g}."
    )
    for pair in data["pairs"]:
        for entry in pair["strongest"]:
            if entry.get("note"):
                console.print(
                    f"[yellow]Note:[/yellow] {escape(pair['a'])} / {escape(pair['b'])} lag "
                    f"{entry['lag']:+d}: {escape(entry['note'])}",
                    emoji=False,
                )
    for clamp in data["inputs_clamped"]:
        why = clamp.get("reason") or "allowed {} to {}".format(*clamp["allowed"])
        console.print(
            f"[yellow]Clamped:[/yellow] {clamp['input']} {escape(str(clamp['requested']))} -> "
            f"{escape(str(clamp['used']))} ({escape(why)})"
        )
    console.print(f"Lag convention: {escape(method['lag_convention'])}")
    console.print(
        f"Transform: {escape(method['transform_rule'])} {escape(method['why_changes_default'])}"
    )
    for pair in data["pairs"]:
        best = {e["lag"] for e in pair["strongest"]}
        others = [e for e in pair["significant"] if e["lag"] not in best]
        if others:
            listed = ", ".join(
                f"lag {e['lag']:+d} (r {e['r']:+.3f}, q_ar1 {_p_text(e['q_ar1'])})" for e in others
            )
            console.print(f"Also significant: {escape(pair['a'])} / {escape(pair['b'])}: {listed}",
                          emoji=False)
        if pair["not_tested"]:
            listed = ", ".join(
                f"lag {nt['lag']:+d} (n {nt['n']}"
                + (", no variation)" if nt["reason"] == "no_variation" else ")")
                for nt in pair["not_tested"]
            )
            console.print(
                f"[yellow]Not tested[/yellow] (minimum {method['min_overlap']} overlapping "
                f"periods): {escape(pair['a'])} / {escape(pair['b'])}: {listed}",
                emoji=False,
            )
    for item in data["excluded_series"]:
        console.print(
            f"[yellow]Excluded:[/yellow] {escape(item['series_key'])}: {escape(item['reason'])}",
            emoji=False,
        )
    _print_data_gaps(data)
    for line in data["cannot_prove"]:
        console.print(f"[yellow]Cannot prove:[/yellow] {escape(line)}")


@history_group.command(name="day")
@click.argument("day")
@click.option(
    "--by",
    type=click.Choice(["collected", "observed"]),
    default="collected",
    show_default=True,
    help="collected: what was captured that day; observed: values whose observed_at is that day",
)
@click.option("--source", default=None, help="One collector source name")
@click.option("--limit", default=None, type=int,
              help="Most items listed in all (with --by observed, both lists together)")
@click.option("--per-source", "per_source", default=None, type=int,
              help="Most items listed per source (with --by observed, both lists together)")
@click.pass_context
def history_day(
    ctx: click.Context,
    day: str,
    by: str,
    source: str | None,
    limit: int | None,
    per_source: int | None,
) -> None:
    """What the history store recorded for one UTC day (YYYY-MM-DD)."""
    import time

    from .collector import SOURCES
    from .history_timeline import (
        DEFAULT_LIMIT,
        DEFAULT_PER_SOURCE_LIMIT,
        day_timeline,
        parse_day,
    )

    now = time.time()
    _, problem = parse_day(day, now)
    if problem:
        raise click.BadParameter(problem, param_hint="DAY")
    data = day_timeline(
        _get_fetcher().cache.db_path,
        day,
        by=by,
        source=source,
        roster=[name for name, _, _, _ in SOURCES],
        limit=DEFAULT_LIMIT if limit is None else limit,
        per_source_limit=DEFAULT_PER_SOURCE_LIMIT if per_source is None else per_source,
        now=now,
    )
    if _bail_on_error(ctx, data):
        return

    window = data["window"]
    span = f"{window['start']} to {window['end']} (end exclusive)"
    if not window["complete"]:
        span += f", in progress through {window['through']}"
    console.print(f"[bold]{data['day']}[/bold] (UTC) by {data['by']} date: {span}")
    if by == "collected":
        _print_day_collected(data)
    else:
        _print_day_observed(data)
    _print_data_gaps(data)
    for line in data["cannot_prove"]:
        console.print(f"[yellow]Cannot prove:[/yellow] {escape(line)}")


def _print_day_collected(data: dict) -> None:
    c = data["collector"]
    if c["state"] == "ran":
        console.print(
            f"Collector: ran, {c['captures']:,} captures of {c['sources_captured']} "
            f"source(s), {c['first_capture_at']} to {c['last_capture_at']}; longest gap "
            f"{c['longest_gap_s']:,.0f} s ({c['longest_gap_from']} to {c['longest_gap_to']})"
        )
    else:
        console.print(f"Collector: [yellow]{c['state']}[/yellow]. {escape(c['explanation'])}")

    styles = {"changed": "green", "unchanged": "green", "answered": "green",
              "failed": "red", "never_run": "dim"}
    table = Table(title=f"Sources on {data['day']}", box=box.SIMPLE_HEAVY)
    for name in ("Source", "State", "Tries", "OK", "Degr", "Err", "Changed", "Same",
                 "First", "Last", "Obs", "Reason / context"):
        table.add_column(name, justify="right" if name in {
            "Tries", "OK", "Degr", "Err", "Changed", "Same", "Obs"} else "left")
    for row in data["sources"]:
        counts = row.get("status_counts") or {}
        changes = row.get("payload_changes") or {}
        state = Text(row["day_state"], style=styles.get(row["day_state"], "yellow"))
        if row["attempts"]:
            top = (row.get("reasons") or [None])[0]
            context = ""
            if top:
                kind = "extraction: " if top.get("kind") == "extraction" else ""
                context = f"{kind}{top['reason']} (x{top['count']})"
            if row.get("more_reasons"):
                context += f" +{row['more_reasons']} more"
            stored = row.get("observations_stored")
            if stored is not None:
                obs = str(stored)
            else:
                # An extractor that raised stored nothing: unknown, not "none".
                obs = "?" if row.get("captures_extractor_raised") else "-"
            if row.get("partial_failure"):
                state = Text(f"{row['day_state']}, {counts['error']} failed", style="yellow")
        else:
            parts = []
            if row.get("last_capture_before"):
                parts.append(f"last before {row['last_capture_before']}")
            if row.get("next_capture_after"):
                parts.append(f"next after {row['next_capture_after']}")
            context = ", ".join(parts)
            obs = str(row["observations_retained"]) if row["observations_retained"] else "-"
        table.add_row(
            _cell(row["source"]),
            state,
            str(row["attempts"]),
            str(counts.get("ok", "-")),
            str(counts.get("degraded", "-")),
            str(counts.get("error", "-")),
            (f"{changes['changed']}" + (f" +{changes['first']} first" if changes["first"] else ""))
            if changes else "-",
            str(changes.get("unchanged", "-")),
            _cell(row.get("first_capture_at") or "-"),
            _cell(row.get("last_capture_at") or "-"),
            obs,
            _cell(context),
        )
    console.print(table)
    states = ", ".join(f"{k} {v}" for k, v in sorted(data["state_counts"].items()))
    console.print(f"States: {states}.")

    items = data["observations"]
    trunc = data["truncation"]
    if items:
        obs_table = Table(
            title=f"Observations saved that day ({trunc['returned']:,} of {trunc['matched']:,})",
            box=box.SIMPLE_HEAVY,
        )
        for name in ("Collected", "Source", "Series", "Observed", "Published", "Value", "Unit"):
            obs_table.add_column(name, justify="right" if name == "Value" else "left")
        for item in items:
            obs_table.add_row(
                item["collected_at"],
                _cell(item["source"]),
                _cell(item["series_key"]),
                _cell(item["observed_at"] or "unknown"),
                _cell(item["published_at"] or "unknown"),
                f"{item['value']:g}",
                _cell(item.get("unit") or ""),
            )
        console.print(obs_table)
    else:
        console.print("[dim]No observations saved that day.[/dim]")


def _print_day_observed(data: dict) -> None:
    def _points_table(title: str, points: list[dict]) -> Table:
        table = Table(title=title, box=box.SIMPLE_HEAVY)
        for name in ("Observed", "Precision", "Series", "Value", "Unit", "Published",
                     "Collected", "Stored"):
            table.add_column(name, justify="right" if name in {"Value", "Stored"} else "left")
        for point in points:
            stored = str(point["stored_values"])
            if point["stored_values"] > 1:
                stored += f" (first {point['first_value']:g} at {point['first_collected_at']})"
            table.add_row(
                _cell(point["observed_at"]),
                point["precision"],
                _cell(point["series_key"]),
                f"{point['value']:g}",
                _cell(point.get("unit") or ""),
                _cell(point["published_at"] or "unknown"),
                point["collected_at"],
                stored,
            )
        return table

    day_trunc = data["truncation"]["day_values"]
    if data["day_values"]:
        console.print(_points_table(
            f"Values observed on {data['day']} ({day_trunc['returned']:,} of "
            f"{day_trunc['matched']:,})",
            data["day_values"],
        ))
    else:
        console.print(f"[yellow]No stored value is observed on {data['day']}.[/yellow]")
    if data["period_values"]:
        period_trunc = data["truncation"]["period_values"]
        console.print(_points_table(
            f"Period values containing the day, not values for it "
            f"({period_trunc['returned']:,} of {period_trunc['matched']:,})",
            data["period_values"],
        ))
        console.print(f"[dim]{escape(data['period_values_note'])}[/dim]")
    if data["sources"]:
        table = Table(title="By source", box=box.SIMPLE_HEAVY)
        for name in ("Source", "Day values", "Revised", "Period values", "No observed_at"):
            table.add_column(name, justify="left" if name == "Source" else "right")
        for row in data["sources"]:
            table.add_row(
                _cell(row["source"]),
                str(row["day_values"]),
                str(row["day_values_revised"]),
                str(row["period_values"]),
                str(row["without_observed_at_collected_that_day"]),
            )
        console.print(table)
# ---------------------------------------------------------------------------
# Backfill (history FRED and the ECB already serve, into the history store)
# ---------------------------------------------------------------------------


@history_group.group(name="backfill")
def backfill_group() -> None:
    """Load history FRED or the ECB Data Portal already serve into the history store.

    Values are the publisher's current vintage, so revisions made before the
    first backfill are invisible. Read them back with intel history series.
    """


def _run_backfill(
    ctx: click.Context, provider: str, requests: tuple[str, ...], start: str | None
) -> None:
    from . import history_backfill
    from .history import HistoryStore

    fetcher = _get_fetcher()
    run = history_backfill.backfill_fred if provider == "fred" else history_backfill.backfill_ecb
    store = HistoryStore(fetcher.cache.db_path)
    try:
        data = _run(run(fetcher, store, list(requests), start))
    finally:
        store.close()
    if ctx.obj.get("json"):
        _print_json(data)
    else:
        _print_backfill(data)
    if "error" in data or data["totals"]["failed"]:
        ctx.exit(1)


def _print_backfill(data: dict) -> None:
    if data.get("error"):
        console.print(f"[red]Error:[/red] {escape(str(data['error']))}")
    # A store write failure (history_backfill._store_failure) names what it
    # did not write; the committed requests follow as a table.
    for label, key in (
        ("Write failed on", "failed_request"),
        ("Fetched but not written", "fetched_not_written"),
        ("Upstream failures logged", "upstream_failures_logged"),
        ("Upstream failures not logged", "upstream_failures_not_logged"),
    ):
        value = data.get(key)
        if value:
            names = value if isinstance(value, list) else [value]
            console.print(f"{label}: {escape(', '.join(names))}")
    if not data.get("requests"):
        return
    title = f"Backfill into {data['source']}"
    if data.get("collected_at"):
        title += f" at {data['collected_at']}"
    if data.get("start"):
        title += f" from {data['start']}"
    table = Table(title=escape(title), box=box.SIMPLE_HEAVY)
    table.add_column("Series", style="bold")
    table.add_column("Status")
    table.add_column("Loaded", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Revised", justify="right")
    table.add_column("Unchanged", justify="right")
    table.add_column("Missing", justify="right")
    table.add_column("Observed from")
    table.add_column("Observed to")
    for req in data["requests"]:
        if req["status"] == "error":
            table.add_row(_cell(req["request"]), Text("error", style="red"), *["-"] * 7)
            continue
        for s in req["series"]:
            table.add_row(
                _cell(s["series_key"]),
                Text("ok", style="green"),
                str(s["loaded"]),
                str(s["stored_new"]),
                str(s["stored_revised"]),
                str(s["unchanged"]),
                "unknown" if s["missing_skipped"] is None else str(s["missing_skipped"]),
                _cell(s["first_observed_at"] or "-"),
                _cell(s["last_observed_at"] or "-"),
            )
    console.print(table)
    totals = data.get("totals")
    if totals:
        console.print(
            f"Stored {totals['stored_new']} new and {totals['stored_revised']} revised values, "
            f"{totals['unchanged']} unchanged, in {escape(data['db_path'])}."
        )
    _print_data_gaps(data)


@backfill_group.command(name="fred")
@click.argument("series_ids", nargs=-1, required=True)
@click.option("--start", default=None, help="Only observations on or after YYYY-MM-DD")
@click.pass_context
def backfill_fred_cmd(ctx: click.Context, series_ids: tuple[str, ...], start: str | None) -> None:
    """Load FRED graph CSV series (up to 5).

    For example: intel history backfill fred WALCL RRPONTSYD DGS10 --start 2020-01-01
    """
    _run_backfill(ctx, "fred", series_ids, start)


@backfill_group.command(name="ecb")
@click.argument("keys", nargs=-1, required=True)
@click.option("--start", default=None, help="Only observations on or after YYYY-MM-DD")
@click.pass_context
def backfill_ecb_cmd(ctx: click.Context, keys: tuple[str, ...], start: str | None) -> None:
    """Load ECB Data Portal series (up to 2 keys).

    Each key is DATASET.KEY, for example BSI.M.U2.Y.V.M30.X.1.U2.2300.Z01.E
    (euro area M3); a key with + alternatives loads every series it matches.
    """
    _run_backfill(ctx, "ecb", keys, start)


if __name__ == "__main__":
    main()
