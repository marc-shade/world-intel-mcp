"""Country configuration, hotspots, waterways, and conflict zones.

Pure data module — no I/O, no external dependencies.
"""

from __future__ import annotations


TIER1_COUNTRIES: dict[str, dict] = {
    "USA": {"name": "United States", "keywords": ["united states", "usa", "american"], "baseline_risk": 15, "event_multiplier": 0.3},
    "CHN": {"name": "China", "keywords": ["china", "chinese", "beijing"], "baseline_risk": 35, "event_multiplier": 2.5},
    "RUS": {"name": "Russia", "keywords": ["russia", "russian", "moscow"], "baseline_risk": 55, "event_multiplier": 1.8},
    "UKR": {"name": "Ukraine", "keywords": ["ukraine", "ukrainian", "kyiv"], "baseline_risk": 85, "event_multiplier": 1.0},
    "SYR": {"name": "Syria", "keywords": ["syria", "syrian", "damascus"], "baseline_risk": 80, "event_multiplier": 1.2},
    "YEM": {"name": "Yemen", "keywords": ["yemen", "yemeni", "sanaa", "houthi"], "baseline_risk": 75, "event_multiplier": 1.3},
    "MMR": {"name": "Myanmar", "keywords": ["myanmar", "burma", "burmese"], "baseline_risk": 70, "event_multiplier": 1.1},
    "SDN": {"name": "Sudan", "keywords": ["sudan", "sudanese", "khartoum"], "baseline_risk": 80, "event_multiplier": 1.4},
    "NGA": {"name": "Nigeria", "keywords": ["nigeria", "nigerian", "lagos", "abuja"], "baseline_risk": 50, "event_multiplier": 1.0},
    "AFG": {"name": "Afghanistan", "keywords": ["afghanistan", "afghan", "kabul", "taliban"], "baseline_risk": 70, "event_multiplier": 1.1},
    "IRQ": {"name": "Iraq", "keywords": ["iraq", "iraqi", "baghdad"], "baseline_risk": 55, "event_multiplier": 1.0},
    "IRN": {"name": "Iran", "keywords": ["iran", "iranian", "tehran"], "baseline_risk": 50, "event_multiplier": 2.0},
    "TWN": {"name": "Taiwan", "keywords": ["taiwan", "taiwanese", "taipei"], "baseline_risk": 30, "event_multiplier": 3.0},
    "PRK": {"name": "North Korea", "keywords": ["north korea", "dprk", "pyongyang"], "baseline_risk": 45, "event_multiplier": 2.5},
    "ISR": {"name": "Israel", "keywords": ["israel", "israeli", "tel aviv", "jerusalem"], "baseline_risk": 55, "event_multiplier": 1.5},
    "PSE": {"name": "Palestine", "keywords": ["palestine", "palestinian", "gaza", "west bank"], "baseline_risk": 85, "event_multiplier": 1.0},
    "LBN": {"name": "Lebanon", "keywords": ["lebanon", "lebanese", "beirut", "hezbollah"], "baseline_risk": 60, "event_multiplier": 1.3},
    "ETH": {"name": "Ethiopia", "keywords": ["ethiopia", "ethiopian", "addis ababa"], "baseline_risk": 55, "event_multiplier": 1.0},
    "COD": {"name": "DR Congo", "keywords": ["congo", "drc", "kinshasa", "congolese"], "baseline_risk": 60, "event_multiplier": 1.0},
    "PAK": {"name": "Pakistan", "keywords": ["pakistan", "pakistani", "islamabad"], "baseline_risk": 45, "event_multiplier": 1.0},
    "IND": {"name": "India", "keywords": ["india", "indian", "new delhi"], "baseline_risk": 30, "event_multiplier": 0.5},
    "MEX": {"name": "Mexico", "keywords": ["mexico", "mexican", "mexico city"], "baseline_risk": 40, "event_multiplier": 0.8},
}


