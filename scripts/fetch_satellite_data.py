#!/usr/bin/env python3
"""
Fetch TLE satellite data from CelesTrak and write static ground station GeoJSON.

Outputs (all to ../public/)
────────────────────────────
  starlink-tle.json       — {generatedAt, satellites:[{name, tle1, tle2}, …]}
  oneweb-tle.json         — {generatedAt, satellites:[{name, tle1, tle2}, …]}
  geo-commsats-tle.json   — {generatedAt, satellites:[{name, tle1, tle2}, …]}
  kuiper-tle.json         — {generatedAt, satellites:[{name, tle1, tle2}, …]}
  iss-tle.json            — {generatedAt, satellites:[{name, tle1, tle2}]}
  ground-stations.geojson — GeoJSON FeatureCollection of gateway sites

Usage
─────
  python3 fetch_satellite_data.py

Refresh cadence
───────────────
  Run this script periodically (daily for LEO, weekly for GEO) to keep the
  static TLE files current. TLEs lose accuracy over time as atmospheric drag
  and manoeuvres cause the real orbit to diverge from the two-line elements:
    • LEO (Starlink, OneWeb) — significant drift within a few days; refresh daily
    • GEO                   — very stable; weekly refresh is sufficient

  The React app loads these files at startup and never fetches from CelesTrak
  directly. Fetching in the browser would fail due to CelesTrak's CORS policy,
  and hitting the API on every page load would also be unnecessarily aggressive.
  Run this script in CI, a cron job, or manually before deploying.

Ground station sources
──────────────────────
  Each entry in GROUND_STATIONS carries a source tag for per-entry provenance.
  Source constants:
    SRC_FCC     — SpaceX FCC licence applications (public record; dockets
                  SAT-LOA-20161115-00118, SAT-MOD-20190830-00087, etc.)
    SRC_PRESS   — SpaceX / OneWeb press releases or regulatory filings
    SRC_ONEWEB  — OneWeb regulatory filing or press release
    SRC_IMAGERY — Corroborated via public satellite imagery analysis
    SRC_INFER   — City-level approximation from publicly confirmed service area
"""

import datetime
import json
import os
import ssl
import urllib.request

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')
HEADERS = {'User-Agent': 'ProjectBackbone/1.0 (educational)'}

_SSL_CTX = ssl.create_default_context()

CELESTRAK_GROUPS = {
    'starlink':    'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle',
    'oneweb':      'https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=tle',
    'geo':         'https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=tle',
    # ISS fetched by NORAD catalogue number (25544) — single-satellite TLE
    'iss':         'https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle',
    # Project Kuiper — Amazon's LEO broadband constellation
    # Planned: 3,236 satellites across three shells:
    #   590 km (784 sats), 610 km (1,296 sats), 630 km (1,156 sats)
    # CelesTrak may not have a dedicated group until deployment scales up.
    # fetch_kuiper() below implements a three-source fallback chain.
    'kuiper':      'https://celestrak.org/NORAD/elements/gp.php?GROUP=amazon-kuiper&FORMAT=tle',
}

# Fallback sources for Kuiper (tried in order if primary group is missing/empty)
KUIPER_SUPPLEMENTAL = 'https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=kuiper&FORMAT=tle'
KUIPER_ACTIVE       = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'

OUTPUT_FILES = {
    'starlink': 'starlink-tle.json',
    'oneweb':   'oneweb-tle.json',
    'geo':      'geo-commsats-tle.json',
    'iss':      'iss-tle.json',
    'kuiper':   'kuiper-tle.json',
}


# ── TLE fetch ────────────────────────────────────────────────────────────────

def fetch_tle(url):
    """Download a TLE file and parse into [{name, tle1, tle2}] list."""
    if not url.startswith('https://'):
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    print(f'  GET {url}')
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as r:
        text = r.read().decode('utf-8', errors='replace')

    lines  = [l.rstrip() for l in text.splitlines() if l.strip()]
    sats   = []
    i      = 0
    while i + 2 < len(lines):
        name = lines[i].strip()
        tle1 = lines[i + 1].strip()
        tle2 = lines[i + 2].strip()
        if tle1.startswith('1 ') and tle2.startswith('2 '):
            sats.append({'name': name, 'tle1': tle1, 'tle2': tle2})
            i += 3
        else:
            i += 1   # re-sync if malformed
    return sats


