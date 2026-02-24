"""Election calendar and risk scoring source for world-intel-mcp.

Pure data module — reads from config.countries.UPCOMING_ELECTIONS and
computes proximity-based risk scores. No I/O, no API keys.
"""

import logging
from datetime import date, datetime, timezone

from ..config.countries import UPCOMING_ELECTIONS

logger = logging.getLogger("world-intel-mcp.sources.elections")

# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

_PROXIMITY_SCORES: list[tuple[int, int]] = [
    (30, 100),
    (90, 70),
    (180, 40),
    (365, 20),
]
_FALLBACK_PROXIMITY = 5

_IMPACT_MULTIPLIERS: dict[str, float] = {
    "high": 1.5,
    "medium": 1.0,
    "low": 0.6,
}


def _proximity_score(days_until: int) -> int:
    """Score based on how close the election is."""
    abs_days = abs(days_until)
    for threshold, score in _PROXIMITY_SCORES:
        if abs_days <= threshold:
            return score
    return _FALLBACK_PROXIMITY


def _compute_risk(days_until: int, impact: str) -> float:
    """Compute election risk: proximity_score * impact_multiplier."""
    base = _proximity_score(days_until)
    multiplier = _IMPACT_MULTIPLIERS.get(impact, 1.0)
    return round(base * multiplier, 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_election_calendar(
    fetcher: object,  # noqa: ARG001 — kept for API consistency
    country: str | None = None,
) -> dict:
    """Return the election calendar with proximity risk scoring.

    Args:
        fetcher: Unused (pure data), kept for dispatch consistency.
        country: Optional ISO-3 code or country name filter.

    Returns:
        Dict with elections list, count, highest_risk entry, source.
    """
    today = date.today()
    now = datetime.now(timezone.utc)

    elections: list[dict] = []
    country_lower = country.lower().strip() if country else ""

    for entry in UPCOMING_ELECTIONS:
        # Filter
        if country_lower:
            if (
                country_lower not in entry["country"].lower()
                and country_lower != entry["iso3"].lower()
            ):
                continue

        try:
            election_date = date.fromisoformat(entry["date"])
        except ValueError:
            continue

        days_until = (election_date - today).days
        risk_score = _compute_risk(days_until, entry["instability_impact"])

        elections.append({
            "country": entry["country"],
            "iso3": entry["iso3"],
            "election_type": entry["election_type"],
            "date": entry["date"],
            "description": entry["description"],
            "days_until": days_until,
            "status": "past" if days_until < 0 else "upcoming",
            "instability_impact": entry["instability_impact"],
            "risk_score": risk_score,
        })

    # Sort by risk_score descending
    elections.sort(key=lambda e: e["risk_score"], reverse=True)

    highest_risk = elections[0] if elections else None

    return {
        "elections": elections,
        "count": len(elections),
        "highest_risk": highest_risk,
        "source": "election-calendar",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
