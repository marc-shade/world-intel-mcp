"""Cyber threat intelligence feed aggregation for world-intel-mcp.

Aggregates threat data from multiple free public feeds:
- Feodo Tracker (abuse.ch) -- C2 botnet IPs
- CISA Known Exploited Vulnerabilities -- actively exploited CVEs
- SANS ISC DShield -- top attacking IPs
- NetAPI honeypot feed -- IPs that attacked NetAPI's honeypot sensors

No API keys required.
"""

import asyncio
import csv
import io
import logging
from datetime import datetime, timezone, timedelta

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.cyber")

# ---------------------------------------------------------------------------
# Feed URLs
# ---------------------------------------------------------------------------

_FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.json"
_CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_SANS_ISC_URL = "https://isc.sans.edu/api/topips/records/20?json"
# IPv4 addresses with a real attack on NetAPI's honeypot sensors in the last
# 48 hours (CC BY 4.0, regenerated hourly, no key). The CSV carries the attack
# type, first / last seen, country and ASN of every address.
_NETAPI_HONEYPOT_URL = (
    "https://netapi.com/api2/?method=compromised&dataset_type=ip&format=csv"
)
# The list holds tens of thousands of addresses; only the most recently
# active ones are merged, so they do not crowd out the other feeds.
_NETAPI_MAX_ITEMS = 25

# ---------------------------------------------------------------------------
# Severity ranking for sorting
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_feodo(data: list | None) -> list[dict]:
    """Normalize Feodo Tracker C2 IP entries."""
    if not data or not isinstance(data, list):
        return []

    items: list[dict] = []
    for entry in data:
        status = entry.get("status", "").lower()
        severity = "critical" if status == "online" else "medium"
        items.append({
            "type": "c2_ip",
            "indicator": entry.get("ip_address", ""),
            "threat": entry.get("malware", "unknown"),
            "severity": severity,
            "source_feed": "feodo-tracker",
            "first_seen": entry.get("first_seen", ""),
            "details": {
                "port": entry.get("port"),
                "status": entry.get("status"),
                "hostname": entry.get("hostname"),
                "as_number": entry.get("as_number"),
                "as_name": entry.get("as_name"),
                "country": entry.get("country"),
                "last_online": entry.get("last_online"),
            },
        })
    return items


def _normalize_cisa_kev(data: dict | None) -> list[dict]:
    """Normalize CISA Known Exploited Vulnerabilities, last 30 days only."""
    if not data or not isinstance(data, dict):
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    vulnerabilities = data.get("vulnerabilities", [])

    items: list[dict] = []
    for vuln in vulnerabilities:
        date_added = vuln.get("dateAdded", "")
        if date_added < cutoff:
            continue

        ransomware = vuln.get("knownRansomwareCampaignUse", "").lower()
        severity = "critical" if ransomware == "known" else "high"

        cve_id = vuln.get("cveID", "")
        vendor = vuln.get("vendorProject", "")
        product = vuln.get("product", "")
        vuln_name = vuln.get("vulnerabilityName", "")

        items.append({
            "type": "vulnerability",
            "indicator": cve_id,
            "threat": f"{vendor} {product}: {vuln_name}",
            "severity": severity,
            "source_feed": "cisa-kev",
            "first_seen": date_added,
            "details": {
                "vendor": vendor,
                "product": product,
                "vulnerability_name": vuln_name,
                "due_date": vuln.get("dueDate"),
                "ransomware_use": vuln.get("knownRansomwareCampaignUse"),
                "required_action": vuln.get("requiredAction"),
                "notes": vuln.get("notes"),
            },
        })
    return items


def _normalize_sans_isc(data: list | None) -> list[dict]:
    """Normalize SANS ISC DShield top attacking IPs."""
    if not data or not isinstance(data, list):
        return []

    items: list[dict] = []
    for entry in data:
        ip = entry.get("ip", "")
        if not ip:
            continue
        items.append({
            "type": "attack_ip",
            "indicator": ip,
            "threat": f"DShield top attacker ({entry.get('attacks', 0)} attacks)",
            "severity": "high",
            "source_feed": "sans-dshield",
            "first_seen": entry.get("firstseen", ""),
            "details": {
                "count": entry.get("count"),
                "attacks": entry.get("attacks"),
                "first_seen": entry.get("firstseen"),
                "last_seen": entry.get("lastseen"),
                "as_name": entry.get("asname"),
                "as_country": entry.get("ascountry"),
            },
        })
    return items


