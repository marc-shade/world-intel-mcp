"""Strategic maritime trade routes and chokepoints.

Pure data module — no I/O, no external dependencies.
Sources: UNCTAD Review of Maritime Transport, US EIA World Transit Chokepoints,
MarineTraffic, World Shipping Council.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TRADE_ROUTES — 19 critical maritime chokepoints and shipping lanes
# Fields: name, lat, lon, type, daily_vessel_transits, oil_flow_mbd,
#         trade_value_pct, countries, notes
# ---------------------------------------------------------------------------

TRADE_ROUTES: list[dict] = [
    {"name": "Strait of Hormuz", "lat": 26.57, "lon": 56.25, "type": "chokepoint",
     "daily_vessel_transits": 80, "oil_flow_mbd": 20.5, "trade_value_pct": 21,
     "countries": ["IRN", "OMN", "ARE"], "notes": "World's most critical oil chokepoint, ~20% of global oil"},
    {"name": "Strait of Malacca", "lat": 2.50, "lon": 101.50, "type": "chokepoint",
     "daily_vessel_transits": 200, "oil_flow_mbd": 16.0, "trade_value_pct": 25,
     "countries": ["MYS", "IDN", "SGP"], "notes": "Shortest route between Pacific and Indian Ocean, ~25% global trade"},
    {"name": "Suez Canal", "lat": 30.58, "lon": 32.27, "type": "canal",
     "daily_vessel_transits": 50, "oil_flow_mbd": 5.5, "trade_value_pct": 12,
     "countries": ["EGY"], "notes": "Connects Mediterranean and Red Sea, 12% global trade"},
    {"name": "Bab el-Mandeb", "lat": 12.58, "lon": 43.33, "type": "chokepoint",
     "daily_vessel_transits": 65, "oil_flow_mbd": 6.2, "trade_value_pct": 10,
     "countries": ["YEM", "DJI", "ERI"], "notes": "Gate to Suez Canal from Indian Ocean, Houthi threat zone"},
    {"name": "Panama Canal", "lat": 9.08, "lon": -79.68, "type": "canal",
     "daily_vessel_transits": 35, "oil_flow_mbd": 0.9, "trade_value_pct": 5,
     "countries": ["PAN"], "notes": "Connects Atlantic and Pacific, drought-restricted since 2023"},
    {"name": "Turkish Straits (Bosphorus)", "lat": 41.12, "lon": 29.05, "type": "chokepoint",
     "daily_vessel_transits": 120, "oil_flow_mbd": 3.0, "trade_value_pct": 3,
     "countries": ["TUR"], "notes": "Connects Black Sea to Mediterranean, Russian oil exports"},
    {"name": "Danish Straits", "lat": 55.60, "lon": 12.60, "type": "chokepoint",
     "daily_vessel_transits": 90, "oil_flow_mbd": 3.2, "trade_value_pct": 2,
     "countries": ["DNK", "SWE"], "notes": "Baltic Sea access, Russian energy exports, Nord Stream corridor"},
    {"name": "Strait of Gibraltar", "lat": 35.97, "lon": -5.60, "type": "chokepoint",
     "daily_vessel_transits": 250, "oil_flow_mbd": 3.0, "trade_value_pct": 4,
     "countries": ["ESP", "MAR", "GBR"], "notes": "Atlantic-Mediterranean gateway"},
    {"name": "Cape of Good Hope", "lat": -34.36, "lon": 18.47, "type": "route",
     "daily_vessel_transits": 40, "oil_flow_mbd": 6.0, "trade_value_pct": 8,
     "countries": ["ZAF"], "notes": "Suez Canal alternative, Houthi rerouting hub since 2024"},
    {"name": "Lombok Strait", "lat": -8.40, "lon": 115.70, "type": "chokepoint",
     "daily_vessel_transits": 30, "oil_flow_mbd": 1.5, "trade_value_pct": 2,
     "countries": ["IDN"], "notes": "Malacca bypass for deep-draft VLCCs"},
    {"name": "Taiwan Strait", "lat": 24.00, "lon": 118.50, "type": "chokepoint",
     "daily_vessel_transits": 150, "oil_flow_mbd": 5.0, "trade_value_pct": 20,
     "countries": ["TWN", "CHN"], "notes": "Semiconductor supply chain route, geopolitical flashpoint"},
    {"name": "Mozambique Channel", "lat": -17.00, "lon": 42.00, "type": "route",
     "daily_vessel_transits": 25, "oil_flow_mbd": 2.0, "trade_value_pct": 2,
     "countries": ["MOZ", "MDG"], "notes": "East African LNG export corridor"},
    {"name": "Strait of Sunda", "lat": -6.10, "lon": 105.80, "type": "chokepoint",
     "daily_vessel_transits": 15, "oil_flow_mbd": 0.5, "trade_value_pct": 1,
     "countries": ["IDN"], "notes": "Java-Sumatra strait, Malacca alternative"},
    {"name": "Northern Sea Route", "lat": 73.00, "lon": 100.00, "type": "route",
     "daily_vessel_transits": 5, "oil_flow_mbd": 0.3, "trade_value_pct": 0.1,
     "countries": ["RUS"], "notes": "Arctic route, seasonal, Russian-controlled, growing LNG traffic"},
    {"name": "English Channel", "lat": 50.50, "lon": 1.00, "type": "route",
     "daily_vessel_transits": 500, "oil_flow_mbd": 2.0, "trade_value_pct": 5,
     "countries": ["GBR", "FRA"], "notes": "Busiest shipping lane in the world by vessel count"},
    {"name": "Korea Strait", "lat": 34.00, "lon": 129.50, "type": "chokepoint",
     "daily_vessel_transits": 100, "oil_flow_mbd": 3.5, "trade_value_pct": 4,
     "countries": ["KOR", "JPN"], "notes": "Sea of Japan access, Japan-Korea trade corridor"},
    {"name": "Strait of Luzon", "lat": 20.00, "lon": 121.00, "type": "chokepoint",
     "daily_vessel_transits": 50, "oil_flow_mbd": 3.0, "trade_value_pct": 5,
     "countries": ["PHL", "TWN"], "notes": "South China Sea-Pacific gateway, PLAN patrol zone"},
    {"name": "Dover Strait", "lat": 51.05, "lon": 1.40, "type": "chokepoint",
     "daily_vessel_transits": 400, "oil_flow_mbd": 1.5, "trade_value_pct": 3,
     "countries": ["GBR", "FRA"], "notes": "Narrowest point of English Channel, TSS enforced"},
    {"name": "Dardanelles", "lat": 40.20, "lon": 26.40, "type": "chokepoint",
     "daily_vessel_transits": 120, "oil_flow_mbd": 3.0, "trade_value_pct": 3,
     "countries": ["TUR"], "notes": "Aegean entrance to Turkish Straits, grain corridor"},
]

# ---------------------------------------------------------------------------
# CLOUD_REGIONS — Major cloud provider regions (AWS, Azure, GCP)
# Fields: name, provider, region_code, lat, lon, launched, zone_count, notes
# ---------------------------------------------------------------------------

CLOUD_REGIONS: list[dict] = [
    # AWS Major Regions
    {"name": "US East (Virginia)", "provider": "AWS", "region_code": "us-east-1", "lat": 39.05, "lon": -77.49, "launched": 2006, "zone_count": 6, "notes": "AWS's largest region, default for most services"},
    {"name": "US West (Oregon)", "provider": "AWS", "region_code": "us-west-2", "lat": 45.95, "lon": -119.57, "launched": 2011, "zone_count": 4, "notes": "Second-largest AWS region"},
    {"name": "Europe (Ireland)", "provider": "AWS", "region_code": "eu-west-1", "lat": 53.34, "lon": -6.26, "launched": 2007, "zone_count": 3, "notes": "Primary EU region"},
    {"name": "Europe (Frankfurt)", "provider": "AWS", "region_code": "eu-central-1", "lat": 50.11, "lon": 8.68, "launched": 2014, "zone_count": 3, "notes": "German data sovereignty"},
    {"name": "Asia Pacific (Tokyo)", "provider": "AWS", "region_code": "ap-northeast-1", "lat": 35.68, "lon": 139.77, "launched": 2011, "zone_count": 4, "notes": "AWS's largest APAC region"},
    {"name": "Asia Pacific (Singapore)", "provider": "AWS", "region_code": "ap-southeast-1", "lat": 1.35, "lon": 103.82, "launched": 2010, "zone_count": 3, "notes": "Southeast Asia hub"},
    {"name": "Asia Pacific (Sydney)", "provider": "AWS", "region_code": "ap-southeast-2", "lat": -33.87, "lon": 151.21, "launched": 2012, "zone_count": 3, "notes": "Oceania region"},
    {"name": "Middle East (Bahrain)", "provider": "AWS", "region_code": "me-south-1", "lat": 26.07, "lon": 50.55, "launched": 2019, "zone_count": 3, "notes": "First AWS MENA region"},
    {"name": "Africa (Cape Town)", "provider": "AWS", "region_code": "af-south-1", "lat": -33.93, "lon": 18.42, "launched": 2020, "zone_count": 3, "notes": "First AWS Africa region"},
    {"name": "South America (São Paulo)", "provider": "AWS", "region_code": "sa-east-1", "lat": -23.55, "lon": -46.63, "launched": 2011, "zone_count": 3, "notes": "Only AWS LatAm region"},
    # Azure Major Regions
    {"name": "East US", "provider": "Azure", "region_code": "eastus", "lat": 37.37, "lon": -79.15, "launched": 2010, "zone_count": 3, "notes": "Azure's largest region (Virginia)"},
    {"name": "West Europe", "provider": "Azure", "region_code": "westeurope", "lat": 52.37, "lon": 4.90, "launched": 2010, "zone_count": 3, "notes": "Netherlands, primary EU"},
    {"name": "North Europe", "provider": "Azure", "region_code": "northeurope", "lat": 53.35, "lon": -6.26, "launched": 2010, "zone_count": 3, "notes": "Ireland"},
    {"name": "Southeast Asia", "provider": "Azure", "region_code": "southeastasia", "lat": 1.28, "lon": 103.83, "launched": 2010, "zone_count": 3, "notes": "Singapore"},
    {"name": "Japan East", "provider": "Azure", "region_code": "japaneast", "lat": 35.68, "lon": 139.77, "launched": 2014, "zone_count": 3, "notes": "Tokyo, primary Japan"},
    {"name": "UAE North", "provider": "Azure", "region_code": "uaenorth", "lat": 25.27, "lon": 55.30, "launched": 2019, "zone_count": 3, "notes": "Dubai"},
    {"name": "South Africa North", "provider": "Azure", "region_code": "southafricanorth", "lat": -25.73, "lon": 28.22, "launched": 2019, "zone_count": 3, "notes": "Johannesburg"},
    {"name": "Brazil South", "provider": "Azure", "region_code": "brazilsouth", "lat": -23.55, "lon": -46.63, "launched": 2014, "zone_count": 3, "notes": "São Paulo"},
    # GCP Major Regions
    {"name": "US Central (Iowa)", "provider": "GCP", "region_code": "us-central1", "lat": 41.26, "lon": -95.86, "launched": 2012, "zone_count": 4, "notes": "GCP's largest region, Council Bluffs"},
    {"name": "US East (South Carolina)", "provider": "GCP", "region_code": "us-east1", "lat": 33.84, "lon": -81.16, "launched": 2015, "zone_count": 3, "notes": "Moncks Corner"},
    {"name": "Europe West (Belgium)", "provider": "GCP", "region_code": "europe-west1", "lat": 50.45, "lon": 3.82, "launched": 2015, "zone_count": 3, "notes": "St. Ghislain"},
    {"name": "Europe West (London)", "provider": "GCP", "region_code": "europe-west2", "lat": 51.51, "lon": -0.13, "launched": 2017, "zone_count": 3, "notes": "London"},
    {"name": "Asia East (Taiwan)", "provider": "GCP", "region_code": "asia-east1", "lat": 24.05, "lon": 120.69, "launched": 2014, "zone_count": 3, "notes": "Changhua County"},
    {"name": "Asia Northeast (Tokyo)", "provider": "GCP", "region_code": "asia-northeast1", "lat": 35.68, "lon": 139.77, "launched": 2016, "zone_count": 3, "notes": "Tokyo"},
    {"name": "Asia Southeast (Singapore)", "provider": "GCP", "region_code": "asia-southeast1", "lat": 1.35, "lon": 103.82, "launched": 2017, "zone_count": 3, "notes": "Jurong West"},
    {"name": "Australia Southeast (Melbourne)", "provider": "GCP", "region_code": "australia-southeast1", "lat": -37.81, "lon": 144.96, "launched": 2017, "zone_count": 3, "notes": "Melbourne"},
    {"name": "South America East (São Paulo)", "provider": "GCP", "region_code": "southamerica-east1", "lat": -23.55, "lon": -46.63, "launched": 2017, "zone_count": 3, "notes": "Osasco"},
    {"name": "Middle East (Tel Aviv)", "provider": "GCP", "region_code": "me-west1", "lat": 32.09, "lon": 34.77, "launched": 2022, "zone_count": 3, "notes": "Israel"},
]

# ---------------------------------------------------------------------------
# FINANCIAL_CENTERS — GFCI top 20 + key regional centers
# Fields: name, country, iso3, lat, lon, gfci_rank, gfci_rating,
#         specialization, exchange, notes
# ---------------------------------------------------------------------------

FINANCIAL_CENTERS: list[dict] = [
    {"name": "New York", "country": "USA", "iso3": "USA", "lat": 40.71, "lon": -74.01, "gfci_rank": 1, "gfci_rating": 760, "specialization": "equities, derivatives, banking", "exchange": "NYSE/NASDAQ", "notes": "World's largest financial center, $25T+ equity market cap"},
    {"name": "London", "country": "UK", "iso3": "GBR", "lat": 51.51, "lon": -0.13, "gfci_rank": 2, "gfci_rating": 744, "specialization": "forex, insurance, banking", "exchange": "LSE", "notes": "Largest FX trading hub (~38% global volume)"},
    {"name": "Singapore", "country": "Singapore", "iso3": "SGP", "lat": 1.28, "lon": 103.85, "gfci_rank": 3, "gfci_rating": 742, "specialization": "wealth management, FX, commodities", "exchange": "SGX", "notes": "Asia-Pacific wealth management hub"},
    {"name": "Hong Kong", "country": "China (SAR)", "iso3": "HKG", "lat": 22.32, "lon": 114.17, "gfci_rank": 4, "gfci_rating": 741, "specialization": "IPOs, banking, yuan offshore", "exchange": "HKEX", "notes": "Gateway to mainland China capital markets"},
    {"name": "San Francisco", "country": "USA", "iso3": "USA", "lat": 37.77, "lon": -122.42, "gfci_rank": 5, "gfci_rating": 738, "specialization": "venture capital, fintech", "exchange": "—", "notes": "Global VC capital, tech finance hub"},
    {"name": "Shanghai", "country": "China", "iso3": "CHN", "lat": 31.23, "lon": 121.47, "gfci_rank": 6, "gfci_rating": 735, "specialization": "equities, bonds, commodities", "exchange": "SSE", "notes": "Largest exchange in mainland China"},
    {"name": "Los Angeles", "country": "USA", "iso3": "USA", "lat": 34.05, "lon": -118.24, "gfci_rank": 7, "gfci_rating": 733, "specialization": "entertainment finance, VC", "exchange": "—", "notes": "Growing fintech ecosystem"},
    {"name": "Tokyo", "country": "Japan", "iso3": "JPN", "lat": 35.68, "lon": 139.77, "gfci_rank": 8, "gfci_rating": 730, "specialization": "equities, bonds, banking", "exchange": "JPX", "notes": "Third-largest equity market globally"},
    {"name": "Seoul", "country": "South Korea", "iso3": "KOR", "lat": 37.57, "lon": 126.98, "gfci_rank": 9, "gfci_rating": 728, "specialization": "equities, crypto, semiconductors", "exchange": "KRX", "notes": "World's busiest crypto trading market"},
    {"name": "Shenzhen", "country": "China", "iso3": "CHN", "lat": 22.54, "lon": 114.06, "gfci_rank": 10, "gfci_rating": 726, "specialization": "tech equities, IPOs", "exchange": "SZSE", "notes": "ChiNext board, tech-heavy market"},
    {"name": "Chicago", "country": "USA", "iso3": "USA", "lat": 41.88, "lon": -87.63, "gfci_rank": 11, "gfci_rating": 724, "specialization": "derivatives, commodities, futures", "exchange": "CME/CBOT", "notes": "World's largest derivatives exchange"},
    {"name": "Sydney", "country": "Australia", "iso3": "AUS", "lat": -33.87, "lon": 151.21, "gfci_rank": 12, "gfci_rating": 722, "specialization": "mining, superannuation", "exchange": "ASX", "notes": "Largest exchange in Southern Hemisphere"},
    {"name": "Zurich", "country": "Switzerland", "iso3": "CHE", "lat": 47.37, "lon": 8.54, "gfci_rank": 13, "gfci_rating": 720, "specialization": "private banking, insurance", "exchange": "SIX", "notes": "Global private banking capital"},
    {"name": "Frankfurt", "country": "Germany", "iso3": "DEU", "lat": 50.11, "lon": 8.68, "gfci_rank": 14, "gfci_rating": 718, "specialization": "banking, ECB HQ", "exchange": "Xetra/FWB", "notes": "ECB headquarters, eurozone financial hub"},
    {"name": "Dubai", "country": "UAE", "iso3": "ARE", "lat": 25.20, "lon": 55.27, "gfci_rank": 15, "gfci_rating": 716, "specialization": "Islamic finance, wealth management", "exchange": "DFM/DIFC", "notes": "Bridge between East and West, DIFC free zone"},
    {"name": "Paris", "country": "France", "iso3": "FRA", "lat": 48.86, "lon": 2.35, "gfci_rank": 16, "gfci_rating": 714, "specialization": "insurance, asset management", "exchange": "Euronext Paris", "notes": "Post-Brexit gains in euro clearing"},
    {"name": "Mumbai", "country": "India", "iso3": "IND", "lat": 19.08, "lon": 72.88, "gfci_rank": 17, "gfci_rating": 712, "specialization": "equities, derivatives, banking", "exchange": "BSE/NSE", "notes": "NSE is world's largest derivatives exchange by volume"},
    {"name": "Toronto", "country": "Canada", "iso3": "CAN", "lat": 43.65, "lon": -79.38, "gfci_rank": 18, "gfci_rating": 710, "specialization": "mining, banking, cannabis", "exchange": "TSX", "notes": "World's #1 mining finance exchange"},
    {"name": "Abu Dhabi", "country": "UAE", "iso3": "ARE", "lat": 24.45, "lon": 54.65, "gfci_rank": 19, "gfci_rating": 708, "specialization": "sovereign wealth, energy finance", "exchange": "ADX/ADGM", "notes": "ADIA (world's 3rd largest SWF), energy focus"},
    {"name": "Geneva", "country": "Switzerland", "iso3": "CHE", "lat": 46.20, "lon": 6.14, "gfci_rank": 20, "gfci_rating": 706, "specialization": "private banking, commodity trading", "exchange": "—", "notes": "Global commodity trading capital, wealth management"},
]
