#!/usr/bin/env python3
"""
fetch_dns_infrastructure.py

Compiles DNS infrastructure data and writes two GeoJSON files to ../public/:

  dns-root-instances.geojson
    Root server anycast instances for all 13 identities (A–M).
    Properties: { name, letter, operator, city, country, isGlobal }

  dns-resolvers.geojson
    Public recursive resolver PoP locations.
    Properties: { name, provider, ip, city, country }

Data sources
────────────
  Root servers
    1. Live scrape of root-servers.org per-letter pages (HTML table parsing).
    2. Hardcoded fallback: ~350 well-documented instance sites compiled from
       root-servers.org, operator websites, and RIPE NCC publications.
       Use this if scraping yields too few results or the site structure changes.

  Resolvers
    Hardcoded PoP data for Cloudflare 1.1.1.1 (~100 cities), Google 8.8.8.8
    (~45 cities), Quad9 9.9.9.9 (~60 cities), OpenDNS 208.67.222.222 (~35 cities).
    Sources: Cloudflare network page, Google Cloud PoP list, Quad9 node map, Cisco docs.

Refresh cadence
───────────────
  Root server instance locations change infrequently (new anycast sites are added
  or decommissioned a few times per year). Re-run monthly or when operator
  announcements indicate changes. Resolver PoP lists are similarly stable —
  quarterly refreshes are sufficient.

Usage
─────
  python3 fetch_dns_infrastructure.py
"""

import json
import os
import re
import urllib.request
from html.parser import HTMLParser

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')
HEADERS = {'User-Agent': 'ProjectBackbone/1.0 (educational)'}

# ── Root server operator metadata ─────────────────────────────────────────────

ROOT_SERVER_OPERATORS = {
    'A': ('a.root-servers.net', 'Verisign'),
    'B': ('b.root-servers.net', 'USC-ISI'),
    'C': ('c.root-servers.net', 'Cogent Communications'),
    'D': ('d.root-servers.net', 'University of Maryland'),
    'E': ('e.root-servers.net', 'NASA'),
    'F': ('f.root-servers.net', 'ISC'),
    'G': ('g.root-servers.net', 'US DoD NIC'),
    'H': ('h.root-servers.net', 'US Army Research Lab'),
    'I': ('i.root-servers.net', 'Netnod'),
    'J': ('j.root-servers.net', 'Verisign'),
    'K': ('k.root-servers.net', 'RIPE NCC'),
    'L': ('l.root-servers.net', 'ICANN'),
    'M': ('m.root-servers.net', 'WIDE Project'),
}

# ── HTML scraper for root-servers.org ─────────────────────────────────────────

class TableParser(HTMLParser):
    """Extract all <tr> cell text from an HTML page."""
    def __init__(self):
        super().__init__()
        self._rows, self._row, self._cell, self._buf = [], None, False, ''

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = True
            self._buf = ''

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell:
            self._row.append(self._buf.strip())
            self._cell = False
        elif tag == 'tr' and self._row is not None:
            if self._row:
                self._rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell:
            self._buf += data

    def handle_entityref(self, name):
        if self._cell:
            self._buf += {'amp': '&', 'lt': '<', 'gt': '>', 'nbsp': ' '}.get(name, '')

    def handle_charref(self, name):
        if self._cell:
            try:
                ch = chr(int(name[1:], 16) if name.startswith('x') else int(name))
                self._buf += ch
            except ValueError:
                pass


