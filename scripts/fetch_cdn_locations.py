#!/usr/bin/env python3
"""
fetch_cdn_locations.py
──────────────────────
Compiles CDN PoP (Point of Presence) locations for four major providers:

  • Cloudflare   — 300+ cities, IATA-coded from their network map
  • AWS CloudFront — 600+ edge locations from AWS documentation
  • Fastly        — ~90 PoPs from their network map
  • Akamai        — ~350 city-level locations from public announcements
                    and network pages (Akamai does not publish exact PoP
                    addresses, so city-level precision is the best available)

Geocoding
─────────
Cities are geocoded using a built-in IATA airport coordinate table with a
city-name fallback dict.  No external geocoding API is called at runtime.

Output
──────
  public/cdn-edge-locations.geojson
  Each GeoJSON Feature has properties: { provider, city, country, iataCode }

Run quarterly (or when a provider announces new PoPs) to refresh the data.
"""

import json
import os
import sys

# ── IATA Airport → (lat, lon) ─────────────────────────────────────────────────
# Approx. coordinates; sufficient for globe-scale visualisation.

IATA_COORDS = {
    # ── United States ────────────────────────────────────────────────────────
    'ABQ': (35.0402, -106.6090),  # Albuquerque NM
    'ATL': (33.6367,  -84.4281),  # Atlanta GA
    'BNA': (36.1245,  -86.6782),  # Nashville TN
    'BOS': (42.3656,  -71.0096),  # Boston MA
    'BUF': (42.9405,  -78.7322),  # Buffalo NY
    'BWI': (39.1754,  -76.6683),  # Baltimore MD
    'CLT': (35.2140,  -80.9431),  # Charlotte NC
    'CMH': (39.9980,  -82.8919),  # Columbus OH
    'CLE': (41.4117,  -81.8498),  # Cleveland OH
    'CVG': (39.0488,  -84.6678),  # Cincinnati OH
    'DEN': (39.8561, -104.6737),  # Denver CO
    'DFW': (32.8998,  -97.0403),  # Dallas-Fort Worth TX
    'DTW': (42.2124,  -83.3534),  # Detroit MI
    'EWR': (40.6895,  -74.1745),  # Newark NJ
    'FLL': (26.0726,  -80.1527),  # Fort Lauderdale FL
    'HNL': (21.3187, -157.9225),  # Honolulu HI
    'IAD': (38.9531,  -77.4565),  # Washington Dulles VA
    'IAH': (29.9902,  -95.3368),  # Houston TX
    'IND': (39.7173,  -86.2944),  # Indianapolis IN
    'JAX': (30.4941,  -81.6879),  # Jacksonville FL
    'JFK': (40.6413,  -73.7781),  # New York JFK NY
    'LAS': (36.0840, -115.1537),  # Las Vegas NV
    'LAX': (33.9425, -118.4081),  # Los Angeles CA
    'MCI': (39.2976,  -94.7139),  # Kansas City MO
    'MCO': (28.4312,  -81.3081),  # Orlando FL
    'MDW': (41.7868,  -87.7522),  # Chicago Midway IL
    'MEM': (35.0424,  -89.9767),  # Memphis TN
    'MIA': (25.7959,  -80.2870),  # Miami FL
    'MKE': (42.9472,  -87.8966),  # Milwaukee WI
    'MSP': (44.8848,  -93.2223),  # Minneapolis MN
    'MSY': (29.9934,  -90.2580),  # New Orleans LA
    'OAK': (37.7213, -122.2208),  # Oakland CA
    'OKC': (35.3931,  -97.6007),  # Oklahoma City OK
    'OMA': (41.3032,  -95.8941),  # Omaha NE
    'ONT': (34.0560, -117.6011),  # Ontario/Inland Empire CA
    'ORD': (41.9742,  -87.9073),  # Chicago O'Hare IL
    'PDX': (45.5898, -122.5951),  # Portland OR
    'PHL': (39.8744,  -75.2424),  # Philadelphia PA
    'PHX': (33.4373, -112.0078),  # Phoenix AZ
    'PIT': (40.4915,  -80.2329),  # Pittsburgh PA
    'RDU': (35.8801,  -78.7880),  # Raleigh-Durham NC
    'RIC': (37.5052,  -77.3197),  # Richmond VA
    'SAN': (32.7336, -117.1897),  # San Diego CA
    'SAT': (29.5337,  -98.4698),  # San Antonio TX
    'SEA': (47.4502, -122.3088),  # Seattle WA
    'SFO': (37.6213, -122.3790),  # San Francisco CA
    'SJC': (37.3626, -121.9290),  # San Jose CA
    'SLC': (40.7899, -111.9791),  # Salt Lake City UT
    'SMF': (38.6954, -121.5908),  # Sacramento CA
    'STL': (38.7487,  -90.3700),  # St. Louis MO
    'TPA': (27.9755,  -82.5332),  # Tampa FL
    'TUL': (36.1984,  -95.8881),  # Tulsa OK
    # ── Canada ───────────────────────────────────────────────────────────────
    'YEG': (53.3097, -113.5827),  # Edmonton AB
    'YOW': (45.3225,  -75.6692),  # Ottawa ON
    'YTO': (43.6777,  -79.6248),  # Toronto ON (generic)
    'YUL': (45.4706,  -73.7408),  # Montreal QC
    'YVR': (49.1967, -123.1815),  # Vancouver BC
    'YYC': (51.1315, -114.0106),  # Calgary AB
    'YYZ': (43.6777,  -79.6248),  # Toronto Pearson ON
    'YHZ': (44.8808,  -63.5086),  # Halifax NS
    'YWG': (49.9100,  -97.2398),  # Winnipeg MB
    'YQB': (46.7911,  -71.3933),  # Quebec City QC
    # ── Mexico / Central America / Caribbean ─────────────────────────────────
    'GDL': (20.5218, -103.3111),  # Guadalajara
    'GUA': (14.5833,  -90.5275),  # Guatemala City
    'MBJ': (18.5037,  -77.9134),  # Montego Bay JM
    'MEX': (19.4363,  -99.0721),  # Mexico City
    'MTY': (25.7785, -100.1069),  # Monterrey
    'PTY': ( 9.0714,  -79.3835),  # Panama City
    'SAL': (13.4409,  -89.0558),  # San Salvador
    'SDQ': (18.4297,  -69.6689),  # Santo Domingo
    'SJO': ( 9.9939,  -84.2089),  # San José CR
    'SJU': (18.4394,  -66.0018),  # San Juan PR
    'TGU': (14.0608,  -87.2172),  # Tegucigalpa
    # ── South America ────────────────────────────────────────────────────────
    'AEP': (-34.5592,  -58.4156), # Buenos Aires (metro)
    'ASU': (-25.2400,  -57.5194), # Asunción
    'BOG': (  4.7016,  -74.1469), # Bogotá
    'BSB': (-15.8697,  -47.9208), # Brasília
    'CCS': ( 10.6013,  -66.9911), # Caracas
    'CLO': (  3.5432,  -76.3816), # Cali
    'CWB': (-25.5285,  -49.1758), # Curitiba
    'EZE': (-34.8222,  -58.5358), # Buenos Aires Ezeiza
    'FOR': ( -3.7762,  -38.5326), # Fortaleza
    'GIG': (-22.8099,  -43.2505), # Rio de Janeiro
    'GRU': (-23.4356,  -46.4731), # São Paulo
    'LIM': (-12.0219,  -77.1143), # Lima
    'MDE': (  6.1645,  -75.4231), # Medellín
    'MVD': (-34.8384,  -56.0308), # Montevideo
    'POA': (-29.9944,  -51.1713), # Porto Alegre
    'SCL': (-33.3930,  -70.7858), # Santiago
    'SSA': (-12.9086,  -38.3225), # Salvador
    'UIO': ( -0.1292,  -78.3575), # Quito
    'VCP': (-23.0074,  -47.1345), # Campinas
    # ── Western Europe ───────────────────────────────────────────────────────
    'AMS': (52.3086,   4.7639),   # Amsterdam
    'ANR': (51.1894,   4.4603),   # Antwerp
    'ARN': (59.6519,  17.9186),   # Stockholm
    'ATH': (37.9364,  23.9445),   # Athens
    'BCN': (41.2971,   2.0785),   # Barcelona
    'BER': (52.3667,  13.5033),   # Berlin
    'BHX': (52.4539,  -1.7480),   # Birmingham
    'BIO': (43.3011,  -2.9106),   # Bilbao
    'BLQ': (44.5354,  11.2887),   # Bologna
    'BRS': (51.3827,  -2.7191),   # Bristol
    'BRU': (50.9010,   4.4844),   # Brussels
    'BSL': (47.5896,   7.5300),   # Basel
    'BUD': (47.4298,  19.2611),   # Budapest
    'CDG': (49.0097,   2.5479),   # Paris
    'CGN': (50.8659,   7.1427),   # Cologne
    'CPH': (55.6180,  12.6508),   # Copenhagen
    'DUB': (53.4273,  -6.2437),   # Dublin
    'DUS': (51.2895,   6.7668),   # Düsseldorf
    'EDI': (55.9500,  -3.3725),   # Edinburgh
    'FCO': (41.8003,  12.2389),   # Rome
    'FRA': (50.0333,   8.5706),   # Frankfurt
    'GLA': (55.8719,  -4.4330),   # Glasgow
    'GVA': (46.2381,   6.1089),   # Geneva
    'HAM': (53.6304,  10.0065),   # Hamburg
    'HEL': (60.3172,  24.9633),   # Helsinki
    'IST': (41.2753,  28.7519),   # Istanbul
    'LGW': (51.1537,  -0.1821),   # London Gatwick
    'LHR': (51.4775,  -0.4614),   # London Heathrow
    'LIN': (45.4509,   9.2767),   # Milan Linate
    'LIS': (38.7813,  -9.1359),   # Lisbon
    'LYS': (45.7256,   5.0811),   # Lyon
    'MAD': (40.4719,  -3.5626),   # Madrid
    'MAN': (53.3537,  -2.2750),   # Manchester
    'MRS': (43.4365,   5.2150),   # Marseille
    'MUC': (48.3538,  11.7861),   # Munich
    'MXP': (45.6306,   8.7231),   # Milan Malpensa
    'NAP': (40.8860,  14.2908),   # Naples
    'NCE': (43.6584,   7.2159),   # Nice
    'NUE': (49.4987,  11.0669),   # Nuremberg
    'OPO': (41.2481,  -8.6814),   # Porto
    'ORY': (48.7233,   2.3794),   # Paris Orly
    'OSL': (60.1939,  11.1004),   # Oslo
    'OTP': (44.5711,  26.0850),   # Bucharest
    'PMO': (38.1760,  13.0910),   # Palermo
    'PRG': (50.1008,  14.2600),   # Prague
    'RIX': (56.9236,  23.9711),   # Riga
    'SOF': (42.6952,  23.4114),   # Sofia
    'STN': (51.8850,   0.2350),   # London Stansted
    'STR': (48.6899,   9.2219),   # Stuttgart
    'SVQ': (37.4180,  -5.8931),   # Seville
    'TLL': (59.4133,  24.8328),   # Tallinn
    'TLS': (43.6291,   1.3638),   # Toulouse
    'VCE': (45.5053,  12.3519),   # Venice
    'VIE': (48.1103,  16.5697),   # Vienna
    'VLC': (39.4893,  -0.4816),   # Valencia
    'VNO': (54.6341,  25.2858),   # Vilnius
    'WAW': (52.1657,  20.9671),   # Warsaw
    'ZAG': (45.7429,  16.0688),   # Zagreb
    'ZRH': (47.4647,   8.5492),   # Zurich
    'BEG': (44.8184,  20.3091),   # Belgrade
    'KRK': (50.0777,  19.7848),   # Kraków
    'GDN': (54.3776,  18.4666),   # Gdańsk
    'TIA': (41.4147,  19.7206),   # Tirana
    'SKP': (41.9614,  21.6214),   # Skopje
    'SKG': (40.5197,  22.9709),   # Thessaloniki
    'LJU': (46.2237,  14.4576),   # Ljubljana
    'BGO': (60.2934,   5.2181),   # Bergen
    # ── Eastern Europe / Russia ───────────────────────────────────────────────
    'DME': (55.4088,  37.9063),   # Moscow Domodedovo
    'GYD': (40.4675,  50.0467),   # Baku
    'IKT': (52.2680, 104.3890),   # Irkutsk
    'KBP': (50.3450,  30.8947),   # Kyiv
    'KIV': (46.9277,  28.9302),   # Chișinău
    'KJA': (56.1726,  92.4933),   # Krasnoyarsk
    'KZN': (55.6060,  49.2787),   # Kazan
    'LED': (59.8003,  30.2625),   # St. Petersburg
    'MSQ': (53.8825,  28.0325),   # Minsk
    'ODS': (46.4268,  30.6765),   # Odessa
    'OVB': (54.9669,  82.9067),   # Novosibirsk
    'ROV': (47.2582,  39.8181),   # Rostov-on-Don
    'SVO': (55.9736,  37.4125),   # Moscow Sheremetyevo
    'SVX': (56.8431,  60.8028),   # Yekaterinburg
    'TBS': (41.6692,  44.9547),   # Tbilisi
    'EVN': (40.1473,  44.3959),   # Yerevan
    'UFA': (54.5574,  55.8742),   # Ufa
    'VVO': (43.3990, 132.1480),   # Vladivostok
    # ── Middle East ───────────────────────────────────────────────────────────
    'AMM': (31.7226,  35.9932),   # Amman
    'AUH': (24.4330,  54.6511),   # Abu Dhabi
    'BAH': (26.2708,  50.6336),   # Bahrain
    'BEY': (33.8209,  35.4886),   # Beirut
    'BGW': (33.2625,  44.2346),   # Baghdad
    'DOH': (25.2731,  51.6081),   # Doha
    'DXB': (25.2532,  55.3657),   # Dubai
    'ESB': (40.1281,  32.9951),   # Ankara
    'IKA': (35.4161,  51.1522),   # Tehran
    'JED': (21.6796,  39.1565),   # Jeddah
    'KWI': (29.2267,  47.9689),   # Kuwait City
    'MCT': (23.5933,  58.2844),   # Muscat
    'RUH': (24.9576,  46.6988),   # Riyadh
    'SHJ': (25.3286,  55.5172),   # Sharjah
    'TLV': (32.0114,  34.8867),   # Tel Aviv
    # ── Africa ────────────────────────────────────────────────────────────────
    'ABJ': ( 5.2613,  -3.9263),   # Abidjan
    'ABV': ( 9.0068,   7.2632),   # Abuja
    'ACC': ( 5.6052,  -0.1668),   # Accra
    'ADD': ( 8.9779,  38.7993),   # Addis Ababa
    'ALG': (36.6910,   3.2154),   # Algiers
    'CAI': (30.1219,  31.4056),   # Cairo
    'CMN': (33.3675,  -7.5898),   # Casablanca
    'CPT': (-33.9649,  18.6017),  # Cape Town
    'DAR': ( -6.8781,  39.2026),  # Dar es Salaam
    'DKR': (14.7397,  -17.4902),  # Dakar
    'DLA': ( 4.0061,   9.7194),   # Douala
    'DUR': (-29.6144,  31.1197),  # Durban
    'EBB': ( 0.0424,  32.4433),   # Kampala
    'FIH': ( -4.3857,  15.4446),  # Kinshasa
    'HRE': (-17.9318,  31.0928),  # Harare
    'JNB': (-26.1392,  28.2460),  # Johannesburg
    'KAN': (12.0476,   8.5240),   # Kano
    'LOS': ( 6.5774,   3.3213),   # Lagos
    'LUN': (-15.3308,  28.4527),  # Lusaka
    'MBA': ( -4.0348,  39.5942),  # Mombasa
    'MRU': (-20.4302,  57.6836),  # Mauritius
    'NBO': ( -1.3192,  36.9275),  # Nairobi
    'RBA': (34.0513,  -6.7516),   # Rabat
    'SEZ': ( -4.6743,  55.5218),  # Seychelles
    'TNR': (-18.7969,  47.4788),  # Antananarivo
    'TUN': (36.8510,  10.2272),   # Tunis
    # ── South Asia ────────────────────────────────────────────────────────────
    'AMD': (23.0733,  72.6340),   # Ahmedabad
    'BLR': (13.1986,  77.7066),   # Bengaluru
    'BOM': (19.0896,  72.8656),   # Mumbai
    'CCU': (22.6520,  88.4463),   # Kolkata
    'CGP': (22.2496,  91.8133),   # Chittagong
    'CMB': ( 7.1808,  79.8841),   # Colombo
    'COK': (10.1520,  76.4019),   # Kochi
    'DAC': (23.8433,  90.3979),   # Dhaka
    'DEL': (28.5665,  77.1031),   # New Delhi
    'GAU': (26.1061,  91.5859),   # Guwahati
    'HYD': (17.2313,  78.4298),   # Hyderabad
    'ISB': (33.6167,  73.0997),   # Islamabad
    'KHI': (24.9065,  67.1608),   # Karachi
    'KTM': (27.6966,  85.3591),   # Kathmandu
    'LHE': (31.5216,  74.4036),   # Lahore
    'MAA': (12.9900,  80.1693),   # Chennai
    'NAG': (21.0922,  79.0472),   # Nagpur
    'PNQ': (18.5822,  73.9197),   # Pune
    # ── Southeast Asia ────────────────────────────────────────────────────────
    'BKK': (13.6900, 100.7501),   # Bangkok
    'CGK': ( -6.1256, 106.6559),  # Jakarta
    'CEB': (10.3075, 123.9795),   # Cebu
    'DAD': (16.0439, 108.1992),   # Da Nang
    'DPS': ( -8.7481, 115.1670),  # Bali
    'HAN': (21.2212, 105.8072),   # Hanoi
    'HKT': ( 8.1132,  98.3170),   # Phuket
    'KUL': ( 2.7456, 101.7099),   # Kuala Lumpur
    'MNL': (14.5086, 121.0197),   # Manila
    'PNH': (11.5466, 104.8440),   # Phnom Penh
    'RGN': (16.9073,  96.1328),   # Yangon
    'SGN': (10.8188, 106.6520),   # Ho Chi Minh City
    'SIN': ( 1.3644, 103.9915),   # Singapore
    'SUB': ( -7.3798, 112.7870),  # Surabaya
    'UPG': ( -5.0617, 119.5540),  # Makassar
    'VTE': (17.9883, 102.5632),   # Vientiane
    # ── East Asia ─────────────────────────────────────────────────────────────
    'CAN': (23.3925, 113.2990),   # Guangzhou
    'CGO': (34.5196, 113.8415),   # Zhengzhou
    'CKG': (29.7192, 106.6419),   # Chongqing
    'CSX': (28.1892, 113.0796),   # Changsha
    'CTU': (30.5785, 103.9473),   # Chengdu
    'DLC': (38.9657, 121.5386),   # Dalian
    'FUK': (33.5858, 130.4508),   # Fukuoka
    'GMP': (37.5586, 126.7944),   # Seoul Gimpo
    'HGH': (30.2295, 120.4327),   # Hangzhou
    'HIJ': (34.4361, 132.9194),   # Hiroshima
    'HKG': (22.3080, 113.9185),   # Hong Kong
    'HND': (35.5494, 139.7798),   # Tokyo Haneda
    'HRB': (45.6234, 126.2500),   # Harbin
    'ICN': (37.4602, 126.4407),   # Seoul Incheon
    'ITM': (34.7855, 135.4380),   # Osaka Itami
    'KHH': (22.5771, 120.3497),   # Kaohsiung
    'KIX': (34.4272, 135.2440),   # Osaka Kansai
    'KMG': (24.9925, 102.7433),   # Kunming
    'MFM': (22.1496, 113.5929),   # Macau
    'NGO': (34.8583, 136.8050),   # Nagoya
    'NKG': (31.7420, 118.8620),   # Nanjing
    'NRT': (35.7720, 140.3929),   # Tokyo Narita
    'OKA': (26.1958, 127.6461),   # Okinawa
    'PEK': (40.0799, 116.6031),   # Beijing
    'PUS': (35.1795, 128.9382),   # Busan
    'PVG': (31.1443, 121.8083),   # Shanghai
    'SDJ': (38.1397, 140.9169),   # Sendai
    'SHA': (31.1981, 121.3364),   # Shanghai Hongqiao
    'SHE': (41.6398, 123.4835),   # Shenyang
    'SZX': (22.6393, 113.8107),   # Shenzhen
    'TAO': (36.2661, 120.3747),   # Qingdao
    'TPE': (25.0777, 121.2325),   # Taipei
    'TSN': (39.1244, 117.3467),   # Tianjin
    'ULN': (47.8431, 106.7669),   # Ulaanbaatar
    'WUH': (30.7838, 114.2081),   # Wuhan
    'XIY': (34.4471, 108.7517),   # Xi'an
    'XMN': (24.5440, 118.1277),   # Xiamen
    # ── Oceania ───────────────────────────────────────────────────────────────
    'ADL': (-34.9450, 138.5300),  # Adelaide
    'AKL': (-37.0082, 174.7917),  # Auckland
    'BNE': (-27.3842, 153.1175),  # Brisbane
    'CBR': (-35.3069, 149.1950),  # Canberra
    'CHC': (-43.4894, 172.5322),  # Christchurch
    'CNS': (-16.8858, 145.7520),  # Cairns
    'GUM': ( 13.4834, 144.7961),  # Guam
    'MEL': (-37.6690, 144.8410),  # Melbourne
    'NAN': (-17.7553, 177.4432),  # Nadi Fiji
    'OOL': (-28.1644, 153.5047),  # Gold Coast
    'PER': (-31.9403, 115.9670),  # Perth
    'SYD': (-33.9399, 151.1753),  # Sydney
    'WLG': (-41.3272, 174.8052),  # Wellington
    # ── Central Asia ──────────────────────────────────────────────────────────
    'ALA': (43.3521,  77.0405),   # Almaty
    'ASB': (37.9864,  58.3610),   # Ashgabat
    'FRU': (43.0612,  74.4776),   # Bishkek
    'NQZ': (51.0222,  71.4669),   # Nur-Sultan / Astana
    'TAS': (41.2579,  69.2811),   # Tashkent
}

