"""Tests for sources/cyber.py — respx-mocked feed aggregation.

Gaps / not covered: live feed schemas may drift from the mocked payloads;
the CISA KEV 30-day cutoff is exercised with a fixed old date, not a
boundary-exact date; circuit-breaker interaction is not exercised here.
"""

import asyncio as asyncio_mod
import csv
from datetime import datetime, timezone, timedelta

import httpx
import pytest
import respx

from world_intel_mcp.fetcher import Fetcher
from world_intel_mcp.sources.cyber import (
    _normalize_cisa_kev,
    _NETAPI_MAX_ITEMS,
    _normalize_feodo,
    _normalize_netapi,
    _normalize_sans_isc,
    fetch_cyber_threats,
)

_RECENT = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")

_FEODO = [
    {
        "ip_address": "1.2.3.4",
        "malware": "Emotet",
        "status": "online",
        "port": 443,
        "hostname": "bad.example",
        "as_number": 64500,
        "as_name": "EVIL-AS",
        "country": "US",
        "first_seen": "2026-08-01",
        "last_online": "2026-08-30",
    },
    {
        "ip_address": "5.6.7.8",
        "malware": "QakBot",
        "status": "offline",
        "first_seen": "2026-01-01",
    },
]

_CISA = {
    "vulnerabilities": [
        {
            "cveID": "CVE-2026-0001",
            "vendorProject": "Acme",
            "product": "Router",
            "vulnerabilityName": "RCE in admin panel",
            "dateAdded": _RECENT,
            "knownRansomwareCampaignUse": "Known",
            "dueDate": "2026-09-15",
            "requiredAction": "Patch",
            "notes": "",
        },
        {
            "cveID": "CVE-2026-0002",
            "vendorProject": "Beta",
            "product": "CMS",
            "vulnerabilityName": "SQLi",
            "dateAdded": _RECENT,
            "knownRansomwareCampaignUse": "Unknown",
        },
        {
            # Older than the 30-day cutoff — must be filtered out.
            "cveID": "CVE-2020-9999",
            "vendorProject": "Old",
            "product": "Legacy",
            "vulnerabilityName": "Ancient bug",
            "dateAdded": "2020-01-01",
            "knownRansomwareCampaignUse": "Known",
        },
    ]
}

_SANS = [
    {
        "ip": "9.9.9.9",
        "attacks": 1234,
        "count": 10,
        "firstseen": "2026-08-20",
        "lastseen": "2026-08-31",
        "asname": "SOME-AS",
        "ascountry": "CN",
    },
    {"ip": "", "attacks": 5},  # no IP — skipped
]

_NETAPI_HEADER = (
    "ip,first_seen,last_seen,category,top_threat,threats,country,asn,as_name,sensors\n"
)

_NETAPI_CSV = (
    _NETAPI_HEADER
    + "203.0.113.10,2026-08-29T10:00:00Z,2026-08-30T12:00:00Z,B,ssh-bruteforce,"
    + 'ssh-bruteforce|shell-recon,DE,64501,"EXAMPLE-AS, Inc.",3\n'
    + "198.51.100.7,2026-08-02T08:00:00Z,2026-08-28T09:30:00Z,D,form-spam,"
    + "form-spam,,,,1\n"
    + ",,,,,,,,,\n"  # no IP — skipped
)


def _mock_all_feeds() -> None:
    respx.get(url__regex=r".*feodotracker\.abuse\.ch.*").mock(
        return_value=httpx.Response(200, json=_FEODO)
    )
    respx.get(url__regex=r".*cisa\.gov.*").mock(
        return_value=httpx.Response(200, json=_CISA)
    )
    respx.get(url__regex=r".*isc\.sans\.edu.*").mock(
        return_value=httpx.Response(200, json=_SANS)
    )
    respx.get(url__regex=r".*netapi\.com.*").mock(
        return_value=httpx.Response(200, text=_NETAPI_CSV)
    )