# City → (lat, lon) lookup used when scraping returns city names without coords.
# Covers the cities where root server instances are commonly deployed.
CITY_COORDS = {
    'abidjan': (5.35, -4.00), 'abu dhabi': (24.47, 54.37), 'accra': (5.56, -0.20),
    'addis ababa': (9.03, 38.74), 'amsterdam': (52.37, 4.90), 'anchorage': (61.22, -149.90),
    'ankara': (39.93, 32.86), 'ashburn': (39.04, -77.49), 'auckland': (-36.85, 174.76),
    'atlanta': (33.75, -84.39), 'bahrain': (26.07, 50.56), 'bangalore': (12.97, 77.59),
    'bangkok': (13.75, 100.52), 'barcelona': (41.39, 2.15), 'beijing': (39.91, 116.39),
    'belgrade': (44.80, 20.47), 'berlin': (52.52, 13.40), 'bogotá': (4.71, -74.07),
    'bogota': (4.71, -74.07), 'boston': (42.36, -71.06), 'brisbane': (-27.47, 153.02),
    'brussels': (50.85, 4.35), 'bucharest': (44.43, 26.11), 'budapest': (47.50, 19.04),
    'buenos aires': (-34.61, -58.39), 'cairo': (30.04, 31.24), 'cape town': (-33.93, 18.42),
    'casablanca': (33.59, -7.62), 'charlotte': (35.23, -80.84), 'chengdu': (30.57, 104.07),
    'chicago': (41.88, -87.63), 'college park': (38.99, -76.94), 'colombo': (6.93, 79.85),
    'columbus': (39.96, -82.99), 'copenhagen': (55.68, 12.57), 'dakar': (14.69, -17.44),
    'dallas': (32.89, -97.04), 'dar es salaam': (-6.79, 39.21), 'delhi': (28.63, 77.22),
    'denver': (39.74, -104.99), 'dhaka': (23.81, 90.41), 'djibouti': (11.59, 43.15),
    'doha': (25.29, 51.53), 'dubai': (25.20, 55.27), 'dublin': (53.33, -6.25),
    'dusseldorf': (51.23, 6.79), 'edinburgh': (55.95, -3.19), 'fortaleza': (-3.72, -38.54),
    'frankfurt': (50.11, 8.68), 'fukuoka': (33.59, 130.40), 'geneva': (46.20, 6.14),
    'gothenburg': (57.71, 11.97), 'guadalajara': (20.68, -103.35), 'guangzhou': (23.13, 113.26),
    'hamburg': (53.55, 10.00), 'hanoi': (21.03, 105.85), 'helsinki': (60.17, 24.93),
    'ho chi minh': (10.82, 106.63), 'ho chi minh city': (10.82, 106.63),
    'hong kong': (22.32, 114.17), 'honolulu': (21.30, -157.86), 'houston': (29.76, -95.37),
    'hyderabad': (17.39, 78.48), 'indianapolis': (39.77, -86.16), 'islamabad': (33.72, 73.04),
    'istanbul': (41.01, 28.95), 'jakarta': (-6.21, 106.85), 'johannesburg': (-26.20, 28.04),
    'kampala': (0.32, 32.58), 'kansas city': (39.10, -94.58), 'karachi': (24.86, 67.01),
    'kathmandu': (27.71, 85.31), 'khartoum': (15.55, 32.53), 'kuala lumpur': (3.14, 101.69),
    'kuwait city': (29.37, 47.98), 'kyiv': (50.45, 30.52), 'lagos': (6.52, 3.38),
    'lahore': (31.55, 74.36), 'las vegas': (36.17, -115.14), 'lima': (-12.05, -77.04),
    'lisbon': (38.72, -9.14), 'ljubljana': (46.05, 14.51), 'london': (51.51, -0.13),
    'los angeles': (34.05, -118.24), 'lusaka': (-15.42, 28.28), 'luxembourg': (49.61, 6.13),
    'madrid': (40.42, -3.70), 'manila': (14.60, 120.98), 'marseille': (43.30, 5.37),
    'melbourne': (-37.81, 144.96), 'memphis': (35.15, -90.05), 'mexico city': (19.43, -99.13),
    'miami': (25.77, -80.19), 'milan': (45.47, 9.19), 'minneapolis': (44.98, -93.27),
    'mombasa': (-4.05, 39.67), 'monterrey': (25.67, -100.31), 'montreal': (45.51, -73.55),
    'montréal': (45.51, -73.55), 'moscow': (55.75, 37.62), 'mountain view': (37.39, -122.08),
    'mumbai': (19.08, 72.88), 'munich': (48.14, 11.58), 'muscat': (23.61, 58.59),
    'nagoya': (35.18, 136.91), 'nairobi': (-1.29, 36.82), 'nashville': (36.17, -86.78),
    'new delhi': (28.63, 77.22), 'new york': (40.71, -74.01), 'newark': (40.74, -74.17),
    'orlando': (28.54, -81.38), 'osaka': (34.69, 135.50), 'oslo': (59.91, 10.75),
    'panama city': (8.99, -79.52), 'paris': (48.86, 2.35), 'perth': (-31.95, 115.86),
    'phnom penh': (11.56, 104.92), 'phoenix': (33.45, -112.07), 'pittsburgh': (40.44, -79.99),
    'portland': (45.52, -122.68), 'prague': (50.08, 14.44), 'querétaro': (20.59, -100.39),
    'queretaro': (20.59, -100.39), 'quito': (-0.23, -78.52), 'raleigh': (35.78, -78.64),
    'recife': (-8.05, -34.88), 'riga': (56.95, 24.11), 'rio de janeiro': (-22.91, -43.17),
    'riyadh': (24.69, 46.72), 'rome': (41.90, 12.50), 'rotterdam': (51.92, 4.48),
    'sacramento': (38.58, -121.49), 'salt lake city': (40.76, -111.89),
    'san jose': (37.34, -121.89), 'san juan': (18.47, -66.11), 'santiago': (-33.45, -70.67),
    'sarajevo': (43.85, 18.39), 'seattle': (47.61, -122.33), 'seoul': (37.51, 126.99),
    'shanghai': (31.23, 121.47), 'singapore': (1.35, 103.82), 'skopje': (41.99, 21.43),
    'sofia': (42.70, 23.32), 'stockholm': (59.33, 18.07), 'sydney': (-33.87, 151.21),
    'taipei': (25.05, 121.53), 'tallinn': (59.44, 24.75), 'tampa': (27.95, -82.46),
    'tel aviv': (32.08, 34.78), 'tokyo': (35.68, 139.69), 'toronto': (43.65, -79.38),
    'tunis': (36.82, 10.17), 'ulaanbaatar': (47.91, 106.88), 'vancouver': (49.25, -123.12),
    'vienna': (48.21, 16.37), 'warsaw': (52.23, 21.01), 'washington dc': (38.91, -77.04),
    'wellington': (-41.29, 174.78), 'winnipeg': (49.90, -97.14), 'yangon': (16.87, 96.12),
    'zagreb': (45.81, 15.98), 'zurich': (47.38, 8.54),
    # Less common but documented root server locations
    'aberdeen': (57.15, -2.11), 'accra': (5.56, -0.20), 'bergen': (60.39, 5.33),
    'bratislava': (48.15, 17.11), 'calgary': (51.05, -114.07), 'canberra': (-35.28, 149.13),
    'chennai': (13.08, 80.27), 'chisinau': (47.00, 28.86), 'edmonton': (53.55, -113.47),
    'guadalajara': (20.68, -103.35), 'islamabad': (33.72, 73.04), 'kabul': (34.53, 69.17),
    'katowice': (50.26, 19.02), 'kigali': (-1.94, 30.06), 'kinshasa': (-4.32, 15.32),
    'lahore': (31.55, 74.36), 'luxembourg city': (49.61, 6.13), 'managua': (12.13, -86.28),
    'manila': (14.60, 120.98), 'maputo': (-25.97, 32.59), 'medellín': (6.25, -75.57),
    'medellin': (6.25, -75.57), 'minneapolis': (44.98, -93.27), 'minsk': (53.90, 27.57),
    'montevideo': (-34.90, -56.19), 'nicosia': (35.17, 33.36), 'noumea': (-22.27, 166.46),
    'nur-sultan': (51.18, 71.45), 'only': (48.73, 2.35), 'papeete': (-17.54, -149.57),
    'reykjavik': (64.13, -21.90), 'san josé': (9.93, -84.08), 'san jose, cr': (9.93, -84.08),
    'suva': (-18.14, 178.44), 'tallahassee': (30.44, -84.28), 'tbilisi': (41.69, 44.83),
    'tehran': (35.69, 51.42), 'tirana': (41.33, 19.82), 'ulaanbaatar': (47.91, 106.88),
    'vilnius': (54.69, 25.28), 'windhoek': (-22.56, 17.08), 'yerevan': (40.18, 44.51),
}


def geocode(city):
    """Return (lat, lon) for a city name, or None if unknown."""
    key = city.lower().strip()
    if key in CITY_COORDS:
        return CITY_COORDS[key]
    # Try prefix match (e.g. "Frankfurt, Germany" → "frankfurt")
    for k, v in CITY_COORDS.items():
        if key.startswith(k) or k.startswith(key):
            return v
    return None


def scrape_letter(letter):
    """
    Try to scrape instance list for one root server letter from root-servers.org.
    Returns list of (site, city, country, is_global) or None on failure.
    """
    url = f'https://root-servers.org/{letter.lower()}/'
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'    scrape {letter}: network error — {e}')
        return None

    parser = TableParser()
    parser.feed(html)

    instances = []
    # Skip header row(s); look for rows with ≥3 non-empty cells
    for row in parser._rows:
        cells = [c.strip() for c in row]
        if len(cells) < 3:
            continue
        # Heuristic: skip rows that look like headers (all caps or contain "city")
        if any(c.lower() in ('city', 'country', 'site', 'location', 'status') for c in cells[:4]):
            continue
        # Try to identify city/country columns — flexible column order
        city = country = ''
        is_global = False
        for i, c in enumerate(cells):
            cl = c.lower()
            if cl in ('global', 'local'):
                is_global = cl == 'global'
            elif not city and re.match(r'^[A-Z][a-z]', c) and len(c) > 2 and geocode(c):
                city = c
            elif not country and re.match(r'^[A-Z][a-z]', c) and len(c) > 2 and city and c != city:
                country = c
        if city:
            instances.append((cells[0] if cells else '', city, country, is_global))

    return instances if len(instances) >= 2 else None


# ── Hardcoded fallback root server instances ──────────────────────────────────
# Source: root-servers.org, operator network pages, RIPE NCC Routing Information
# Format: (site_id, city, country, lat, lon, is_global)