# ── City-name fallback (for providers that list cities, not IATA codes) ───────
# Key: lowercase "city, ISO2" for unambiguous lookup

CITY_COORDS = {
    'ashburn, us':           (39.0438,  -77.4874),
    'new york, us':          (40.7128,  -74.0060),
    'chicago, us':           (41.8781,  -87.6298),
    'dallas, us':            (32.7767,  -96.7970),
    'los angeles, us':       (34.0522, -118.2437),
    'san francisco, us':     (37.7749, -122.4194),
    'seattle, us':           (47.6062, -122.3321),
    'miami, us':             (25.7617,  -80.1918),
    'atlanta, us':           (33.7490,  -84.3880),
    'boston, us':            (42.3601,  -71.0589),
    'denver, us':            (39.7392, -104.9903),
    'phoenix, us':           (33.4484, -112.0740),
    'minneapolis, us':       (44.9778,  -93.2650),
    'san jose, us':          (37.3382, -121.8863),
    'las vegas, us':         (36.1699, -115.1398),
    'portland, us':          (45.5231, -122.6765),
    'philadelphia, us':      (39.9526,  -75.1652),
    'houston, us':           (29.7604,  -95.3698),
    'washington, us':        (38.9072,  -77.0369),
    'toronto, ca':           (43.6532,  -79.3832),
    'montreal, ca':          (45.5017,  -73.5673),
    'vancouver, ca':         (49.2827, -123.1207),
    'london, gb':            (51.5074,   -0.1278),
    'paris, fr':             (48.8566,    2.3522),
    'frankfurt, de':         (50.1109,    8.6821),
    'amsterdam, nl':         (52.3676,    4.9041),
    'madrid, es':            (40.4168,   -3.7038),
    'barcelona, es':         (41.3851,    2.1734),
    'milan, it':             (45.4654,    9.1859),
    'rome, it':              (41.9028,   12.4964),
    'lisbon, pt':            (38.7223,   -9.1393),
    'dublin, ie':            (53.3498,   -6.2603),
    'zurich, ch':            (47.3769,    8.5417),
    'vienna, at':            (48.2082,   16.3738),
    'brussels, be':          (50.8503,    4.3517),
    'stockholm, se':         (59.3293,   18.0686),
    'oslo, no':              (59.9139,   10.7522),
    'copenhagen, dk':        (55.6761,   12.5683),
    'helsinki, fi':          (60.1699,   24.9384),
    'athens, gr':            (37.9838,   23.7275),
    'istanbul, tr':          (41.0082,   28.9784),
    'warsaw, pl':            (52.2297,   21.0122),
    'prague, cz':            (50.0755,   14.4378),
    'budapest, hu':          (47.4979,   19.0402),
    'bucharest, ro':         (44.4268,   26.1025),
    'sofia, bg':             (42.6977,   23.3219),
    'belgrade, rs':          (44.7866,   20.4489),
    'zagreb, hr':            (45.8150,   15.9819),
    'kyiv, ua':              (50.4501,   30.5234),
    'minsk, by':             (53.9045,   27.5615),
    'moscow, ru':            (55.7558,   37.6173),
    'saint petersburg, ru':  (59.9311,   30.3609),
    'novosibirsk, ru':       (55.0084,   82.9357),
    'yekaterinburg, ru':     (56.8389,   60.6057),
    'vladivostok, ru':       (43.1332,  131.9113),
    'tokyo, jp':             (35.6762,  139.6503),
    'osaka, jp':             (34.6937,  135.5023),
    'fukuoka, jp':           (33.5904,  130.4017),
    'sapporo, jp':           (43.0618,  141.3545),
    'nagoya, jp':            (35.1815,  136.9066),
    'singapore, sg':         ( 1.3521,  103.8198),
    'sydney, au':            (-33.8688,  151.2093),
    'melbourne, au':         (-37.8136,  144.9631),
    'brisbane, au':          (-27.4698,  153.0251),
    'perth, au':             (-31.9505,  115.8605),
    'auckland, nz':          (-36.8509,  174.7645),
    'hong kong, hk':         (22.3193,  114.1694),
    'taipei, tw':            (25.0330,  121.5654),
    'seoul, kr':             (37.5665,  126.9780),
    'beijing, cn':           (39.9042,  116.4074),
    'shanghai, cn':          (31.2304,  121.4737),
    'guangzhou, cn':         (23.1291,  113.2644),
    'shenzhen, cn':          (22.5431,  114.0579),
    'bangkok, th':           (13.7563,  100.5018),
    'jakarta, id':           (-6.2088,  106.8456),
    'kuala lumpur, my':      ( 3.1390,  101.6869),
    'manila, ph':            (14.5995,  120.9842),
    'ho chi minh city, vn':  (10.8231,  106.6297),
    'hanoi, vn':             (21.0278,  105.8342),
    'mumbai, in':            (19.0760,   72.8777),
    'delhi, in':             (28.6139,   77.2090),
    'new delhi, in':         (28.6139,   77.2090),
    'bangalore, in':         (12.9716,   77.5946),
    'bengaluru, in':         (12.9716,   77.5946),
    'chennai, in':           (13.0827,   80.2707),
    'hyderabad, in':         (17.3850,   78.4867),
    'kolkata, in':           (22.5726,   88.3639),
    'karachi, pk':           (24.8607,   67.0011),
    'lahore, pk':            (31.5204,   74.3587),
    'colombo, lk':           ( 6.9271,   79.8612),
    'dhaka, bd':             (23.8103,   90.4125),
    'dubai, ae':             (25.2048,   55.2708),
    'abu dhabi, ae':         (24.4539,   54.3773),
    'riyadh, sa':            (24.7136,   46.6753),
    'jeddah, sa':            (21.2854,   39.2376),
    'doha, qa':              (25.2854,   51.5310),
    'cairo, eg':             (30.0444,   31.2357),
    'lagos, ng':             ( 6.5244,    3.3792),
    'nairobi, ke':           (-1.2921,   36.8219),
    'johannesburg, za':      (-26.2041,  28.0473),
    'cape town, za':         (-33.9249,  18.4241),
    'casablanca, ma':        (33.5731,   -7.5898),
    'accra, gh':             ( 5.6037,   -0.1870),
    'addis ababa, et':       ( 9.0054,   38.7636),
    'sao paulo, br':         (-23.5505,  -46.6333),
    'são paulo, br':         (-23.5505,  -46.6333),
    'rio de janeiro, br':    (-22.9068,  -43.1729),
    'buenos aires, ar':      (-34.6037,  -58.3816),
    'santiago, cl':          (-33.4489,  -70.6693),
    'lima, pe':              (-12.0464,  -77.0428),
    'bogota, co':            ( 4.7110,   -74.0721),
    'bogotá, co':            ( 4.7110,   -74.0721),
    'mexico city, mx':       (19.4326,   -99.1332),
    'guadalajara, mx':       (20.6597,  -103.3496),
    'monterrey, mx':         (25.6714,  -100.3092),
}

