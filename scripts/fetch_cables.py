#!/usr/bin/env python3
"""
Fetch and normalize TeleGeography submarine cable data.
Outputs cables.geojson and landing-points.geojson into ../public/
"""

import json
import re
import ssl
import urllib.request
import os

CABLES_URL  = "https://www.submarinecablemap.com/api/v3/cable/cable-geo.json"
LANDING_URL = "https://www.submarinecablemap.com/api/v3/landing-point/landing-point-geo.json"

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')

_SSL_CTX = ssl.create_default_context()


def fetch_json(url):
    if not url.startswith('https://'):
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'ProjectBackbone/1.0 (educational)'})
    with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as r:
        return json.loads(r.read())


# ── Sanitisation helpers ──────────────────────────────────────────────────────

def _safe_str(v, maxlen=256):
    """Coerce to string, truncate, strip null bytes."""
    return str(v or '')[:maxlen].replace('\x00', '')


def _safe_color(v):
    """Accept only #rrggbb / #rgb hex strings; fall back to default."""
    s = str(v or '').strip()
    return s if re.fullmatch(r'#[0-9a-fA-F]{3,6}', s) else '#4fc3f7'


def _safe_float(v):
    try:
        f = float(v)
        return f if -1e9 < f < 1e9 else None
    except (TypeError, ValueError):
        return None


MAX_SEGMENT_DEG = 0.5  # insert a point whenever a segment exceeds this many degrees


def densify_ring(coords):
    """Interpolate intermediate points so no segment exceeds MAX_SEGMENT_DEG."""
    out = []
    for i in range(len(coords) - 1):
        try:
            x0, y0 = float(coords[i][0]),     float(coords[i][1])
            x1, y1 = float(coords[i + 1][0]), float(coords[i + 1][1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (-180 <= x0 <= 180 and -90 <= y0 <= 90):
            continue
        if not (-180 <= x1 <= 180 and -90 <= y1 <= 90):
            continue
        dist  = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        steps = max(1, int(dist / MAX_SEGMENT_DEG))
        for s in range(steps):
            t = s / steps
            out.append([x0 + t * (x1 - x0), y0 + t * (y1 - y0)])
    if coords:
        out.append(coords[-1])
    return out


def densify_geometry(geom):
    t = geom['type']
    if t == 'LineString':
        return {'type': t, 'coordinates': densify_ring(geom['coordinates'])}
    if t == 'MultiLineString':
        return {'type': t, 'coordinates': [densify_ring(r) for r in geom['coordinates']]}
    return geom


def normalize_cables(raw):
    features = []
    for f in raw.get('features', []):
        props = f.get('properties', {})
        if not f.get('geometry'):
            continue
        features.append({
            'type': 'Feature',
            'geometry': densify_geometry(f['geometry']),
            'properties': {
                'id':        _safe_str(props.get('id', '')),
                'name':      _safe_str(props.get('name', 'Unknown')),
                'color':     _safe_color(props.get('color')),
                'rfs_year':  _safe_str(props.get('rfs', '')),
                'length_km': _safe_float(props.get('length')),
                'owners':    [_safe_str(o.get('name', '')) for o in props.get('owners', []) if isinstance(o, dict)][:50],
            },
        })
    return {'type': 'FeatureCollection', 'features': features}


def normalize_landing_points(raw):
    features = []
    for f in raw.get('features', []):
        props = f.get('properties', {})
        if not f.get('geometry'):
            continue
        features.append({
            'type': 'Feature',
            'geometry': f['geometry'],
            'properties': {
                'id':     _safe_str(props.get('id', '')),
                'name':   _safe_str(props.get('name', 'Unknown')),
                'cables': [_safe_str(c.get('name', '')) for c in props.get('cables', []) if isinstance(c, dict)],
            },
        })
    return {'type': 'FeatureCollection', 'features': features}


def write_json(data, path):
    with open(path, 'w') as f:
        json.dump(data, f)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Fetching cable data...")
    cables = normalize_cables(fetch_json(CABLES_URL))
    out = os.path.join(OUT_DIR, 'cables.geojson')
    write_json(cables, out)
    print(f"  -> {len(cables['features'])} cables written to {out}\n")

    print("Fetching landing point data...")
    lps = normalize_landing_points(fetch_json(LANDING_URL))
    out = os.path.join(OUT_DIR, 'landing-points.geojson')
    write_json(lps, out)
    print(f"  -> {len(lps['features'])} landing points written to {out}\n")

    print("Done.")


if __name__ == '__main__':
    main()