@respx.mock
@pytest.mark.asyncio
async def test_fetch_cyber_threats_aggregates_all_feeds(fetcher: Fetcher) -> None:
    _mock_all_feeds()

    result = await fetch_cyber_threats(fetcher)

    assert result["source"] == "cyber-feeds"
    assert result["feeds_attempted"] == 4
    assert result["feeds_successful"] == 4
    # 2 feodo + 2 KEV (old one cut) + 1 SANS (empty-IP skipped) + 2 netapi
    assert result["count"] == 7

    # Severity ordering: criticals first, then high, medium, low.
    severities = [t["severity"] for t in result["threats"]]
    assert severities == [
        "critical",
        "critical",
        "high",
        "high",
        "high",
        "medium",
        "medium",
    ]

    # Within criticals, newest first_seen first (KEV added 5 days ago beats
    # the feodo entry from 2026-08-01).
    assert result["threats"][0]["indicator"] == "CVE-2026-0001"
    assert result["threats"][1]["indicator"] == "1.2.3.4"

    # Old KEV entry filtered by the 30-day cutoff.
    indicators = {t["indicator"] for t in result["threats"]}
    assert "CVE-2020-9999" not in indicators

    assert result["by_type"] == {
        "c2_ip": 2,
        "vulnerability": 2,
        "attack_ip": 3,
    }
    assert result["by_severity"] == {"critical": 2, "high": 3, "medium": 2}

    # Field contract on one item per feed.
    feodo = next(t for t in result["threats"] if t["indicator"] == "1.2.3.4")
    assert feodo["type"] == "c2_ip"
    assert feodo["threat"] == "Emotet"
    assert feodo["source_feed"] == "feodo-tracker"
    assert feodo["details"]["port"] == 443
    assert feodo["details"]["country"] == "US"

    kev = next(t for t in result["threats"] if t["indicator"] == "CVE-2026-0002")
    assert kev["severity"] == "high"  # not ransomware-linked
    assert kev["threat"] == "Beta CMS: SQLi"

    sans = next(t for t in result["threats"] if t["indicator"] == "9.9.9.9")
    assert sans["threat"] == "DShield top attacker (1234 attacks)"
    assert sans["details"]["as_country"] == "CN"

    netapi = next(t for t in result["threats"] if t["indicator"] == "203.0.113.10")
    assert netapi["type"] == "attack_ip"
    assert netapi["severity"] == "high"
    assert netapi["source_feed"] == "netapi-honeypot"
    assert netapi["threat"] == "Honeypot attacker (ssh-bruteforce)"
    assert netapi["first_seen"] == "2026-08-29T10:00:00Z"
    assert netapi["details"] == {
        "category": "B",
        "threats": ["ssh-bruteforce", "shell-recon"],
        "last_seen": "2026-08-30T12:00:00Z",
        "country": "DE",
        "as_number": 64501,
        "as_name": "EXAMPLE-AS, Inc.",
        "sensors": 3,
    }
    spam = next(t for t in result["threats"] if t["indicator"] == "198.51.100.7")
    assert spam["severity"] == "medium"  # category D, form spam
    assert spam["details"]["country"] is None
    assert spam["details"]["as_number"] is None

    # High items: KEV added 5 days ago, then the NetAPI address first seen
    # 2026-08-29, then the SANS entry first seen 2026-08-20.
    assert [t["indicator"] for t in result["threats"][2:5]] == [
        "CVE-2026-0002",
        "203.0.113.10",
        "9.9.9.9",
    ]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_cyber_threats_limit(fetcher: Fetcher) -> None:
    _mock_all_feeds()

    result = await fetch_cyber_threats(fetcher, limit=2)
    assert result["count"] == 2
    assert [t["severity"] for t in result["threats"]] == ["critical", "critical"]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_cyber_threats_all_feeds_down(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All 4 feeds failing must be visible via feeds_successful=0, never
    reported as a quiet threat landscape with feeds_successful=4."""

    async def _no_sleep(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(asyncio_mod, "sleep", _no_sleep)

    respx.get(url__regex=r".*").mock(return_value=httpx.Response(500))

    result = await fetch_cyber_threats(fetcher)
    assert result["feeds_successful"] == 0
    assert result["feeds_attempted"] == 4
    assert result["threats"] == []
    assert result["count"] == 0
    assert result["by_type"] == {}
    assert result["by_severity"] == {}


@respx.mock
@pytest.mark.asyncio
async def test_fetch_cyber_threats_partial_outage(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_sleep(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(asyncio_mod, "sleep", _no_sleep)

    respx.get(url__regex=r".*feodotracker\.abuse\.ch.*").mock(
        return_value=httpx.Response(200, json=_FEODO)
    )
    respx.get(url__regex=r".*cisa\.gov.*").mock(return_value=httpx.Response(500))
    respx.get(url__regex=r".*isc\.sans\.edu.*").mock(return_value=httpx.Response(500))
    respx.get(url__regex=r".*netapi\.com.*").mock(return_value=httpx.Response(500))

    result = await fetch_cyber_threats(fetcher)
    assert result["feeds_successful"] == 1
    assert result["count"] == 2
    assert all(t["source_feed"] == "feodo-tracker" for t in result["threats"])


def test_normalizers_reject_wrong_shapes() -> None:
    assert _normalize_feodo(None) == []
    assert _normalize_feodo({"not": "a list"}) == []
    assert _normalize_cisa_kev(None) == []
    assert _normalize_cisa_kev([1, 2]) == []
    assert _normalize_sans_isc(None) == []
    assert _normalize_sans_isc({}) == []
    assert _normalize_netapi(None) is None
    assert _normalize_netapi("") is None
    assert _normalize_netapi("<html><body>502 Bad Gateway</body></html>") is None
    assert _normalize_netapi("address,last_seen\n203.0.113.10,x\n") is None
    # a valid list without rows is not a failure
    assert _normalize_netapi(_NETAPI_HEADER) == []


def test_normalize_netapi_contains_csv_errors() -> None:
    """A field larger than csv.field_size_limit() raises csv.Error inside the
    reader. The feed is then rejected instead of the error escaping."""
    huge = "x" * (csv.field_size_limit() + 10)
    assert _normalize_netapi(_NETAPI_HEADER + f"203.0.113.10,{huge}\n") is None


@respx.mock
@pytest.mark.asyncio
async def test_rejected_netapi_body_is_not_counted_as_a_feed(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An HTML page with status 200 is cached like a list, but it must not
    raise the healthy-feed count."""
    async def _no_sleep(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(asyncio_mod, "sleep", _no_sleep)

    respx.get(url__regex=r".*feodotracker\.abuse\.ch.*").mock(
        return_value=httpx.Response(200, json=_FEODO)
    )
    respx.get(url__regex=r".*cisa\.gov.*").mock(return_value=httpx.Response(500))
    respx.get(url__regex=r".*isc\.sans\.edu.*").mock(return_value=httpx.Response(500))
    respx.get(url__regex=r".*netapi\.com.*").mock(
        return_value=httpx.Response(200, text="<html><body>maintenance</body></html>")
    )

    result = await fetch_cyber_threats(fetcher)
    assert result["feeds_successful"] == 1
    assert all(t["source_feed"] == "feodo-tracker" for t in result["threats"])


def test_normalize_netapi_keeps_the_most_recent_addresses() -> None:
    """The list holds tens of thousands of addresses; only the most recently
    active ones are merged, newest last_seen first."""
    rows = "".join(
        f"192.0.2.{i},2026-08-01T00:00:00Z,2026-08-{i + 1:02d}T00:00:00Z,C,"
        "env-file-hunting,env-file-hunting,US,64500,EXAMPLE-AS,1\n"
        for i in range(_NETAPI_MAX_ITEMS + 5)
    )
    items = _normalize_netapi(_NETAPI_HEADER + rows)
    assert len(items) == _NETAPI_MAX_ITEMS
    assert items[0]["indicator"] == f"192.0.2.{_NETAPI_MAX_ITEMS + 4}"
    assert items[-1]["indicator"] == "192.0.2.5"
    assert all(t["severity"] == "high" for t in items)
    assert all(t["threat"] == "Honeypot attacker (env-file-hunting)" for t in items)