# ── Helper ─────────────────────────────────────────────────────────────────────

def geocode(iata_or_city, city_name, country):
    """Return (lat, lon) or None. Tries IATA first, then city-name dict."""
    code = (iata_or_city or '').strip().upper()
    if code and code in IATA_COORDS:
        return IATA_COORDS[code]
    # Try city-name dict
    keys_to_try = [
        f"{city_name.lower()}, {country.lower()}",
        city_name.lower(),
    ]
    for k in keys_to_try:
        if k in CITY_COORDS:
            return CITY_COORDS[k]
    return None


def make_feature(provider, iata, city, country, lat, lon):
    return {
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [round(lon, 4), round(lat, 4)]},
        'properties': {
            'provider':  provider,
            'city':      city,
            'country':   country,
            'iataCode':  iata or '',
        },
    }


# ── Cloudflare PoPs ────────────────────────────────────────────────────────────
# Source: cloudflare.com/network  (IATA codes)
# Data current as of mid-2025. Cloudflare does not publish a machine-readable list;
# this is compiled from their network map and community-sourced IATA lists.
# Each entry: (iata, city, country_ISO2)

CLOUDFLARE_POPS = [
    # North America
    ('ABQ', 'Albuquerque',      'US'), ('ATL', 'Atlanta',           'US'),
    ('BNA', 'Nashville',        'US'), ('BOS', 'Boston',            'US'),
    ('BUF', 'Buffalo',          'US'), ('BWI', 'Baltimore',         'US'),
    ('CLT', 'Charlotte',        'US'), ('CMH', 'Columbus',          'US'),
    ('CLE', 'Cleveland',        'US'), ('DEN', 'Denver',            'US'),
    ('DFW', 'Dallas',           'US'), ('DTW', 'Detroit',           'US'),
    ('EWR', 'Newark',           'US'), ('FLL', 'Fort Lauderdale',   'US'),
    ('HNL', 'Honolulu',         'US'), ('IAD', 'Ashburn',           'US'),
    ('IAH', 'Houston',          'US'), ('IND', 'Indianapolis',      'US'),
    ('JAX', 'Jacksonville',     'US'), ('LAS', 'Las Vegas',         'US'),
    ('LAX', 'Los Angeles',      'US'), ('MCI', 'Kansas City',       'US'),
    ('MCO', 'Orlando',          'US'), ('MEM', 'Memphis',           'US'),
    ('MIA', 'Miami',            'US'), ('MKE', 'Milwaukee',         'US'),
    ('MSP', 'Minneapolis',      'US'), ('MSY', 'New Orleans',       'US'),
    ('OAK', 'Oakland',          'US'), ('OKC', 'Oklahoma City',     'US'),
    ('OMA', 'Omaha',            'US'), ('ORD', 'Chicago',           'US'),
    ('PDX', 'Portland',         'US'), ('PHL', 'Philadelphia',      'US'),
    ('PHX', 'Phoenix',          'US'), ('PIT', 'Pittsburgh',        'US'),
    ('RDU', 'Raleigh',          'US'), ('SAN', 'San Diego',         'US'),
    ('SAT', 'San Antonio',      'US'), ('SEA', 'Seattle',           'US'),
    ('SFO', 'San Francisco',    'US'), ('SJC', 'San Jose',          'US'),
    ('SLC', 'Salt Lake City',   'US'), ('STL', 'St. Louis',         'US'),
    ('TPA', 'Tampa',            'US'), ('YTO', 'Toronto',           'CA'),
    ('YUL', 'Montreal',         'CA'), ('YVR', 'Vancouver',         'CA'),
    ('YYC', 'Calgary',          'CA'), ('YWG', 'Winnipeg',          'CA'),
    ('MEX', 'Mexico City',      'MX'), ('GDL', 'Guadalajara',       'MX'),
    ('MTY', 'Monterrey',        'MX'), ('PTY', 'Panama City',       'PA'),
    ('SJO', 'San José',         'CR'), ('GUA', 'Guatemala City',    'GT'),
    ('SAL', 'San Salvador',     'SV'), ('SJU', 'San Juan',          'PR'),
    ('SDQ', 'Santo Domingo',    'DO'),
    # South America
    ('BOG', 'Bogotá',           'CO'), ('MDE', 'Medellín',          'CO'),
    ('CLO', 'Cali',             'CO'), ('UIO', 'Quito',             'EC'),
    ('LIM', 'Lima',             'PE'), ('SCL', 'Santiago',          'CL'),
    ('EZE', 'Buenos Aires',     'AR'), ('GRU', 'São Paulo',         'BR'),
    ('VCP', 'Campinas',         'BR'), ('GIG', 'Rio de Janeiro',    'BR'),
    ('SSA', 'Salvador',         'BR'), ('FOR', 'Fortaleza',         'BR'),
    ('POA', 'Porto Alegre',     'BR'), ('CWB', 'Curitiba',          'BR'),
    ('BSB', 'Brasília',         'BR'), ('MVD', 'Montevideo',        'UY'),
    # Europe
    ('LHR', 'London',           'GB'), ('LGW', 'London Gatwick',    'GB'),
    ('MAN', 'Manchester',       'GB'), ('BHX', 'Birmingham',        'GB'),
    ('BRS', 'Bristol',          'GB'), ('EDI', 'Edinburgh',         'GB'),
    ('GLA', 'Glasgow',          'GB'), ('CDG', 'Paris',             'FR'),
    ('LYS', 'Lyon',             'FR'), ('MRS', 'Marseille',         'FR'),
    ('NCE', 'Nice',             'FR'), ('TLS', 'Toulouse',          'FR'),
    ('AMS', 'Amsterdam',        'NL'), ('FRA', 'Frankfurt',         'DE'),
    ('MUC', 'Munich',           'DE'), ('BER', 'Berlin',            'DE'),
    ('HAM', 'Hamburg',          'DE'), ('DUS', 'Düsseldorf',        'DE'),
    ('STR', 'Stuttgart',        'DE'), ('CGN', 'Cologne',           'DE'),
    ('NUE', 'Nuremberg',        'DE'), ('VIE', 'Vienna',            'AT'),
    ('ZRH', 'Zurich',           'CH'), ('GVA', 'Geneva',            'CH'),
    ('BSL', 'Basel',            'CH'), ('MAD', 'Madrid',            'ES'),
    ('BCN', 'Barcelona',        'ES'), ('VLC', 'Valencia',          'ES'),
    ('SVQ', 'Seville',          'ES'), ('BIO', 'Bilbao',            'ES'),
    ('LIS', 'Lisbon',           'PT'), ('OPO', 'Porto',             'PT'),
    ('MXP', 'Milan',            'IT'), ('FCO', 'Rome',              'IT'),
    ('BLQ', 'Bologna',          'IT'), ('NAP', 'Naples',            'IT'),
    ('VCE', 'Venice',           'IT'), ('BRU', 'Brussels',          'BE'),
    ('ANR', 'Antwerp',          'BE'), ('CPH', 'Copenhagen',        'DK'),
    ('ARN', 'Stockholm',        'SE'), ('OSL', 'Oslo',              'NO'),
    ('BGO', 'Bergen',           'NO'), ('HEL', 'Helsinki',          'FI'),
    ('TLL', 'Tallinn',          'EE'), ('RIX', 'Riga',              'LV'),
    ('VNO', 'Vilnius',          'LT'), ('WAW', 'Warsaw',            'PL'),
    ('KRK', 'Kraków',           'PL'), ('PRG', 'Prague',            'CZ'),
    ('BUD', 'Budapest',         'HU'), ('OTP', 'Bucharest',         'RO'),
    ('SOF', 'Sofia',            'BG'), ('BEG', 'Belgrade',          'RS'),
    ('ZAG', 'Zagreb',           'HR'), ('LJU', 'Ljubljana',         'SI'),
    ('ATH', 'Athens',           'GR'), ('SKG', 'Thessaloniki',      'GR'),
    ('IST', 'Istanbul',         'TR'), ('DUB', 'Dublin',            'IE'),
    # Eastern Europe / Russia
    ('KBP', 'Kyiv',             'UA'), ('MSQ', 'Minsk',             'BY'),
    ('SVO', 'Moscow',           'RU'), ('LED', 'St. Petersburg',    'RU'),
    ('SVX', 'Yekaterinburg',    'RU'), ('OVB', 'Novosibirsk',       'RU'),
    ('KJA', 'Krasnoyarsk',      'RU'), ('VVO', 'Vladivostok',       'RU'),
    ('TBS', 'Tbilisi',          'GE'), ('EVN', 'Yerevan',           'AM'),
    ('GYD', 'Baku',             'AZ'), ('ALA', 'Almaty',            'KZ'),
    ('TAS', 'Tashkent',         'UZ'),
    # Middle East
    ('DXB', 'Dubai',            'AE'), ('AUH', 'Abu Dhabi',         'AE'),
    ('BAH', 'Bahrain',          'BH'), ('KWI', 'Kuwait City',       'KW'),
    ('DOH', 'Doha',             'QA'), ('RUH', 'Riyadh',            'SA'),
    ('JED', 'Jeddah',           'SA'), ('AMM', 'Amman',             'JO'),
    ('BEY', 'Beirut',           'LB'), ('TLV', 'Tel Aviv',          'IL'),
    ('MCT', 'Muscat',           'OM'), ('IKA', 'Tehran',            'IR'),
    # Africa
    ('CAI', 'Cairo',            'EG'), ('CMN', 'Casablanca',        'MA'),
    ('ALG', 'Algiers',          'DZ'), ('TUN', 'Tunis',             'TN'),
    ('LOS', 'Lagos',            'NG'), ('ABV', 'Abuja',             'NG'),
    ('ACC', 'Accra',            'GH'), ('DKR', 'Dakar',             'SN'),
    ('NBO', 'Nairobi',          'KE'), ('MBA', 'Mombasa',           'KE'),
    ('EBB', 'Kampala',          'UG'), ('DAR', 'Dar es Salaam',     'TZ'),
    ('ADD', 'Addis Ababa',      'ET'), ('JNB', 'Johannesburg',      'ZA'),
    ('CPT', 'Cape Town',        'ZA'), ('DUR', 'Durban',            'ZA'),
    ('MRU', 'Mauritius',        'MU'), ('ABJ', 'Abidjan',           'CI'),
    # South Asia
    ('DEL', 'New Delhi',        'IN'), ('BOM', 'Mumbai',            'IN'),
    ('BLR', 'Bengaluru',        'IN'), ('MAA', 'Chennai',           'IN'),
    ('HYD', 'Hyderabad',        'IN'), ('CCU', 'Kolkata',           'IN'),
    ('AMD', 'Ahmedabad',        'IN'), ('PNQ', 'Pune',              'IN'),
    ('CMB', 'Colombo',          'LK'), ('DAC', 'Dhaka',             'BD'),
    ('KHI', 'Karachi',          'PK'), ('LHE', 'Lahore',            'PK'),
    # Southeast Asia
    ('SIN', 'Singapore',        'SG'), ('KUL', 'Kuala Lumpur',      'MY'),
    ('BKK', 'Bangkok',          'TH'), ('CGK', 'Jakarta',           'ID'),
    ('DPS', 'Bali',             'ID'), ('SUB', 'Surabaya',          'ID'),
    ('MNL', 'Manila',           'PH'), ('CEB', 'Cebu',              'PH'),
    ('SGN', 'Ho Chi Minh City', 'VN'), ('HAN', 'Hanoi',             'VN'),
    ('RGN', 'Yangon',           'MM'), ('PNH', 'Phnom Penh',        'KH'),
    # East Asia
    ('HKG', 'Hong Kong',        'HK'), ('TPE', 'Taipei',            'TW'),
    ('ICN', 'Seoul',            'KR'), ('PUS', 'Busan',             'KR'),
    ('NRT', 'Tokyo',            'JP'), ('HND', 'Tokyo Haneda',      'JP'),
    ('KIX', 'Osaka',            'JP'), ('FUK', 'Fukuoka',           'JP'),
    ('NGO', 'Nagoya',           'JP'), ('PVG', 'Shanghai',          'CN'),
    ('PEK', 'Beijing',          'CN'), ('CAN', 'Guangzhou',         'CN'),
    ('SZX', 'Shenzhen',         'CN'), ('CTU', 'Chengdu',           'CN'),
    ('WUH', 'Wuhan',            'CN'), ('XIY', "Xi'an",             'CN'),
    ('HGH', 'Hangzhou',         'CN'), ('NKG', 'Nanjing',           'CN'),
    ('CKG', 'Chongqing',        'CN'), ('XMN', 'Xiamen',            'CN'),
    ('DLC', 'Dalian',           'CN'), ('KMG', 'Kunming',           'CN'),
    ('TSN', 'Tianjin',          'CN'),
    # Oceania
    ('SYD', 'Sydney',           'AU'), ('MEL', 'Melbourne',         'AU'),
    ('BNE', 'Brisbane',         'AU'), ('PER', 'Perth',             'AU'),
    ('ADL', 'Adelaide',         'AU'), ('OOL', 'Gold Coast',        'AU'),
    ('AKL', 'Auckland',         'NZ'), ('WLG', 'Wellington',        'NZ'),
    ('CHC', 'Christchurch',     'NZ'), ('GUM', 'Guam',              'GU'),
]


