#!/usr/bin/env python3
"""
Download Natural Earth geographic data for Project Backbone.
Outputs borders.geojson, rivers.geojson, lakes.geojson into ../public/
"""

import json
import urllib.request
import os

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"

SOURCES = {
    # 50m scale: includes small islands, territories, French Polynesia etc.
    'borders.geojson': f'{BASE}/ne_50m_admin_0_countries.geojson',
    'rivers.geojson':  f'{BASE}/ne_50m_rivers_lake_centerlines.geojson',
    'lakes.geojson':   f'{BASE}/ne_50m_lakes.geojson',
}

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')


def fetch_and_save(url, path):
    print(f"  GET {url}")
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())
    with open(path, 'w') as f:
        json.dump(data, f)
    return len(data.get('features', []))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for filename, url in SOURCES.items():
        out = os.path.join(OUT_DIR, filename)
        count = fetch_and_save(url, out)
        print(f"  -> {count} features written to {out}\n")
    print("Done.")


if __name__ == '__main__':
    main()
