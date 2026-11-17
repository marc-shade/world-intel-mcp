"""Tests for sources/cyber.py — respx-mocked feed aggregation.

Gaps / not covered: live feed schemas may drift from the mocked payloads;
the CISA KEV 30-day cutoff is exercised with a fixed old date, not a
boundary-exact date; circuit-breaker interaction is not exercised here.
"""

import asyncio as asyncio_mod
from datetime import datetime, timezone, timedelta

import httpx
import pytest
import respx

from world_intel_mcp.fetcher import Fetcher
from world_intel_mcp.sources.cyber import (
    _normalize_cisa_kev,
    _normalize_feodo,
    _normalize_sans_isc,
    _normalize_urlhaus,
    fetch_cyber_threats,
)

@pytest.fixture(autouse=True)
def _urlhaus_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("URLHAUS_AUTH_KEY", "test-key")


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

_URLHAUS = {
    "urls": [
        {
            "url": "http://evil.example/mal.exe",
            "threat": "malware_download",
            "url_status": "online",
            "dateadded": "2026-08-30",
            "tags": ["exe"],
            "reporter": "abuse_ch",
        },
        {
            "url": "http://old.example/gone.exe",
            "threat": "malware_download",
            "url_status": "offline",
            "dateadded": "2026-08-01",
        },
    ]
}


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
    respx.get(url__regex=r".*urlhaus-api\.abuse\.ch.*").mock(
        return_value=httpx.Response(200, json=_URLHAUS)
    )


@respx.mock
@pytest.mark.asyncio
async def test_fetch_cyber_threats_aggregates_all_feeds(fetcher: Fetcher) -> None:
    _mock_all_feeds()

    result = await fetch_cyber_threats(fetcher)

    assert result["source"] == "cyber-feeds"
    assert result["feeds_attempted"] == 4
    assert result["feeds_successful"] == 4
    # 2 feodo + 2 KEV (old one cut) + 1 SANS (empty-IP skipped) + 2 urlhaus
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
        "low",
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
        "attack_ip": 1,
        "malware_url": 2,
    }
    assert result["by_severity"] == {"critical": 2, "high": 3, "medium": 1, "low": 1}

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

    urlh = next(
        t for t in result["threats"] if t["indicator"] == "http://evil.example/mal.exe"
    )
    assert urlh["severity"] == "high"  # online
    offline = next(
        t for t in result["threats"] if t["indicator"] == "http://old.example/gone.exe"
    )
    assert offline["severity"] == "low"


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
    respx.get(url__regex=r".*urlhaus-api\.abuse\.ch.*").mock(
        return_value=httpx.Response(500)
    )

    result = await fetch_cyber_threats(fetcher)
    assert result["feeds_successful"] == 1
    assert result["count"] == 2
    assert all(t["source_feed"] == "feodo-tracker" for t in result["threats"])


@respx.mock
@pytest.mark.asyncio
async def test_urlhaus_sends_auth_key(fetcher: Fetcher) -> None:
    _mock_all_feeds()
    await fetch_cyber_threats(fetcher)
    call = next(c for c in respx.calls if "urlhaus-api" in str(c.request.url))
    assert call.request.headers["Auth-Key"] == "test-key"


@respx.mock
@pytest.mark.asyncio
async def test_urlhaus_without_key_is_failed_not_success(
    fetcher: Fetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("URLHAUS_AUTH_KEY")
    _mock_all_feeds()
    result = await fetch_cyber_threats(fetcher)
    assert result["feeds_successful"] == 3
    assert result["feeds_attempted"] == 4
    assert all(t["source_feed"] != "urlhaus" for t in result["threats"])
    assert not any("urlhaus-api" in str(c.request.url) for c in respx.calls)


def test_normalizers_reject_wrong_shapes() -> None:
    assert _normalize_feodo(None) == []
    assert _normalize_feodo({"not": "a list"}) == []
    assert _normalize_cisa_kev(None) == []
    assert _normalize_cisa_kev([1, 2]) == []
    assert _normalize_sans_isc(None) == []
    assert _normalize_sans_isc({}) == []
    assert _normalize_urlhaus(None) == []
    assert _normalize_urlhaus([]) == []
    assert _normalize_urlhaus({"urls": "not-a-list"}) == []