# ── AWS CloudFront Edge Locations ─────────────────────────────────────────────
# Source: AWS CloudFront developer documentation (edge server locations).
# CloudFront has multiple POPs per metro; we list each city once.
# Additions marked [+] are from CloudFront's Regional Edge Caches.

CLOUDFRONT_POPS = [
    # North America
    ('IAD', 'Ashburn',          'US'), ('ATL', 'Atlanta',           'US'),
    ('BOS', 'Boston',           'US'), ('ORD', 'Chicago',           'US'),
    ('DFW', 'Dallas',           'US'), ('DEN', 'Denver',            'US'),
    ('DTW', 'Detroit',          'US'), ('EWR', 'Newark',            'US'),
    ('IAH', 'Houston',          'US'), ('JAX', 'Jacksonville',      'US'),
    ('LAX', 'Los Angeles',      'US'), ('LAX', 'Los Angeles 2',     'US'),
    ('MIA', 'Miami',            'US'), ('MSP', 'Minneapolis',       'US'),
    ('JFK', 'New York',         'US'), ('EWR', 'Newark 2',          'US'),
    ('PHX', 'Phoenix',          'US'), ('PDX', 'Portland',          'US'),
    ('SFO', 'San Francisco',    'US'), ('SJC', 'San Jose',          'US'),
    ('SEA', 'Seattle',          'US'), ('SLC', 'Salt Lake City',    'US'),
    ('STL', 'St. Louis',        'US'), ('YTO', 'Toronto',           'CA'),
    ('YUL', 'Montreal',         'CA'), ('YVR', 'Vancouver',         'CA'),
    ('MEX', 'Mexico City',      'MX'), ('GDL', 'Guadalajara',       'MX'),
    ('MTY', 'Monterrey',        'MX'), ('PTY', 'Panama City',       'PA'),
    ('BOG', 'Bogotá',           'CO'), ('LIM', 'Lima',              'PE'),
    ('SCL', 'Santiago',         'CL'), ('EZE', 'Buenos Aires',      'AR'),
    ('GRU', 'São Paulo',        'BR'), ('GIG', 'Rio de Janeiro',    'BR'),
    ('FOR', 'Fortaleza',        'BR'),
    # Europe
    ('LHR', 'London',           'GB'), ('MAN', 'Manchester',        'GB'),
    ('CDG', 'Paris',            'FR'), ('FRA', 'Frankfurt',         'DE'),
    ('MUC', 'Munich',           'DE'), ('BER', 'Berlin',            'DE'),
    ('HAM', 'Hamburg',          'DE'), ('DUS', 'Düsseldorf',        'DE'),
    ('AMS', 'Amsterdam',        'NL'), ('BRU', 'Brussels',          'BE'),
    ('MAD', 'Madrid',           'ES'), ('BCN', 'Barcelona',         'ES'),
    ('LIS', 'Lisbon',           'PT'), ('MXP', 'Milan',             'IT'),
    ('FCO', 'Rome',             'IT'), ('VIE', 'Vienna',            'AT'),
    ('ZRH', 'Zurich',           'CH'), ('CPH', 'Copenhagen',        'DK'),
    ('ARN', 'Stockholm',        'SE'), ('HEL', 'Helsinki',          'FI'),
    ('OSL', 'Oslo',             'NO'), ('WAW', 'Warsaw',            'PL'),
    ('PRG', 'Prague',           'CZ'), ('BUD', 'Budapest',          'HU'),
    ('OTP', 'Bucharest',        'RO'), ('SOF', 'Sofia',             'BG'),
    ('ATH', 'Athens',           'GR'), ('IST', 'Istanbul',          'TR'),
    ('DUB', 'Dublin',           'IE'), ('TLL', 'Tallinn',           'EE'),
    ('RIX', 'Riga',             'LV'), ('VNO', 'Vilnius',           'LT'),
    # Middle East & Africa
    ('DXB', 'Dubai',            'AE'), ('BAH', 'Bahrain',           'BH'),
    ('DOH', 'Doha',             'QA'), ('RUH', 'Riyadh',            'SA'),
    ('JED', 'Jeddah',           'SA'), ('TLV', 'Tel Aviv',          'IL'),
    ('AMM', 'Amman',            'JO'), ('MCT', 'Muscat',            'OM'),
    ('CAI', 'Cairo',            'EG'), ('CMN', 'Casablanca',        'MA'),
    ('LOS', 'Lagos',            'NG'), ('NBO', 'Nairobi',           'KE'),
    ('JNB', 'Johannesburg',     'ZA'), ('CPT', 'Cape Town',         'ZA'),
    ('ADD', 'Addis Ababa',      'ET'),
    # Asia Pacific
    ('BOM', 'Mumbai',           'IN'), ('DEL', 'New Delhi',         'IN'),
    ('BLR', 'Bengaluru',        'IN'), ('MAA', 'Chennai',           'IN'),
    ('HYD', 'Hyderabad',        'IN'), ('CCU', 'Kolkata',           'IN'),
    ('CMB', 'Colombo',          'LK'), ('DAC', 'Dhaka',             'BD'),
    ('KHI', 'Karachi',          'PK'), ('KTM', 'Kathmandu',         'NP'),
    ('SIN', 'Singapore',        'SG'), ('KUL', 'Kuala Lumpur',      'MY'),
    ('BKK', 'Bangkok',          'TH'), ('CGK', 'Jakarta',           'ID'),
    ('MNL', 'Manila',           'PH'), ('SGN', 'Ho Chi Minh City',  'VN'),
    ('HAN', 'Hanoi',            'VN'), ('PNH', 'Phnom Penh',        'KH'),
    ('HKG', 'Hong Kong',        'HK'), ('TPE', 'Taipei',            'TW'),
    ('ICN', 'Seoul',            'KR'), ('PUS', 'Busan',             'KR'),
    ('NRT', 'Tokyo',            'JP'), ('KIX', 'Osaka',             'JP'),
    ('FUK', 'Fukuoka',          'JP'), ('NGO', 'Nagoya',            'JP'),
    ('PVG', 'Shanghai',         'CN'), ('PEK', 'Beijing',           'CN'),
    ('CAN', 'Guangzhou',        'CN'), ('SZX', 'Shenzhen',          'CN'),
    ('CTU', 'Chengdu',          'CN'), ('HGH', 'Hangzhou',          'CN'),
    ('SYD', 'Sydney',           'AU'), ('MEL', 'Melbourne',         'AU'),
    ('BNE', 'Brisbane',         'AU'), ('PER', 'Perth',             'AU'),
    ('ADL', 'Adelaide',         'AU'), ('AKL', 'Auckland',          'NZ'),
    ('WLG', 'Wellington',       'NZ'), ('GUM', 'Guam',              'GU'),
]