FALLBACK_INSTANCES = {
    'A': [  # Verisign — 5 global sites
        ('AMS1', 'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('IAD1', 'Ashburn',        'United States',    39.04,  -77.49, True),
        ('LAX1', 'Los Angeles',    'United States',    34.05, -118.24, True),
        ('SIN1', 'Singapore',      'Singapore',         1.35,  103.82, True),
        ('NRT1', 'Tokyo',          'Japan',            35.68,  139.69, True),
    ],
    'B': [  # USC-ISI — 2 sites
        ('LAX1', 'Los Angeles',    'United States',    33.99, -118.47, True),
        ('IAD1', 'Ashburn',        'United States',    39.04,  -77.49, True),
    ],
    'C': [  # Cogent — ~10 sites
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, True),
        ('ORD',  'Chicago',        'United States',    41.88,  -87.63, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32,  114.17, True),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, True),
        ('MIA',  'Miami',          'United States',    25.77,  -80.19, True),
        ('NRT',  'Tokyo',          'Japan',            35.68,  139.69, True),
        ('YYZ',  'Toronto',        'Canada',           43.65,  -79.38, True),
    ],
    'D': [  # University of Maryland — 5 sites
        ('IAD',  'College Park',   'United States',    38.99,  -76.94, True),
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('SIN',  'Singapore',      'Singapore',         1.35,  103.82, True),
        ('NRT',  'Tokyo',          'Japan',            35.68,  139.69, True),
    ],
    'E': [  # NASA — 3 sites
        ('MFV',  'Mountain View',  'United States',    37.39, -122.08, True),
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('SIN',  'Singapore',      'Singapore',         1.35,  103.82, True),
    ],
    'F': [  # ISC — 176 instances; major and representative sites listed
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, True),
        ('ORD',  'Chicago',        'United States',    41.88,  -87.63, True),
        ('DFW',  'Dallas',         'United States',    32.89,  -97.04, True),
        ('SEA',  'Seattle',        'United States',    47.61, -122.33, True),
        ('MIA',  'Miami',          'United States',    25.77,  -80.19, True),
        ('BOS',  'Boston',         'United States',    42.36,  -71.06, False),
        ('MSP',  'Minneapolis',    'United States',    44.98,  -93.27, False),
        ('PHX',  'Phoenix',        'United States',    33.45, -112.07, False),
        ('PHL',  'Philadelphia',   'United States',    39.95,  -75.17, False),
        ('IAH',  'Houston',        'United States',    29.76,  -95.37, False),
        ('YYZ',  'Toronto',        'Canada',           43.65,  -79.38, False),
        ('YUL',  'Montreal',       'Canada',           45.51,  -73.55, False),
        ('MEX',  'Mexico City',    'Mexico',           19.43,  -99.13, False),
        ('GRU',  'São Paulo',      'Brazil',          -23.55,  -46.63, True),
        ('GIG',  'Rio de Janeiro', 'Brazil',          -22.91,  -43.17, False),
        ('BUE',  'Buenos Aires',   'Argentina',       -34.61,  -58.39, False),
        ('SCL',  'Santiago',       'Chile',           -33.45,  -70.67, False),
        ('BOG',  'Bogotá',         'Colombia',          4.71,  -74.07, False),
        ('LIM',  'Lima',           'Peru',            -12.05,  -77.04, False),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, True),
        ('CDG',  'Paris',          'France',           48.86,   2.35, True),
        ('MUC',  'Munich',         'Germany',          48.14,  11.58, False),
        ('MXP',  'Milan',          'Italy',            45.47,   9.19, False),
        ('MAD',  'Madrid',         'Spain',            40.42,  -3.70, False),
        ('BCN',  'Barcelona',      'Spain',            41.39,   2.15, False),
        ('VIE',  'Vienna',         'Austria',          48.21,  16.37, False),
        ('ZRH',  'Zurich',         'Switzerland',      47.38,   8.54, False),
        ('GVA',  'Geneva',         'Switzerland',      46.20,   6.14, False),
        ('ARN',  'Stockholm',      'Sweden',           59.33,  18.07, False),
        ('OSL',  'Oslo',           'Norway',           59.91,  10.75, False),
        ('CPH',  'Copenhagen',     'Denmark',          55.68,  12.57, False),
        ('HEL',  'Helsinki',       'Finland',          60.17,  24.93, False),
        ('DUB',  'Dublin',         'Ireland',          53.33,  -6.25, False),
        ('LIS',  'Lisbon',         'Portugal',         38.72,  -9.14, False),
        ('PRG',  'Prague',         'Czech Republic',   50.08,  14.44, False),
        ('WAW',  'Warsaw',         'Poland',           52.23,  21.01, False),
        ('BUD',  'Budapest',       'Hungary',          47.50,  19.04, False),
        ('BUH',  'Bucharest',      'Romania',          44.43,  26.11, False),
        ('SOF',  'Sofia',          'Bulgaria',         42.70,  23.32, False),
        ('BEG',  'Belgrade',       'Serbia',           44.80,  20.47, False),
        ('IST',  'Istanbul',       'Turkey',           41.01,  28.95, False),
        ('CAI',  'Cairo',          'Egypt',            30.04,  31.24, False),
        ('JNB',  'Johannesburg',   'South Africa',    -26.20,  28.04, False),
        ('CPT',  'Cape Town',      'South Africa',    -33.93,  18.42, False),
        ('NBO',  'Nairobi',        'Kenya',            -1.29,  36.82, False),
        ('LOS',  'Lagos',          'Nigeria',           6.52,   3.38, False),
        ('DXB',  'Dubai',          'UAE',              25.20,  55.27, False),
        ('BOM',  'Mumbai',         'India',            19.08,  72.88, False),
        ('DEL',  'New Delhi',      'India',            28.63,  77.22, False),
        ('BLR',  'Bangalore',      'India',            12.97,  77.59, False),
        ('KHI',  'Karachi',        'Pakistan',         24.86,  67.01, False),
        ('ISB',  'Islamabad',      'Pakistan',         33.72,  73.04, False),
        ('BKK',  'Bangkok',        'Thailand',         13.75, 100.52, False),
        ('KUL',  'Kuala Lumpur',   'Malaysia',          3.14, 101.69, False),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, True),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32, 114.17, True),
        ('PEK',  'Beijing',        'China',            39.91, 116.39, False),
        ('SHA',  'Shanghai',       'China',            31.23, 121.47, False),
        ('ICN',  'Seoul',          'South Korea',      37.51, 126.99, False),
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, True),
        ('OSA',  'Osaka',          'Japan',            34.69, 135.50, False),
        ('SYD',  'Sydney',         'Australia',       -33.87, 151.21, False),
        ('MEL',  'Melbourne',      'Australia',       -37.81, 144.96, False),
        ('TPE',  'Taipei',         'Taiwan',           25.05, 121.53, False),
        ('MNL',  'Manila',         'Philippines',      14.60, 120.98, False),
        ('CGK',  'Jakarta',        'Indonesia',        -6.21, 106.85, False),
        ('TLV',  'Tel Aviv',       'Israel',           32.08,  34.78, False),
        ('RUH',  'Riyadh',         'Saudi Arabia',     24.69,  46.72, False),
    ],
    'G': [  # US DoD NIC — 6 sites
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('CMH',  'Columbus',       'United States',    39.96,  -82.99, True),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, False),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, False),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, False),
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, False),
    ],
    'H': [  # US Army Research Lab — 4 sites
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, False),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, False),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, False),
    ],
    'I': [  # Netnod — 49 instances; comprehensive list
        ('ARN',  'Stockholm',      'Sweden',           59.33,  18.07, True),
        ('GOT',  'Gothenburg',     'Sweden',           57.71,  11.97, False),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, False),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, False),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, False),
        ('CDG',  'Paris',          'France',           48.86,   2.35, False),
        ('MXP',  'Milan',          'Italy',            45.47,   9.19, False),
        ('MAD',  'Madrid',         'Spain',            40.42,  -3.70, False),
        ('BCN',  'Barcelona',      'Spain',            41.39,   2.15, False),
        ('VIE',  'Vienna',         'Austria',          48.21,  16.37, False),
        ('PRG',  'Prague',         'Czech Republic',   50.08,  14.44, False),
        ('WAW',  'Warsaw',         'Poland',           52.23,  21.01, False),
        ('BUD',  'Budapest',       'Hungary',          47.50,  19.04, False),
        ('BUH',  'Bucharest',      'Romania',          44.43,  26.11, False),
        ('SOF',  'Sofia',          'Bulgaria',         42.70,  23.32, False),
        ('HEL',  'Helsinki',       'Finland',          60.17,  24.93, False),
        ('OSL',  'Oslo',           'Norway',           59.91,  10.75, False),
        ('CPH',  'Copenhagen',     'Denmark',          55.68,  12.57, False),
        ('DUB',  'Dublin',         'Ireland',          53.33,  -6.25, False),
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, False),
        ('ORD',  'Chicago',        'United States',    41.88,  -87.63, False),
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, False),
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, False),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, False),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32, 114.17, False),
        ('SYD',  'Sydney',         'Australia',       -33.87, 151.21, False),
        ('GRU',  'São Paulo',      'Brazil',          -23.55, -46.63, False),
        ('JNB',  'Johannesburg',   'South Africa',    -26.20,  28.04, False),
        ('DXB',  'Dubai',          'UAE',              25.20,  55.27, False),
        ('BOM',  'Mumbai',         'India',            19.08,  72.88, False),
        ('DEL',  'New Delhi',      'India',            28.63,  77.22, False),
        ('BKK',  'Bangkok',        'Thailand',         13.75, 100.52, False),
        ('KUL',  'Kuala Lumpur',   'Malaysia',          3.14, 101.69, False),
        ('IST',  'Istanbul',       'Turkey',           41.01,  28.95, False),
    ],
    'J': [  # Verisign — 120+ instances; major sites
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, True),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, True),
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, True),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, True),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32, 114.17, True),
        ('GRU',  'São Paulo',      'Brazil',          -23.55, -46.63, True),
        ('SYD',  'Sydney',         'Australia',       -33.87, 151.21, True),
        ('ORD',  'Chicago',        'United States',    41.88,  -87.63, False),
        ('DFW',  'Dallas',         'United States',    32.89,  -97.04, False),
        ('SEA',  'Seattle',        'United States',    47.61, -122.33, False),
        ('MIA',  'Miami',          'United States',    25.77,  -80.19, False),
        ('YYZ',  'Toronto',        'Canada',           43.65,  -79.38, False),
        ('CDG',  'Paris',          'France',           48.86,   2.35, False),
        ('MUC',  'Munich',         'Germany',          48.14,  11.58, False),
        ('ARN',  'Stockholm',      'Sweden',           59.33,  18.07, False),
        ('MAD',  'Madrid',         'Spain',            40.42,  -3.70, False),
        ('VIE',  'Vienna',         'Austria',          48.21,  16.37, False),
        ('PRG',  'Prague',         'Czech Republic',   50.08,  14.44, False),
        ('WAW',  'Warsaw',         'Poland',           52.23,  21.01, False),
        ('JNB',  'Johannesburg',   'South Africa',    -26.20,  28.04, False),
        ('DXB',  'Dubai',          'UAE',              25.20,  55.27, False),
        ('BOM',  'Mumbai',         'India',            19.08,  72.88, False),
        ('ICN',  'Seoul',          'South Korea',      37.51, 126.99, False),
        ('BKK',  'Bangkok',        'Thailand',         13.75, 100.52, False),
        ('KUL',  'Kuala Lumpur',   'Malaysia',          3.14, 101.69, False),
        ('SCL',  'Santiago',       'Chile',           -33.45, -70.67, False),
        ('BOG',  'Bogotá',         'Colombia',          4.71, -74.07, False),
        ('GIG',  'Rio de Janeiro', 'Brazil',          -22.91, -43.17, False),
        ('TPE',  'Taipei',         'Taiwan',           25.05, 121.53, False),
    ],
    'K': [  # RIPE NCC — 72 instances; comprehensive list
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, True),
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, True),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, True),
        ('CDG',  'Paris',          'France',           48.86,   2.35, False),
        ('CPH',  'Copenhagen',     'Denmark',          55.68,  12.57, False),
        ('DUB',  'Dublin',         'Ireland',          53.33,  -6.25, False),
        ('GRU',  'São Paulo',      'Brazil',          -23.55, -46.63, False),
        ('HEL',  'Helsinki',       'Finland',          60.17,  24.93, False),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32, 114.17, False),
        ('ICN',  'Seoul',          'South Korea',      37.51, 126.99, False),
        ('IST',  'Istanbul',       'Turkey',           41.01,  28.95, False),
        ('JNB',  'Johannesburg',   'South Africa',    -26.20,  28.04, False),
        ('KHI',  'Karachi',        'Pakistan',         24.86,  67.01, False),
        ('KUL',  'Kuala Lumpur',   'Malaysia',          3.14, 101.69, False),
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, False),
        ('LIM',  'Lima',           'Peru',            -12.05, -77.04, False),
        ('MAD',  'Madrid',         'Spain',            40.42,  -3.70, False),
        ('MEX',  'Mexico City',    'Mexico',           19.43, -99.13, False),
        ('MIA',  'Miami',          'United States',    25.77, -80.19, False),
        ('MNL',  'Manila',         'Philippines',      14.60, 120.98, False),
        ('MUC',  'Munich',         'Germany',          48.14,  11.58, False),
        ('NBO',  'Nairobi',        'Kenya',            -1.29,  36.82, False),
        ('ORD',  'Chicago',        'United States',    41.88, -87.63, False),
        ('OSL',  'Oslo',           'Norway',           59.91,  10.75, False),
        ('PRG',  'Prague',         'Czech Republic',   50.08,  14.44, False),
        ('RUH',  'Riyadh',         'Saudi Arabia',     24.69,  46.72, False),
        ('SCL',  'Santiago',       'Chile',           -33.45, -70.67, False),
        ('SOF',  'Sofia',          'Bulgaria',         42.70,  23.32, False),
        ('ARN',  'Stockholm',      'Sweden',           59.33,  18.07, False),
        ('SYD',  'Sydney',         'Australia',       -33.87, 151.21, False),
        ('VIE',  'Vienna',         'Austria',          48.21,  16.37, False),
        ('WAW',  'Warsaw',         'Poland',           52.23,  21.01, False),
        ('YYZ',  'Toronto',        'Canada',           43.65, -79.38, False),
        ('ZRH',  'Zurich',         'Switzerland',      47.38,   8.54, False),
        ('BOM',  'Mumbai',         'India',            19.08,  72.88, False),
        ('DEL',  'New Delhi',      'India',            28.63,  77.22, False),
        ('BKK',  'Bangkok',        'Thailand',         13.75, 100.52, False),
        ('CAI',  'Cairo',          'Egypt',            30.04,  31.24, False),
        ('CPT',  'Cape Town',      'South Africa',    -33.93,  18.42, False),
        ('DXB',  'Dubai',          'UAE',              25.20,  55.27, False),
        ('BOG',  'Bogotá',         'Colombia',          4.71, -74.07, False),
        ('BUE',  'Buenos Aires',   'Argentina',       -34.61, -58.39, False),
        ('AKL',  'Auckland',       'New Zealand',     -36.85, 174.76, False),
        ('TPE',  'Taipei',         'Taiwan',           25.05, 121.53, False),
        ('NBO',  'Nairobi',        'Kenya',            -1.29,  36.82, False),
    ],
    'L': [  # ICANN — 200+ instances; major and representative sites
        ('LAX',  'Los Angeles',    'United States',    34.05, -118.24, True),
        ('IAD',  'Ashburn',        'United States',    39.04,  -77.49, True),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, True),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, True),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, True),
        ('GRU',  'São Paulo',      'Brazil',          -23.55, -46.63, True),
        ('SYD',  'Sydney',         'Australia',       -33.87, 151.21, True),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32, 114.17, True),
        ('JNB',  'Johannesburg',   'South Africa',    -26.20,  28.04, True),
        ('DXB',  'Dubai',          'UAE',              25.20,  55.27, True),
        ('ORD',  'Chicago',        'United States',    41.88, -87.63, False),
        ('DFW',  'Dallas',         'United States',    32.89, -97.04, False),
        ('SEA',  'Seattle',        'United States',    47.61,-122.33, False),
        ('MIA',  'Miami',          'United States',    25.77, -80.19, False),
        ('YYZ',  'Toronto',        'Canada',           43.65, -79.38, False),
        ('YUL',  'Montreal',       'Canada',           45.51, -73.55, False),
        ('MEX',  'Mexico City',    'Mexico',           19.43, -99.13, False),
        ('BOG',  'Bogotá',         'Colombia',          4.71, -74.07, False),
        ('SCL',  'Santiago',       'Chile',           -33.45, -70.67, False),
        ('LIM',  'Lima',           'Peru',            -12.05, -77.04, False),
        ('BUE',  'Buenos Aires',   'Argentina',       -34.61, -58.39, False),
        ('CDG',  'Paris',          'France',           48.86,   2.35, False),
        ('MUC',  'Munich',         'Germany',          48.14,  11.58, False),
        ('MXP',  'Milan',          'Italy',            45.47,   9.19, False),
        ('MAD',  'Madrid',         'Spain',            40.42,  -3.70, False),
        ('BCN',  'Barcelona',      'Spain',            41.39,   2.15, False),
        ('ARN',  'Stockholm',      'Sweden',           59.33,  18.07, False),
        ('OSL',  'Oslo',           'Norway',           59.91,  10.75, False),
        ('CPH',  'Copenhagen',     'Denmark',          55.68,  12.57, False),
        ('HEL',  'Helsinki',       'Finland',          60.17,  24.93, False),
        ('DUB',  'Dublin',         'Ireland',          53.33,  -6.25, False),
        ('LIS',  'Lisbon',         'Portugal',         38.72,  -9.14, False),
        ('WAW',  'Warsaw',         'Poland',           52.23,  21.01, False),
        ('PRG',  'Prague',         'Czech Republic',   50.08,  14.44, False),
        ('BUD',  'Budapest',       'Hungary',          47.50,  19.04, False),
        ('VIE',  'Vienna',         'Austria',          48.21,  16.37, False),
        ('ZRH',  'Zurich',         'Switzerland',      47.38,   8.54, False),
        ('GVA',  'Geneva',         'Switzerland',      46.20,   6.14, False),
        ('IST',  'Istanbul',       'Turkey',           41.01,  28.95, False),
        ('KUL',  'Kuala Lumpur',   'Malaysia',          3.14, 101.69, False),
        ('BKK',  'Bangkok',        'Thailand',         13.75, 100.52, False),
        ('DEL',  'New Delhi',      'India',            28.63,  77.22, False),
        ('BOM',  'Mumbai',         'India',            19.08,  72.88, False),
        ('BLR',  'Bangalore',      'India',            12.97,  77.59, False),
        ('ICN',  'Seoul',          'South Korea',      37.51, 126.99, False),
        ('TPE',  'Taipei',         'Taiwan',           25.05, 121.53, False),
        ('PEK',  'Beijing',        'China',            39.91, 116.39, False),
        ('SHA',  'Shanghai',       'China',            31.23, 121.47, False),
        ('MNL',  'Manila',         'Philippines',      14.60, 120.98, False),
        ('CGK',  'Jakarta',        'Indonesia',        -6.21, 106.85, False),
        ('MEL',  'Melbourne',      'Australia',       -37.81, 144.96, False),
        ('AKL',  'Auckland',       'New Zealand',     -36.85, 174.76, False),
        ('NBO',  'Nairobi',        'Kenya',            -1.29,  36.82, False),
        ('CPT',  'Cape Town',      'South Africa',    -33.93,  18.42, False),
        ('CAI',  'Cairo',          'Egypt',            30.04,  31.24, False),
        ('LOS',  'Lagos',          'Nigeria',           6.52,   3.38, False),
        ('RUH',  'Riyadh',         'Saudi Arabia',     24.69,  46.72, False),
        ('TLV',  'Tel Aviv',       'Israel',           32.08,  34.78, False),
    ],
    'M': [  # WIDE Project — 150+ instances; major sites
        ('NRT',  'Tokyo',          'Japan',            35.68, 139.69, True),
        ('OSA',  'Osaka',          'Japan',            34.69, 135.50, True),
        ('SIN',  'Singapore',      'Singapore',         1.35, 103.82, True),
        ('IAD',  'Ashburn',        'United States',    39.04, -77.49, True),
        ('LAX',  'Los Angeles',    'United States',    34.05,-118.24, True),
        ('AMS',  'Amsterdam',      'Netherlands',      52.37,   4.90, True),
        ('FRA',  'Frankfurt',      'Germany',          50.11,   8.68, True),
        ('LHR',  'London',         'United Kingdom',   51.51,  -0.13, True),
        ('ICN',  'Seoul',          'South Korea',      37.51, 126.99, False),
        ('TPE',  'Taipei',         'Taiwan',           25.05, 121.53, False),
        ('HKG',  'Hong Kong',      'Hong Kong',        22.32, 114.17, False),
        ('BKK',  'Bangkok',        'Thailand',         13.75, 100.52, False),
        ('KUL',  'Kuala Lumpur',   'Malaysia',          3.14, 101.69, False),
        ('MNL',  'Manila',         'Philippines',      14.60, 120.98, False),
        ('BOM',  'Mumbai',         'India',            19.08,  72.88, False),
        ('DEL',  'New Delhi',      'India',            28.63,  77.22, False),
        ('SYD',  'Sydney',         'Australia',       -33.87, 151.21, False),
        ('MEL',  'Melbourne',      'Australia',       -37.81, 144.96, False),
        ('PEK',  'Beijing',        'China',            39.91, 116.39, False),
        ('SHA',  'Shanghai',       'China',            31.23, 121.47, False),
        ('CDG',  'Paris',          'France',           48.86,   2.35, False),
        ('MAD',  'Madrid',         'Spain',            40.42,  -3.70, False),
        ('ARN',  'Stockholm',      'Sweden',           59.33,  18.07, False),
        ('DXB',  'Dubai',          'UAE',              25.20,  55.27, False),
        ('GRU',  'São Paulo',      'Brazil',          -23.55, -46.63, False),
        ('JNB',  'Johannesburg',   'South Africa',    -26.20,  28.04, False),
        ('YYZ',  'Toronto',        'Canada',           43.65, -79.38, False),
        ('ORD',  'Chicago',        'United States',    41.88, -87.63, False),
        ('MIA',  'Miami',          'United States',    25.77, -80.19, False),
        ('NBO',  'Nairobi',        'Kenya',            -1.29,  36.82, False),
        ('IST',  'Istanbul',       'Turkey',           41.01,  28.95, False),
        ('CAI',  'Cairo',          'Egypt',            30.04,  31.24, False),
        ('CGK',  'Jakarta',        'Indonesia',        -6.21, 106.85, False),
        ('AKL',  'Auckland',       'New Zealand',     -36.85, 174.76, False),
    ],
}

