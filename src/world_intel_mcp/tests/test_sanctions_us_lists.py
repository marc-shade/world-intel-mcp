"""Tests for the US restricted-party lists in sources/sanctions.py.

The name search used to read only the OFAC SDN list, so a party on the BIS
Entity List, the Military End User List, the OFAC non-SDN lists, DoD 1260H,
Section 889, the FCC Covered List or the UFLPA Entity List came back as
"0 matches". The rows below are real rows from the trade.gov Consolidated
Screening List CSV and the us-restricted-parties all.csv of 2026-11-20
(long columns trimmed); none of these four parties is on the SDN list.

Gaps / not covered: matching is the same substring match as before, so
spelling variants that are not listed as aliases are still missed.
"""

import httpx
import respx

from world_intel_mcp.sources.sanctions import (
    _CSL_CSV_URL,
    _OFAC_CSV_URL,
    _US_RESTRICTED_CSV_URL,
    fetch_sanctions_search,
)

_SDN_CSV_ROWS = (
    '36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ',
    '306,"BANCO NACIONAL DE CUBA",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"a.k.a. \'BNC\'."',
)
SDN_CSV = "\n".join(_SDN_CSV_ROWS)

_CSL_HEADER = (
    '"_id","source","entity_number","type","programs","name","title","addresses",'
    '"federal_register_notice","start_date","end_date","standard_order","license_requirement",'
    '"license_policy","call_sign","vessel_type","gross_tonnage","gross_registered_tonnage",'
    '"vessel_flag","vessel_owner","remarks","source_list_url","alt_names","citizenships",'
    '"dates_of_birth","nationalities","places_of_birth","source_information_url","ids"'
)
_CSL_CSV_ROWS = (
    _CSL_HEADER,
    (
        '"03af7d6df1cb349107d67791c92fcfba4422eda0c148aad1b730fc89","Entity List (EL) - Bureau of Industry and Security",'
        '"","","","Huawei Technologies Co., Ltd.","","Tsim Sha Tsui, Kowloon, HK","84 FR 22963","2019-05-21","","",'
        '"For All Items Subject to the EAR","Presumption of denial","","","","","","","",'
        '"https://www.bis.gov/regulations/ear/744#supplement-4-744","","","","","","",""'
    ),
    (
        '"ebb648a4c4f14a3dbb22829dcbf84c33","Military End User (MEU) List - Bureau of Industry and Security",'
        '"","","","Academy of Aerospace Solid Propulsion Technology (AASPT)","","Tian Wang te Zi #1, Baqiao District, '
        'Xian, China, CN","85 FR 83799","2020-12-23","","","For any item subject to the EAR listed in supplement no. 2 '
        'to part 744.","","","","","","","","","https://www.bis.gov/regulations/ear/744#supplement-7-744","","","","","","",""'
    ),
    (
        '"36","Specially Designated Nationals (SDN) - Treasury Department","36","Entity","CUBA","AEROCARIBBEAN AIRLINES",'
        '"","Havana, CU","","","","","","","","","","","","","","https://sanctionslist.ofac.treas.gov/Home/SdnList",'
        '"AERO-CARIBBEAN","","","","","",""'
    ),
)
CSL_CSV = "\n".join(_CSL_CSV_ROWS)

_FEED_CSV_ROWS = (
    "RECORD_ID,NAME,NAME_TYPE,DATA_SOURCE,LIST_NAME,LISTED_ON,PARENT_NAME,SOURCE_URL",
    (
        "us_fcc_covered-china-mobile-international-usa-inc,China Mobile International USA Inc,PRIMARY,US_FCC_COVERED,"
        "FCC Covered List (Secure and Trusted Communications Networks Act),2022-03-25,,"
        "https://www.fcc.gov/supplychain/coveredlist"
    ),
    (
        'us_dhs_uflpa-aksu-aodu-sugar-industry-co-ltd,"Aksu Aodu Sugar Industry Co., Ltd.",PRIMARY,US_DHS_UFLPA,'
        "UFLPA Entity List,2026-08-03,,https://www.federalregister.gov/documents/2026/10/29/2026-22094/"
        "notice-regarding-the-uyghur-forced-labor-prevention-act-entity-list"
    ),
    (
        "us_dod_1260h-14th-research-institute-of-cetc,14th Research Institute of CETC,PRIMARY,US_DOD_1260H,"
        "DoD Chinese Military Companies (Section 1260H),2026-06-10,China Electronics Technology Group Corporation,"
        "https://www.federalregister.gov/documents/2026/06/10/2026-11571/notice-of-availability-of-designation-of-"
        "chinese-military-companies"
    ),
    (
        "us_dod_1260h-14th-research-institute-of-cetc,Nanjing Research Institute of Electronics Technology,ALIAS,"
        "US_DOD_1260H,DoD Chinese Military Companies (Section 1260H),2026-06-10,"
        "China Electronics Technology Group Corporation,https://www.federalregister.gov/"
    ),
)
FEED_CSV = "\n".join(_FEED_CSV_ROWS)