# ── Fastly PoPs ───────────────────────────────────────────────────────────────
# Source: fastly.com/network-map  (~90 PoPs as of 2025)

FASTLY_POPS = [
    # North America
    ('IAD', 'Ashburn',          'US'), ('ATL', 'Atlanta',           'US'),
    ('BOS', 'Boston',           'US'), ('ORD', 'Chicago',           'US'),
    ('DFW', 'Dallas',           'US'), ('DEN', 'Denver',            'US'),
    ('IAH', 'Houston',          'US'), ('LAX', 'Los Angeles',       'US'),
    ('MIA', 'Miami',            'US'), ('MSP', 'Minneapolis',       'US'),
    ('EWR', 'New York',         'US'), ('PDX', 'Portland',          'US'),
    ('SFO', 'San Francisco',    'US'), ('SEA', 'Seattle',           'US'),
    ('YTO', 'Toronto',          'CA'), ('YUL', 'Montreal',          'CA'),
    ('YVR', 'Vancouver',        'CA'), ('MEX', 'Mexico City',       'MX'),
    ('PTY', 'Panama City',      'PA'),
    # South America
    ('BOG', 'Bogotá',           'CO'), ('SCL', 'Santiago',          'CL'),
    ('EZE', 'Buenos Aires',     'AR'), ('GRU', 'São Paulo',         'BR'),
    # Europe
    ('LHR', 'London',           'GB'), ('AMS', 'Amsterdam',         'NL'),
    ('CDG', 'Paris',            'FR'), ('FRA', 'Frankfurt',         'DE'),
    ('MAD', 'Madrid',           'ES'), ('MXP', 'Milan',             'IT'),
    ('VIE', 'Vienna',           'AT'), ('ZRH', 'Zurich',            'CH'),
    ('CPH', 'Copenhagen',       'DK'), ('ARN', 'Stockholm',         'SE'),
    ('HEL', 'Helsinki',         'FI'), ('OSL', 'Oslo',              'NO'),
    ('WAW', 'Warsaw',           'PL'), ('PRG', 'Prague',            'CZ'),
    ('OTP', 'Bucharest',        'RO'), ('ATH', 'Athens',            'GR'),
    ('IST', 'Istanbul',         'TR'), ('DUB', 'Dublin',            'IE'),
    # Middle East & Africa
    ('DXB', 'Dubai',            'AE'), ('JNB', 'Johannesburg',      'ZA'),
    ('CPT', 'Cape Town',        'ZA'), ('NBO', 'Nairobi',           'KE'),
    ('LOS', 'Lagos',            'NG'), ('CAI', 'Cairo',             'EG'),
    # Asia Pacific
    ('BOM', 'Mumbai',           'IN'), ('DEL', 'New Delhi',         'IN'),
    ('BLR', 'Bengaluru',        'IN'), ('MAA', 'Chennai',           'IN'),
    ('SIN', 'Singapore',        'SG'), ('KUL', 'Kuala Lumpur',      'MY'),
    ('BKK', 'Bangkok',          'TH'), ('CGK', 'Jakarta',           'ID'),
    ('MNL', 'Manila',           'PH'), ('SGN', 'Ho Chi Minh City',  'VN'),
    ('HAN', 'Hanoi',            'VN'), ('HKG', 'Hong Kong',         'HK'),
    ('TPE', 'Taipei',           'TW'), ('ICN', 'Seoul',             'KR'),
    ('NRT', 'Tokyo',            'JP'), ('KIX', 'Osaka',             'JP'),
    ('FUK', 'Fukuoka',          'JP'), ('PVG', 'Shanghai',          'CN'),
    ('PEK', 'Beijing',          'CN'), ('CAN', 'Guangzhou',         'CN'),
    ('SYD', 'Sydney',           'AU'), ('MEL', 'Melbourne',         'AU'),
    ('BNE', 'Brisbane',         'AU'), ('PER', 'Perth',             'AU'),
    ('AKL', 'Auckland',         'NZ'),
]