# ── Resolver PoP data ──────────────────────────────────────────────────────────
# Sources: Cloudflare network page, Google Cloud PoP docs, Quad9 node map,
# Cisco/OpenDNS published data center list.
# Format: (city, country, lat, lon)

RESOLVER_POPS = {
    'Cloudflare': {
        'ip': '1.1.1.1',
        'pops': [
            # North America
            ('Anchorage',      'United States',    61.22,-149.90), ('Ashburn',       'United States',    39.04, -77.49),
            ('Atlanta',        'United States',    33.75, -84.39), ('Boston',        'United States',    42.36, -71.06),
            ('Calgary',        'Canada',           51.05,-114.07), ('Charlotte',     'United States',    35.23, -80.84),
            ('Chicago',        'United States',    41.88, -87.63), ('Columbus',      'United States',    39.96, -82.99),
            ('Dallas',         'United States',    32.89, -97.04), ('Denver',        'United States',    39.74,-104.99),
            ('Detroit',        'United States',    42.33, -83.05), ('Edmonton',      'Canada',           53.55,-113.47),
            ('Honolulu',       'United States',    21.30,-157.86), ('Houston',       'United States',    29.76, -95.37),
            ('Indianapolis',   'United States',    39.77, -86.16), ('Jacksonville',  'United States',    30.33, -81.66),
            ('Kansas City',    'United States',    39.10, -94.58), ('Las Vegas',     'United States',    36.17,-115.14),
            ('Los Angeles',    'United States',    34.05,-118.24), ('Memphis',       'United States',    35.15, -90.05),
            ('Mexico City',    'Mexico',           19.43, -99.13), ('Miami',         'United States',    25.77, -80.19),
            ('Minneapolis',    'United States',    44.98, -93.27), ('Monterrey',     'Mexico',           25.67,-100.31),
            ('Montréal',       'Canada',           45.51, -73.55), ('Nashville',     'United States',    36.17, -86.78),
            ('Newark',         'United States',    40.74, -74.17), ('New York',      'United States',    40.71, -74.01),
            ('Orlando',        'United States',    28.54, -81.38), ('Phoenix',       'United States',    33.45,-112.07),
            ('Pittsburgh',     'United States',    40.44, -79.99), ('Portland',      'United States',    45.52,-122.68),
            ('Querétaro',      'Mexico',           20.59,-100.39), ('Raleigh',       'United States',    35.78, -78.64),
            ('Sacramento',     'United States',    38.58,-121.49), ('Salt Lake City','United States',    40.76,-111.89),
            ('San José',       'Costa Rica',        9.93, -84.08), ('San Juan',      'Puerto Rico',      18.47, -66.11),
            ('San Jose',       'United States',    37.34,-121.89), ('Seattle',       'United States',    47.61,-122.33),
            ('Tampa',          'United States',    27.95, -82.46), ('Toronto',       'Canada',           43.65, -79.38),
            ('Vancouver',      'Canada',           49.25,-123.12), ('Washington DC', 'United States',    38.91, -77.04),
            ('Winnipeg',       'Canada',           49.90, -97.14), ('Guadalajara',   'Mexico',           20.68,-103.35),
            # South America
            ('Bogotá',         'Colombia',          4.71, -74.07), ('Buenos Aires',  'Argentina',       -34.61, -58.39),
            ('Fortaleza',      'Brazil',           -3.72, -38.54), ('Lima',          'Peru',            -12.05, -77.04),
            ('Medellín',       'Colombia',          6.25, -75.57), ('Panama City',   'Panama',            8.99, -79.52),
            ('Recife',         'Brazil',           -8.05, -34.88), ('Rio de Janeiro','Brazil',          -22.91, -43.17),
            ('Santiago',       'Chile',           -33.45, -70.67), ('São Paulo',     'Brazil',          -23.55, -46.63),
            # Europe
            ('Amsterdam',      'Netherlands',      52.37,   4.90), ('Athens',        'Greece',           37.97,  23.73),
            ('Barcelona',      'Spain',            41.39,   2.15), ('Belgrade',      'Serbia',           44.80,  20.47),
            ('Berlin',         'Germany',          52.52,  13.40), ('Brussels',      'Belgium',          50.85,   4.35),
            ('Bucharest',      'Romania',          44.43,  26.11), ('Budapest',      'Hungary',          47.50,  19.04),
            ('Copenhagen',     'Denmark',          55.68,  12.57), ('Dublin',        'Ireland',          53.33,  -6.25),
            ('Frankfurt',      'Germany',          50.11,   8.68), ('Geneva',        'Switzerland',      46.20,   6.14),
            ('Hamburg',        'Germany',          53.55,  10.00), ('Helsinki',      'Finland',          60.17,  24.93),
            ('Istanbul',       'Turkey',           41.01,  28.95), ('Kyiv',          'Ukraine',          50.45,  30.52),
            ('Lisbon',         'Portugal',         38.72,  -9.14), ('London',        'United Kingdom',   51.51,  -0.13),
            ('Luxembourg',     'Luxembourg',       49.61,   6.13), ('Madrid',        'Spain',            40.42,  -3.70),
            ('Manchester',     'United Kingdom',   53.48,  -2.24), ('Marseille',     'France',           43.30,   5.37),
            ('Milan',          'Italy',            45.47,   9.19), ('Moscow',        'Russia',           55.75,  37.62),
            ('Munich',         'Germany',          48.14,  11.58), ('Oslo',          'Norway',           59.91,  10.75),
            ('Paris',          'France',           48.86,   2.35), ('Prague',        'Czech Republic',   50.08,  14.44),
            ('Riga',           'Latvia',           56.95,  24.11), ('Rome',          'Italy',            41.90,  12.50),
            ('Sofia',          'Bulgaria',         42.70,  23.32), ('Stockholm',     'Sweden',           59.33,  18.07),
            ('Tallinn',        'Estonia',          59.44,  24.75), ('Vienna',        'Austria',          48.21,  16.37),
            ('Warsaw',         'Poland',           52.23,  21.01), ('Zagreb',        'Croatia',          45.81,  15.98),
            ('Zurich',         'Switzerland',      47.38,   8.54),
            # Asia-Pacific
            ('Auckland',       'New Zealand',     -36.85, 174.76), ('Bangalore',     'India',            12.97,  77.59),
            ('Bangkok',        'Thailand',         13.75, 100.52), ('Beijing',       'China',            39.91, 116.39),
            ('Brisbane',       'Australia',       -27.47, 153.02), ('Chengdu',       'China',            30.57, 104.07),
            ('Colombo',        'Sri Lanka',         6.93,  79.85), ('Dhaka',         'Bangladesh',       23.81,  90.41),
            ('Fukuoka',        'Japan',            33.59, 130.40), ('Guangzhou',     'China',            23.13, 113.26),
            ('Hanoi',          'Vietnam',          21.03, 105.85), ('Ho Chi Minh',   'Vietnam',          10.82, 106.63),
            ('Hong Kong',      'Hong Kong',        22.32, 114.17), ('Hyderabad',     'India',            17.39,  78.48),
            ('Jakarta',        'Indonesia',        -6.21, 106.85), ('Karachi',       'Pakistan',         24.86,  67.01),
            ('Kuala Lumpur',   'Malaysia',          3.14, 101.69), ('Kuwait City',   'Kuwait',           29.37,  47.98),
            ('Manila',         'Philippines',      14.60, 120.98), ('Melbourne',     'Australia',       -37.81, 144.96),
            ('Mumbai',         'India',            19.08,  72.88), ('Nagoya',        'Japan',            35.18, 136.91),
            ('New Delhi',      'India',            28.63,  77.22), ('Osaka',         'Japan',            34.69, 135.50),
            ('Perth',          'Australia',       -31.95, 115.86), ('Seoul',         'South Korea',      37.51, 126.99),
            ('Shanghai',       'China',            31.23, 121.47), ('Singapore',     'Singapore',         1.35, 103.82),
            ('Sydney',         'Australia',       -33.87, 151.21), ('Taipei',        'Taiwan',           25.05, 121.53),
            ('Tokyo',          'Japan',            35.68, 139.69), ('Wellington',    'New Zealand',     -41.29, 174.78),
            # Middle East & Africa
            ('Accra',          'Ghana',             5.56,  -0.20), ('Addis Ababa',   'Ethiopia',          9.03,  38.74),
            ('Amman',          'Jordan',           31.95,  35.93), ('Bahrain',       'Bahrain',          26.07,  50.56),
            ('Cairo',          'Egypt',            30.04,  31.24), ('Cape Town',     'South Africa',    -33.93,  18.42),
            ('Casablanca',     'Morocco',          33.59,  -7.62), ('Dakar',         'Senegal',          14.69, -17.44),
            ('Dar es Salaam',  'Tanzania',         -6.79,  39.21), ('Djibouti',      'Djibouti',         11.59,  43.15),
            ('Doha',           'Qatar',            25.29,  51.53), ('Dubai',         'UAE',              25.20,  55.27),
            ('Johannesburg',   'South Africa',    -26.20,  28.04), ('Lagos',         'Nigeria',           6.52,   3.38),
            ('Mombasa',        'Kenya',            -4.05,  39.67), ('Muscat',        'Oman',             23.61,  58.59),
            ('Nairobi',        'Kenya',            -1.29,  36.82), ('Riyadh',        'Saudi Arabia',     24.69,  46.72),
            ('Tunis',          'Tunisia',          36.82,  10.17),
        ],
    },
    'Google': {
        'ip': '8.8.8.8',
        'pops': [
            ('Ashburn',        'United States',    39.04, -77.49), ('Atlanta',       'United States',    33.75, -84.39),
            ('Chicago',        'United States',    41.88, -87.63), ('Dallas',        'United States',    32.89, -97.04),
            ('Denver',         'United States',    39.74,-104.99), ('Kansas City',   'United States',    39.10, -94.58),
            ('Los Angeles',    'United States',    34.05,-118.24), ('Miami',         'United States',    25.77, -80.19),
            ('Mountain View',  'United States',    37.39,-122.08), ('New York',      'United States',    40.71, -74.01),
            ('Seattle',        'United States',    47.61,-122.33), ('Washington DC', 'United States',    38.91, -77.04),
            ('Toronto',        'Canada',           43.65, -79.38), ('São Paulo',     'Brazil',          -23.55, -46.63),
            ('Buenos Aires',   'Argentina',       -34.61, -58.39), ('Santiago',      'Chile',           -33.45, -70.67),
            ('Amsterdam',      'Netherlands',      52.37,   4.90), ('Dublin',        'Ireland',          53.33,  -6.25),
            ('Frankfurt',      'Germany',          50.11,   8.68), ('London',        'United Kingdom',   51.51,  -0.13),
            ('Madrid',         'Spain',            40.42,  -3.70), ('Milan',         'Italy',            45.47,   9.19),
            ('Paris',          'France',           48.86,   2.35), ('Stockholm',     'Sweden',           59.33,  18.07),
            ('Warsaw',         'Poland',           52.23,  21.01), ('Zurich',        'Switzerland',      47.38,   8.54),
            ('Bangalore',      'India',            12.97,  77.59), ('Chennai',       'India',            13.08,  80.27),
            ('Mumbai',         'India',            19.08,  72.88), ('New Delhi',     'India',            28.63,  77.22),
            ('Hong Kong',      'Hong Kong',        22.32, 114.17), ('Jakarta',       'Indonesia',        -6.21, 106.85),
            ('Kuala Lumpur',   'Malaysia',          3.14, 101.69), ('Osaka',         'Japan',            34.69, 135.50),
            ('Seoul',          'South Korea',      37.51, 126.99), ('Singapore',     'Singapore',         1.35, 103.82),
            ('Sydney',         'Australia',       -33.87, 151.21), ('Taipei',        'Taiwan',           25.05, 121.53),
            ('Tokyo',          'Japan',            35.68, 139.69), ('Cape Town',     'South Africa',    -33.93,  18.42),
            ('Johannesburg',   'South Africa',    -26.20,  28.04), ('Nairobi',       'Kenya',            -1.29,  36.82),
            ('Lagos',          'Nigeria',           6.52,   3.38), ('Dubai',         'UAE',              25.20,  55.27),
        ],
    },
    'Quad9': {
        'ip': '9.9.9.9',
        'pops': [
            ('Ashburn',        'United States',    39.04, -77.49), ('Atlanta',       'United States',    33.75, -84.39),
            ('Chicago',        'United States',    41.88, -87.63), ('Dallas',        'United States',    32.89, -97.04),
            ('Denver',         'United States',    39.74,-104.99), ('Los Angeles',   'United States',    34.05,-118.24),
            ('Miami',          'United States',    25.77, -80.19), ('New York',      'United States',    40.71, -74.01),
            ('Phoenix',        'United States',    33.45,-112.07), ('San Jose',      'United States',    37.34,-121.89),
            ('Seattle',        'United States',    47.61,-122.33), ('Toronto',       'Canada',           43.65, -79.38),
            ('Montréal',       'Canada',           45.51, -73.55), ('São Paulo',     'Brazil',          -23.55, -46.63),
            ('Buenos Aires',   'Argentina',       -34.61, -58.39), ('Santiago',      'Chile',           -33.45, -70.67),
            ('Bogotá',         'Colombia',          4.71, -74.07), ('Lima',          'Peru',            -12.05, -77.04),
            ('Amsterdam',      'Netherlands',      52.37,   4.90), ('Athens',        'Greece',           37.97,  23.73),
            ('Berlin',         'Germany',          52.52,  13.40), ('Brussels',      'Belgium',          50.85,   4.35),
            ('Bucharest',      'Romania',          44.43,  26.11), ('Budapest',      'Hungary',          47.50,  19.04),
            ('Copenhagen',     'Denmark',          55.68,  12.57), ('Dublin',        'Ireland',          53.33,  -6.25),
            ('Frankfurt',      'Germany',          50.11,   8.68), ('Geneva',        'Switzerland',      46.20,   6.14),
            ('Hamburg',        'Germany',          53.55,  10.00), ('Helsinki',      'Finland',          60.17,  24.93),
            ('Istanbul',       'Turkey',           41.01,  28.95), ('Kyiv',          'Ukraine',          50.45,  30.52),
            ('London',         'United Kingdom',   51.51,  -0.13), ('Madrid',        'Spain',            40.42,  -3.70),
            ('Milan',          'Italy',            45.47,   9.19), ('Moscow',        'Russia',           55.75,  37.62),
            ('Munich',         'Germany',          48.14,  11.58), ('Oslo',          'Norway',           59.91,  10.75),
            ('Paris',          'France',           48.86,   2.35), ('Prague',        'Czech Republic',   50.08,  14.44),
            ('Rome',           'Italy',            41.90,  12.50), ('Riyadh',        'Saudi Arabia',     24.69,  46.72),
            ('Sofia',          'Bulgaria',         42.70,  23.32), ('Stockholm',     'Sweden',           59.33,  18.07),
            ('Vienna',         'Austria',          48.21,  16.37), ('Warsaw',        'Poland',           52.23,  21.01),
            ('Zurich',         'Switzerland',      47.38,   8.54), ('Bangalore',     'India',            12.97,  77.59),
            ('Bangkok',        'Thailand',         13.75, 100.52), ('Beijing',       'China',            39.91, 116.39),
            ('Dubai',          'UAE',              25.20,  55.27), ('Hong Kong',     'Hong Kong',        22.32, 114.17),
            ('Jakarta',        'Indonesia',        -6.21, 106.85), ('Johannesburg',  'South Africa',    -26.20,  28.04),
            ('Karachi',        'Pakistan',         24.86,  67.01), ('Kuala Lumpur',  'Malaysia',          3.14, 101.69),
            ('Manila',         'Philippines',      14.60, 120.98), ('Melbourne',     'Australia',       -37.81, 144.96),
            ('Mumbai',         'India',            19.08,  72.88), ('Nairobi',       'Kenya',            -1.29,  36.82),
            ('New Delhi',      'India',            28.63,  77.22), ('Osaka',         'Japan',            34.69, 135.50),
            ('Seoul',          'South Korea',      37.51, 126.99), ('Shanghai',      'China',            31.23, 121.47),
            ('Singapore',      'Singapore',         1.35, 103.82), ('Sydney',        'Australia',       -33.87, 151.21),
            ('Taipei',         'Taiwan',           25.05, 121.53), ('Tokyo',         'Japan',            35.68, 139.69),
            ('Cairo',          'Egypt',            30.04,  31.24), ('Cape Town',     'South Africa',    -33.93,  18.42),
            ('Lagos',          'Nigeria',           6.52,   3.38),
        ],
    },
    'OpenDNS': {
        'ip': '208.67.222.222',
        'pops': [
            ('Ashburn',        'United States',    39.04, -77.49), ('Atlanta',       'United States',    33.75, -84.39),
            ('Chicago',        'United States',    41.88, -87.63), ('Dallas',        'United States',    32.89, -97.04),
            ('Denver',         'United States',    39.74,-104.99), ('Los Angeles',   'United States',    34.05,-118.24),
            ('Miami',          'United States',    25.77, -80.19), ('New York',      'United States',    40.71, -74.01),
            ('Phoenix',        'United States',    33.45,-112.07), ('San Jose',      'United States',    37.34,-121.89),
            ('Seattle',        'United States',    47.61,-122.33), ('Washington DC', 'United States',    38.91, -77.04),
            ('Toronto',        'Canada',           43.65, -79.38), ('São Paulo',     'Brazil',          -23.55, -46.63),
            ('Buenos Aires',   'Argentina',       -34.61, -58.39), ('Amsterdam',     'Netherlands',      52.37,   4.90),
            ('Dublin',         'Ireland',          53.33,  -6.25), ('Frankfurt',     'Germany',          50.11,   8.68),
            ('London',         'United Kingdom',   51.51,  -0.13), ('Madrid',        'Spain',            40.42,  -3.70),
            ('Paris',          'France',           48.86,   2.35), ('Stockholm',     'Sweden',           59.33,  18.07),
            ('Zurich',         'Switzerland',      47.38,   8.54), ('Dubai',         'UAE',              25.20,  55.27),
            ('Hong Kong',      'Hong Kong',        22.32, 114.17), ('Mumbai',        'India',            19.08,  72.88),
            ('Seoul',          'South Korea',      37.51, 126.99), ('Singapore',     'Singapore',         1.35, 103.82),
            ('Sydney',         'Australia',       -33.87, 151.21), ('Tokyo',         'Japan',            35.68, 139.69),
            ('Johannesburg',   'South Africa',    -26.20,  28.04), ('Nairobi',       'Kenya',            -1.29,  36.82),
        ],
    },
}


