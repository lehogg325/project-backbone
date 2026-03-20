#!/usr/bin/env python3
"""
fetch_terrestrial_fiber.py
──────────────────────────
Builds two GeoJSON files of terrestrial fiber infrastructure:

  fiber-routes-verified.geojson
      Real telecom ways from OpenStreetMap (Overpass API), tagged as
      man_made=pipeline/pipeline=telecom, telecom=line, utility=telecom, etc.
      Coverage is patchy but accurate wherever volunteers have mapped it
      (good in parts of Europe, North America, Japan; sparse elsewhere).

  fiber-routes-estimated.geojson
      Estimated routes that connect IXPs, major data centres, and cable
      landing stations along realistic corridors.  Routes are pulled toward
      Natural Earth 10 m road / rail lines rather than drawn as raw great-
      circle arcs, so they follow infrastructure rights-of-way.
      A Kruskal MST plus k=2 redundant edges per node ensures every region
      is fully connected with plausible redundancy.

Data sources
────────────
  OpenStreetMap     Overpass API — verified routes
  FCC BDC           broadbandmap.fcc.gov — no fiber route geometry available
                    (availability / fabric data only); skipped.
  OFCOM / ARCEP     No machine-readable route geometry published; skipped.
  Natural Earth     ne_10m_roads.geojson from nvkelso/natural-earth-vector
                    (GitHub CDN) — used only as road-corridor guide for snapping.
  public/*.geojson  IXP, data-centre, and landing-point nodes from this project.

Dependencies
────────────
  Standard library only.  networkx / shapely / geopandas are NOT required.
  All spatial work is pure Python.

Caching
───────
  Overpass results are cached in scripts/.cache/ (7-day TTL) so re-runs
  avoid hammering the public API.

Run annually (or when major new infrastructure is announced).
"""

import gzip
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR, '.cache')
PUBLIC_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'public'))

