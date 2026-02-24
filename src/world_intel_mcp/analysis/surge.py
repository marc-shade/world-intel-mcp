"""Military surge detection — identifies foreign military concentration anomalies.

Pure analysis module — no I/O.
"""

from __future__ import annotations


SENSITIVE_REGIONS: dict[str, dict] = {
    "persian_gulf": {
        "bbox": "20,45,30,60",
        "baseline_presence": {"United States": 15, "Iran": 5},
    },
    "taiwan_strait": {
        "bbox": "21,116,27,123",
        "baseline_presence": {"China": 10, "United States": 5},
    },
    "baltic_sea": {
        "bbox": "53,10,66,30",
        "baseline_presence": {"Russia": 3, "United States": 2},
    },
    "south_china_sea": {
        "bbox": "0,100,25,122",
        "baseline_presence": {"China": 8, "United States": 4},
    },
    "korean_dmz": {
        "bbox": "33,124,43,132",
        "baseline_presence": {"United States": 5},
    },
    "black_sea": {
        "bbox": "40,27,47,42",
        "baseline_presence": {"Russia": 5, "Turkey": 3},
    },
    "red_sea": {
        "bbox": "12,32,30,44",
        "baseline_presence": {"United States": 3},
    },
    "arctic": {
        "bbox": "65,-180,90,180",
        "baseline_presence": {"Russia": 3, "United States": 2},
    },
}

# Map theater names from military.THEATERS to sensitive regions
_THEATER_REGION_MAP: dict[str, list[str]] = {
    "european": ["baltic_sea", "black_sea"],
    "indo_pacific": ["taiwan_strait", "south_china_sea"],
    "middle_east": ["persian_gulf", "red_sea"],
    "arctic": ["arctic"],
    "korean_peninsula": ["korean_dmz"],
}


def detect_surges(
    theater_data: dict[str, dict],
    temporal_baselines: dict[str, dict] | None = None,
) -> list[dict]:
    """Detect military surges by comparing current presence to baselines.

    For each sensitive region:
    1. Map theater_data countries to region baseline_presence
    2. Compute surge_ratio = current / baseline per country
    3. Flag: >2x = elevated, >3x = critical
    4. If temporal_baselines show z_score > 2.0, boost severity

    Args:
        theater_data: From fetch_theater_posture: {theater: {count, countries, ...}}.
        temporal_baselines: Optional {region: {z_score, multiplier, ...}}.

    Returns:
        List of surge dicts sorted by surge_ratio descending.
    """
    temporal_baselines = temporal_baselines or {}
    surges: list[dict] = []

    for region_name, region_info in SENSITIVE_REGIONS.items():
        baseline_presence = region_info["baseline_presence"]

        # Aggregate aircraft counts from matching theaters
        current_by_country: dict[str, int] = {}
        for theater_name, mapped_regions in _THEATER_REGION_MAP.items():
            if region_name not in mapped_regions:
                continue
            theater = theater_data.get(theater_name, {})
            theater_countries = theater.get("countries", [])
            theater_count = theater.get("count", 0)
            if not theater_countries:
                continue
            # Distribute count across countries in the theater
            per_country = max(1, theater_count // len(theater_countries))
            for country in theater_countries:
                current_by_country[country] = (
                    current_by_country.get(country, 0) + per_country
                )

        # Check each country against baseline
        for country, baseline in baseline_presence.items():
            current = current_by_country.get(country, 0)
            if baseline <= 0:
                continue

            surge_ratio = current / baseline

            if surge_ratio < 1.5:
                continue

            # Determine severity
            if surge_ratio >= 3.0:
                severity = "critical"
            elif surge_ratio >= 2.0:
                severity = "elevated"
            else:
                severity = "watch"

            surge_entry: dict = {
                "region": region_name,
                "country": country,
                "current": current,
                "baseline": baseline,
                "surge_ratio": round(surge_ratio, 2),
                "severity": severity,
            }

            # Temporal anomaly boost
            temporal = temporal_baselines.get(region_name)
            if temporal and temporal.get("z_score", 0) > 2.0:
                surge_entry["temporal_anomaly"] = {
                    "z_score": temporal["z_score"],
                    "multiplier": temporal.get("multiplier"),
                }
                # Boost severity one level
                if severity == "watch":
                    surge_entry["severity"] = "elevated"
                elif severity == "elevated":
                    surge_entry["severity"] = "critical"

            surges.append(surge_entry)

    surges.sort(key=lambda s: s["surge_ratio"], reverse=True)
    return surges
