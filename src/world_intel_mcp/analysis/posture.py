"""Strategic posture assessment — composite risk from all intelligence domains.

Aggregates scores from 9 domains into an overall global risk assessment.
Each domain is scored 0-100 with a weight, producing a weighted composite.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("world-intel-mcp.analysis.posture")


# Domain weights (sum to 1.0)
DOMAIN_WEIGHTS: dict[str, float] = {
    "military": 0.18,
    "political": 0.16,
    "conflict": 0.16,
    "infrastructure": 0.10,
    "economic": 0.10,
    "cyber": 0.08,
    "health": 0.07,
    "climate": 0.08,
    "space": 0.07,
}


async def _safe(coro, label: str) -> dict:
    try:
        return await coro
    except Exception as exc:
        logger.warning("Posture: %s failed: %s", label, exc)
        return {}


def _risk_level(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    elif score >= 55:
        return "HIGH"
    elif score >= 35:
        return "ELEVATED"
    elif score >= 20:
        return "GUARDED"
    return "LOW"


def _score_military(surge_data: dict, posture_data: dict) -> tuple[float, list[str]]:
    """Score military domain 0-100 from surge + theater posture."""
    signals: list[str] = []
    score = 0.0

    surge_count = surge_data.get("surge_count", 0)
    if surge_count > 0:
        score += min(50.0, surge_count * 20.0)
        surges = surge_data.get("surges", [])
        for s in surges[:3]:
            signals.append(f"Surge: {s.get('region', 'unknown')} ({s.get('aircraft_count', '?')} aircraft)")

    theaters = posture_data.get("theaters", [])
    active_theaters = [t for t in theaters if t.get("aircraft_count", 0) > 10]
    score += min(50.0, len(active_theaters) * 12.0)
    for t in active_theaters[:3]:
        signals.append(f"{t.get('name', '?')}: {t.get('aircraft_count', 0)} aircraft")

    return min(100.0, score), signals


def _score_political(instability_data: dict) -> tuple[float, list[str]]:
    """Score political domain 0-100 from instability index."""
    signals: list[str] = []
    countries = instability_data.get("countries", [])
    if not countries:
        return 0.0, signals

    # Average of top-5 CII scores
    top5 = sorted(countries, key=lambda c: c.get("instability_index", 0), reverse=True)[:5]
    avg = sum(c.get("instability_index", 0) for c in top5) / len(top5)
    for c in top5[:3]:
        signals.append(f"{c.get('country_name', c.get('country_code', '?'))}: CII {c.get('instability_index', 0)}")

    return min(100.0, avg), signals


def _score_conflict(hotspot_data: dict) -> tuple[float, list[str]]:
    """Score conflict domain 0-100 from hotspot escalation."""
    signals: list[str] = []
    hotspots = hotspot_data.get("hotspots", [])
    if not hotspots:
        return 0.0, signals

    top5 = sorted(hotspots, key=lambda h: h.get("score", 0), reverse=True)[:5]
    avg = sum(h.get("score", 0) for h in top5) / len(top5)
    for h in top5[:3]:
        signals.append(f"{h.get('name', '?')}: {h.get('score', 0)}/100")

    return min(100.0, avg), signals


def _score_infrastructure(cable_data: dict, outage_data: dict) -> tuple[float, list[str]]:
    """Score infrastructure 0-100 from cable health + outages."""
    signals: list[str] = []
    score = 0.0

    corridors = cable_data.get("corridors", {})
    at_risk = [n for n, c in corridors.items() if isinstance(c, dict) and c.get("status_score", 0) >= 2]
    score += min(50.0, len(at_risk) * 15.0)
    for c in at_risk[:2]:
        signals.append(f"Cable: {c} at risk")

    outage_count = outage_data.get("outage_count", 0)
    score += min(50.0, outage_count * 5.0)
    if outage_count > 0:
        signals.append(f"{outage_count} internet outages")

    return min(100.0, score), signals


def _score_economic(shipping_data: dict) -> tuple[float, list[str]]:
    """Score economic 0-100 from shipping stress."""
    signals: list[str] = []
    stress = shipping_data.get("stress_score", 0)
    assessment = shipping_data.get("assessment", "unknown")
    if stress > 0:
        signals.append(f"Shipping stress: {stress} ({assessment})")
    return min(100.0, stress), signals


def _score_cyber(cyber_data: dict) -> tuple[float, list[str]]:
    """Score cyber 0-100 from threat intelligence."""
    signals: list[str] = []
    threat_count = cyber_data.get("threat_count", 0)
    score = min(100.0, threat_count * 2.0)
    if threat_count > 0:
        signals.append(f"{threat_count} active threats")
    by_source = cyber_data.get("by_source", {})
    for src, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:2]:
        signals.append(f"{src}: {count}")
    return score, signals


def _score_health(health_data: dict) -> tuple[float, list[str]]:
    """Score health 0-100 from disease outbreaks."""
    signals: list[str] = []
    count = health_data.get("count", 0)
    high_concern = health_data.get("high_concern_count", 0)
    score = min(100.0, high_concern * 25.0 + count * 3.0)
    if high_concern > 0:
        signals.append(f"{high_concern} high-concern pathogen alerts")
    if count > 0:
        signals.append(f"{count} outbreak reports")
    return score, signals


def _score_climate(climate_data: dict) -> tuple[float, list[str]]:
    """Score climate 0-100 from anomalies."""
    signals: list[str] = []
    anomalies = climate_data.get("anomalies", [])
    extreme = [a for a in anomalies if abs(a.get("temp_deviation_c", 0)) > 3.0]
    score = min(100.0, len(extreme) * 15.0 + len(anomalies) * 3.0)
    for a in extreme[:2]:
        signals.append(f"{a.get('zone', '?')}: {a.get('temp_deviation_c', 0):+.1f}°C")
    return score, signals


def _score_space(sw_data: dict) -> tuple[float, list[str]]:
    """Score space weather 0-100 from Kp index."""
    signals: list[str] = []
    kp = sw_data.get("current_kp")
    if kp is None:
        return 0.0, signals
    # Kp 0-9 mapped to 0-100
    score = min(100.0, kp * 11.0)
    signals.append(f"Kp={kp} ({sw_data.get('kp_level', 'Unknown')})")
    return score, signals


async def fetch_strategic_posture(fetcher) -> dict:
    """Compute composite strategic posture from all intelligence domains.

    Calls 9 existing source functions in parallel, scores each domain 0-100,
    and produces a weighted composite risk assessment.
    """
    from ..sources import space_weather, infrastructure, shipping, cyber, health, climate
    from ..sources import intelligence, military

    (
        surge_data,
        posture_data,
        instability_data,
        hotspot_data,
        cable_data,
        outage_data,
        shipping_data,
        cyber_data,
        health_data,
        climate_data,
        sw_data,
    ) = await asyncio.gather(
        _safe(intelligence.fetch_military_surge(fetcher), "military_surge"),
        _safe(military.fetch_theater_posture(fetcher), "theater_posture"),
        _safe(intelligence.fetch_instability_index(fetcher), "instability"),
        _safe(intelligence.fetch_hotspot_escalation(fetcher), "hotspot_escalation"),
        _safe(infrastructure.fetch_cable_health(fetcher), "cable_health"),
        _safe(infrastructure.fetch_internet_outages(fetcher), "internet_outages"),
        _safe(shipping.fetch_shipping_index(fetcher), "shipping"),
        _safe(cyber.fetch_cyber_threats(fetcher), "cyber"),
        _safe(health.fetch_disease_outbreaks(fetcher), "health"),
        _safe(climate.fetch_climate_anomalies(fetcher), "climate"),
        _safe(space_weather.fetch_space_weather(fetcher), "space_weather"),
    )

    # Score each domain
    mil_score, mil_signals = _score_military(surge_data, posture_data)
    pol_score, pol_signals = _score_political(instability_data)
    con_score, con_signals = _score_conflict(hotspot_data)
    inf_score, inf_signals = _score_infrastructure(cable_data, outage_data)
    eco_score, eco_signals = _score_economic(shipping_data)
    cyb_score, cyb_signals = _score_cyber(cyber_data)
    hlt_score, hlt_signals = _score_health(health_data)
    clm_score, clm_signals = _score_climate(climate_data)
    spc_score, spc_signals = _score_space(sw_data)

    domain_scores = {
        "military": {"score": round(mil_score, 1), "level": _risk_level(mil_score), "signals": mil_signals},
        "political": {"score": round(pol_score, 1), "level": _risk_level(pol_score), "signals": pol_signals},
        "conflict": {"score": round(con_score, 1), "level": _risk_level(con_score), "signals": con_signals},
        "infrastructure": {"score": round(inf_score, 1), "level": _risk_level(inf_score), "signals": inf_signals},
        "economic": {"score": round(eco_score, 1), "level": _risk_level(eco_score), "signals": eco_signals},
        "cyber": {"score": round(cyb_score, 1), "level": _risk_level(cyb_score), "signals": cyb_signals},
        "health": {"score": round(hlt_score, 1), "level": _risk_level(hlt_score), "signals": hlt_signals},
        "climate": {"score": round(clm_score, 1), "level": _risk_level(clm_score), "signals": clm_signals},
        "space": {"score": round(spc_score, 1), "level": _risk_level(spc_score), "signals": spc_signals},
    }

    # Weighted composite
    composite = sum(
        domain_scores[domain]["score"] * weight
        for domain, weight in DOMAIN_WEIGHTS.items()
    )
    composite = min(100.0, max(0.0, composite))

    # Top threats: highest-scored signals across all domains
    all_signals = []
    for domain, info in domain_scores.items():
        for sig in info["signals"]:
            all_signals.append({"domain": domain, "signal": sig, "domain_score": info["score"]})
    all_signals.sort(key=lambda s: s["domain_score"], reverse=True)

    return {
        "composite_score": round(composite, 1),
        "risk_level": _risk_level(composite),
        "domain_scores": domain_scores,
        "weights": DOMAIN_WEIGHTS,
        "top_threats": all_signals[:10],
        "domains_assessed": len(DOMAIN_WEIGHTS),
        "source": "strategic-posture-assessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