os.makedirs(CACHE_DIR, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────

OVERPASS_URL   = 'https://overpass-api.de/api/interpreter'
NE_ROADS_URL   = (
    'https://raw.githubusercontent.com/nvkelso/natural-earth-vector'
    '/master/geojson/ne_10m_roads.geojson'
)
CACHE_TTL_DAYS = 7
UA             = 'ProjectBackbone/1.0 (terrestrial-fiber-viz; non-commercial)'

# Overpass bounding boxes: (west, south, east, north)
OVERPASS_REGIONS = [
    ('north_america',  (-170,  15,  -50,  75)),
    ('europe',         ( -30,  33,   45,  72)),
    ('east_asia',      ( 100,  20,  155,  55)),
    ('south_asia',     (  60,   5,  100,  40)),
    ('southeast_asia', (  95, -10,  150,  25)),
    ('south_america',  ( -85, -60,  -30,  15)),
    ('west_africa',    ( -20, -10,   20,  20)),
    ('east_africa',    (  20, -35,   55,  25)),
    ('north_africa',   ( -10,  15,   45,  40)),
    ('middle_east',    (  30,  12,   65,  42)),
    ('central_asia',   (  50,  35,  100,  58)),
    ('russia_west',    (  25,  48,   90,  70)),
    ('siberia',        (  90,  48,  180,  75)),
    ('oceania',        ( 110, -45,  180,  -5)),
]

# OSM tags that indicate trunk/long-haul telecom fiber
OVERPASS_QUERY = """\
[out:json][timeout:120][bbox:{south},{west},{north},{east}];
(
  way["man_made"="pipeline"]["pipeline"="telecom"];
  way["telecom"="line"];
  way["utility"="telecom"]["man_made"~"cable|pipeline"];
  way["communication"="line"]["power"!~"."]["barrier"!~"."];
  way["cable"="yes"]["man_made"="cable"]["utility"="telecom"];
);
out geom;
"""

# ── Math ──────────────────────────────────────────────────────────────────────

def haversine(lon1, lat1, lon2, lat2):
    """Great-circle distance in km."""
    R    = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def interp_gc(lon1, lat1, lon2, lat2, steps):
    """Linear (not true great-circle) interpolation — good enough at these scales."""
    return [
        (lon1 + i / steps * (lon2 - lon1),
         lat1 + i / steps * (lat2 - lat1))
        for i in range(steps + 1)
    ]

# ── Grid spatial index ────────────────────────────────────────────────────────

class GridIndex:
    """
    Lat/lon grid index for O(1) approximate nearest-point queries.
    cell_deg controls cell size; 3° ≈ 330 km at the equator.
    """
    def __init__(self, points, cell_deg=3.0):
        self.cell = cell_deg
        self.grid = defaultdict(list)
        for pt in points:
            gx = int(math.floor(pt[0] / cell_deg))
            gy = int(math.floor(pt[1] / cell_deg))
            self.grid[(gx, gy)].append(pt)

    def nearest(self, lon, lat, max_km=150):
        """Return nearest (lon, lat) within max_km, or None."""
        cx = int(math.floor(lon / self.cell))
        cy = int(math.floor(lat / self.cell))
        # Search ring by ring; stop when nearest possible point in next ring
        # exceeds current best.
        max_rings = max(1, int(math.ceil(max_km / (self.cell * 80.0)))) + 1
        best_d, best_pt = float('inf'), None
        for ring in range(max_rings + 1):
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    for pt in self.grid.get((cx + dx, cy + dy), []):
                        d = haversine(lon, lat, pt[0], pt[1])
                        if d < best_d:
                            best_d, best_pt = d, pt
            if ring >= 1:
                # Minimum possible km in the next ring (conservative)
                min_next = (ring - 0.5) * self.cell * 80.0
                if min_next > best_d:
                    break
        return best_pt if best_d <= max_km else None

# ── Cache utilities ───────────────────────────────────────────────────────────

def _cache_file(key):
    return os.path.join(CACHE_DIR, f'{key}.json')

def _cache_valid(key):
    p = _cache_file(key)
    if not os.path.exists(p):
        return False
    return (time.time() - os.path.getmtime(p)) < CACHE_TTL_DAYS * 86400

def _cache_read(key):
    with open(_cache_file(key), encoding='utf-8') as f:
        return json.load(f)

def _cache_write(key, data):
    with open(_cache_file(key), 'w', encoding='utf-8') as f:
        json.dump(data, f)

# ── Overpass / OSM ────────────────────────────────────────────────────────────

def _query_overpass(name, bbox, retries=2):
    """Fetch Overpass JSON for one region; returns raw dict."""
    west, south, east, north = bbox
    query = OVERPASS_QUERY.format(south=south, west=west, north=north, east=east)
    payload = urllib.parse.urlencode({'data': query}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=payload)
    req.add_header('User-Agent', UA)
    req.add_header('Accept-Encoding', 'gzip')

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=150) as resp:
                raw = resp.read()
                if resp.info().get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as exc:
            if attempt < retries:
                wait = 15 * (attempt + 1)
                print(f'    retry {attempt + 1}/{retries} after {wait}s ({exc})')
                time.sleep(wait)
            else:
                raise


def fetch_osm_routes():
    """
    Query Overpass for all OVERPASS_REGIONS and return list of GeoJSON features.
    Results are cached per region; only stale regions are re-fetched.
    """
    all_features = []
    country_hint = {
        'north_america': 'US',  'europe': 'EU',     'east_asia': 'CN',
        'south_asia': 'IN',     'southeast_asia': 'SG', 'south_america': 'BR',
        'west_africa': 'NG',    'east_africa': 'KE', 'north_africa': 'EG',
        'middle_east': 'AE',    'central_asia': 'KZ', 'russia_west': 'RU',
        'siberia': 'RU',        'oceania': 'AU',
    }

    for name, bbox in OVERPASS_REGIONS:
        cache_key = f'osm_{name}'
        try:
            if _cache_valid(cache_key):
                print(f'  [{name}] cached', end='')
                osm = _cache_read(cache_key)
            else:
                print(f'  [{name}] querying Overpass…', end='', flush=True)
                osm = _query_overpass(name, bbox)
                _cache_write(cache_key, osm)
                time.sleep(3)   # polite delay between requests

            feats = _osm_to_features(osm, name, country_hint.get(name, ''))
            print(f'  →  {len(feats)} segments')
            all_features.extend(feats)

        except KeyboardInterrupt:
            print('\n  Interrupted — using partial results')
            break
        except Exception as exc:
            print(f'  FAILED: {exc}')

    return all_features