INTEL_HOTSPOTS: dict[str, dict] = {
    "tehran": {"lat": 35.69, "lon": 51.39, "baseline_escalation": 3, "associated_countries": ["IRN", "ISR"]},
    "kyiv": {"lat": 50.45, "lon": 30.52, "baseline_escalation": 5, "associated_countries": ["UKR", "RUS"]},
    "taipei": {"lat": 25.03, "lon": 121.57, "baseline_escalation": 3, "associated_countries": ["TWN", "CHN"]},
    "pyongyang": {"lat": 39.02, "lon": 125.75, "baseline_escalation": 3, "associated_countries": ["PRK", "KOR"]},
    "gaza": {"lat": 31.42, "lon": 34.35, "baseline_escalation": 5, "associated_countries": ["PSE", "ISR"]},
    "kabul": {"lat": 34.53, "lon": 69.17, "baseline_escalation": 3, "associated_countries": ["AFG", "PAK"]},
    "damascus": {"lat": 33.51, "lon": 36.29, "baseline_escalation": 4, "associated_countries": ["SYR", "IRN", "ISR"]},
    "khartoum": {"lat": 15.59, "lon": 32.53, "baseline_escalation": 5, "associated_countries": ["SDN"]},
    "sanaa": {"lat": 15.37, "lon": 44.19, "baseline_escalation": 4, "associated_countries": ["YEM"]},
    "naypyidaw": {"lat": 19.76, "lon": 96.07, "baseline_escalation": 3, "associated_countries": ["MMR"]},
    "baghdad": {"lat": 33.31, "lon": 44.37, "baseline_escalation": 3, "associated_countries": ["IRQ", "IRN"]},
    "mogadishu": {"lat": 2.05, "lon": 45.32, "baseline_escalation": 4, "associated_countries": ["SOM"]},
    "addis_ababa": {"lat": 9.02, "lon": 38.75, "baseline_escalation": 3, "associated_countries": ["ETH"]},
    "kinshasa": {"lat": -4.32, "lon": 15.31, "baseline_escalation": 3, "associated_countries": ["COD"]},
    "bamako": {"lat": 12.64, "lon": -8.0, "baseline_escalation": 3, "associated_countries": ["MLI"]},
    "ouagadougou": {"lat": 12.37, "lon": -1.52, "baseline_escalation": 3, "associated_countries": ["BFA"]},
    "beirut": {"lat": 33.89, "lon": 35.50, "baseline_escalation": 4, "associated_countries": ["LBN", "ISR"]},
    "hormuz_strait": {"lat": 26.57, "lon": 56.25, "baseline_escalation": 3, "associated_countries": ["IRN", "OMN"]},
    "south_china_sea": {"lat": 15.0, "lon": 115.0, "baseline_escalation": 3, "associated_countries": ["CHN", "PHL", "VNM"]},
    "crimea": {"lat": 44.95, "lon": 34.10, "baseline_escalation": 4, "associated_countries": ["UKR", "RUS"]},
    "bab_el_mandeb": {"lat": 12.58, "lon": 43.33, "baseline_escalation": 4, "associated_countries": ["YEM", "DJI", "ERI"]},
    "suez_canal": {"lat": 30.46, "lon": 32.34, "baseline_escalation": 2, "associated_countries": ["EGY"]},
}


STRATEGIC_WATERWAYS: list[dict] = [
    {"name": "Strait of Hormuz", "lat": 26.57, "lon": 56.25, "throughput": "21M bbl/day oil"},
    {"name": "Strait of Malacca", "lat": 2.5, "lon": 101.8, "throughput": "25% global trade"},
    {"name": "Suez Canal", "lat": 30.46, "lon": 32.34, "throughput": "12% global trade"},
    {"name": "Panama Canal", "lat": 9.08, "lon": -79.68, "throughput": "5% global trade"},
    {"name": "Bab-el-Mandeb", "lat": 12.58, "lon": 43.33, "throughput": "4.8M bbl/day oil"},
    {"name": "Taiwan Strait", "lat": 24.0, "lon": 119.5, "throughput": "88% advanced chips"},
    {"name": "Strait of Gibraltar", "lat": 35.96, "lon": -5.50, "throughput": "Mediterranean access"},
    {"name": "GIUK Gap", "lat": 62.0, "lon": -15.0, "throughput": "NATO submarine choke"},
    {"name": "Bosphorus", "lat": 41.12, "lon": 29.05, "throughput": "3M bbl/day oil"},
]