def _normalize_netapi(text: str | None) -> list[dict]:
    """Normalize the NetAPI honeypot IP list (CSV), most recently active first."""
    if not text or not isinstance(text, str):
        return []

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "ip" not in reader.fieldnames:
        return []

    rows = [row for row in reader if (row.get("ip") or "").strip()]
    rows.sort(key=lambda r: r.get("last_seen") or "", reverse=True)

    items: list[dict] = []
    for row in rows[:_NETAPI_MAX_ITEMS]:
        category = (row.get("category") or "").upper()
        top_threat = row.get("top_threat") or ""
        asn = row.get("asn") or ""
        sensors = row.get("sensors") or ""
        items.append({
            "type": "attack_ip",
            "indicator": row["ip"].strip(),
            "threat": (
                f"Honeypot attacker ({top_threat})" if top_threat else "Honeypot attacker"
            ),
            # Category D is form spam; A-C are malware, brute force and exploits.
            "severity": "medium" if category == "D" else "high",
            "source_feed": "netapi-honeypot",
            "first_seen": row.get("first_seen") or "",
            "details": {
                "category": category or None,
                "threats": [t for t in (row.get("threats") or "").split("|") if t],
                "last_seen": row.get("last_seen"),
                "country": row.get("country") or None,
                "as_number": int(asn) if asn.isdigit() else None,
                "as_name": row.get("as_name") or None,
                "sensors": int(sensors) if sensors.isdigit() else None,
            },
        })
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_cyber_threats(
    fetcher: Fetcher,
    limit: int = 50,
) -> dict:
    """Aggregate cyber threat intelligence from free public feeds.

    Fetches data from Feodo Tracker, CISA KEV, SANS ISC DShield, and the
    NetAPI honeypot feed in parallel, normalizes into a common format, and
    returns the top threats sorted by severity and recency.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        limit: Maximum number of threat items to return.

    Returns:
        Dict with threats list, counts, breakdowns by type and severity,
        source, and timestamp.
    """
    feodo_data, cisa_data, sans_data, netapi_text = await asyncio.gather(
        fetcher.get_json(
            _FEODO_URL,
            source="feodo-tracker",
            cache_key="cyber:feodo",
            cache_ttl=1800,
        ),
        fetcher.get_json(
            _CISA_KEV_URL,
            source="cisa-kev",
            cache_key="cyber:cisa_kev",
            cache_ttl=3600,
        ),
        fetcher.get_json(
            _SANS_ISC_URL,
            source="sans-dshield",
            cache_key="cyber:sans_isc",
            cache_ttl=1800,
        ),
        fetcher.get_text(
            _NETAPI_HONEYPOT_URL,
            source="netapi-honeypot",
            cache_key="cyber:netapi_honeypot",
            cache_ttl=3600,
            timeout=60,
        ),
    )

    # Track which feeds returned data
    feeds_successful = 0

    feodo_items = _normalize_feodo(feodo_data)
    if feodo_data is not None:
        feeds_successful += 1
    else:
        logger.warning("Feodo Tracker feed returned no data")

    cisa_items = _normalize_cisa_kev(cisa_data)
    if cisa_data is not None:
        feeds_successful += 1
    else:
        logger.warning("CISA KEV feed returned no data")

    sans_items = _normalize_sans_isc(sans_data)
    if sans_data is not None:
        feeds_successful += 1
    else:
        logger.warning("SANS ISC DShield feed returned no data")

    netapi_items = _normalize_netapi(netapi_text)
    if netapi_text is not None:
        feeds_successful += 1
    else:
        logger.warning("NetAPI honeypot feed returned no data")

    # Merge all threats
    all_threats = feodo_items + cisa_items + sans_items + netapi_items

    # Sort by severity (critical first), then by recency (newest first_seen first).
    # Use stable sort: first by date descending, then by severity ascending.
    all_threats.sort(key=lambda t: t.get("first_seen", ""), reverse=True)
    all_threats.sort(key=lambda t: _SEVERITY_ORDER.get(t.get("severity", "low"), 3))

    # Apply limit
    threats = all_threats[:limit]

    # Compute breakdowns
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for t in threats:
        threat_type = t.get("type", "unknown")
        by_type[threat_type] = by_type.get(threat_type, 0) + 1
        sev = t.get("severity", "low")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "threats": threats,
        "count": len(threats),
        "feeds_successful": feeds_successful,
        "feeds_attempted": 4,
        "by_type": by_type,
        "by_severity": by_severity,
        "source": "cyber-feeds",
        "timestamp": _utc_now_iso(),
    }
