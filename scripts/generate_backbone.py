#!/usr/bin/env python3
"""
Generate approximate terrestrial backbone routes from data center and IXP locations.

Algorithm
─────────
1. Combine all IXPs + data centers with network_count >= 3 (meaningful hubs only)
2. Intra-country  : connect each node to its K_LOCAL nearest neighbours
                    within the same country (deduped)
3. International  : find cities with HUB_MIN facilities ("major hubs"),
                    connect each hub to its K_INTL nearest hub cities abroad
4. Densify each LineString so segments stay ≤ MAX_SEGMENT_DEG
   (prevents GlobeView chord-clipping)

Output: public/backbone.geojson
"""

import json
import math
import os
from collections import defaultdict

OUT_DIR      = os.path.join(os.path.dirname(__file__), '..', 'public')
MAX_SEG_DEG  = 0.5   # max degrees between interpolated waypoints
K_LOCAL      = 3     # nearest neighbours within country
K_INTL       = 3     # nearest hub cities to link internationally
HUB_MIN      = 5     # facilities in a city to qualify as a hub
MIN_NETWORKS = 3     # minimum network_count for a DC to be included


# ── Maths helpers ──────────────────────────────────────────────────────────────

def haversine(lon1, lat1, lon2, lat2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def densify(p0, p1):
    """Return list of [lon, lat] from p0 to p1 with points every MAX_SEG_DEG."""
    x0, y0 = p0
    x1, y1 = p1
    dist  = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    steps = max(1, int(dist / MAX_SEG_DEG))
    pts   = [[x0 + (x1 - x0) * s / steps,
              y0 + (y1 - y0) * s / steps] for s in range(steps)]
    pts.append([x1, y1])
    return pts


# ── Data loading ───────────────────────────────────────────────────────────────

def load_features(path):
    with open(path) as f:
        return json.load(f)['features']


def build_nodes(dc_features, ixp_features):
    nodes = []
    for f in ixp_features:
        lon, lat = f['geometry']['coordinates']
        p = f['properties']
        nodes.append({'lon': lon, 'lat': lat,
                      'country': p.get('country', ''),
                      'city':    p.get('city', '') or '',
                      'name':    p.get('name', ''),
                      'kind':    'ixp'})

    for f in dc_features:
        if (f['properties'].get('network_count') or 0) < MIN_NETWORKS:
            continue
        lon, lat = f['geometry']['coordinates']
        p = f['properties']
        nodes.append({'lon': lon, 'lat': lat,
                      'country': p.get('country', ''),
                      'city':    p.get('city', '') or '',
                      'name':    p.get('name', ''),
                      'kind':    'dc'})
    return nodes


# ── Edge generation ────────────────────────────────────────────────────────────

def intra_country_edges(nodes):
    by_country = defaultdict(list)
    for i, n in enumerate(nodes):
        if n['country']:
            by_country[n['country']].append(i)

    edges   = set()
    features = []
    for country, indices in by_country.items():
        if len(indices) < 2:
            continue
        for i in indices:
            a = nodes[i]
            dists = sorted(
                ((haversine(a['lon'], a['lat'], nodes[j]['lon'], nodes[j]['lat']), j)
                 for j in indices if j != i)
            )
            for _, j in dists[:K_LOCAL]:
                key = frozenset([i, j])
                if key in edges:
                    continue
                edges.add(key)
                b = nodes[j]
                features.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': densify([a['lon'], a['lat']], [b['lon'], b['lat']]),
                    },
                    'properties': {
                        'route_type': 'intra-country',
                        'country':    country,
                        'from':       a['city'] or a['name'],
                        'to':         b['city'] or b['name'],
                    },
                })
    return features, len(edges)


def international_hub_edges(nodes):
    # city key → (lon, lat, country)
    city_count = defaultdict(int)
    city_coord = {}
    for n in nodes:
        key = f"{n['city'].strip()}|{n['country']}"
        city_count[key] += 1
        if key not in city_coord:
            city_coord[key] = (n['lon'], n['lat'], n['country'])

    hubs     = {k: city_coord[k] for k, v in city_count.items()
                if v >= HUB_MIN and k.split('|')[0]}
    hub_list = list(hubs.items())   # [(key, (lon, lat, cty)), ...]

    edges    = set()
    features = []
    for i, (key_a, (lon_a, lat_a, cty_a)) in enumerate(hub_list):
        dists = sorted(
            (haversine(lon_a, lat_a, lon_b, lat_b), j, key_b)
            for j, (key_b, (lon_b, lat_b, cty_b)) in enumerate(hub_list)
            if j != i and cty_b != cty_a
        )
        for _, j, key_b in dists[:K_INTL]:
            edge = frozenset([key_a, key_b])
            if edge in edges:
                continue
            edges.add(edge)
            lon_b, lat_b, cty_b = hubs[key_b]
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': densify([lon_a, lat_a], [lon_b, lat_b]),
                },
                'properties': {
                    'route_type':   'international',
                    'from':         key_a.split('|')[0],
                    'to':           key_b.split('|')[0],
                    'from_country': cty_a,
                    'to_country':   cty_b,
                },
            })
    return features, len(edges), len(hubs)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    dc_features  = load_features(os.path.join(OUT_DIR, 'data-centers.geojson'))
    ixp_features = load_features(os.path.join(OUT_DIR, 'ixps.geojson'))

    nodes = build_nodes(dc_features, ixp_features)
    print(f"Nodes (IXPs + DCs with ≥{MIN_NETWORKS} networks): {len(nodes)}")

    print("Building intra-country edges…")
    local_feats, n_local = intra_country_edges(nodes)
    print(f"  {n_local} edges")

    print("Building international hub edges…")
    intl_feats, n_intl, n_hubs = international_hub_edges(nodes)
    print(f"  {n_hubs} hub cities → {n_intl} international edges")

    all_features = local_feats + intl_feats
    out = os.path.join(OUT_DIR, 'backbone.geojson')
    with open(out, 'w') as f:
        json.dump({'type': 'FeatureCollection', 'features': all_features}, f)

    print(f"\nbackbone.geojson: {len(all_features)} total routes → {out}")
    print("Done.")


if __name__ == '__main__':
    main()
