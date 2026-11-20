"""US sanctions and restricted-party search source for world-intel-mcp.

Searches the US Treasury OFAC Specially Designated Nationals (SDN) list and,
by default, the other US restricted-party lists:

* the trade.gov Consolidated Screening List (CSL): BIS Entity List, Military
  End User and Unverified Lists, Denied Persons List, State's ITAR debarments
  and nonproliferation sanctions, and the OFAC non-SDN lists (SSI, CMIC,
  NS-MBS, ...). Its SDN rows are skipped because sdn.csv already has them.
* the US lists that are in neither file: DoD 1260H Chinese military
  companies, Section 889 covered telecom companies, the FCC Covered List and
  the UFLPA Entity List, rebuilt daily from the Federal Register, eCFR,
  fcc.gov and dhs.gov by the us-restricted-parties feed (CC BY 4.0).

No API key required. A list that cannot be downloaded is reported in
``lists_unavailable``; it is never read as "no match".
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
_CSL_CSV_URL = (
    "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv"
)
_US_RESTRICTED_CSV_URL = (
    "https://github.com/Mattbusel/us-restricted-parties/releases/latest/download/all.csv"
)

# CSL rows from this source duplicate sdn.csv.
_CSL_SDN_SOURCE_PREFIX = "Specially Designated Nationals"

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
    us_lists: bool = True,
) -> dict:
    """Search the OFAC SDN list and the other US restricted-party lists.

    Downloads the SDN CSV (and, with ``us_lists``, the CSL and the
    us-restricted-parties CSV), caches each for 24h, and performs substring
    matching on name, country, and program fields. Every match carries the
    ``list`` it came from.

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        query: Substring to match against entity names.
        country: Country filter (substring match).
        program: Sanctions program filter (substring match).
        limit: Maximum results to return.
        us_lists: Also search the CSL and the four US lists outside it. With
            False only the SDN is read (the country dossier's SDN screen).

    Returns:
        Dict with matches, count, total_entities, query info, source, and with
        ``us_lists`` the per-list ``lists_searched`` and ``lists_unavailable``.
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
        if not us_lists:
            return {
                "matches": [],
                "count": 0,
                "total_entities": 0,
                "query": {"query": query, "country": country, "program": program},
                "source": "ofac-sdn",
                "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

    query_lower = query.lower().strip()
    country_lower = country.lower().strip() if country else ""
    program_lower = program.lower().strip() if program else ""

    matches: list[dict] = []
    total_entities = 0

    # Parse CSV — SDN format: ent_num, SDN_Name, SDN_Type, Program, Title,
    #   Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks
    for row in csv.reader(io.StringIO(csv_text or "")):
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

        match = {
            "name": name,
            "type": sdn_type,
            "programs": programs,
            "remarks": remarks[:300] if len(remarks) > 300 else remarks,
        }
        if us_lists:
            match["list"] = "OFAC Specially Designated Nationals (SDN)"
        matches.append(match)

        if len(matches) >= limit:
            break

    if not us_lists:
        return {
            "matches": matches,
            "count": len(matches),
            "total_entities": total_entities,
            "query": {"query": query, "country": country, "program": program},
            "source": "ofac-sdn",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    lists_searched: dict[str, int] = {}
    lists_unavailable: list[str] = []
    if csv_text is None:
        lists_unavailable.append("ofac-sdn")
    else:
        lists_searched["ofac-sdn"] = total_entities

    csl_text = await fetcher.get_text(
        _CSL_CSV_URL,
        source="trade-gov-csl",
        cache_key="sanctions:trade_gov:csl_csv",
        cache_ttl=_CACHE_TTL,
        timeout=60.0,
    )
    if csl_text is None:
        logger.warning("Failed to download the trade.gov Consolidated Screening List")
        lists_unavailable.append("trade-gov-csl")
    else:
        rows = 0
        for rec in csv.DictReader(io.StringIO(csl_text.lstrip("﻿"))):
            source = (rec.get("source") or "").strip()
            if not source or source.startswith(_CSL_SDN_SOURCE_PREFIX):
                continue
            rows += 1
            if len(matches) >= limit:
                continue
            name = (rec.get("name") or "").strip()
            alt_names = (rec.get("alt_names") or "").strip()
            places = "; ".join(
                (rec.get(k) or "") for k in ("addresses", "nationalities", "citizenships")
            )
            programs = (rec.get("programs") or "").strip()
            if query_lower and query_lower not in name.lower() and query_lower not in alt_names.lower():
                continue
            if country_lower and country_lower not in places.lower():
                continue
            if program_lower and program_lower not in programs.lower() and program_lower not in source.lower():
                continue
            remarks = (rec.get("remarks") or rec.get("license_requirement") or "").strip()
            matches.append({
                "name": name,
                "type": (rec.get("type") or "").strip(),
                "programs": programs,
                "remarks": remarks[:300],
                "list": source,
            })
        lists_searched["trade-gov-csl"] = rows
        total_entities += rows

    feed_text = await fetcher.get_text(
        _US_RESTRICTED_CSV_URL,
        source="us-restricted-parties",
        cache_key="sanctions:us_restricted_parties:all_csv",
        cache_ttl=_CACHE_TTL,
        timeout=30.0,
    )
    if feed_text is None:
        logger.warning("Failed to download the 1260H / 889 / FCC / UFLPA lists")
        lists_unavailable.append("us-restricted-parties")
    else:
        # One row per name (primary name and each alias) for one RECORD_ID.
        records: dict[str, dict] = {}
        for rec in csv.DictReader(io.StringIO(feed_text.lstrip("﻿"))):
            rid = (rec.get("RECORD_ID") or "").strip()
            name = (rec.get("NAME") or "").strip()
            if not rid or not name:
                continue
            entry = records.setdefault(rid, {"names": [], "primary": "", "row": rec})
            entry["names"].append(name)
            if (rec.get("NAME_TYPE") or "").upper() == "PRIMARY" and not entry["primary"]:
                entry["primary"] = name
                entry["row"] = rec
        for entry in records.values():
            if len(matches) >= limit:
                break
            rec = entry["row"]
            list_name = (rec.get("LIST_NAME") or "").strip()
            if query_lower and not any(query_lower in n.lower() for n in entry["names"]):
                continue
            # These lists carry no country field, so a country search
            # cannot be answered from them and does not match them.
            if country_lower:
                continue
            if program_lower and program_lower not in list_name.lower():
                continue
            parent = (rec.get("PARENT_NAME") or "").strip()
            listed_on = (rec.get("LISTED_ON") or "").strip()
            notes = [
                f"listed on {listed_on}" if listed_on else "",
                f"subsidiary of {parent}" if parent else "",
                (rec.get("SOURCE_URL") or "").strip(),
            ]
            matches.append({
                "name": entry["primary"] or entry["names"][0],
                "type": "Entity",
                "programs": list_name,
                "remarks": "; ".join(n for n in notes if n),
                "list": list_name,
            })
        lists_searched["us-restricted-parties"] = len(records)
        total_entities += len(records)

    return {
        "matches": matches,
        "count": len(matches),
        "total_entities": total_entities,
        "query": {"query": query, "country": country, "program": program},
        "source": "ofac-sdn+trade-gov-csl+us-restricted-parties",
        "lists_searched": lists_searched,
        "lists_unavailable": lists_unavailable,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