def _osm_to_features(osm, region, country_hint):
    """Convert OSM way elements to GeoJSON LineString features."""
    features = []
    for elem in osm.get('elements', []):
        if elem['type'] != 'way':
            continue
        geom = elem.get('geometry', [])
        if len(geom) < 2:
            continue

        coords = [(g['lon'], g['lat']) for g in geom]

        # Total length filter: skip anything < 5 km (last-mile drops, in-building)
        total_km = sum(
            haversine(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
            for i in range(len(coords) - 1)
        )
        if total_km < 5:
            continue

        tags     = elem.get('tags', {})
        operator = tags.get('operator', tags.get('owner', ''))
        name_tag = tags.get('name', tags.get('ref', ''))

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'LineString', 'coordinates': coords},
            'properties': {
                'source':    'OpenStreetMap',
                'type':      'verified',
                'operator':  operator,
                'name':      name_tag,
                'region':    region,
                'country':   country_hint,
                'length_km': round(total_km, 1),
                'osm_id':    elem.get('id', ''),
            },
        })
    return features

# ── FCC / OFCOM / ARCEP — documented no-ops ──────────────────────────────────

def note_government_sources():
    """
    Document why government data sources are not used:

    FCC Broadband Data Collection (broadbandmap.fcc.gov)
        Provides broadband availability by census block location and fabric
        (address-level) data.  Does NOT publish long-haul fiber route geometries.
        The NTIA BEAD programme (Infrastructure Investment and Jobs Act 2021) is
        building a national broadband map but route-level infrastructure geometry
        has not been released publicly as of mid-2025.
        → Skipped.

    OFCOM Connected Nations (UK)
        Publishes broadband coverage statistics by postcode sector and local
        authority, not physical route geometries.
        → Skipped.

    ARCEP Observatoire du Déploiement des Réseaux (France)
        Publishes address-level fibre-to-the-premises deployment status by
        operator.  Not route geometries.
        → Skipped.

    All three regimes were checked; none publish machine-readable trunk/long-haul
    fiber route data.  OSM is the best available open source for verified routes.
    """
    print('  FCC BDC:     availability/fabric data only — no route geometry')
    print('  OFCOM:       postcode-sector coverage — no route geometry')
    print('  ARCEP:       FTTP address-level data   — no route geometry')

# ── Natural Earth roads — routing guide ──────────────────────────────────────

