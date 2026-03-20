#!/usr/bin/env python3
"""
Fetch PeeringDB facility and IXP data.
Outputs data-centers.geojson and ixps.geojson into ../public/

Coordinates for IXPs are resolved via ixfac (IX-to-facility associations)
since the ix endpoint does not carry lat/lon directly.
Participant counts come from ixlan.net_count.
"""

import json
import ssl
import urllib.request
import os

BASE    = "https://peeringdb.com/api"
HEADERS = {'User-Agent': 'ProjectBackbone/1.0 (educational)'}
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')

_SSL_CTX = ssl.create_default_context()


# ── Sanitisation helpers ──────────────────────────────────────────────────────

def _safe_str(v, maxlen=256):
    """Coerce to string, truncate, strip null bytes."""
    return str(v or '')[:maxlen].replace('\x00', '')


def _safe_float(v):
    try:
        f = float(v)
        return f if -1e9 < f < 1e9 else None
    except (TypeError, ValueError):
        return None


def fetch(endpoint, page_size=10000):
    results = []
    skip = 0
    while True:
        url = f"{BASE}/{endpoint}?limit={page_size}&skip={skip}"
        if not url.startswith('https://'):
            raise ValueError(f"Refusing non-HTTPS URL: {url}")
        print(f"  GET {url}")
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as r:
            page = json.loads(r.read())
        if not isinstance(page, dict) or not isinstance(page.get('data'), list):
            raise ValueError(f"Unexpected response shape from {url}")
        page = page['data']
        results.extend(page)
        if len(page) < page_size:
            break
        skip += page_size
    return results


def build_data_centers(facs, fac_network_count):
    features = []
    for f in facs:
        lat = f.get('latitude')
        lon = f.get('longitude')
        if lat is None or lon is None:
            continue
        try:
            coords = [float(lon), float(lat)]
        except (ValueError, TypeError):
            continue
        if not (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
            continue
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': coords},
            'properties': {
                'id':            f.get('id'),
                'name':          _safe_str(f.get('name', '')),
                'aka':           _safe_str(f.get('aka', '')),
                'city':          _safe_str(f.get('city', '')),
                'state':         _safe_str(f.get('state', '')),
                'country':       _safe_str(f.get('country', '')),
                'website':       _safe_str(f.get('website', ''), maxlen=512),
                'network_count': fac_network_count.get(f.get('id'), 0),
            },
        })
    return {'type': 'FeatureCollection', 'features': features}


def build_ixps(ixes, ix_coords, ix_participants):
    features = []
    for ix in ixes:
        ix_id = ix.get('id')
        coords = ix_coords.get(ix_id)
        if coords is None:
            continue
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': coords},
            'properties': {
                'id':           ix_id,
                'name':         _safe_str(ix.get('name', '')),
                'aka':          _safe_str(ix.get('aka', '')),
                'city':         _safe_str(ix.get('city', '')),
                'country':      _safe_str(ix.get('country', '')),
                'region':       _safe_str(ix.get('region_continent', '')),
                'website':      _safe_str(ix.get('website', ''), maxlen=512),
                'participants': ix_participants.get(ix_id, 0),
            },
        })
    return {'type': 'FeatureCollection', 'features': features}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Fetching facilities (data centers)...")
    facs = fetch('fac')
    print(f"  {len(facs)} facilities\n")

    print("Fetching Internet Exchanges...")
    ixes = fetch('ix')
    print(f"  {len(ixes)} IXPs\n")

    print("Fetching IX-to-facility associations (for IXP coordinates)...")
    ixfacs = fetch('ixfac')
    print(f"  {len(ixfacs)} associations\n")

    print("Fetching IXLANs (to map ixlan_id -> ix_id)...")
    ixlans = fetch('ixlan')
    print(f"  {len(ixlans)} IXLANs\n")

    print("Fetching netixlan (one record per network per IX)...")
    netixlans = fetch('netixlan')
    print(f"  {len(netixlans)} netixlan records\n")

    print("Fetching netfac (network-to-facility, for importance score)...")
    netfacs = fetch('netfac')
    print(f"  {len(netfacs)} netfac records\n")

    # fac_id -> [lon, lat]
    fac_coords = {}
    for f in facs:
        if f.get('latitude') and f.get('longitude'):
            try:
                fac_coords[f['id']] = [float(f['longitude']), float(f['latitude'])]
            except (ValueError, TypeError):
                pass

    # ix_id -> [lon, lat]  (first associated facility wins)
    ix_coords = {}
    for assoc in ixfacs:
        ix_id  = assoc.get('ix_id')
        fac_id = assoc.get('fac_id')
        if ix_id not in ix_coords and fac_id in fac_coords:
            ix_coords[ix_id] = fac_coords[fac_id]

    # ixlan_id -> ix_id
    ixlan_to_ix = {il['id']: il['ix_id'] for il in ixlans if il.get('ix_id')}

    # ix_id -> participant count (count distinct networks per IX)
    ix_participants = {}
    for rec in netixlans:
        ix_id = ixlan_to_ix.get(rec.get('ixlan_id'))
        if ix_id:
            ix_participants[ix_id] = ix_participants.get(ix_id, 0) + 1

    # fac_id -> number of colocated networks (importance proxy)
    fac_network_count = {}
    for rec in netfacs:
        fac_id = rec.get('fac_id')
        if fac_id:
            fac_network_count[fac_id] = fac_network_count.get(fac_id, 0) + 1

    # ── Write data-centers.geojson ────────────────────────────
    dc = build_data_centers(facs, fac_network_count)
    out = os.path.join(OUT_DIR, 'data-centers.geojson')
    with open(out, 'w') as f:
        json.dump(dc, f)
    print(f"data-centers.geojson: {len(dc['features'])} features -> {out}")

    # ── Write ixps.geojson ────────────────────────────────────
    ixp = build_ixps(ixes, ix_coords, ix_participants)
    out = os.path.join(OUT_DIR, 'ixps.geojson')
    with open(out, 'w') as f:
        json.dump(ixp, f)
    placed    = len(ixp['features'])
    no_coords = len(ixes) - placed
    print(f"ixps.geojson:         {placed} features -> {out}")
    if no_coords:
        print(f"  ({no_coords} IXPs skipped — no facility association / coordinates)")

    print("\nDone.")


if __name__ == '__main__':
    main()