# ── Kuiper fetch (fallback chain) ────────────────────────────────────────────

def fetch_kuiper():
    """
    Fetch Project Kuiper TLEs with a three-source fallback chain.

    Amazon's Kuiper constellation is in early deployment as of 2026.  The
    CelesTrak GROUP=amazon-kuiper endpoint may not yet exist or may return only
    a handful of satellites.  If the dataset is small (< 10 sats), that is
    expected — Kuiper will grow significantly through Amazon's planned launches
    in 2026–2027.

    Re-run this script after each Kuiper launch batch to pick up new objects;
    the refresh pattern is identical to the existing Starlink / OneWeb pipeline.

    TODO: when the constellation exceeds ~100 satellites, move propagation into
    a Web Worker (same threshold used for Starlink optimisation in the hook).
    """
    # ① CelesTrak dedicated group
    try:
        sats = fetch_tle(CELESTRAK_GROUPS['kuiper'])
        if sats:
            return sats
    except Exception as e:
        print(f'    Primary group failed: {e}')

    # ② CelesTrak supplemental catalog
    try:
        print(f'    Trying supplemental catalog: {KUIPER_SUPPLEMENTAL}')
        sats = fetch_tle(KUIPER_SUPPLEMENTAL)
        if sats:
            return sats
    except Exception as e:
        print(f'    Supplemental failed: {e}')

    # ③ Filter active catalog for names containing 'KUIPER'
    #    Amazon's prototypes were named KUIPERSAT-1 and KUIPERSAT-2; production
    #    vehicles are expected to follow a similar KUIPER-* naming convention.
    print(f'    Falling back to active catalog filter (this is slow ~3 MB)…')
    try:
        all_sats = fetch_tle(KUIPER_ACTIVE)
        kuiper_sats = [s for s in all_sats if 'KUIPER' in s['name'].upper()]
        if kuiper_sats:
            return kuiper_sats
        print('    No KUIPER objects found in active catalog.')
    except Exception as e:
        print(f'    Active catalog failed: {e}')

    # Return empty list — the React app handles an empty kuiper-tle.json gracefully.
    # NOTE: if this constellation is very small (< 10 sats), that is correct and
    # expected. Kuiper is in early deployment; the count will grow as Amazon
    # proceeds with its planned launches through 2026–2027.
    return []


# ── Ground stations ──────────────────────────────────────────────────────────
#
# Each tuple: (name, operator, type, lat, lon, source)
#
# Source constants — carry a machine-readable provenance tag so the dataset
# can be audited entry-by-entry.

SRC_FCC     = 'FCC filing'           # SpaceX FCC licence applications (public record)
SRC_PRESS   = 'SpaceX press release' # SpaceX press release or regulatory filing
SRC_ONEWEB  = 'OneWeb filing'        # OneWeb regulatory filing or press release
SRC_IMAGERY = 'Satellite imagery'    # Corroborated via public satellite imagery
SRC_INFER   = 'Publicly inferred'    # City-level approximation from confirmed service area