CONFLICT_ZONES: list[dict] = [
    {"name": "Ukraine", "lat": 48.38, "lon": 35.0, "type": "interstate_war", "since": "2022-02"},
    {"name": "Gaza", "lat": 31.42, "lon": 34.35, "type": "asymmetric_conflict", "since": "2023-10"},
    {"name": "Sudan", "lat": 15.5, "lon": 32.5, "type": "civil_war", "since": "2023-04"},
    {"name": "Myanmar", "lat": 21.0, "lon": 96.0, "type": "civil_war", "since": "2021-02"},
    {"name": "Sahel", "lat": 14.0, "lon": 2.0, "type": "insurgency", "since": "2012-01"},
    {"name": "DRC/Great Lakes", "lat": -1.5, "lon": 29.0, "type": "multi_party_conflict", "since": "2021-11"},
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_country(iso3: str) -> dict | None:
    """Look up country config by ISO-3 code."""
    return TIER1_COUNTRIES.get(iso3.upper())


def get_event_multiplier(iso3: str) -> float:
    """Get event multiplier for a country (default 1.0)."""
    entry = TIER1_COUNTRIES.get(iso3.upper())
    if entry is not None:
        return entry["event_multiplier"]
    return 1.0


def match_country_by_name(name: str) -> str | None:
    """Match a country name/keyword to ISO-3 code. Returns None if no match."""
    lower = name.lower().strip()
    for iso3, info in TIER1_COUNTRIES.items():
        if lower == info["name"].lower():
            return iso3
        for keyword in info["keywords"]:
            if keyword in lower or lower in keyword:
                return iso3
    return None


# ---------------------------------------------------------------------------
# Election calendar
# ---------------------------------------------------------------------------

UPCOMING_ELECTIONS: list[dict] = [
    {"country": "Germany", "iso3": "DEU", "election_type": "federal", "date": "2025-02-23", "description": "Federal election (Bundestag)", "instability_impact": "low"},
    {"country": "Ecuador", "iso3": "ECU", "election_type": "presidential", "date": "2025-02-09", "description": "Presidential runoff", "instability_impact": "medium"},
    {"country": "Belarus", "iso3": "BLR", "election_type": "presidential", "date": "2025-01-26", "description": "Presidential election", "instability_impact": "high"},
    {"country": "Canada", "iso3": "CAN", "election_type": "federal", "date": "2025-10-20", "description": "Federal election", "instability_impact": "low"},
    {"country": "Iraq", "iso3": "IRQ", "election_type": "parliamentary", "date": "2025-10-01", "description": "Parliamentary election", "instability_impact": "high"},
    {"country": "Chile", "iso3": "CHL", "election_type": "presidential", "date": "2025-11-16", "description": "Presidential election", "instability_impact": "medium"},
    {"country": "Poland", "iso3": "POL", "election_type": "presidential", "date": "2025-05-18", "description": "Presidential election", "instability_impact": "low"},
    {"country": "Philippines", "iso3": "PHL", "election_type": "midterm", "date": "2025-05-12", "description": "Midterm elections", "instability_impact": "medium"},
    {"country": "Singapore", "iso3": "SGP", "election_type": "general", "date": "2025-05-03", "description": "General election", "instability_impact": "low"},
    {"country": "Australia", "iso3": "AUS", "election_type": "federal", "date": "2025-05-17", "description": "Federal election", "instability_impact": "low"},
    {"country": "South Korea", "iso3": "KOR", "election_type": "presidential", "date": "2025-06-03", "description": "Snap presidential election", "instability_impact": "medium"},
    {"country": "Ivory Coast", "iso3": "CIV", "election_type": "presidential", "date": "2025-10-01", "description": "Presidential election", "instability_impact": "high"},
    {"country": "Norway", "iso3": "NOR", "election_type": "parliamentary", "date": "2025-09-08", "description": "Parliamentary election", "instability_impact": "low"},
    {"country": "United States", "iso3": "USA", "election_type": "midterm", "date": "2026-11-03", "description": "Midterm elections", "instability_impact": "medium"},
    {"country": "Brazil", "iso3": "BRA", "election_type": "municipal", "date": "2026-10-04", "description": "Municipal elections", "instability_impact": "medium"},
    {"country": "Mexico", "iso3": "MEX", "election_type": "midterm", "date": "2027-06-06", "description": "Midterm elections", "instability_impact": "medium"},
    {"country": "France", "iso3": "FRA", "election_type": "presidential", "date": "2027-04-10", "description": "Presidential election", "instability_impact": "medium"},
    {"country": "India", "iso3": "IND", "election_type": "general", "date": "2029-04-01", "description": "General election (projected)", "instability_impact": "medium"},
]


def get_election_risk(iso3: str) -> dict | None:
    """Return the next upcoming election for a country with days_until."""
    from datetime import date

    today = date.today()
    upper = iso3.upper()
    best: dict | None = None
    best_days: int = 999999

    for entry in UPCOMING_ELECTIONS:
        if entry["iso3"] != upper:
            continue
        try:
            election_date = date.fromisoformat(entry["date"])
        except ValueError:
            continue
        days_until = (election_date - today).days
        if days_until < best_days:
            best_days = days_until
            best = {**entry, "days_until": days_until}

    return best


# ---------------------------------------------------------------------------
# Nuclear test sites
# ---------------------------------------------------------------------------

NUCLEAR_TEST_SITES: list[dict] = [
    {"name": "Punggye-ri", "country": "North Korea", "iso3": "PRK", "lat": 41.28, "lon": 129.08, "status": "active", "last_test": "2017-09-03", "notes": "DPRK primary test site, 6 tests conducted"},
    {"name": "Lop Nur", "country": "China", "iso3": "CHN", "lat": 41.75, "lon": 88.35, "status": "dormant", "last_test": "1996-07-29", "notes": "Chinese test site, 45 tests"},
    {"name": "Novaya Zemlya", "country": "Russia", "iso3": "RUS", "lat": 73.37, "lon": 54.78, "status": "dormant", "last_test": "1990-10-24", "notes": "Soviet/Russian arctic test site, Tsar Bomba"},
    {"name": "Nevada NTS", "country": "United States", "iso3": "USA", "lat": 37.07, "lon": -116.05, "status": "dormant_reference", "last_test": "1992-09-23", "notes": "US primary test site, 928 tests"},
    {"name": "Semipalatinsk", "country": "Kazakhstan", "iso3": "KAZ", "lat": 50.07, "lon": 78.43, "status": "closed", "last_test": "1989-10-19", "notes": "Soviet test site, 456 tests, closed 1991"},
]
