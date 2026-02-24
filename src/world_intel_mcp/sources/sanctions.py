"""OFAC sanctions search source for world-intel-mcp.

Searches the US Treasury OFAC Specially Designated Nationals (SDN) list
via the consolidated CSV download. No API key required.
"""

import csv
import io
import logging
from datetime import datetime, timezone

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.sanctions")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OFAC_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"

_CACHE_TTL = 86400  # 24 hours


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_sanctions_search(
    fetcher: Fetcher,
    query: str = "",
    country: str | None = None,
    program: str | None = None,
    limit: int = 50,
) -> dict:
    """Search the OFAC SDN consolidated list.

    Downloads the SDN CSV, caches for 24h, and performs substring matching
    on name, country, and program fields.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        query: Substring to match against entity names.
        country: Country filter (substring match).
        program: Sanctions program filter (substring match).
        limit: Maximum results to return.

    Returns:
        Dict with matches, count, total_entities, query info, source.
    """
    now = datetime.now(timezone.utc)

    csv_text = await fetcher.get_text(
        _OFAC_CSV_URL,
        source="ofac-sdn",
        cache_key="sanctions:ofac:sdn_csv",
        cache_ttl=_CACHE_TTL,
        timeout=30.0,
    )

    if csv_text is None:
        logger.warning("Failed to download OFAC SDN list")
        return {
            "matches": [],
            "count": 0,
            "total_entities": 0,
            "query": {"query": query, "country": country, "program": program},
            "source": "ofac-sdn",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Parse CSV — SDN format: ent_num, SDN_Name, SDN_Type, Program, Title,
    #   Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks
    reader = csv.reader(io.StringIO(csv_text))

    query_lower = query.lower().strip()
    country_lower = country.lower().strip() if country else ""
    program_lower = program.lower().strip() if program else ""

    matches: list[dict] = []
    total_entities = 0

    for row in reader:
        if len(row) < 4:
            continue

        total_entities += 1
        name = row[1].strip()
        sdn_type = row[2].strip()
        programs = row[3].strip()
        remarks = row[11].strip() if len(row) > 11 else ""

        # Extract country from remarks if present
        entry_country = ""
        if remarks:
            for part in remarks.split(";"):
                part = part.strip()
                if part.startswith("nationality") or part.startswith("country"):
                    entry_country = part

        # Apply filters
        if query_lower and query_lower not in name.lower():
            continue
        if country_lower and country_lower not in entry_country.lower() and country_lower not in remarks.lower():
            continue
        if program_lower and program_lower not in programs.lower():
            continue

        matches.append({
            "name": name,
            "type": sdn_type,
            "programs": programs,
            "remarks": remarks[:300] if len(remarks) > 300 else remarks,
        })

        if len(matches) >= limit:
            break

    return {
        "matches": matches,
        "count": len(matches),
        "total_entities": total_entities,
        "query": {"query": query, "country": country, "program": program},
        "source": "ofac-sdn",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