def load_road_guidance():
    """
    Download Natural Earth 10 m roads GeoJSON (Major & Secondary Highways only)
    and return a GridIndex of sampled road points (~50 km spacing).
    Used purely as a corridor guide; routes are *attracted* toward roads,
    not constrained to them.
    """
    cache_p = os.path.join(CACHE_DIR, 'ne_10m_roads.geojson')

    if not os.path.exists(cache_p):
        print(f'  Downloading Natural Earth 10m roads ({NE_ROADS_URL})…')
        try:
            req = urllib.request.Request(NE_ROADS_URL)
            req.add_header('User-Agent', UA)
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            with open(cache_p, 'wb') as f:
                f.write(data)
            print(f'    Saved {len(data) // 1024:,} KB')
        except Exception as exc:
            print(f'    Download failed: {exc}')
            return None

    print('  Parsing road geometry…', end='', flush=True)
    with open(cache_p, encoding='utf-8') as f:
        fc = json.load(f)

    road_pts = []
    n_segs   = 0
    for feat in fc.get('features', []):
        props  = feat.get('properties', {}) or {}
        r_type = props.get('type') or ''
        # Only major infrastructure corridors; skip local roads and ferries
        if r_type not in ('Major Highway', 'Secondary Highway'):
            continue

        geom  = feat.get('geometry', {}) or {}
        gtype = geom.get('type', '')
        coord_lists = (
            [geom['coordinates']] if gtype == 'LineString'
            else geom.get('coordinates', []) if gtype == 'MultiLineString'
            else []
        )
        for coords in coord_lists:
            if len(coords) < 2:
                continue
            n_segs += 1
            for i in range(len(coords) - 1):
                lon1, lat1 = coords[i][0],   coords[i][1]
                lon2, lat2 = coords[i+1][0], coords[i+1][1]
                seg_km = haversine(lon1, lat1, lon2, lat2)
                steps  = max(1, int(seg_km / 50))
                for t in range(steps + 1):
                    frac = t / steps
                    road_pts.append((
                        lon1 + frac * (lon2 - lon1),
                        lat1 + frac * (lat2 - lat1),
                    ))

    print(f'  {len(road_pts):,} road sample pts from {n_segs:,} segments')
    return GridIndex(road_pts, cell_deg=3.0)

# ── Infrastructure node loading ───────────────────────────────────────────────

def _load_geojson(filename):
    p = os.path.join(PUBLIC_DIR, filename)
    if not os.path.exists(p):
        print(f'  Warning: {p} not found — skipping')
        return []
    with open(p, encoding='utf-8') as f:
        return json.load(f).get('features', [])


def _deduplicate_spatial(nodes, grid_km=60):
    """
    Thin a list of (lon, lat, meta) tuples by keeping at most one per ~grid_km cell.
    Prevents dense coastal clusters of landing points from dominating the graph.
    """
    cell_deg = grid_km / 111.0
    seen     = {}
    result   = []
    for lon, lat, meta in nodes:
        gx = int(math.floor(lon / cell_deg))
        gy = int(math.floor(lat / cell_deg))
        key = (gx, gy)
        if key not in seen:
            seen[key] = True
            result.append((lon, lat, meta))
    return result


def load_infrastructure_nodes():
    """
    Load IXPs, network-rich data centres, and cable landing points.
    Returns a dict {id: {lon, lat, type, label, country}}.
    """
    raw = []

    # IXPs — all of them; each is a significant peering hub
    for feat in _load_geojson('ixps.geojson'):
        c = feat['geometry']['coordinates']
        p = feat['properties']
        raw.append((c[0], c[1], {
            'type':    'ixp',
            'label':   p.get('name', ''),
            'country': p.get('country', ''),
        }))
    n_ixp = len(raw)
    print(f'    IXPs:            {n_ixp:4d}')

    # Data centres — only those with ≥ 20 colocated networks
    before = len(raw)
    for feat in _load_geojson('data-centers.geojson'):
        p = feat['properties']
        if (p.get('network_count') or 0) < 20:
            continue
        c = feat['geometry']['coordinates']
        raw.append((c[0], c[1], {
            'type':    'dc',
            'label':   p.get('name', ''),
            'country': p.get('country', ''),
        }))
    print(f'    Major DCs (≥20): {len(raw) - before:4d}')

    # Cable landing points — spatially thinned to ~1 per 60 km cell
    lp_raw = []
    for feat in _load_geojson('landing-points.geojson'):
        c = feat['geometry']['coordinates']
        p = feat['properties']
        lp_raw.append((c[0], c[1], {
            'type':    'landing',
            'label':   p.get('name', ''),
            'country': '',
        }))
    lp_thin = _deduplicate_spatial(lp_raw, grid_km=60)
    raw.extend(lp_thin)
    print(f'    Landing pts:     {len(lp_raw):4d}  →  {len(lp_thin):4d} after dedup')

    nodes = {
        i: {'lon': lon, 'lat': lat, **meta}
        for i, (lon, lat, meta) in enumerate(raw)
    }
    print(f'    Total nodes:     {len(nodes):4d}')
    return nodes

