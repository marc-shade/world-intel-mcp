"""Infrastructure cascade simulation — 'what if cable X is cut?' impact propagation.

Pure analysis module — no I/O.
"""

from __future__ import annotations


# Cable corridor -> country dependency mapping (% of internet capacity)
CABLE_DEPENDENCIES: dict[str, dict[str, float]] = {
    "transatlantic_north": {
        "United Kingdom": 0.6,
        "France": 0.4,
        "Germany": 0.3,
        "Netherlands": 0.25,
        "United States": 0.15,
        "Ireland": 0.5,
    },
    "transatlantic_south": {
        "Brazil": 0.5,
        "Portugal": 0.3,
        "Spain": 0.2,
        "Argentina": 0.15,
        "South Africa": 0.1,
    },
    "asia_europe": {
        "India": 0.4,
        "Saudi Arabia": 0.35,
        "UAE": 0.3,
        "Pakistan": 0.25,
        "Singapore": 0.2,
        "Malaysia": 0.15,
    },
    "red_sea": {
        "Egypt": 0.5,
        "Saudi Arabia": 0.3,
        "Djibouti": 0.8,
        "Yemen": 0.6,
        "Eritrea": 0.5,
        "Sudan": 0.3,
    },
    "transpacific": {
        "Japan": 0.3,
        "United States": 0.1,
        "South Korea": 0.2,
        "Taiwan": 0.25,
        "Philippines": 0.15,
    },
    "mediterranean": {
        "Italy": 0.3,
        "Greece": 0.4,
        "Turkey": 0.2,
        "Egypt": 0.15,
        "Spain": 0.1,
        "Israel": 0.2,
    },
}

# Waterway -> cable corridors that pass through it
WATERWAY_CORRIDOR_MAP: dict[str, list[str]] = {
    "Suez Canal": ["red_sea", "asia_europe", "mediterranean"],
    "Strait of Hormuz": ["asia_europe"],
    "Strait of Malacca": ["transpacific"],
    "Bab-el-Mandeb": ["red_sea", "asia_europe"],
    "Strait of Gibraltar": ["mediterranean", "transatlantic_south"],
}


def _impact_score(capacity_loss: float) -> int:
    """Convert capacity loss (0.0-1.0) to impact score (0-100)."""
    return min(100, int(capacity_loss * 100))


def _risk_level(score: int) -> str:
    if score >= 60:
        return "critical"
    if score >= 40:
        return "high"
    if score >= 20:
        return "moderate"
    return "low"


def simulate_cascade(
    disrupted_corridors: list[str],
    current_health: dict[str, dict] | None = None,
) -> dict:
    """Simulate infrastructure cascade from corridor disruption.

    For each disrupted corridor:
    1. Look up country dependencies
    2. Compute capacity_loss per country (dependency_pct * disruption_severity)
    3. Check for cascading effects (country depends on multiple disrupted corridors)
    4. Score each country: 0-100 impact

    Args:
        disrupted_corridors: Corridor names from infrastructure.CABLE_CORRIDORS.
        current_health: Optional current cable health from fetch_cable_health.

    Returns:
        Dict with disrupted corridors, country impacts, and cascading risks.
    """
    # Determine disruption severity per corridor
    corridor_severity: dict[str, float] = {}
    for corridor in disrupted_corridors:
        if corridor not in CABLE_DEPENDENCIES:
            continue
        # Check current health for severity scaling
        severity = 1.0
        if current_health:
            health = current_health.get(corridor, {})
            status_score = health.get("status_score", 0)
            # Scale: 0=clear(full disruption simulated), 1=advisory(0.8x), 2=at_risk(0.9x), 3=disrupted(1.0x already)
            if status_score >= 3:
                severity = 1.0
            elif status_score >= 2:
                severity = 0.9
            elif status_score >= 1:
                severity = 0.8
            else:
                severity = 1.0  # simulating full disruption of a clear corridor
        corridor_severity[corridor] = severity

    # Compute per-country capacity loss
    country_losses: dict[str, dict] = {}

    for corridor, severity in corridor_severity.items():
        deps = CABLE_DEPENDENCIES.get(corridor, {})
        for country, dependency_pct in deps.items():
            loss = dependency_pct * severity

            if country not in country_losses:
                country_losses[country] = {
                    "total_loss": 0.0,
                    "affected_corridors": [],
                }
            entry = country_losses[country]
            entry["total_loss"] += loss
            entry["affected_corridors"].append(corridor)

    # Cap total loss at 1.0 and compute scores
    country_impacts: list[dict] = []
    for country, data in country_losses.items():
        total_loss = min(1.0, data["total_loss"])
        score = _impact_score(total_loss)
        country_impacts.append({
            "country": country,
            "total_capacity_loss": round(total_loss, 3),
            "affected_corridors": data["affected_corridors"],
            "impact_score": score,
            "risk_level": _risk_level(score),
        })

    country_impacts.sort(key=lambda c: c["impact_score"], reverse=True)

    # Detect cascading risks (countries affected by 2+ disrupted corridors)
    cascading_risks: list[dict] = []
    multi_corridor_countries = [
        c for c in country_impacts if len(c["affected_corridors"]) >= 2
    ]
    if multi_corridor_countries:
        countries_affected = [c["country"] for c in multi_corridor_countries]
        cascading_risks.append({
            "description": (
                f"Multi-corridor disruption: {len(countries_affected)} countries "
                f"depend on 2+ disrupted corridors"
            ),
            "countries_affected": countries_affected,
        })

    # Check waterway-level cascades
    for waterway, corridors in WATERWAY_CORRIDOR_MAP.items():
        overlap = [c for c in corridors if c in corridor_severity]
        if len(overlap) >= 2:
            cascading_risks.append({
                "description": (
                    f"Waterway choke: {waterway} has {len(overlap)} disrupted "
                    f"cable corridors ({', '.join(overlap)})"
                ),
                "countries_affected": list({
                    country
                    for corridor in overlap
                    for country in CABLE_DEPENDENCIES.get(corridor, {})
                }),
            })

    return {
        "disrupted": list(corridor_severity.keys()),
        "country_impacts": country_impacts,
        "cascading_risks": cascading_risks,
    }
