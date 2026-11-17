"""Worked research questions served as MCP prompts.

Each prompt is a research question a model can run against this server:
the tools to call (named exactly as registered), the arguments to pass
them, what each call is for, and the limits an honest answer has to
respect. ``guide.py`` turns these into MCP ``Prompt`` / ``GetPromptResult``
objects; this module holds the data and the text rendering only.

Step arguments are data (``Step.args``), not prose, so the tests can hold
every argument a prompt tells a model to pass against that tool's
``inputSchema``: the name exists, a required parameter is supplied, an
enum value is allowed and a number is a number. Every tool named here
must exist in the live registry, and every ``intel_*`` name that appears
anywhere in a rendered prompt, argument values included, must be one of
that prompt's own tools. ``tests/test_guide.py`` pins all of this, so a
renamed tool or parameter fails the suite instead of leaving a prompt
that sends a model somewhere that is not there.

Gaps / not covered:
- The tests check argument names, types and enum values against the
  schemas and output-field names against the package source. They cannot
  check that a step's purpose text describes what the tool returns; that
  rests on reading the source modules.
"""

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Rendered into every prompt after its own limits.
COMMON_LIMITS: tuple[str, ...] = (
    "A tool that returns an error, a note or a data_gaps entry has told you "
    "what is missing: report it as missing. Missing data is never zero, calm "
    "or peace.",
    "Many tools do not mark a failure. When every upstream request fails "
    "they return an empty list, a zero count, a neutral score, a LOW risk "
    "label, an all-clear status or a false flag. Read an empty list or a "
    "zero as nothing returned, not nothing happened, and confirm with a "
    "second tool before calling a place quiet.",
    "Give each figure the date it describes (the observation date) as well "
    "as when it was fetched; they are often different. If a tool gives no "
    "observation date, say so.",
    "Describe what the data show. This server does not forecast prices, "
    "give trading advice or prove causation.",
)

ANSWER_SHAPE = (
    "Answer with: the place, period and measure you used; each number with "
    "its unit (or say the source states none) and date; the comparison you "
    "were asked for; every data gap; "
    "and one line on what this data cannot tell."
)

_MAX_ARG_CHARS = 200
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_INTEGER = re.compile(r"[+-]?\d+", re.ASCII)
_DECIMAL = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
# Values with these characters are quoted so they cannot run into the
# next argument in "name value, name value". In a call, a value with a
# space is quoted too, so "Sudan days 9999" cannot read as extra pairs.
_QUOTE_IF = re.compile(r"[,;\"<>]")
_QUOTE_IN_CALL = re.compile(r"[,;\"<>\s]")
TOOL_NAME = re.compile(r"\bintel_[a-z0-9_]+\b")
# The tool-name guard reads a value the way a model might: compatibility
# forms folded (NFKC), case folded, hyphens as underscores, and no word
# boundary in front, so INTEL_AOI_DELETE and _intel_aoi_delete are caught.
_GUARD_NAME = re.compile(r"intel_[a-z0-9_]+")

ARG_KINDS = ("text", "int", "number")


def _number_text(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)


@dataclass(frozen=True)
class PromptArg:
    name: str
    description: str
    required: bool = False
    # Used when the argument is not given. An optional argument without a
    # default is left out of every call that would take it, and ``absent``
    # stands in for it in the prose.
    default: str | None = None
    absent: str | None = None
    choices: tuple[str, ...] = ()
    kind: str = "text"
    minimum: float | None = None
    maximum: float | None = None

    @property
    def help(self) -> str:
        """The description with the accepted range and default appended."""
        parts = [self.description]
        if self.minimum is not None and self.maximum is not None:
            parts.append(f"{_number_text(self.minimum)} to {_number_text(self.maximum)}")
        if self.default is not None:
            parts.append(f"default {self.default}")
        return "; ".join(parts)


@dataclass(frozen=True)
class Fill:
    """An argument value the model has to work out, usually from an
    earlier step's output. Rendered as ``<what>``."""

    what: str


@dataclass(frozen=True)
class Step:
    tool: str
    purpose: str
    # (parameter, value) pairs. A value is a literal, "{argument}" for a
    # prompt argument (or a derived value), or a Fill.
    args: tuple[tuple[str, Any], ...] = ()
    # A prompt argument this call needs; without it the step says to skip.
    only_if: str | None = None


@dataclass(frozen=True)
class ResearchPrompt:
    name: str
    title: str
    domain: str
    question: str
    steps: tuple[Step, ...]
    limits: tuple[str, ...]
    arguments: tuple[PromptArg, ...] = ()
    # (name, source argument, factor): a value computed from a numeric
    # argument, such as twice a comparison window.
    derived: tuple[tuple[str, str, int], ...] = ()

    def __post_init__(self) -> None:
        # A step that takes no arguments may be written as a
        # (tool, purpose) pair.
        object.__setattr__(
            self,
            "steps",
            tuple(s if isinstance(s, Step) else Step(*s) for s in self.steps),
        )

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(step.tool for step in self.steps)

    @property
    def description(self) -> str:
        return f"{self.title}. Uses {', '.join(dict.fromkeys(self.tools))}."


class PromptArgumentError(ValueError):
    """A prompt was requested with missing, unknown or invalid arguments."""