# ── Efficient k-nearest-neighbour with bbox pre-filter ────────────────────────

def _find_knn(nodes, node_id, k, max_km):
    """
    Return up to k nearest other nodes within max_km, as [(dist, other_id)].
    Uses bounding-box pre-filter to avoid full O(n) scan in dense regions.
    """
    ni      = nodes[node_id]
    lon0    = ni['lon']
    lat0    = ni['lat']
    dlat    = max_km / 111.0
    dlon    = max_km / max(1.0, 111.0 * math.cos(math.radians(lat0)))
    lat_lo  = lat0 - dlat
    lat_hi  = lat0 + dlat
    lon_lo  = lon0 - dlon
    lon_hi  = lon0 + dlon

    candidates = []
    for mid, nm in nodes.items():
        if mid == node_id:
            continue
        if not (lat_lo <= nm['lat'] <= lat_hi and lon_lo <= nm['lon'] <= lon_hi):
            continue
        d = haversine(lon0, lat0, nm['lon'], nm['lat'])
        if d <= max_km:
            candidates.append((d, mid))
    candidates.sort()
    return candidates[:k]

# ── Graph construction: Kruskal MST + redundant edges ────────────────────────

def build_graph(nodes, max_edge_km=2500, mst_k=12, extra_k=2):
    """
    1. Build a sparse candidate-edge set: each node → mst_k nearest within max_edge_km.
    2. Run Kruskal's MST to ensure full connectivity.
    3. Add extra_k more nearest edges per node for redundancy (simulates backup paths).
    Returns list of (node_id_a, node_id_b) pairs.
    """
    ids = list(nodes.keys())
    n   = len(ids)
    print(f'  Building candidate edges for {n} nodes…', end='', flush=True)

    all_edges = set()   # frozenset pairs to avoid duplicates
    edge_dists = {}     # frozenset → distance

    for nid in ids:
        for d, mid in _find_knn(nodes, nid, mst_k, max_edge_km):
            e = frozenset((nid, mid))
            if e not in edge_dists or edge_dists[e] > d:
                edge_dists[e] = d
                all_edges.add(e)

    sorted_edges = sorted(all_edges, key=lambda e: edge_dists[e])
    print(f'  {len(sorted_edges):,} candidates')

    # ── Kruskal ──────────────────────────────────────────────────────────────
    parent = {nid: nid for nid in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px == py:
            return False
        parent[px] = py
        return True

    mst_set  = set()
    mst_list = []
    for e in sorted_edges:
        a, b = tuple(e)
        if union(a, b):
            mst_set.add(e)
            mst_list.append((a, b))

    # ── Extra redundancy edges ────────────────────────────────────────────────
    final_edges = set(mst_set)
    for nid in ids:
        added = 0
        for d, mid in _find_knn(nodes, nid, extra_k + mst_k, max_edge_km):
            e = frozenset((nid, mid))
            if e not in final_edges:
                final_edges.add(e)
                added += 1
            if added >= extra_k:
                break

    result = [tuple(e) for e in final_edges]
    print(f'  MST: {len(mst_list)} edges  +  {len(result) - len(mst_list)} redundant  =  {len(result)} total')
    return result

# ── Road-snapped route between two nodes ─────────────────────────────────────

def route_snapped(lon1, lat1, lon2, lat2, road_index, snap_km=120, attraction=0.55):
    """
    Return a (lon, lat) polyline that follows road corridors where they exist.

    Algorithm
    ─────────
    1. Divide the great-circle arc into segments of ≤ 180 km.
    2. For each interior waypoint, look for a road point within snap_km.
    3. If found, shift the waypoint toward the road point by `attraction` factor.
       (attraction=1 → fully on road; attraction=0 → raw great-circle.)
    4. Return the adjusted polyline.
    """
    dist_km = haversine(lon1, lat1, lon2, lat2)
    if dist_km < 30:
        return [(lon1, lat1), (lon2, lat2)]

    steps = max(2, int(dist_km / 180))
    raw   = interp_gc(lon1, lat1, lon2, lat2, steps)

    if road_index is None:
        return raw

    result = [raw[0]]
    for lon, lat in raw[1:-1]:
        nearest = road_index.nearest(lon, lat, max_km=snap_km)
        if nearest:
            rlon, rlat = nearest
            lon = lon + attraction * (rlon - lon)
            lat = lat + attraction * (rlat - lat)
        result.append((lon, lat))
    result.append(raw[-1])
    return result


def _split_antimeridian(coords):
    """Split a coordinate list into segments at antimeridian jumps (> 180° lon)."""
    segs, seg = [], [coords[0]]
    for pt in coords[1:]:
        if abs(pt[0] - seg[-1][0]) > 180:
            if len(seg) > 1:
                segs.append(seg)
            seg = [pt]
        else:
            seg.append(pt)
    if len(seg) > 1:
        segs.append(seg)
    return segs

# ── Estimated route generation ────────────────────────────────────────────────

def estimate_routes(nodes, road_index, max_edge_km=2500):
    """
    Build estimated fiber routes for all edges in the infrastructure graph.
    Returns list of GeoJSON features.
    """
    if len(nodes) < 2:
        print('  Not enough nodes')
        return []

    edges    = build_graph(nodes, max_edge_km=max_edge_km)
    features = []

    for a, b in edges:
        na, nb  = nodes[a], nodes[b]
        coords  = route_snapped(na['lon'], na['lat'], nb['lon'], nb['lat'], road_index)
        segs    = _split_antimeridian(coords)
        dist_km = haversine(na['lon'], na['lat'], nb['lon'], nb['lat'])
        r_type  = 'international' if dist_km > 500 else 'national'

        for seg in segs:
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[round(c[0], 4), round(c[1], 4)] for c in seg],
                },
                'properties': {
                    'source':     'estimated',
                    'type':       'estimated',
                    'route_type': r_type,
                    'from':       na['label'] or na['type'],
                    'to':         nb['label'] or nb['type'],
                    'length_km':  round(dist_km, 1),
                },
            })

    print(f'  Generated {len(features)} estimated segments')
    return features