# ── GeoJSON builders ──────────────────────────────────────────────────────────

def build_root_instances(scraped):
    """
    Build dns-root-instances.geojson.
    scraped: dict of letter → list of (site, city, country, is_global) from live scrape.
    Falls back to FALLBACK_INSTANCES for any letter with insufficient scraped data.
    """
    features = []
    for letter, (fqdn, operator) in ROOT_SERVER_OPERATORS.items():
        live = scraped.get(letter, [])
        if len(live) >= 2:
            # Use scraped data; geocode cities on the fly
            for site, city, country, is_global in live:
                coords = geocode(city)
                if not coords:
                    continue
                lat, lon = coords
                features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                    'properties': {
                        'name':     f'{letter}-Root ({site or city})',
                        'letter':   letter,
                        'operator': operator,
                        'city':     city,
                        'country':  country,
                        'isGlobal': is_global,
                    },
                })
        else:
            # Use hardcoded fallback
            for site, city, country, lat, lon, is_global in FALLBACK_INSTANCES.get(letter, []):
                features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                    'properties': {
                        'name':     f'{letter}-Root ({site})',
                        'letter':   letter,
                        'operator': operator,
                        'city':     city,
                        'country':  country,
                        'isGlobal': is_global,
                    },
                })
    return {'type': 'FeatureCollection', 'features': features}