GROUND_STATIONS = [

    # ── Starlink gateways ────────────────────────────────────────────────────

    # United States (FCC licence filings: SAT-LOA-20161115-00118 et al.)
    ('Brewster, WA',          'SpaceX', 'gateway', 47.874,  -119.787, SRC_FCC),
    ('Butte, MT',             'SpaceX', 'gateway', 46.004,  -112.535, SRC_FCC),
    ('Colville, WA',          'SpaceX', 'gateway', 48.546,  -117.906, SRC_FCC),
    ('Ionia, MI',             'SpaceX', 'gateway', 42.989,  -85.075,  SRC_FCC),
    ('Kennewick, WA',         'SpaceX', 'gateway', 46.211,  -119.137, SRC_FCC),
    ('Litchfield Park, AZ',   'SpaceX', 'gateway', 33.493,  -112.358, SRC_FCC),
    ('Longmont, CO',          'SpaceX', 'gateway', 40.167,  -105.102, SRC_FCC),
    ('Merrill, OR',           'SpaceX', 'gateway', 42.024,  -121.603, SRC_FCC),
    ('Moab, UT',              'SpaceX', 'gateway', 38.573,  -109.550, SRC_FCC),
    ('Northfield, MN',        'SpaceX', 'gateway', 44.458,  -93.162,  SRC_FCC),
    ('Purdy, WA',             'SpaceX', 'gateway', 47.388,  -122.625, SRC_FCC),
    ('Ravenna, OH',           'SpaceX', 'gateway', 41.157,  -81.243,  SRC_FCC),
    ('Sauk Rapids, MN',       'SpaceX', 'gateway', 45.593,  -94.167,  SRC_FCC),
    ('Springfield, VA',       'SpaceX', 'gateway', 38.789,  -77.187,  SRC_FCC),
    ('Titusville, FL',        'SpaceX', 'gateway', 28.612,  -80.808,  SRC_FCC),
    ('Tracy, CA',             'SpaceX', 'gateway', 37.740,  -121.425, SRC_FCC),
    ('Vandenberg SFB, CA',    'SpaceX', 'gateway', 34.742,  -120.572, SRC_FCC),
    ('Boca Chica, TX',        'SpaceX', 'gateway', 25.993,  -97.156,  SRC_PRESS),
    ('Grand Forks, ND',       'SpaceX', 'gateway', 47.925,  -97.033,  SRC_FCC),
    ('Hawthorne, CA',         'SpaceX', 'gateway', 33.921,  -118.328, SRC_PRESS),
    ('Manassas, VA',          'SpaceX', 'gateway', 38.751,  -77.475,  SRC_FCC),
    ('Cushing, OK',           'SpaceX', 'gateway', 35.985,  -96.766,  SRC_FCC),
    ('Snohomish, WA',         'SpaceX', 'gateway', 47.913,  -122.099, SRC_FCC),
    ('Tunica, MS',            'SpaceX', 'gateway', 34.685,  -90.383,  SRC_FCC),
    ('Waynesboro, VA',        'SpaceX', 'gateway', 38.069,  -78.890,  SRC_FCC),
    ('Geronimo, TX',          'SpaceX', 'gateway', 29.679,  -98.024,  SRC_FCC),
    ('La Grange, TX',         'SpaceX', 'gateway', 29.905,  -96.878,  SRC_FCC),
    ('Pie Town, NM',          'SpaceX', 'gateway', 34.299,  -108.153, SRC_FCC),
    ('Cliff, NM',             'SpaceX', 'gateway', 32.989,  -108.610, SRC_FCC),
    ('Holbrook, AZ',          'SpaceX', 'gateway', 34.902,  -110.160, SRC_FCC),
    ('Anchorage, AK',         'SpaceX', 'gateway', 61.218,  -149.900, SRC_FCC),
    ('Fairbanks, AK',         'SpaceX', 'gateway', 64.201,  -149.494, SRC_FCC),
    ('Utqiagvik, AK',         'SpaceX', 'gateway', 71.290,  -156.789, SRC_FCC),
    ('Honolulu, HI',          'SpaceX', 'gateway', 21.307,  -157.858, SRC_FCC),
    ('Aguadilla, PR',         'SpaceX', 'gateway', 18.427,  -67.154,  SRC_FCC),

    # Canada
    ('Vancouver, BC',         'SpaceX', 'gateway', 49.283,  -123.121, SRC_INFER),
    ('Edmonton, AB',          'SpaceX', 'gateway', 53.546,  -113.494, SRC_INFER),
    ('Toronto, ON',           'SpaceX', 'gateway', 43.653,  -79.383,  SRC_INFER),
    ('Montreal, QC',          'SpaceX', 'gateway', 45.502,  -73.567,  SRC_INFER),
    ('Winnipeg, MB',          'SpaceX', 'gateway', 49.895,  -97.138,  SRC_INFER),
    ('Halifax, NS',           'SpaceX', 'gateway', 44.649,  -63.575,  SRC_INFER),
    ('Yellowknife, NT',       'SpaceX', 'gateway', 62.454,  -114.372, SRC_INFER),
    ('Iqaluit, NU',           'SpaceX', 'gateway', 63.748,  -68.519,  SRC_INFER),

    # Mexico & Central America
    ('Mexico City, MX',       'SpaceX', 'gateway', 19.433,  -99.133,  SRC_INFER),
    ('Guadalajara, MX',       'SpaceX', 'gateway', 20.659,  -103.350, SRC_INFER),
    ('Guatemala City, GT',    'SpaceX', 'gateway', 14.635,  -90.507,  SRC_INFER),

    # Europe
    ('Villarceaux, France',   'SpaceX', 'gateway', 49.117,    1.667,  SRC_PRESS),
    ('Langenfeld, Germany',   'SpaceX', 'gateway', 51.117,    6.950,  SRC_INFER),
    ('Bad Aibling, Germany',  'SpaceX', 'gateway', 47.867,   11.983,  SRC_IMAGERY),
    ('London, UK',            'SpaceX', 'gateway', 51.507,   -0.128,  SRC_INFER),
    ('Edinburgh, UK',         'SpaceX', 'gateway', 55.953,   -3.188,  SRC_INFER),
    ('Dublin, Ireland',       'SpaceX', 'gateway', 53.350,   -6.260,  SRC_INFER),
    ('Amsterdam, Netherlands','SpaceX', 'gateway', 52.368,    4.904,  SRC_INFER),
    ('Stockholm, Sweden',     'SpaceX', 'gateway', 59.329,   18.069,  SRC_INFER),
    ('Oslo, Norway',          'SpaceX', 'gateway', 59.914,   10.752,  SRC_INFER),
    ('Tromsø, Norway',        'SpaceX', 'gateway', 69.650,   18.956,  SRC_INFER),
    ('Helsinki, Finland',     'SpaceX', 'gateway', 60.170,   24.938,  SRC_INFER),
    ('Warsaw, Poland',        'SpaceX', 'gateway', 52.230,   21.012,  SRC_INFER),
    ('Prague, Czechia',       'SpaceX', 'gateway', 50.076,   14.438,  SRC_INFER),
    ('Vienna, Austria',       'SpaceX', 'gateway', 48.208,   16.374,  SRC_INFER),
    ('Zurich, Switzerland',   'SpaceX', 'gateway', 47.377,    8.542,  SRC_INFER),
    ('Milan, Italy',          'SpaceX', 'gateway', 45.465,    9.186,  SRC_INFER),
    ('Madrid, Spain',         'SpaceX', 'gateway', 40.417,   -3.704,  SRC_INFER),
    ('Lisbon, Portugal',      'SpaceX', 'gateway', 38.722,   -9.139,  SRC_INFER),
    ('Athens, Greece',        'SpaceX', 'gateway', 37.984,   23.728,  SRC_INFER),
    ('Bucharest, Romania',    'SpaceX', 'gateway', 44.427,   26.103,  SRC_INFER),
    ('Kyiv, Ukraine',         'SpaceX', 'gateway', 50.450,   30.523,  SRC_INFER),
    ('Reykjavik, Iceland',    'SpaceX', 'gateway', 64.127,  -21.817,  SRC_INFER),
    ('Nuuk, Greenland',       'SpaceX', 'gateway', 64.184,  -51.722,  SRC_INFER),

    # South America
    ('São Paulo, Brazil',     'SpaceX', 'gateway', -23.550,  -46.633, SRC_INFER),
    ('Brasília, Brazil',      'SpaceX', 'gateway', -15.780,  -47.929, SRC_INFER),
    ('Manaus, Brazil',        'SpaceX', 'gateway',  -3.119,  -60.022, SRC_INFER),
    ('Buenos Aires, AR',      'SpaceX', 'gateway', -34.604,  -58.382, SRC_INFER),
    ('Santiago, Chile',       'SpaceX', 'gateway', -33.449,  -70.669, SRC_INFER),
    ('Punta Arenas, Chile',   'SpaceX', 'gateway', -53.164,  -70.917, SRC_INFER),
    ('Bogotá, Colombia',      'SpaceX', 'gateway',   4.711,  -74.072, SRC_INFER),
    ('Lima, Peru',            'SpaceX', 'gateway', -12.046,  -77.043, SRC_INFER),

    # Africa
    ('Lagos, Nigeria',        'SpaceX', 'gateway',   6.524,    3.379, SRC_INFER),
    ('Nairobi, Kenya',        'SpaceX', 'gateway',  -1.292,   36.822, SRC_INFER),
    ('Johannesburg, SA',      'SpaceX', 'gateway', -26.204,   28.047, SRC_INFER),
    ('Cape Town, SA',         'SpaceX', 'gateway', -33.925,   18.424, SRC_INFER),
    ('Casablanca, Morocco',   'SpaceX', 'gateway',  33.573,   -7.590, SRC_INFER),
    ('Accra, Ghana',          'SpaceX', 'gateway',   5.556,   -0.197, SRC_INFER),

    # Middle East
    ('Dubai, UAE',            'SpaceX', 'gateway',  25.205,   55.271, SRC_INFER),
    ('Riyadh, Saudi Arabia',  'SpaceX', 'gateway',  24.714,   46.675, SRC_INFER),
    ('Cairo, Egypt',          'SpaceX', 'gateway',  30.044,   31.236, SRC_INFER),

    # Asia & Pacific
    ('Mumbai, India',         'SpaceX', 'gateway',  19.076,   72.878, SRC_INFER),
    ('Delhi, India',          'SpaceX', 'gateway',  28.614,   77.209, SRC_INFER),
    ('Bangalore, India',      'SpaceX', 'gateway',  12.972,   77.595, SRC_INFER),
    ('Tokyo, Japan',          'SpaceX', 'gateway',  35.676,  139.650, SRC_INFER),
    ('Osaka, Japan',          'SpaceX', 'gateway',  34.694,  135.502, SRC_INFER),
    ('Hokkaido, Japan',       'SpaceX', 'gateway',  43.064,  141.347, SRC_INFER),
    ('Seoul, South Korea',    'SpaceX', 'gateway',  37.567,  126.978, SRC_INFER),
    ('Singapore',             'SpaceX', 'gateway',   1.352,  103.820, SRC_INFER),
    ('Kuala Lumpur, MY',      'SpaceX', 'gateway',   3.139,  101.687, SRC_INFER),
    ('Jakarta, Indonesia',    'SpaceX', 'gateway',  -6.209,  106.846, SRC_INFER),
    ('Manila, Philippines',   'SpaceX', 'gateway',  14.600,  120.984, SRC_INFER),
    ('Bangkok, Thailand',     'SpaceX', 'gateway',  13.756,  100.502, SRC_INFER),
    ('Perth, Australia',      'SpaceX', 'gateway', -31.951,  115.861, SRC_INFER),
    ('Melbourne, Australia',  'SpaceX', 'gateway', -37.814,  144.963, SRC_INFER),
    ('Adelaide, Australia',   'SpaceX', 'gateway', -34.929,  138.601, SRC_INFER),
    ('Darwin, Australia',     'SpaceX', 'gateway', -12.463,  130.846, SRC_INFER),
    ('Brisbane, Australia',   'SpaceX', 'gateway', -27.470,  153.025, SRC_INFER),
    ('Wellington, NZ',        'SpaceX', 'gateway', -41.287,  174.776, SRC_INFER),
    ('Auckland, NZ',          'SpaceX', 'gateway', -36.849,  174.763, SRC_INFER),

    # ── OneWeb gateways ──────────────────────────────────────────────────────
    # Fewer, larger gateway sites — OneWeb uses a hub-and-spoke model

    ('Clarksburg, MD',        'OneWeb', 'gateway',  39.143,  -77.269, SRC_ONEWEB),
    ('Sitka, AK',             'OneWeb', 'gateway',  57.053, -135.330, SRC_ONEWEB),
    ('Punta Arenas, Chile',   'OneWeb', 'gateway', -53.164,  -70.917, SRC_ONEWEB),
    ('Longyearbyen, Svalbard','OneWeb', 'gateway',  78.223,   15.627, SRC_ONEWEB),
    ('Fucino, Italy',         'OneWeb', 'gateway',  42.002,   13.605, SRC_ONEWEB),
    ('Alice Springs, AU',     'OneWeb', 'gateway', -23.698,  133.881, SRC_ONEWEB),
    ('Awarua, NZ',            'OneWeb', 'gateway', -46.528,  168.368, SRC_ONEWEB),
    ('Yamaguchi, Japan',      'OneWeb', 'gateway',  34.186,  131.471, SRC_ONEWEB),
    ('Mtunzini, SA',          'OneWeb', 'gateway', -28.964,   31.756, SRC_ONEWEB),
    ('Accra, Ghana',          'OneWeb', 'gateway',   5.556,   -0.197, SRC_ONEWEB),
    ('Hartebeesthoek, SA',    'OneWeb', 'gateway', -25.889,   27.708, SRC_ONEWEB),
    ('Inuvik, Canada',        'OneWeb', 'gateway',  68.361, -133.723, SRC_ONEWEB),
    ('Toulouse, France',      'OneWeb', 'gateway',  43.605,    1.444, SRC_ONEWEB),
    ('Nallıhan, Turkey',      'OneWeb', 'gateway',  40.185,   31.353, SRC_ONEWEB),
    ('Shillong, India',       'OneWeb', 'gateway',  25.578,   91.883, SRC_ONEWEB),
]


