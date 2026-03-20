#!/usr/bin/env python3
"""
Download Natural Earth ocean and marine area data for Project Backbone.
Outputs ocean.geojson (fill polygons) and marine-labels.geojson (label points).
"""

import json
import urllib.request
import os

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"

OCEAN_URL        = f"{BASE}/ne_110m_ocean.geojson"
MARINE_POLYS_URL = f"{BASE}/ne_50m_geography_marine_polys.geojson"

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')


def fetch_json(url):
    print(f"  GET {url}")
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def ring_centroid(coords):
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [sum(lons) / len(lons), sum(lats) / len(lats)]


def geometry_centroid(geom):
    if geom['type'] == 'Polygon':
        return ring_centroid(geom['coordinates'][0])
    elif geom['type'] == 'MultiPolygon':
        largest = max(geom['coordinates'], key=lambda p: len(p[0]))
        return ring_centroid(largest[0])
    return None


def make_marine_labels(raw):
    features = []
    for f in raw.get('features', []):
        name = f.get('properties', {}).get('name', '').strip()
        if not name or not f.get('geometry'):
            continue
        pt = geometry_centroid(f['geometry'])
        if pt is None:
            continue
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': pt},
            'properties': {
                'name':      name,
                'name_alt':  f['properties'].get('name_alt', ''),
                'scalerank': f['properties'].get('scalerank', 5),
            },
        })
    return {'type': 'FeatureCollection', 'features': features}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Fetching ocean polygons...")
    ocean = fetch_json(OCEAN_URL)
    out = os.path.join(OUT_DIR, 'ocean.geojson')
    with open(out, 'w') as f:
        json.dump(ocean, f)
    print(f"  -> {len(ocean.get('features', []))} features written to {out}\n")

    print("Fetching marine area polygons...")
    marine_raw = fetch_json(MARINE_POLYS_URL)
    labels = make_marine_labels(marine_raw)
    out = os.path.join(OUT_DIR, 'marine-labels.geojson')
    with open(out, 'w') as f:
        json.dump(labels, f)
    print(f"  -> {len(labels['features'])} label points written to {out}\n")

    print("Done.")


if __name__ == '__main__':
    main()