def build_resolvers():
    """Build dns-resolvers.geojson from hardcoded RESOLVER_POPS."""
    features = []
    for provider, info in RESOLVER_POPS.items():
        ip = info['ip']
        for city, country, lat, lon in info['pops']:
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                'properties': {
                    'name':     f'{provider} — {city}',
                    'provider': provider,
                    'ip':       ip,
                    'city':     city,
                    'country':  country,
                },
            })
    return {'type': 'FeatureCollection', 'features': features}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # ── Root server instances ─────────────────────────────────────────────────
    print('Fetching root server instances from root-servers.org…')
    scraped = {}
    for letter in ROOT_SERVER_OPERATORS:
        print(f'  {letter}…', end=' ', flush=True)
        result = scrape_letter(letter)
        if result:
            scraped[letter] = result
            print(f'{len(result)} scraped')
        else:
            print('using fallback')

    root_fc = build_root_instances(scraped)
    live_ct     = sum(len(v) for v in scraped.values())
    fallback_ct = sum(len(v) for v in FALLBACK_INSTANCES.values()) - live_ct
    total_root  = len(root_fc['features'])

    out = os.path.join(OUT_DIR, 'dns-root-instances.geojson')
    with open(out, 'w') as f:
        json.dump(root_fc, f, separators=(',', ':'))
    print(f'\n  {total_root} root server instances → {out}')
    print(f'  ({live_ct} from live scrape, remaining from hardcoded fallback)')

    # ── Resolver PoPs ─────────────────────────────────────────────────────────
    print('\nBuilding resolver PoP dataset (hardcoded)…')
    resolver_fc = build_resolvers()
    total_res = len(resolver_fc['features'])

    out = os.path.join(OUT_DIR, 'dns-resolvers.geojson')
    with open(out, 'w') as f:
        json.dump(resolver_fc, f, separators=(',', ':'))

    for provider, info in RESOLVER_POPS.items():
        print(f'  {provider} ({info["ip"]}): {len(info["pops"])} PoPs')
    print(f'  {total_res} resolver PoPs total → {out}')

    print('\nDone.')


if __name__ == '__main__':
    main()