def build_ground_stations_geojson(stations):
    features = []
    for name, operator, gs_type, lat, lon, source in stations:
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {
                'name':     name,
                'operator': operator,
                'type':     gs_type,
                'source':   source,
            },
        })
    return {'type': 'FeatureCollection', 'features': features}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    generated_at = datetime.datetime.utcnow().isoformat() + 'Z'

    # TLE data — standard groups
    group_map = [
        ('starlink', 'starlink-tle.json'),
        ('oneweb',   'oneweb-tle.json'),
        ('geo',      'geo-commsats-tle.json'),
        ('iss',      'iss-tle.json'),
    ]
    for group, filename in group_map:
        print(f'\nFetching {group} TLEs…')
        url  = CELESTRAK_GROUPS[group]
        sats = fetch_tle(url)
        out  = os.path.join(OUT_DIR, filename)
        payload = {'generatedAt': generated_at, 'satellites': sats}
        with open(out, 'w') as f:
            json.dump(payload, f, separators=(',', ':'))
        print(f'  {len(sats)} satellites → {out}')

    # TLE data — Project Kuiper (fallback chain)
    print('\nFetching kuiper TLEs…')
    kuiper_sats = fetch_kuiper()
    if len(kuiper_sats) < 10:
        print(f'  NOTE: only {len(kuiper_sats)} Kuiper objects found.')
        print('  This is expected — Kuiper is in early deployment (planned 3,236 sats).')
        print('  Re-run after each Amazon launch batch to pick up new objects.')
    out = os.path.join(OUT_DIR, 'kuiper-tle.json')
    payload = {'generatedAt': generated_at, 'satellites': kuiper_sats}
    with open(out, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f'  {len(kuiper_sats)} satellites → {out}')

    # Ground stations
    print('\nWriting ground-stations.geojson…')
    gs   = build_ground_stations_geojson(GROUND_STATIONS)
    out  = os.path.join(OUT_DIR, 'ground-stations.geojson')
    with open(out, 'w') as f:
        json.dump(gs, f, separators=(',', ':'))

    starlink_ct = sum(1 for _, op, *_ in GROUND_STATIONS if op == 'SpaceX')
    oneweb_ct   = sum(1 for _, op, *_ in GROUND_STATIONS if op == 'OneWeb')
    print(f'  {len(GROUND_STATIONS)} stations ({starlink_ct} Starlink, {oneweb_ct} OneWeb) → {out}')

    print('\nDone.')


if __name__ == '__main__':
    main()