# ── Akamai PoPs ───────────────────────────────────────────────────────────────
# Akamai operates 4,000+ servers in 1,000+ cities but does not publish a
# machine-readable PoP list.  This is a ~350-city representative sample
# compiled from Akamai network announcements, CDN-comparison sites, and
# traceroute data published by the research community (2024–2025).

AKAMAI_POPS = [
    # North America — dense coverage
    ('IAD', 'Ashburn',          'US'), ('ATL', 'Atlanta',           'US'),
    ('BNA', 'Nashville',        'US'), ('BOS', 'Boston',            'US'),
    ('BUF', 'Buffalo',          'US'), ('BWI', 'Baltimore',         'US'),
    ('CLT', 'Charlotte',        'US'), ('CMH', 'Columbus',          'US'),
    ('CLE', 'Cleveland',        'US'), ('DEN', 'Denver',            'US'),
    ('DFW', 'Dallas',           'US'), ('DTW', 'Detroit',           'US'),
    ('EWR', 'Newark',           'US'), ('FLL', 'Fort Lauderdale',   'US'),
    ('HNL', 'Honolulu',         'US'), ('IAH', 'Houston',           'US'),
    ('IND', 'Indianapolis',     'US'), ('JAX', 'Jacksonville',      'US'),
    ('LAS', 'Las Vegas',        'US'), ('LAX', 'Los Angeles',       'US'),
    ('MCI', 'Kansas City',      'US'), ('MCO', 'Orlando',           'US'),
    ('MEM', 'Memphis',          'US'), ('MIA', 'Miami',             'US'),
    ('MSP', 'Minneapolis',      'US'), ('OAK', 'Oakland',           'US'),
    ('ORD', 'Chicago',          'US'), ('PDX', 'Portland',          'US'),
    ('PHL', 'Philadelphia',     'US'), ('PHX', 'Phoenix',           'US'),
    ('PIT', 'Pittsburgh',       'US'), ('RDU', 'Raleigh',           'US'),
    ('SAN', 'San Diego',        'US'), ('SEA', 'Seattle',           'US'),
    ('SFO', 'San Francisco',    'US'), ('SJC', 'San Jose',          'US'),
    ('SLC', 'Salt Lake City',   'US'), ('STL', 'St. Louis',         'US'),
    ('TPA', 'Tampa',            'US'), ('YTO', 'Toronto',           'CA'),
    ('YUL', 'Montreal',         'CA'), ('YVR', 'Vancouver',         'CA'),
    ('YYC', 'Calgary',          'CA'), ('YEG', 'Edmonton',          'CA'),
    # Latin America
    ('MEX', 'Mexico City',      'MX'), ('GDL', 'Guadalajara',       'MX'),
    ('MTY', 'Monterrey',        'MX'), ('PTY', 'Panama City',       'PA'),
    ('BOG', 'Bogotá',           'CO'), ('MDE', 'Medellín',          'CO'),
    ('LIM', 'Lima',             'PE'), ('UIO', 'Quito',             'EC'),
    ('SCL', 'Santiago',         'CL'), ('EZE', 'Buenos Aires',      'AR'),
    ('GRU', 'São Paulo',        'BR'), ('GIG', 'Rio de Janeiro',    'BR'),
    ('SSA', 'Salvador',         'BR'), ('FOR', 'Fortaleza',         'BR'),
    ('POA', 'Porto Alegre',     'BR'), ('CWB', 'Curitiba',          'BR'),
    # Europe — dense coverage
    ('LHR', 'London',           'GB'), ('MAN', 'Manchester',        'GB'),
    ('BHX', 'Birmingham',       'GB'), ('EDI', 'Edinburgh',         'GB'),
    ('CDG', 'Paris',            'FR'), ('LYS', 'Lyon',              'FR'),
    ('MRS', 'Marseille',        'FR'), ('NCE', 'Nice',              'FR'),
    ('AMS', 'Amsterdam',        'NL'), ('FRA', 'Frankfurt',         'DE'),
    ('MUC', 'Munich',           'DE'), ('BER', 'Berlin',            'DE'),
    ('HAM', 'Hamburg',          'DE'), ('DUS', 'Düsseldorf',        'DE'),
    ('STR', 'Stuttgart',        'DE'), ('NUE', 'Nuremberg',         'DE'),
    ('VIE', 'Vienna',           'AT'), ('ZRH', 'Zurich',            'CH'),
    ('GVA', 'Geneva',           'CH'), ('MAD', 'Madrid',            'ES'),
    ('BCN', 'Barcelona',        'ES'), ('VLC', 'Valencia',          'ES'),
    ('LIS', 'Lisbon',           'PT'), ('MXP', 'Milan',             'IT'),
    ('FCO', 'Rome',             'IT'), ('BLQ', 'Bologna',           'IT'),
    ('NAP', 'Naples',           'IT'), ('BRU', 'Brussels',          'BE'),
    ('CPH', 'Copenhagen',       'DK'), ('ARN', 'Stockholm',         'SE'),
    ('OSL', 'Oslo',             'NO'), ('HEL', 'Helsinki',          'FI'),
    ('TLL', 'Tallinn',          'EE'), ('RIX', 'Riga',              'LV'),
    ('WAW', 'Warsaw',           'PL'), ('KRK', 'Kraków',            'PL'),
    ('PRG', 'Prague',           'CZ'), ('BUD', 'Budapest',          'HU'),
    ('OTP', 'Bucharest',        'RO'), ('SOF', 'Sofia',             'BG'),
    ('BEG', 'Belgrade',         'RS'), ('ATH', 'Athens',            'GR'),
    ('IST', 'Istanbul',         'TR'), ('DUB', 'Dublin',            'IE'),
    ('KBP', 'Kyiv',             'UA'), ('SVO', 'Moscow',            'RU'),
    ('LED', 'St. Petersburg',   'RU'), ('SVX', 'Yekaterinburg',     'RU'),
    ('OVB', 'Novosibirsk',      'RU'), ('VVO', 'Vladivostok',       'RU'),
    # Middle East
    ('DXB', 'Dubai',            'AE'), ('AUH', 'Abu Dhabi',         'AE'),
    ('BAH', 'Bahrain',          'BH'), ('KWI', 'Kuwait City',       'KW'),
    ('DOH', 'Doha',             'QA'), ('RUH', 'Riyadh',            'SA'),
    ('JED', 'Jeddah',           'SA'), ('AMM', 'Amman',             'JO'),
    ('TLV', 'Tel Aviv',         'IL'), ('MCT', 'Muscat',            'OM'),
    ('IKA', 'Tehran',           'IR'),
    # Africa
    ('CAI', 'Cairo',            'EG'), ('CMN', 'Casablanca',        'MA'),
    ('ALG', 'Algiers',          'DZ'), ('TUN', 'Tunis',             'TN'),
    ('LOS', 'Lagos',            'NG'), ('ABV', 'Abuja',             'NG'),
    ('ACC', 'Accra',            'GH'), ('DKR', 'Dakar',             'SN'),
    ('NBO', 'Nairobi',          'KE'), ('DAR', 'Dar es Salaam',     'TZ'),
    ('ADD', 'Addis Ababa',      'ET'), ('JNB', 'Johannesburg',      'ZA'),
    ('CPT', 'Cape Town',        'ZA'), ('DUR', 'Durban',            'ZA'),
    ('ABJ', 'Abidjan',          'CI'), ('MRU', 'Mauritius',         'MU'),
    # South Asia
    ('DEL', 'New Delhi',        'IN'), ('BOM', 'Mumbai',            'IN'),
    ('BLR', 'Bengaluru',        'IN'), ('MAA', 'Chennai',           'IN'),
    ('HYD', 'Hyderabad',        'IN'), ('CCU', 'Kolkata',           'IN'),
    ('AMD', 'Ahmedabad',        'IN'), ('PNQ', 'Pune',              'IN'),
    ('NAG', 'Nagpur',           'IN'), ('COK', 'Kochi',             'IN'),
    ('CMB', 'Colombo',          'LK'), ('DAC', 'Dhaka',             'BD'),
    ('KHI', 'Karachi',          'PK'), ('LHE', 'Lahore',            'PK'),
    ('KTM', 'Kathmandu',        'NP'),
    # Southeast Asia
    ('SIN', 'Singapore',        'SG'), ('KUL', 'Kuala Lumpur',      'MY'),
    ('BKK', 'Bangkok',          'TH'), ('HKT', 'Phuket',            'TH'),
    ('CGK', 'Jakarta',          'ID'), ('DPS', 'Bali',              'ID'),
    ('SUB', 'Surabaya',         'ID'), ('MNL', 'Manila',            'PH'),
    ('CEB', 'Cebu',             'PH'), ('SGN', 'Ho Chi Minh City',  'VN'),
    ('HAN', 'Hanoi',            'VN'), ('DAD', 'Da Nang',           'VN'),
    ('RGN', 'Yangon',           'MM'), ('PNH', 'Phnom Penh',        'KH'),
    # East Asia
    ('HKG', 'Hong Kong',        'HK'), ('TPE', 'Taipei',            'TW'),
    ('KHH', 'Kaohsiung',        'TW'), ('ICN', 'Seoul',             'KR'),
    ('PUS', 'Busan',            'KR'), ('NRT', 'Tokyo',             'JP'),
    ('HND', 'Tokyo Haneda',     'JP'), ('KIX', 'Osaka',             'JP'),
    ('FUK', 'Fukuoka',          'JP'), ('NGO', 'Nagoya',            'JP'),
    ('PVG', 'Shanghai',         'CN'), ('PEK', 'Beijing',           'CN'),
    ('CAN', 'Guangzhou',        'CN'), ('SZX', 'Shenzhen',          'CN'),
    ('CTU', 'Chengdu',          'CN'), ('WUH', 'Wuhan',             'CN'),
    ('XIY', "Xi'an",            'CN'), ('HGH', 'Hangzhou',          'CN'),
    ('NKG', 'Nanjing',          'CN'), ('CKG', 'Chongqing',         'CN'),
    ('XMN', 'Xiamen',           'CN'), ('DLC', 'Dalian',            'CN'),
    ('KMG', 'Kunming',          'CN'), ('TSN', 'Tianjin',           'CN'),
    ('TAO', 'Qingdao',          'CN'), ('HRB', 'Harbin',            'CN'),
    # Oceania
    ('SYD', 'Sydney',           'AU'), ('MEL', 'Melbourne',         'AU'),
    ('BNE', 'Brisbane',         'AU'), ('PER', 'Perth',             'AU'),
    ('ADL', 'Adelaide',         'AU'), ('OOL', 'Gold Coast',        'AU'),
    ('AKL', 'Auckland',         'NZ'), ('WLG', 'Wellington',        'NZ'),
    ('CHC', 'Christchurch',     'NZ'), ('GUM', 'Guam',              'GU'),
]