def _clean(raw: Any) -> str:
    kept = "".join(
        ch for ch in str(raw) if ch.isspace() or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    return " ".join(kept.split())


def _guard_names(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", value).casefold().replace("-", "_")
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    return _GUARD_NAME.findall(folded)


def _parse(prompt: ResearchPrompt, arg: PromptArg, value: str) -> Any:
    if arg.kind == "text":
        return value
    if arg.kind == "int":
        # ASCII digits only: int() also reads other scripts' digits.
        if not _INTEGER.fullmatch(value):
            raise PromptArgumentError(
                f"Prompt '{prompt.name}' argument '{arg.name}' must be a whole "
                f"number (got '{value}')"
            )
        number: float = int(value)
    else:
        try:
            # ASCII digits only: float() also reads other scripts' digits,
            # underscores, inf and nan.
            number = float(value) if _DECIMAL.fullmatch(value) else math.nan
        except ValueError:
            number = math.nan
        if not math.isfinite(number):
            raise PromptArgumentError(
                f"Prompt '{prompt.name}' argument '{arg.name}' must be a number "
                f"(got '{value}')"
            )
    if (arg.minimum is not None and number < arg.minimum) or (
        arg.maximum is not None and number > arg.maximum
    ):
        raise PromptArgumentError(
            f"Prompt '{prompt.name}' argument '{arg.name}' must be between "
            f"{_number_text(arg.minimum)} and {_number_text(arg.maximum)} "
            f"(got '{value}')"
        )
    return number


def _resolve_args(prompt: ResearchPrompt, given: dict[str, str] | None) -> dict[str, Any]:
    given = dict(given or {})
    known = {a.name for a in prompt.arguments}
    unknown = sorted(set(given) - known)
    if unknown:
        accepted = ", ".join(sorted(known)) or "none"
        raise PromptArgumentError(
            f"Prompt '{prompt.name}' does not take {', '.join(unknown)} "
            f"(accepted: {accepted})"
        )
    values: dict[str, Any] = {}
    for arg in prompt.arguments:
        raw = given.get(arg.name)
        # Control and format characters (escape, NUL, zero-width) are
        # dropped, and whitespace, newlines included, collapses to single
        # spaces, so a value stays on its line and cannot add steps or
        # limits.
        value = _clean(raw) if raw is not None else ""
        if len(value) > _MAX_ARG_CHARS:
            raise PromptArgumentError(
                f"Prompt '{prompt.name}' argument '{arg.name}' is longer than "
                f"{_MAX_ARG_CHARS} characters"
            )
        if not value:
            if arg.required:
                raise PromptArgumentError(
                    f"Prompt '{prompt.name}' needs argument '{arg.name}': "
                    f"{arg.description}"
                )
            if arg.default is None:
                values[arg.name] = None
                continue
            value = arg.default
        foreign = sorted(set(_guard_names(value)) - set(prompt.tools))
        if foreign:
            raise PromptArgumentError(
                f"Prompt '{prompt.name}' argument '{arg.name}' names "
                f"{', '.join(foreign)}, which this prompt does not call"
            )
        if arg.choices and value not in arg.choices:
            raise PromptArgumentError(
                f"Prompt '{prompt.name}' argument '{arg.name}' must be one of "
                f"{', '.join(arg.choices)} (got '{value}')"
            )
        values[arg.name] = _parse(prompt, arg, value)
    for name, source, factor in prompt.derived:
        values[name] = values[source] * factor
    return values


def _step_args(step: Step, values: dict[str, Any]) -> dict[str, Any] | None:
    """The arguments for one call, or None when the step is skipped."""
    if step.only_if is not None and values.get(step.only_if) is None:
        return None
    out: dict[str, Any] = {}
    for param, raw in step.args:
        value = raw
        if isinstance(raw, str):
            whole = _PLACEHOLDER.fullmatch(raw)
            if whole:
                value = values.get(whole.group(1))
        if value is not None:
            out[param] = value
    return out


def resolved_steps(
    prompt: ResearchPrompt, arguments: dict[str, str] | None = None
) -> list[tuple[Step, dict[str, Any] | None]]:
    """Each step with the arguments it passes (None: the step is skipped).

    Values keep their types (int, float, list, Fill), which is what the
    schema tests check.
    """
    values = _resolve_args(prompt, arguments)
    return [(step, _step_args(step, values)) for step in prompt.steps]


def _show(value: Any, in_call: bool = False) -> str:
    if isinstance(value, Fill):
        return f"<{value.what}>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number_text(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    text = str(value)
    quote_if = _QUOTE_IN_CALL if in_call else _QUOTE_IF
    return json.dumps(text, ensure_ascii=False) if quote_if.search(text) else text


def render(prompt: ResearchPrompt, arguments: dict[str, str] | None = None) -> str:
    """The prompt's user-message text with its arguments filled in."""
    values = _resolve_args(prompt, arguments)
    absent = {a.name: a.absent or "not given" for a in prompt.arguments}
    prose = {
        name: _show(value) if value is not None else absent[name]
        for name, value in values.items()
    }

    def fill(text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: prose.get(m.group(1), m.group(0)), text)

    lines = [f"Research question: {fill(prompt.question)}", "", "Tools to call:"]
    for i, step in enumerate(prompt.steps, 1):
        args = _step_args(step, values)
        if args is None:
            lines.append(f"{i}. {step.tool}: skip this call; no {step.only_if} was given.")
            continue
        pairs = ", ".join(f"{name} {_show(value, in_call=True)}" for name, value in args.items())
        call = f"call with {pairs}; " if pairs else ""
        lines.append(f"{i}. {step.tool}: {call}{fill(step.purpose)}")
    lines += ["", "Limits to respect:"]
    lines += [f"- {fill(limit)}" for limit in prompt.limits]
    lines += [f"- {limit}" for limit in COMMON_LIMITS]
    lines += ["", ANSWER_SHAPE]
    return "\n".join(lines)


_COUNTRY = PromptArg("country", "Country name, e.g. Sudan", required=True)
_ISO3 = PromptArg("country", "ISO alpha-3 country code, e.g. UKR", required=True)
_FIRMS_REGIONS = (
    "north_america",
    "south_america",
    "europe",
    "africa",
    "middle_east",
    "south_asia",
    "east_asia",
    "southeast_asia",
    "oceania",
)
# The keys of sources/jet_cohort.REGIONS (a test pins the match).
_JET_REGIONS = ("global", "conus", "north_america", "europe", "middle_east", "east_asia")


PROMPTS: tuple[ResearchPrompt, ...] = (
    # --- conflict -------------------------------------------------------
    ResearchPrompt(
        name="conflict-trend",
        title="Conflict trend in one country against the previous period",
        domain="conflict",
        question=(
            "How has organized violence in {country} changed over the last "
            "{days} days, and is it more or less intense than the {days} days "
            "before that?"
        ),
        arguments=(
            PromptArg("country", "Country name as the sources spell it, e.g. Sudan", required=True),
            PromptArg(
                "days", "Length of each comparison window in days", default="30",
                kind="int", minimum=1, maximum=365,
            ),
        ),
        derived=(("span", "days", 2),),
        steps=(
            Step(
                "intel_ucdp_events",
                "UCDP events of all three types (state-based, non-state and "
                "one-sided; see type_of_violence_label) for every country. It "
                "needs UCDP_ACCESS_TOKEN: without it, or when the API refuses "
                "it, the tool returns an error with reason ucdp_unconfigured or "
                "ucdp_fetch_failed, which is missing data, not zero events. It "
                "has no country filter, so keep the events in {country} "
                "yourself, split them at {days} days ago by date_start, and say "
                "that you filtered. limit is the page size and every page is "
                "requested, so it does not cap the result. When a page could "
                "not be fetched the result carries reason ucdp_partial and "
                "pages_failed: its count and fatalities are then lower bounds, "
                "so say the list is incomplete",
                args=(("days", "{span}"), ("limit", 1000)),
            ),
            Step(
                "intel_acled_events",
                "ACLED events in {country} over both windows. It needs "
                "ACLED_EMAIL and ACLED_PASSWORD; without them it returns an "
                "error naming them. limit caps the result: a count equal to the "
                "limit means the list may have been cut off, so say so or call "
                "again with a higher limit",
                args=(("country", "{country}"), ("days", "{span}"), ("limit", 1000)),
            ),
            Step(
                "intel_unrest_events",
                "protests and riots in {country} (also ACLED, same credentials), "
                "kept apart from armed violence. Nearby duplicates are merged: "
                "count plus deduplicated is what was fetched, and when that "
                "equals the limit the list may have been cut off",
                args=(("country", "{country}"), ("days", "{span}"), ("limit", 1000)),
            ),
        ),
        limits=(
            "Event datasets are revised and arrive late, so the most recent "
            "days are the least complete. A quiet final week is not proof of calm.",
            "UCDP is read from one pinned GED release (gedevents/25.1), which "
            "holds events only up to its own cutoff. The tool states neither "
            "that cutoff nor a marker when your window lies after it: it "
            "drops the older events and returns count 0. Check the latest "
            "date_start UCDP returned; when count is 0, or the newest event "
            "is well before the window ends, UCDP has no data for that span, "
            "which is missing data, not zero events.",
            "Count events and fatalities separately: fewer events with more "
            "deaths is not de-escalation.",
            "ACLED and UCDP define an event differently. Compare each source "
            "with itself across the two windows, never one source's count "
            "against the other's.",
        ),
    ),
    ResearchPrompt(
        name="hotspot-escalation",
        title="Which hotspots are escalating and why",
        domain="conflict",
        question=(
            "Which of the built-in hotspots score highest for escalation right "
            "now, and which measured component drives each score?"
        ),
        steps=(
            ("intel_hotspot_escalation", "scores and their components for the 22 hotspots"),
            ("intel_military_surge", "foreign military aircraft concentrations against baseline"),
            ("intel_theater_posture", "military aircraft presence by theater"),
        ),
        limits=(
            "Escalation scores are weighted heuristics against fixed "
            "baselines, renormalized over the components actually measured. "
            "They are not probabilities of war. List the unavailable_components.",
            "The escalation score's military component is 0 at every hotspot "
            "whatever the aircraft data, during a flight outage too, and "
            "unavailable_components does not list it: take military activity "
            "from intel_military_surge and intel_theater_posture instead.",
            "Aircraft tracking sees only aircraft that broadcast a position, "
            "and many military flights do not, so counts are a floor. A "
            "theater that no flight source answered for is listed in "
            "intel_theater_posture's unavailable_theaters, and its regions in "
            "intel_military_surge's unchecked_regions: its count is unknown, "
            "not zero. With no source answering anywhere, both tools return "
            "an error.",
        ),
    ),
    # --- markets and economy ---------------------------------------------
    ResearchPrompt(
        name="market-risk-snapshot",
        title="Cross-asset risk picture today",
        domain="markets",
        question=(
            "What does the current risk picture look like across equities, "
            "volatility, the dollar, rates and crypto?"
        ),
        steps=(
            ("intel_macro_signals", "Fear and Greed, VIX, DXY, gold, 10-year yield, BTC dominance"),
            ("intel_sector_heatmap", "which US equity sectors are leading and lagging"),
            ("intel_yield_curve", "curve shape and spreads"),
            ("intel_macro_composite", "the composite score and the inputs it weighs"),
            (
                "intel_liquidity_board",
                "keyless liquidity readings (Fed balance sheet, Treasury General "
                "Account, reverse repo, net liquidity, money supply), each with "
                "its units and observation date",
            ),
            (
                "intel_net_liquidity",
                "only if liquidity matters to the answer: the weekly US net "
                "liquidity series behind the board's row, with its formula",
            ),
        ),
        limits=(
            "Report current readings and their recent change only. Quote the "
            "composite score next to its inputs, since it is a weighted summary "
            "of them.",
        ),
    ),
    ResearchPrompt(
        name="yield-curve-check",
        title="Is the Treasury curve inverted, and by how much",
        domain="markets",
        question=(
            "Is the US Treasury yield curve inverted today, by how much, and "
            "how has the 10-year minus 2-year spread moved recently?"
        ),
        steps=(
            ("intel_yield_curve", "maturities, the 2s10s and 3m10y spreads and the inversion flag"),
            Step(
                "intel_fred_series",
                "the spread's recent daily history (needs FRED_API_KEY)",
                args=(("series_id", "T10Y2Y"),),
            ),
            ("intel_central_bank_rates", "the policy rate the short end is anchored to"),
            Step(
                "intel_history_backfill",
                "only if FRED_API_KEY is not set: loads the T10Y2Y history from "
                "FRED's keyless graph CSV into the history store (it stores no "
                "unit for this series; a failed fetch is an error capture)",
                args=(("provider", "fred"), ("series", ["T10Y2Y"])),
            ),
            Step(
                "intel_series_history",
                "only after that backfill: the stored T10Y2Y observations with "
                "their observed_at dates",
                args=(("series_key", "backfill:fred:T10Y2Y"),),
            ),
        ),
        limits=(
            "Spreads are in percentage points. A move from 0.10 to 0.30 is "
            "0.20 points, not a 200 percent rise.",
            "Without FRED_API_KEY the curve falls back to four Yahoo "
            "maturities (3M, 5Y, 10Y, 30Y) with no observation dates, so "
            "spread_2s10s comes back null. Say so; do not swap in another "
            "spread without saying which.",
            "An inverted curve describes today's yields. It is not a "
            "recession forecast.",
        ),
    ),
    ResearchPrompt(
        name="central-bank-compare",
        title="Where major central bank policy rates stand",
        domain="markets",
        question=(
            "Where do the Federal Reserve, ECB and Bank of England policy "
            "rates stand now, how has the US federal funds rate moved "
            "recently, and what did the other major central banks last set, "
            "as of the dates on record?"
        ),
        steps=(
            (
                "intel_central_bank_rates",
                "rates for 15 central banks; each entry carries its source "
                "(fred or curated) and as_of date",
            ),
            Step(
                "intel_fred_series",
                "the daily effective federal funds rate history (needs FRED_API_KEY)",
                args=(("series_id", "DFF"),),
            ),
            ("intel_major_crosses", "the major currency cross rates: how they sit against each other today"),
            Step(
                "intel_history_backfill",
                "only if FRED_API_KEY is not set: loads the effective federal "
                "funds rate history from FRED's keyless graph CSV into the "
                "history store (a failed fetch is an error capture)",
                args=(("provider", "fred"), ("series", ["DFF"])),
            ),
            Step(
                "intel_series_history",
                "only after that backfill: the stored observations of that "
                "rate with their observed_at dates",
                args=(("series_key", "backfill:fred:DFF"),),
            ),
        ),
        limits=(
            "Only the Fed, ECB and BoE rates can be live, read from FRED when "
            "FRED_API_KEY is set (source fred). The other twelve come from a "
            "hand-kept table dated 2024-11 to 2025-02 (source curated): report "
            "them as stale, with their as_of dates, never as current.",
            "fred_available only says that FRED_API_KEY is set, not that FRED "
            "answered. A curated Fed, ECB or BoE entry means the FRED read "
            "failed or the key is missing.",
            "The live Fed figure is the effective rate (DFF) and the live BoE "
            "figure is SONIA, an overnight market rate that tracks Bank Rate; "
            "the curated Fed entry is the upper bound of the target range. Do "
            "not read a gap between a live and a curated figure as a policy "
            "change.",
            "Rate changes are in percentage points or basis points (one point "
            "is 100 basis points), not percent of the rate.",
        ),
    ),
    ResearchPrompt(
        name="fx-move",
        title="A currency pair's move and the coverage around it",
        domain="markets",
        question=(
            "How has {symbol} moved against {base} over the last {days} days, "
            "and what news coverage ran alongside the largest daily moves?"
        ),
        arguments=(
            PromptArg("symbol", "Quote currency, ISO code such as EUR", required=True),
            PromptArg("base", "Base currency, ISO code", default="USD"),
            PromptArg("days", "Days of history", default="30", kind="int", minimum=1, maximum=365),
        ),
        steps=(
            Step(
                "intel_forex_timeseries",
                "daily ECB reference rates. Each rate is units of {symbol} per "
                "1 {base}, and trend.change_pct is the change in that number: "
                "a positive change means one {base} buys more {symbol}, so "
                "{symbol} weakened against {base}. Say which way you quote the move",
                args=(("base", "{base}"), ("symbol", "{symbol}"), ("days", "{days}")),
            ),
            ("intel_major_crosses", "where the pair sits among the majors today"),
            Step(
                "intel_gdelt_search",
                "recent articles about the currency. The tool has no date "
                "parameter and searches GDELT's default window, so keep the "
                "articles whose seendate falls on or just after the dates of "
                "the largest moves, and say how many matched",
                args=(("query", Fill("the currency's name, such as yen or euro")), ("mode", "artlist")),
            ),
        ),
        limits=(
            "ECB reference rates are published once per business day. A "
            "weekend or holiday has no observation, which is not a zero change.",
            "An empty rates list with a null trend means the fetch failed, "
            "not that the currency was flat.",
            "News published alongside a move is context. Timing alone does "
            "not show that the news caused the move.",
        ),
    ),
    ResearchPrompt(
        name="company-events",
        title="A company's recent disclosures and results",
        domain="markets",
        question=(
            "What material events has {ticker} disclosed recently, and how did "
            "its reported results compare with estimates?"
        ),
        arguments=(PromptArg("ticker", "Stock ticker, e.g. AAPL", required=True),),
        steps=(
            Step("intel_company_profile", "quote, sector and recent news", args=(("query", "{ticker}"),)),
            Step(
                "intel_company_filings",
                "recent 10-K, 10-Q and 8-K filings",
                args=(("ticker", "{ticker}"),),
            ),
            Step(
                "intel_earnings_surprise",
                "actual against estimated earnings",
                args=(("symbol", "{ticker}"),),
            ),
            (
                "intel_news_market_reaction",
                "companies named in recent news story clusters with the stock's "
                "move on the story's session against a benchmark. If {ticker} "
                "is not listed, no recent cluster was mapped to it, which is "
                "not the same as no news",
            ),
        ),
        limits=(
            "A filing date is when the company filed, not when the event "
            "happened; give both when the filing states the event date.",
            "No buy, sell or hold view: describe what was disclosed.",
        ),
    ),
    ResearchPrompt(
        name="energy-pressure",
        title="Energy prices from futures to the pump",
        domain="markets",
        question=(
            "Are energy prices rising for producers and for consumers, and is "
            "any chokepoint exposure relevant to the move?"
        ),
        steps=(
            ("intel_commodity_quotes", "crude oil and natural gas futures"),
            ("intel_energy_prices", "EIA crude and gas prices (needs EIA_API_KEY)"),
            ("intel_gas_prices", "AAA US retail gasoline and diesel averages"),
            ("intel_trade_routes", "oil flows through the major chokepoints"),
        ),
        limits=(
            "Futures, wholesale and retail pump prices are different measures "
            "with different dates. Never join them into one series.",
            "Chokepoint oil flows are curated reference values, not live "
            "tanker counts.",
        ),
    ),
    ResearchPrompt(
        name="crypto-structure",
        title="Crypto market structure today",
        domain="markets",
        question=(
            "What is the state of the crypto market today: prices, stablecoin "
            "pegs, spot ETF trading and Bitcoin's trend indicators?"
        ),
        steps=(
            ("intel_crypto_quotes", "prices and market caps of the largest coins"),
            ("intel_stablecoin_status", "whether the major stablecoins hold their peg"),
            ("intel_etf_flows", "Bitcoin spot ETF prices and trading volume"),
            ("intel_btc_technicals", "moving averages, Mayer Multiple and distance from "
             "the highest daily price of the last 200 days (ath_in_period, not the "
             "all-time high)"),
        ),
        limits=(
            "intel_etf_flows reports prices and trading volume, not creations "
            "or redemptions. Volume is not net flow.",
            "Technical indicators summarize past prices; they do not predict "
            "the next move.",
        ),
    ),
    # --- hazards ----------------------------------------------------------
    ResearchPrompt(
        name="earthquake-exposure",
        title="Recent strong earthquakes near people",
        domain="hazards",
        question=(
            "Which earthquakes of magnitude {min_magnitude} or more in the "
            "last {hours} hours struck near large populations, and did any "
            "raise a disaster alert?"
        ),
        arguments=(
            PromptArg(
                "min_magnitude", "Smallest magnitude to include", default="5.5",
                kind="number", minimum=0, maximum=10,
            ),
            PromptArg("hours", "Lookback in hours", default="48", kind="int", minimum=1, maximum=720),
        ),
        steps=(
            Step(
                "intel_earthquakes",
                "the earthquakes, newest first and at most 50 by default, so a "
                "count of 50 means older ones may have been cut off; call again "
                "with a higher limit to check",
                args=(("min_magnitude", "{min_magnitude}"), ("hours", "{hours}")),
            ),
            Step(
                "intel_population_exposure",
                "major cities within radius_km (default 200) of recent events. "
                "It ignores the magnitude and hours above: it fetches its own "
                "list of M4.5 and larger quakes from the last 48 hours, at most "
                "50, and names only the nearest of them for each city, so a "
                "city's event_detail (\"M<magnitude> <place>\") can name a "
                "smaller aftershock while a step-1 event is also within reach. "
                "Before dropping a city, compare its lat and lon with each "
                "step-1 event and keep it if any lies within radius_km; check "
                "events_analyzed: 0 can mean its fetch failed",
                args=(("event_types", ["earthquake"]),),
            ),
            Step(
                "intel_disaster_alerts",
                "the GDACS alert level of the same events",
                args=(("event_type", "EQ"),),
            ),
        ),
        limits=(
            "Exposure knows only 105 major cities, each with at least 1.4 "
            "million people. It is not a casualty estimate and misses everyone "
            "outside those cities.",
            "Magnitudes and locations are revised in the first hours after an "
            "event; say when you read them.",
        ),
    ),
    ResearchPrompt(
        name="severe-weather",
        title="Severe weather warnings in the covered regions",
        domain="hazards",
        question=(
            "What severe weather warnings are active in {us_area} and in "
            "{europe_country}, and are any tropical cyclones active?"
        ),
        arguments=(
            PromptArg("us_area", "Two-letter US state code, e.g. TX", absent="the United States"),
            PromptArg("europe_country", "Meteoalarm country, e.g. france", absent="Europe"),
        ),
        steps=(
            Step("intel_weather_alerts", "US National Weather Service alerts", args=(("area", "{us_area}"),)),
            Step(
                "intel_meteoalarm_alerts",
                "European warnings, one country per call; without country it "
                "lists the countries it covers",
                args=(("country", "{europe_country}"),),
            ),
            ("intel_cyclones", "Atlantic and eastern and central Pacific storms from the National Hurricane Center"),
            ("intel_jtwc_cyclones", "western Pacific, Indian Ocean and Southern Hemisphere storms from JTWC"),
        ),
        limits=(
            "NWS covers the US and Meteoalarm covers its participating "
            "European countries only. No alert outside those areas says "
            "nothing about the weather there.",
            "NHC and JTWC cover different basins and can label the same storm "
            "differently. Match storms by position and time before counting.",
        ),
    ),
    ResearchPrompt(
        name="wildfire-situation",
        title="Wildfire activity and the conditions around it",
        domain="hazards",
        question="How active are wildfires in {region} now, and are temperatures or rainfall abnormal there?",
        arguments=(
            PromptArg(
                "region",
                "FIRMS region: north_america, south_america, europe, africa, "
                "middle_east, south_asia, east_asia, southeast_asia or oceania",
                absent="all FIRMS regions",
                choices=_FIRMS_REGIONS,
            ),
        ),
        steps=(
            Step(
                "intel_wildfires",
                "satellite fire detections (needs NASA_FIRMS_API_KEY)",
                args=(("region", "{region}"),),
            ),
            Step(
                "intel_environmental_events",
                "named fires NASA EONET tracks",
                args=(("category", "wildfires"),),
            ),
            ("intel_climate_anomalies", "temperature and precipitation against the prior year"),
        ),
        limits=(
            "FIRMS detections are satellite heat signatures, not mapped fire "
            "perimeters; one large fire produces many detections.",
            "Without NASA_FIRMS_API_KEY the fire tool returns an error. With a "
            "key set, a region FIRMS did not answer is named in failed_regions "
            "and carries its own error (its count of 0 is not a measurement), "
            "and every region failing is an error. Report either as missing "
            "data, not zero fires.",
            "Climate anomalies are measured against the prior year, not a "
            "long-term normal.",
        ),
    ),
    ResearchPrompt(
        name="space-weather-impact",
        title="Space weather and coincident outages",
        domain="hazards",
        question=(
            "How strong is current geomagnetic and solar activity, and are "
            "internet or cloud outages being reported at the same time?"
        ),
        steps=(
            ("intel_space_weather", "Kp index, flare class, solar wind and SWPC alerts"),
            ("intel_internet_outages", "internet outages reported over the last 7 days"),
            ("intel_service_status", "active incidents at the major cloud providers"),
        ),
        limits=(
            "An outage at the same time as a storm does not show the storm "
            "caused it; most outages have local causes.",
            "An empty outage list can mean that both outage sources failed; "
            "the tool does not always say so.",
            "Kp runs 0 to 9 on a quasi-logarithmic scale: Kp 8 is far more "
            "than twice Kp 4.",
        ),
    ),
    # --- migration --------------------------------------------------------
    ResearchPrompt(
        name="displacement-history",
        title="A country's displacement record since 1951",
        domain="migration",
        question=(
            "How has displacement linked to {country} as {role} changed since "
            "records began, and which years saw the largest waves?"
        ),
        arguments=(
            _COUNTRY,
            PromptArg(
                "role",
                "origin (its people abroad, plus IDPs) or host (people it hosts)",
                default="origin",
                choices=("origin", "host"),
            ),
        ),
        steps=(
            Step(
                "intel_migration_history",
                "the yearly record",
                args=(("country", "{country}"), ("role", "{role}")),
            ),
            Step(
                "intel_migration_flows",
                "the latest year's largest corridors out of {country}; for the "
                "host view call it with destination {country} instead",
                args=(("origin", "{country}"),),
            ),
            ("intel_displacement_summary", "UNHCR's global displacement totals, for context"),
            Step(
                "intel_us_border_encounters",
                "only for the origin view: US CBP encounters per month of "
                "{country} citizens, a flow of events (not people, not a "
                "stock) that never adds to the displacement figures above",
                args=(("citizenship", Fill("the country as CBP names it, in capitals, e.g. MEXICO")),),
            ),
        ),
        limits=(
            "UNHCR figures are year-end stocks (people displaced at the end of "
            "each year), not arrivals during the year. A change between two "
            "years is a net change in the stock.",
            "UNHCR revises past years. Say which reporting year you used.",
        ),
    ),
    ResearchPrompt(
        name="migration-surges",
        title="The largest year-over-year displacement changes",
        domain="migration",
        question=(
            "Which origins and corridors had the largest year-over-year change "
            "in displacement in {year}, and how does that compare with net "
            "migration from all causes?"
        ),
        arguments=(
            PromptArg(
                "year", "Reporting year", absent="the latest year with data",
                kind="int", minimum=1951, maximum=2100,
            ),
        ),
        steps=(
            Step(
                "intel_migration_surges",
                "the largest increases and decreases against the year before",
                args=(("year", "{year}"),),
            ),
            ("intel_net_migration", "World Bank net migration for the leading countries"),
            ("intel_humanitarian_summary", "HDX crisis datasets for the leading origins"),
            (
                "intel_us_border_encounters",
                "only if the question turns to arrivals in the US: CBP "
                "encounters per month with same-month prior-year change, a "
                "flow of events, not a stock",
            ),
            (
                "intel_uk_small_boat_arrivals",
                "only if the question turns to arrivals in the UK: Home Office "
                "small boat crossings with year to date against last year, a "
                "flow of arrivals, not a stock",
            ),
        ),
        limits=(
            "World Bank net migration counts every reason, work included; "
            "UNHCR counts forcibly displaced people. Show them side by side "
            "and never add them together.",
            "The mass, major and notable levels are the tool's stated "
            "thresholds, not official designations.",
        ),
    ),
    # --- aviation ---------------------------------------------------------
    ResearchPrompt(
        name="airspace-anomaly",
        title="Unusual business jet or military air activity",
        domain="aviation",
        question=(
            "Is {cohort} air activity over {region} unusual for this time of "
            "the week, and if so, where did the extra aircraft come from?"
        ),
        arguments=(
            PromptArg("cohort", "bizjet or military", default="bizjet", choices=("bizjet", "military")),
            PromptArg(
                "region",
                "global, conus, north_america, europe, middle_east or east_asia",
                default="global",
                choices=_JET_REGIONS,
            ),
        ),
        steps=(
            Step(
                "intel_jet_cohort_snapshot",
                "the current picture; this call also builds the tracked cohort",
                args=(("cohort", "{cohort}"), ("region", "{region}")),
            ),
            Step(
                "intel_jet_activity_anomaly",
                "the latest half-hour against the same slot on earlier weeks",
                args=(("cohort", "{cohort}"), ("region", "{region}")),
            ),
            Step(
                "intel_jet_excess_origins",
                "only if step 2 flags an excess: where the extra departures came from",
                args=(("cohort", "{cohort}"), ("region", "{region}")),
            ),
            ("intel_military_flights", "for the military cohort, a second source of positions"),
        ),
        limits=(
            "ADS-B shows only aircraft whose transponders volunteer receivers "
            "pick up; many military and some private aircraft do not broadcast "
            "a usable position, so counts are a floor.",
            "When intel_military_flights reports source none, no flight "
            "source answered: it carries error, degraded and reason "
            "military_flights_unavailable, and its empty aircraft list is "
            "unknown, not an empty sky.",
            "An anomaly is a deviation from the same slot on earlier weeks. "
            "It is not evidence of anyone's intent.",
            "The anomaly check needs a learned cohort; a fresh install reports "
            "that gap first.",
        ),
    ),
    ResearchPrompt(
        name="airport-disruption",
        title="US airport delays and their likely weather context",
        domain="aviation",
        question="Which major US airports have delays now, and is severe weather active near them?",
        steps=(
            ("intel_airport_delays", "FAA ground stops, delay programs and closures at US airports"),
            ("intel_aviation_domestic", "the airborne traffic snapshot for scale"),
            ("intel_weather_alerts", "NWS alerts for the states of the delayed airports"),
        ),
        limits=(
            "FAA data lists only airports with an active event; an absent airport has none reported.",
            "The airborne total is a snapshot of aircraft OpenSky receives, "
            "not a count of all flights.",
        ),
    ),
    # --- cyber and infrastructure ----------------------------------------
    ResearchPrompt(
        name="cyber-landscape",
        title="Current cyber threat landscape",
        domain="cyber",
        question=(
            "What does the current cyber threat picture look like: newly "
            "known-exploited vulnerabilities, active malware infrastructure, "
            "and which threat actors are in the headlines?"
        ),
        steps=(
            ("intel_cyber_threats", "Feodo, CISA KEV, SANS and URLhaus indicators"),
            ("intel_keyword_spikes", "CVE and APT names rising in headlines against baseline"),
            ("intel_extract_entities", "CVEs, APT groups and organizations in recent headlines"),
        ),
        limits=(
            "Feeds list reported indicators and known-exploited "
            "vulnerabilities. A listing is not attribution and does not show "
            "that any particular organization was hit.",
            "Keyword spikes measure mentions in headlines, not attack volume.",
        ),
    ),
    ResearchPrompt(
        name="internet-disruption",
        title="Internet disruption in one country",
        domain="infrastructure",
        question=(
            "Is internet connectivity in {country} disrupted now, and could a "
            "cable corridor failure explain it?"
        ),
        arguments=(
            _COUNTRY,
            PromptArg(
                "resource",
                "An ASN or prefix to check, e.g. AS3333",
                absent="no ASN or prefix",
            ),
        ),
        steps=(
            ("intel_internet_outages", "outages over the last 7 days; keep those in {country}"),
            Step(
                "intel_bgp_status",
                "routing visibility for that network",
                args=(("resource", "{resource}"),),
                only_if="resource",
            ),
            ("intel_cable_health", "the condition of the six cable corridors"),
            ("intel_cascade_analysis", "which countries depend on an at-risk corridor"),
        ),
        limits=(
            "An empty outage list, an all-clear corridor reading or zero "
            "cable warnings can each be a failed fetch: when the warning feed "
            "is down every corridor reads clear. Check failing_sources in "
            "intel://guide/source-health before calling {country} connected: "
            "it lists every source whose last call failed, even before its "
            "circuit breaker opens.",
            "Cascade analysis is a simulation over curated cable "
            "dependencies, not a measurement of a real outage.",
            "BGP status checks one ASN or prefix at a time; it is not a "
            "global hijack detector.",
        ),
    ),
    ResearchPrompt(
        name="cloud-incidents",
        title="Cloud provider incidents and the regions involved",
        domain="infrastructure",
        question="Which cloud providers report active incidents, and which of their regions are involved?",
        steps=(
            ("intel_service_status", "active incidents at AWS, Azure, GCP, Cloudflare and GitHub"),
            ("intel_cloud_regions", "where the named cloud regions are"),
        ),
        limits=(
            "Status pages are published by the providers themselves and can "
            "lag or understate an incident.",
        ),
    ),
    ResearchPrompt(
        name="maritime-chokepoints",
        title="Pressure on maritime chokepoints",
        domain="maritime",
        question=(
            "Are navigational warnings building at the strategic waterways, "
            "and is shipping stress rising in markets?"
        ),
        steps=(
            ("intel_vessel_snapshot", "a warning-based status for the nine strategic waterways"),
            ("intel_nav_warnings", "the warning texts behind the status"),
            ("intel_trade_routes", "what share of oil and trade each chokepoint carries"),
            ("intel_shipping_index", "a stress score from shipping-linked ETF and equity prices"),
        ),
        limits=(
            "The vessel snapshot counts navigational warnings, not ships. A "
            "warning counts at a waterway only when a position its text states "
            "lies within 300 km of the waterway's reference point "
            "(matching_rule states the rule).",
            "A naval warning that states no readable position counts at no "
            "waterway and changes no status. It is listed in "
            "unplaced_naval_warnings with the reason: read those before "
            "calling any waterway clear.",
            "A waterway status of unknown means the warning feed was "
            "unavailable (error, degraded and reason say why), not a quiet "
            "sea. A status of stale means the feed's newest warning is older "
            "than stale_after_days: the counts describe the feed's last "
            "update (status_as_of), not today. Check feed_stale and "
            "newest_issue_date before calling any status current.",
            "The navarea filter of intel_nav_warnings takes NGA area codes "
            "(4, 12, A, P, C), their series names, or IV and XII for 4 and 12. "
            "Other NAVAREAs arrive inside the A, P and C series, and asking "
            "for one returns an error with reason navarea_not_carried, not a "
            "count of 0.",
            "The shipping stress score is a market proxy, not a freight rate.",
        ),
    ),
    # --- areas of interest --------------------------------------------------
    ResearchPrompt(
        name="aoi-watch-setup",
        title="Start watching an area of interest",
        domain="aoi",
        question=(
            "Set up a watch on {name} (centre {lat}, {lon}, radius {radius_km} "
            "km): what is inside it now, and what should later checks compare against?"
        ),
        arguments=(
            PromptArg("name", "A name for the area", required=True),
            PromptArg("lat", "Centre latitude in degrees", required=True, kind="number", minimum=-90, maximum=90),
            PromptArg("lon", "Centre longitude in degrees", required=True, kind="number", minimum=-180, maximum=180),
            PromptArg("radius_km", "Radius in kilometres", required=True, kind="number", minimum=1, maximum=2000),
        ),
        steps=(
            Step(
                "intel_aoi_define",
                "saves the area",
                args=(("name", "{name}"), ("lat", "{lat}"), ("lon", "{lon}"), ("radius_km", "{radius_km}")),
            ),
            Step(
                "intel_aoi_define_polygon",
                "only if a circle does not fit the area (a border region or a "
                "strait): define it under another name as a polygon of [lat, "
                "lon] vertices, and use that name in the steps below",
                args=(("name", Fill("a name for the polygon")), ("vertices", Fill("3 to 64 [lat, lon] vertices"))),
            ),
            Step(
                "intel_aoi_define_corridor",
                "only if the area is a route (a shipping lane or cable run): "
                "define it under another name as a corridor of waypoints with "
                "a width, and use that name in the steps below",
                args=(
                    ("name", Fill("a name for the corridor")),
                    ("waypoints", Fill("2 to 64 [lat, lon] waypoints")),
                    ("width_km", Fill("the total width in km, 1 to 500")),
                ),
            ),
            Step("intel_aoi_brief", "the cited picture inside {name} today", args=(("name", "{name}"),)),
            Step(
                "intel_aoi_changes",
                "the first change detection call records a baseline for {name}",
                args=(("name", "{name}"),),
            ),
        ),
        limits=(
            "The first change check records a baseline and claims nothing "
            "entered or left.",
            "A domain that fails is listed in data_gaps and left out of the "
            "diff; a wildfire region FIRMS did not answer is listed as partial "
            "coverage. Never read a failed domain as everything leaving. A "
            "whole domain departing at once with no data_gaps entry is still "
            "unconfirmed: check failing_sources in intel://guide/source-health "
            "and say it could not be confirmed.",
            "Each intel_aoi_changes call compares with the snapshot saved by "
            "the call before it (yours or a collector AOI sweep) and then "
            "replaces that snapshot.",
        ),
    ),
    ResearchPrompt(
        name="aoi-review",
        title="What changed in a watched area",
        domain="aoi",
        question="What entered or left {name} since the last snapshot, and is the area escalating?",
        arguments=(PromptArg("name", "The AOI name", required=True),),
        steps=(
            ("intel_aoi_list", "confirm {name} is among the defined areas of interest and see its shape"),
            Step(
                "intel_aoi_changes",
                "new, departed and unchanged items since the previous snapshot, "
                "and previous_taken_at, when that snapshot was saved",
                args=(("name", "{name}"),),
            ),
            Step(
                "intel_aoi_escalation",
                "the escalation score and its components for {name}",
                args=(("name", "{name}"),),
            ),
            Step("intel_aoi_brief", "cited detail behind any change worth reporting", args=(("name", "{name}"),)),
            (
                "intel_aoi_digest",
                "only if asked about every watched area: the change sweep "
                "across all defined AOIs in one call. It advances each AOI's "
                "snapshot as step 2 does, so never run both for {name}",
            ),
        ),
        limits=(
            "Changes are relative to the previous snapshot, whenever it was "
            "saved; give previous_taken_at.",
            "Every intel_aoi_changes call saves a new snapshot. Call it once: a "
            "retried call compares with the snapshot the first call just saved "
            "and reports that nothing changed.",
            "A domain that fails, earthquakes and wildfires included, is "
            "listed in data_gaps and left out of the changes; a wildfire "
            "region FIRMS did not answer is listed as partial coverage. A "
            "whole domain departing at once with no data_gaps entry is still "
            "unconfirmed: check failing_sources in intel://guide/source-health "
            "and report it as unconfirmed.",
            "News for an AOI is found by place name near its centre, so a "
            "nearby place with the same name can leak in.",
        ),
    ),
    # --- news, politics, health ---------------------------------------------
    ResearchPrompt(
        name="story-breadth",
        title="How widely a story is covered and how that changed",
        domain="news",
        question=(
            "How much coverage has {topic} received, how has that changed over "
            "time, and which story clusters carry it?"
        ),
        arguments=(PromptArg("topic", "Search terms for the story", required=True),),
        steps=(
            Step(
                "intel_gdelt_search",
                "coverage volume over time",
                args=(("query", "{topic}"), ("mode", "timelinevol")),
            ),
            Step("intel_gdelt_search", "the articles themselves", args=(("query", "{topic}"), ("mode", "artlist"))),
            ("intel_news_clusters", "the clusters of related stories in the RSS set"),
            ("intel_news_feed", "the latest items from the RSS feeds"),
            (
                "intel_top_stories",
                "stories carried by at least three distinct outlets in the RSS "
                "feeds over the last 24 hours, ranked by outlet count: breadth "
                "across outlets",
            ),
            (
                "intel_situations",
                "situations between and inside countries ranked by how many RSS "
                "headlines cover them",
            ),
            Step(
                "intel_hostility_timeline",
                "only if the story is about one country or a pair: per-day "
                "GDELT article counts for it, where a day GDELT did not return "
                "is null and listed in data_gaps",
                args=(("country", Fill("the country the story is about")),),
            ),
        ),
        limits=(
            "Report the timelinevol series as GDELT returns it and compare it "
            "with itself over time. Do not state a unit for it or call it an "
            "article count.",
            "Coverage volume measures attention, not truth or importance.",
            "The RSS set is a fixed list of feeds. A story missing there may "
            "still be covered elsewhere.",
        ),
    ),
    ResearchPrompt(
        name="election-watch",
        title="Upcoming elections and the signals around them",
        domain="politics",
        question="Which elections are coming up in {country}, and what do current signals show around them?",
        arguments=(PromptArg("country", "ISO alpha-3 country code, e.g. FRA", absent="all countries"),),
        steps=(
            Step(
                "intel_election_calendar",
                "entries from a hand-kept election table of 18 rows dated "
                "2025-01 to 2029-04, each with a status and a proximity risk",
                args=(("country", "{country}"),),
            ),
            Step(
                "intel_country_dossier",
                "economy, sanctions, news and conflict context. It knows only "
                "the 50 countries in its own table and returns an error for others. "
                "Its sanctions section lists sanctions-list entries whose remarks name the "
                "country, which is not an exposure screen; match_count null means "
                "the sanctions list could not be read, not zero matches",
                args=(("country", "{country}"),),
                only_if="country",
            ),
            ("intel_social_signals", "discussion velocity on the tracked subreddits"),
            (
                "intel_prediction_markets",
                "the 20 active Polymarket questions with the most 24-hour "
                "volume. It has no topic filter, so most will be about other "
                "things: keep any about this election and say so if there are none",
            ),
            Step(
                "intel_kalshi_markets",
                "Kalshi open markets in its Elections category, ranked by "
                "volume; keep only those about this election",
                args=(("category", "Elections"),),
            ),
            Step(
                "intel_prediction_compare",
                "the same Elections markets on Kalshi and Polymarket side by "
                "side with the price gap; match_confidence ranks pairs and is "
                "not a probability",
                args=(("category", "Elections"),),
            ),
        ),
        limits=(
            "The calendar is a fixed table, not a feed. An empty list means "
            "the country is not in it, not that no election is due; say the "
            "calendar does not cover it.",
            "Entries with status past have already happened. Leave them out "
            "of upcoming elections: their proximity risk scores the days "
            "after an election like the days before it.",
            "The country filter also matches part of a country name (RUS "
            "returns Belarus), so keep only entries whose iso3 is the code "
            "you asked for.",
            "Proximity risk rises as an election nears; it is a stated "
            "heuristic, not a forecast of unrest or of the result.",
            "Reddit and prediction markets reflect their own participants, "
            "not the electorate.",
        ),
    ),
    ResearchPrompt(
        name="sanctions-screen",
        title="Search the OFAC sanctions list for a name",
        domain="finance",
        question="Does {query} appear on the US Treasury OFAC SDN list, and under which programs?",
        arguments=(PromptArg("query", "Name to search for", required=True),),
        steps=(
            Step("intel_sanctions_search", "name matches on the SDN sanctions list", args=(("query", "{query}"),)),
            Step(
                "intel_company_profile",
                "only if a match is a listed company: who it is",
                args=(("query", Fill("the matched company's name or ticker")),),
            ),
        ),
        limits=(
            "If total_entities is 0, the list could not be read. That is a "
            "failed search, not a clean result. Otherwise total_entities "
            "counts the entries read before the search stopped, not the size "
            "of the list.",
            "Only the primary name of each entry is searched, not its "
            "aliases, so a listed party under another spelling will not match.",
            "Results stop at the limit (default 50): a count equal to the "
            "limit means more names may have matched, so search again with a "
            "higher limit before saying how many did.",
            "Matching is by substring on names. A name match is not an "
            "identity match, and this is not a compliance screening service. "
            "Never answer that a party is not sanctioned.",
            "The SDN list changes. Say when you searched.",
        ),
    ),
    ResearchPrompt(
        name="disease-watch",
        title="Disease outbreak reports",
        domain="health",
        question="Which disease outbreaks are being reported now, and which involve high-concern pathogens?",
        steps=(
            ("intel_disease_outbreaks", "WHO, ProMED and CIDRAP outbreak reports"),
            ("intel_humanitarian_summary", "crisis datasets for the affected countries"),
            ("intel_news_feed", "recent news coverage, for context only"),
        ),
        limits=(
            "Outbreak reports arrive after cases occur and case counts are "
            "revised. Give each report's date.",
            "Reporting is uneven across countries. Fewer reports does not "
            "mean fewer cases.",
        ),
    ),
    # --- history and country views ------------------------------------------
    ResearchPrompt(
        name="history-recall",
        title="What the stored history says about a topic",
        domain="history",
        question=(
            "What has this server stored about {topic} over the last {hours} "
            "hours, and has anything similar been recorded before?"
        ),
        arguments=(
            PromptArg("topic", "Natural language topic", required=True),
            PromptArg(
                "hours", "How far back to search, in hours", default="168",
                kind="int", minimum=1, maximum=87600,
            ),
        ),
        steps=(
            Step(
                "intel_domain_summary",
                "what is stored per category in your window, with the earliest "
                "timestamp inside that window",
                args=(("hours", "{hours}"),),
            ),
            Step(
                "intel_domain_summary",
                "the same over ten years: its earliest timestamps show when "
                "storage began for each domain",
                args=(("hours", 87600),),
            ),
            Step(
                "intel_semantic_search",
                "the stored entries closest in wording to the topic",
                args=(("query", "{topic}"), ("hours", "{hours}")),
            ),
            ("intel_timeline", "the stored entries in time order for the matching domain"),
            Step(
                "intel_similar_events",
                "earlier stored events similar to the strongest match",
                args=(("text", Fill("the text of the strongest match from step 3")),),
            ),
            (
                "intel_series_history",
                "the numeric series the history store holds (a separate store "
                "from the vector store), with observed_at, published_at and "
                "collected_at for each",
            ),
            (
                "intel_collection_health",
                "the collector's run log per source: last success, consecutive "
                "failures and whether it is overdue, which says how complete "
                "that history is",
            ),
        ),
        limits=(
            "History exists only for what the collector stored while it was "
            "running. The earliest timestamp in step 1 is only the earliest "
            "inside your window; use step 2 before calling anything the first "
            "or the largest.",
            "Semantic search ranks by similarity of wording. A high score is "
            "not a factual match.",
            "If the vector store is not available these tools return an "
            "error; say that history could not be read.",
        ),
    ),
    ResearchPrompt(
        name="country-overview",
        title="One country across economy, stability and markets",
        domain="country",
        question=(
            "What is the current picture in {country} across economy, "
            "stability, active signals and its stock market?"
        ),
        arguments=(_ISO3,),
        steps=(
            Step(
                "intel_country_dossier",
                "economy, elections, sanctions, news and conflict. It knows only "
                "the 50 countries in its own table and returns an error for others. "
                "Its sanctions section lists sanctions-list entries whose remarks name the "
                "country, which is not an exposure screen; match_count null means "
                "the sanctions list could not be read, not zero matches",
                args=(("country", "{country}"),),
            ),
            Step(
                "intel_instability_index",
                "the index with its four components. It takes 50 ISO alpha-3 "
                "codes and returns an error listing them for any other. Each "
                "input it could not obtain is named in data_gaps and its "
                "component is null; index_is_lower_bound then means the total "
                "counts the missing parts as zero",
                args=(("country_code", "{country}"),),
            ),
            Step(
                "intel_signal_summary",
                "active signals; this tool takes the country's name, not its code",
                args=(("country", Fill("the country's English name")),),
            ),
            Step(
                "intel_country_stocks",
                "its main stock index; countries without a mapped index return "
                "an error that lists the ones covered",
                args=(("country", "{country}"),),
            ),
        ),
        limits=(
            "The instability index is a weighted composite with country "
            "multipliers. Quote its components, not only the total. Its "
            "ucdp_floor comes from a static baseline table, not from current "
            "UCDP data: a total at the floor says nothing about this month.",
            "World Bank figures in the dossier are annual and often a year or "
            "more old. Give the year of each.",
            "The dossier's elections section reads a hand-kept election "
            "table: empty means the country is not covered, not that no vote "
            "is due, and its match on part of a name can add another "
            "country's election, so keep only entries whose iso3 is "
            "{country}.",
        ),
    ),
)


def get(name: str) -> ResearchPrompt | None:
    for prompt in PROMPTS:
        if prompt.name == name:
            return prompt
    return None
