"""Cyber threat intelligence feed aggregation for world-intel-mcp.

Aggregates threat data from multiple free public feeds:
- Feodo Tracker (abuse.ch) -- C2 botnet IPs
- CISA Known Exploited Vulnerabilities -- actively exploited CVEs
- SANS ISC DShield -- top attacking IPs
- URLhaus (abuse.ch) -- malware distribution URLs

No API keys required, except URLhaus: abuse.ch now requires an Auth-Key on
its API (set URLHAUS_AUTH_KEY); without one that feed is skipped and counted
as failed in feeds_successful/feeds_attempted.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.cyber")

# ---------------------------------------------------------------------------
# Feed URLs
# ---------------------------------------------------------------------------

_FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.json"
_CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_SANS_ISC_URL = "https://isc.sans.edu/api/topips/records/20?json"
_URLHAUS_RECENT_URL = "https://urlhaus-api.abuse.ch/v1/urls/recent/limit/25/"

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


def _normalize_urlhaus(data: dict | None) -> list[dict]:
    """Normalize URLhaus recent malware URLs."""
    if not data or not isinstance(data, dict):
        return []

    urls = data.get("urls", [])
    if not isinstance(urls, list):
        return []

    items: list[dict] = []
    for entry in urls:
        status = (entry.get("url_status") or "").lower()
        severity = "high" if status == "online" else "low"
        items.append({
            "type": "malware_url",
            "indicator": entry.get("url", ""),
            "threat": entry.get("threat", "unknown"),
            "severity": severity,
            "source_feed": "urlhaus",
            "first_seen": entry.get("dateadded", ""),
            "details": {
                "url_status": entry.get("url_status"),
                "tags": entry.get("tags"),
                "reporter": entry.get("reporter"),
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

    Fetches data from Feodo Tracker, CISA KEV, SANS ISC DShield, and
    URLhaus in parallel, normalizes into a common format, and returns
    the top threats sorted by severity and recency.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        limit: Maximum number of threat items to return.

    Returns:
        Dict with threats list, counts, breakdowns by type and severity,
        source, and timestamp.
    """
    urlhaus_key = os.environ.get("URLHAUS_AUTH_KEY")

    async def _urlhaus() -> dict | list | None:
        if not urlhaus_key:
            return None
        return await fetcher.get_json(
            _URLHAUS_RECENT_URL,
            source="urlhaus",
            cache_key="cyber:urlhaus",
            cache_ttl=900,
            headers={"Auth-Key": urlhaus_key},
        )

    feodo_data, cisa_data, sans_data, urlhaus_data = await asyncio.gather(
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
        _urlhaus(),
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

    urlhaus_items = _normalize_urlhaus(urlhaus_data)
    if urlhaus_data is not None:
        feeds_successful += 1
    else:
        logger.warning(
            "URLhaus feed returned no data%s",
            "" if urlhaus_key else " (set URLHAUS_AUTH_KEY; abuse.ch API requires a key)",
        )

    # Merge all threats
    all_threats = feodo_items + cisa_items + sans_items + urlhaus_items

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
