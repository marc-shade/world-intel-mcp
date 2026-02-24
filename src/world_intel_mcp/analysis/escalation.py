"""Hotspot escalation scoring — composite dynamic scores for intel hotspots.

Pure analysis module — no I/O.
"""

from __future__ import annotations


def score_hotspot(
    hotspot_config: dict,
    news_mentions: int = 0,
    military_count: int = 0,
    conflict_events: int = 0,
    convergence_score: float = 0,
    fatalities: int = 0,
    protests: int = 0,
) -> dict:
    """Score a single hotspot 0-100 with component breakdown.

    Components (each 0-20, total 0-100):
    1. baseline: static from config, scaled 0-20 from baseline_escalation 0-5
    2. news_activity: min(20, news_mentions * 0.2)
    3. military: min(20, military_count * 1.0)
    4. conflict: min(20, (conflict_events * 0.5) + (fatalities * 0.1))
    5. social_unrest: min(20, protests * 0.4) + convergence: min(remainder, convergence_score * 2.0)

    Args:
        hotspot_config: From INTEL_HOTSPOTS: {lat, lon, baseline_escalation, associated_countries}.
        news_mentions: GDELT article count near hotspot.
        military_count: Aircraft near hotspot.
        conflict_events: ACLED events near hotspot.
        convergence_score: From geo-convergence.
        fatalities: Total fatalities from conflict events.
        protests: Protest event count near hotspot.

    Returns:
        Dict with score, components, level, and trend_signal.
    """
    baseline_escalation = hotspot_config.get("baseline_escalation", 0)
    baseline = min(20.0, baseline_escalation * 4.0)

    news = min(20.0, news_mentions * 0.2)

    mil = min(20.0, military_count * 1.0)

    conflict = min(20.0, (conflict_events * 0.5) + (fatalities * 0.1))

    # Split last 20 points between social unrest and convergence
    unrest = min(12.0, protests * 0.4)
    convergence = min(20.0 - unrest, convergence_score * 2.0)
    social_convergence = unrest + convergence

    total = baseline + news + mil + conflict + social_convergence
    total = min(100.0, max(0.0, total))

    if total >= 70:
        level = "critical"
    elif total >= 40:
        level = "elevated"
    else:
        level = "watch"

    # Trend signal: compare current dynamic signals to baseline
    dynamic_score = total - baseline
    if dynamic_score > 40:
        trend_signal = "surging"
    elif dynamic_score > 20:
        trend_signal = "rising"
    elif dynamic_score > 5:
        trend_signal = "active"
    else:
        trend_signal = "stable"

    return {
        "score": round(total, 1),
        "components": {
            "baseline": round(baseline, 1),
            "news": round(news, 1),
            "military": round(mil, 1),
            "conflict": round(conflict, 1),
            "social_convergence": round(social_convergence, 1),
        },
        "level": level,
        "trend_signal": trend_signal,
    }


def score_all_hotspots(
    hotspots: dict[str, dict],
    hotspot_signals: dict[str, dict],
) -> list[dict]:
    """Score all hotspots at once, sorted by score descending.

    Args:
        hotspots: INTEL_HOTSPOTS mapping.
        hotspot_signals: {hotspot_name: {news_mentions, military_count,
            conflict_events, convergence_score, fatalities, protests}}.

    Returns:
        List of scored hotspot dicts sorted by score descending.
    """
    results: list[dict] = []

    for name, config in hotspots.items():
        signals = hotspot_signals.get(name, {})
        scored = score_hotspot(
            hotspot_config=config,
            news_mentions=signals.get("news_mentions", 0),
            military_count=signals.get("military_count", 0),
            conflict_events=signals.get("conflict_events", 0),
            convergence_score=signals.get("convergence_score", 0),
            fatalities=signals.get("fatalities", 0),
            protests=signals.get("protests", 0),
        )
        results.append({
            "name": name,
            "lat": config["lat"],
            "lon": config["lon"],
            "associated_countries": config.get("associated_countries", []),
            **scored,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