# ── Output ────────────────────────────────────────────────────────────────────

def write_geojson(filename, features):
    path = os.path.join(PUBLIC_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': features},
                  f, separators=(',', ':'))
    kb = os.path.getsize(path) // 1024
    print(f'  Wrote {path}  ({len(features):,} features, {kb:,} KB)')

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sep = '─' * 60

    # ── 1. Document skipped government sources ────────────────────────────
    print(sep)
    print('Government data sources')
    print(sep)
    note_government_sources()

    # ── 2. Fetch verified routes from OpenStreetMap ───────────────────────
    print()
    print(sep)
    print('OpenStreetMap verified routes  (14 regions)')
    print(sep)
    verified = fetch_osm_routes()
    print(f'  Verified total:  {len(verified):,} features')

    # ── 3. Load Natural Earth roads for route corridor guidance ──────────
    print()
    print(sep)
    print('Natural Earth road corridors')
    print(sep)
    road_index = None
    try:
        road_index = load_road_guidance()
    except Exception as exc:
        print(f'  Skipping road guidance: {exc}')
        print('  Estimated routes will use straight great-circle arcs.')

    # ── 4. Build estimated routes from infrastructure nodes ───────────────
    print()
    print(sep)
    print('Infrastructure node graph  →  estimated routes')
    print(sep)
    print('  Loading nodes…')
    nodes     = load_infrastructure_nodes()
    estimated = estimate_routes(nodes, road_index, max_edge_km=2500)

    # ── 5. Write output files ─────────────────────────────────────────────
    print()
    print(sep)
    print('Output')
    print(sep)
    write_geojson('fiber-routes-verified.geojson',  verified)
    write_geojson('fiber-routes-estimated.geojson', estimated)

    print()
    print('Done.')
    print(f'  Verified routes:  {len(verified):,}')
    print(f'  Estimated routes: {len(estimated):,}')


if __name__ == '__main__':
    main()