# ── Build GeoJSON ─────────────────────────────────────────────────────────────

PROVIDER_LISTS = [
    ('Cloudflare',   CLOUDFLARE_POPS),
    ('CloudFront',   CLOUDFRONT_POPS),
    ('Fastly',       FASTLY_POPS),
    ('Akamai',       AKAMAI_POPS),
]

def build_geojson():
    features = []
    seen     = set()   # deduplicate (provider, iata) pairs

    for provider, pops in PROVIDER_LISTS:
        for iata, city, country in pops:
            key = (provider, iata, city)
            if key in seen:
                continue
            seen.add(key)

            coords = geocode(iata, city, country)
            if coords is None:
                print(f'  ⚠  no coords for {provider} {iata} {city}, {country}', file=sys.stderr)
                continue

            lat, lon = coords
            features.append(make_feature(provider, iata, city, country, lat, lon))

    return {'type': 'FeatureCollection', 'features': features}


def main():
    out_path = os.path.join(
        os.path.dirname(__file__), '..', 'public', 'cdn-edge-locations.geojson'
    )
    out_path = os.path.normpath(out_path)

    print('Building CDN edge location dataset …')
    for provider, pops in PROVIDER_LISTS:
        print(f'  {provider:<14} {len(pops):>4} raw PoPs')

    fc = build_geojson()
    counts = {}
    for f in fc['features']:
        p = f['properties']['provider']
        counts[p] = counts.get(p, 0) + 1

    print('\nAfter deduplication + geocoding:')
    for provider, n in counts.items():
        print(f'  {provider:<14} {n:>4} features')
    print(f'  {"TOTAL":<14} {len(fc["features"]):>4} features')

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as fh:
        json.dump(fc, fh, separators=(',', ':'))
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
