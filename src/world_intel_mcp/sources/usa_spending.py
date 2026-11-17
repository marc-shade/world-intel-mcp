"""US Federal spending data from USAspending.gov API.

No API key required. Public REST API.
"""

import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.usa_spending")

_SPENDING_BASE = "https://api.usaspending.gov/api/v2"
_SPENDING_OVERVIEW_URL = f"{_SPENDING_BASE}/references/toptier_agencies/"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def fetch_usa_spending(
    fetcher: Fetcher,
    agency: str | None = None,
    limit: int = 25,
) -> dict:
    """Fetch federal agency spending overview from USAspending.gov.

    Args:
        fetcher: Shared HTTP fetcher.
        agency: Optional agency name filter.
        limit: Number of agencies to return.

    Returns:
        Dict with agencies[], total_budget, source, timestamp.
    """
    now = datetime.now(timezone.utc)
    fiscal_year = now.year if now.month >= 10 else now.year - 1

    data = await fetcher.get_json(
        _SPENDING_OVERVIEW_URL,
        source="usaspending",
        cache_key=f"spending:agencies:{fiscal_year}",
        cache_ttl=3600,
        params={"sort": "obligated_amount", "order": "desc"},
    )

    if data is None or not isinstance(data, dict):
        return {
            "agencies": [],
            "count": 0,
            "fiscal_year": fiscal_year,
            "source": "usaspending",
            "timestamp": _utc_now_iso(),
            "error": "USAspending agency fetch failed",
            "degraded": True,
        }

    agencies = []
    for item in data.get("results", []):
        name = item.get("agency_name", "")
        if agency and agency.lower() not in name.lower():
            continue
        agencies.append({
            "name": name,
            "abbreviation": item.get("abbreviation", ""),
            "obligated_amount": item.get("obligated_amount"),
            "budget_authority": item.get("budget_authority_amount"),
            "percentage_of_total": item.get("percentage_of_total_budget_authority"),
        })

    agencies = agencies[:limit]
    total = sum(a["obligated_amount"] or 0 for a in agencies)

    return {
        "agencies": agencies,
        "count": len(agencies),
        "total_obligated": total,
        "fiscal_year": fiscal_year,
        "source": "usaspending",
        "timestamp": _utc_now_iso(),
    }