def _mock_all(sdn: int = 200, csl: int = 200, feed: int = 200) -> None:
    respx.get(_OFAC_CSV_URL).mock(return_value=httpx.Response(sdn, text=SDN_CSV if sdn == 200 else ""))
    respx.get(_CSL_CSV_URL).mock(return_value=httpx.Response(csl, text=CSL_CSV if csl == 200 else ""))
    respx.get(_US_RESTRICTED_CSV_URL).mock(
        return_value=httpx.Response(feed, text=FEED_CSV if feed == 200 else "")
    )


@respx.mock
async def test_entity_list_party_is_found(fetcher) -> None:
    _mock_all()
    data = await fetch_sanctions_search(fetcher, query="huawei technologies")
    assert data["count"] == 1
    assert data["matches"][0]["list"] == "Entity List (EL) - Bureau of Industry and Security"


@respx.mock
async def test_meu_party_is_found(fetcher) -> None:
    _mock_all()
    data = await fetch_sanctions_search(fetcher, query="solid propulsion")
    assert [m["list"] for m in data["matches"]] == [
        "Military End User (MEU) List - Bureau of Industry and Security"
    ]


@respx.mock
async def test_fcc_covered_list_party_is_found(fetcher) -> None:
    _mock_all()
    data = await fetch_sanctions_search(fetcher, query="China Mobile International")
    assert data["count"] == 1
    m = data["matches"][0]
    assert m["list"].startswith("FCC Covered List")
    assert "2022-03-25" in m["remarks"]


@respx.mock
async def test_uflpa_party_is_found(fetcher) -> None:
    _mock_all()
    data = await fetch_sanctions_search(fetcher, query="aksu aodu sugar")
    assert [m["list"] for m in data["matches"]] == ["UFLPA Entity List"]


@respx.mock
async def test_1260h_alias_returns_the_primary_name_and_parent(fetcher) -> None:
    _mock_all()
    data = await fetch_sanctions_search(fetcher, query="Nanjing Research Institute of Electronics")
    assert data["count"] == 1
    m = data["matches"][0]
    assert m["name"] == "14th Research Institute of CETC"
    assert m["list"] == "DoD Chinese Military Companies (Section 1260H)"
    assert "subsidiary of China Electronics Technology Group Corporation" in m["remarks"]


@respx.mock
async def test_sdn_rows_in_the_csl_are_not_reported_twice(fetcher) -> None:
    _mock_all()
    data = await fetch_sanctions_search(fetcher, query="aerocaribbean")
    assert data["count"] == 1
    assert data["matches"][0]["list"] == "OFAC Specially Designated Nationals (SDN)"
    assert data["lists_searched"] == {"ofac-sdn": 2, "trade-gov-csl": 2, "us-restricted-parties": 3}
    assert data["total_entities"] == 7


@respx.mock
async def test_a_list_that_fails_to_download_is_named_not_read_as_no_match(fetcher) -> None:
    _mock_all(csl=503)
    data = await fetch_sanctions_search(fetcher, query="huawei")
    assert data["count"] == 0
    assert data["lists_unavailable"] == ["trade-gov-csl"]
    assert "trade-gov-csl" not in data["lists_searched"]


@respx.mock
async def test_sdn_outage_still_searches_the_other_lists(fetcher) -> None:
    _mock_all(sdn=503)
    data = await fetch_sanctions_search(fetcher, query="China Mobile")
    assert data["count"] == 1
    assert data["lists_unavailable"] == ["ofac-sdn"]


@respx.mock
async def test_sdn_only_mode_is_unchanged(fetcher) -> None:
    sdn = respx.get(_OFAC_CSV_URL).mock(return_value=httpx.Response(200, text=SDN_CSV))
    csl = respx.get(_CSL_CSV_URL).mock(return_value=httpx.Response(200, text=CSL_CSV))
    data = await fetch_sanctions_search(fetcher, query="cuba", us_lists=False)
    assert sdn.called and not csl.called
    assert data["source"] == "ofac-sdn"
    assert "lists_searched" not in data
    assert [m["name"] for m in data["matches"]] == ["BANCO NACIONAL DE CUBA"]
