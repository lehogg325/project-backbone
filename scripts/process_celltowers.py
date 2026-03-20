#!/usr/bin/env python3
"""
Convert an OpenCelliD CSV dump to a gridded GeoJSON density map.

Usage
─────
    python3 process_celltowers.py <path/to/cell_towers.csv>

Input columns (standard OpenCelliD export)
───────────────────────────────────────────
    radio, mcc, net, area, cell, unit, lon, lat,
    range, samples, changeable, created, updated

Algorithm
─────────
1. Stream the CSV row-by-row (handles files of any size without loading into RAM)
2. Drop rows with samples < MIN_SAMPLES or invalid / out-of-range coordinates
3. Snap each surviving tower to the nearest GRID_DEG × GRID_DEG cell centre
4. Aggregate per cell: tower count, radio technologies, avg range, total samples,
   dominant country (via MCC lookup), most-recent updated timestamp
5. Emit one GeoJSON Point feature per non-empty cell

Output: public/cell_towers.geojson
"""

import csv
import datetime
import json
import math
import os
import sys

# ── Config ───────────────────────────────────────────────────────────────────

MIN_SAMPLES  = 10       # discard sparse / unreliable readings
GRID_DEG     = 0.1      # cell width/height in degrees (~11 km at equator)
OUT_DIR      = os.path.join(os.path.dirname(__file__), '..', 'public')
REPORT_EVERY = 1_000_000

# Radio technology display order (newest first)
RADIO_ORDER = ['NR', 'LTE', 'UMTS', 'GSM', 'CDMA']

# MCC → country name (ITU E.212, most common codes)
MCC_COUNTRY = {
    '202': 'Greece',       '204': 'Netherlands',  '206': 'Belgium',
    '208': 'France',       '212': 'Monaco',       '213': 'Andorra',
    '214': 'Spain',        '216': 'Hungary',      '218': 'Bosnia',
    '220': 'Serbia',       '222': 'Italy',        '226': 'Romania',
    '228': 'Switzerland',  '230': 'Czechia',      '231': 'Slovakia',
    '232': 'Austria',      '234': 'UK',           '235': 'UK',
    '238': 'Denmark',      '240': 'Sweden',       '242': 'Norway',
    '244': 'Finland',      '246': 'Lithuania',    '247': 'Latvia',
    '248': 'Estonia',      '250': 'Russia',       '255': 'Ukraine',
    '257': 'Belarus',      '259': 'Moldova',      '260': 'Poland',
    '262': 'Germany',      '266': 'Gibraltar',    '268': 'Portugal',
    '270': 'Luxembourg',   '272': 'Ireland',      '274': 'Iceland',
    '276': 'Albania',      '278': 'Malta',        '280': 'Cyprus',
    '282': 'Georgia',      '283': 'Armenia',      '284': 'Bulgaria',
    '286': 'Turkey',       '288': 'Faroe Islands','290': 'Greenland',
    '293': 'Slovenia',     '294': 'N. Macedonia', '295': 'Liechtenstein',
    '297': 'Montenegro',   '302': 'Canada',
    '310': 'USA',          '311': 'USA',          '312': 'USA',
    '313': 'USA',          '314': 'USA',          '315': 'USA',
    '316': 'USA',          '330': 'Puerto Rico',  '334': 'Mexico',
    '338': 'Jamaica',      '340': 'Guadeloupe',   '342': 'Barbados',
    '344': 'Antigua',      '346': 'Cayman Is.',   '350': 'Bermuda',
    '356': 'St. Kitts',    '358': 'St. Lucia',    '360': 'St. Vincent',
    '364': 'Bahamas',      '366': 'Dominica',     '368': 'Cuba',
    '370': 'Dom. Republic','372': 'Haiti',        '374': 'Trinidad',
    '400': 'Azerbaijan',   '401': 'Kazakhstan',   '402': 'Bhutan',
    '404': 'India',        '405': 'India',        '406': 'India',
    '410': 'Pakistan',     '412': 'Afghanistan',  '413': 'Sri Lanka',
    '414': 'Myanmar',      '415': 'Lebanon',      '416': 'Jordan',
    '417': 'Syria',        '418': 'Iraq',         '419': 'Kuwait',
    '420': 'Saudi Arabia', '421': 'Yemen',        '422': 'Oman',
    '424': 'UAE',          '425': 'Israel',       '426': 'Bahrain',
    '427': 'Qatar',        '428': 'Mongolia',     '429': 'Nepal',
    '432': 'Iran',         '434': 'Uzbekistan',   '436': 'Tajikistan',
    '437': 'Kyrgyzstan',   '438': 'Turkmenistan',
    '440': 'Japan',        '441': 'Japan',        '450': 'South Korea',
    '452': 'Vietnam',      '454': 'Hong Kong',    '455': 'Macau',
    '456': 'Cambodia',     '457': 'Laos',
    '460': 'China',        '461': 'China',        '466': 'Taiwan',
    '470': 'Bangladesh',   '472': 'Maldives',
    '502': 'Malaysia',     '505': 'Australia',    '510': 'Indonesia',
    '515': 'Philippines',  '520': 'Thailand',     '525': 'Singapore',
    '530': 'New Zealand',  '537': 'Papua New Guinea',
    '539': 'Tonga',        '542': 'Fiji',         '546': 'New Caledonia',
    '547': 'Fr. Polynesia','549': 'Samoa',
    '602': 'Egypt',        '603': 'Algeria',      '604': 'Morocco',
    '605': 'Tunisia',      '606': 'Libya',        '607': 'Gambia',
    '608': 'Senegal',      '609': 'Mauritania',   '610': 'Mali',
    '611': 'Guinea',       '612': 'Ivory Coast',  '613': 'Burkina Faso',
    '614': 'Niger',        '615': 'Togo',         '616': 'Benin',
    '617': 'Mauritius',    '618': 'Liberia',      '619': 'Sierra Leone',
    '620': 'Ghana',        '621': 'Nigeria',      '622': 'Chad',
    '624': 'Cameroon',     '625': 'Cape Verde',   '628': 'Gabon',
    '629': 'Rep. Congo',   '630': 'DR Congo',     '631': 'Angola',
    '633': 'Seychelles',   '634': 'Sudan',        '635': 'Rwanda',
    '636': 'Ethiopia',     '637': 'Somalia',      '639': 'Kenya',
    '640': 'Tanzania',     '641': 'Uganda',       '642': 'Burundi',
    '643': 'Mozambique',   '645': 'Zambia',       '646': 'Madagascar',
    '648': 'Zimbabwe',     '649': 'Namibia',      '650': 'Malawi',
    '651': 'Lesotho',      '652': 'Botswana',     '653': 'Eswatini',
    '655': 'South Africa', '659': 'South Sudan',
    '702': 'Belize',       '704': 'Guatemala',    '706': 'El Salvador',
    '708': 'Honduras',     '710': 'Nicaragua',    '712': 'Costa Rica',
    '714': 'Panama',       '716': 'Peru',         '722': 'Argentina',
    '724': 'Brazil',       '730': 'Chile',        '732': 'Colombia',
    '734': 'Venezuela',    '736': 'Bolivia',      '740': 'Ecuador',
    '744': 'Paraguay',     '746': 'Suriname',     '748': 'Uruguay',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def snap(value, step):
    """Round value to nearest multiple of step (cell-centre snapping)."""
    return round(math.floor(value / step + 0.5) * step, 10)


def ts_to_date(ts):
    """Unix timestamp → 'YYYY-MM-DD' string, or '' on failure."""
    try:
        return datetime.datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d')
    except Exception:
        return ''


def radio_label(radios):
    """Return techs ordered newest-first, e.g. 'LTE · GSM · UMTS'."""
    present = sorted(
        radios.keys(),
        key=lambda r: (RADIO_ORDER.index(r) if r in RADIO_ORDER else 99, -radios[r])
    )
    return ' · '.join(present)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_celltowers.py <path/to/cell_towers.csv>")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)

    # (gx, gy) → cell accumulator
    grid  = {}
    total = 0
    kept  = 0
    bad   = 0

    print(f"Reading {csv_path} ...")
    with open(csv_path, newline='', encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total += 1
            if total % REPORT_EVERY == 0:
                pct = kept / total * 100
                print(f"  {total:>12,}  rows  |  {kept:>9,} kept ({pct:.1f}%)  |  {len(grid):>7,} cells")

            # ── Filter ───────────────────────────────────────────────────────
            try:
                samples = int(row.get('samples') or 0)
                if samples < MIN_SAMPLES:
                    continue
                lon = float(row['lon'])
                lat = float(row['lat'])
            except (ValueError, TypeError, KeyError):
                bad += 1
                continue

            if not (-180.0 < lon < 180.0 and -90.0 <= lat <= 90.0):
                bad += 1
                continue

            radio   = (row.get('radio')   or '').strip() or 'Unknown'
            mcc     = (row.get('mcc')     or '').strip()
            rng     = row.get('range')    or '0'
            updated = row.get('updated')  or '0'

            # ── Bin ──────────────────────────────────────────────────────────
            key = (snap(lon, GRID_DEG), snap(lat, GRID_DEG))
            if key not in grid:
                grid[key] = {
                    'count':       0,
                    'samples':     0,
                    'radios':      {},
                    'mccs':        {},
                    'range_sum':   0,
                    'range_count': 0,
                    'max_updated': 0,
                }
            c = grid[key]
            c['count']   += 1
            c['samples'] += samples
            c['radios'][radio] = c['radios'].get(radio, 0) + 1
            if mcc:
                c['mccs'][mcc] = c['mccs'].get(mcc, 0) + 1

            try:
                r = float(rng)
                if r > 0:
                    c['range_sum']   += r
                    c['range_count'] += 1
            except (ValueError, TypeError):
                pass

            try:
                u = int(updated)
                if u > c['max_updated']:
                    c['max_updated'] = u
            except (ValueError, TypeError):
                pass

            kept += 1

    print(f"\nTotal rows : {total:,}")
    print(f"Kept       : {kept:,}  ({kept/total*100:.1f}%)" if total else "Kept: 0")
    print(f"Skipped    : {total - kept:,}  (below threshold or invalid)")
    print(f"Grid cells : {len(grid):,}")
    if grid:
        counts    = [v['count'] for v in grid.values()]
        max_count = max(counts)
        p99       = sorted(counts)[int(len(counts) * 0.99)]
        print(f"Max towers/cell : {max_count:,}   p99 : {p99:,}")

    # ── Build GeoJSON ─────────────────────────────────────────────────────────
    features = []
    for (lon, lat), c in grid.items():
        top_mcc  = max(c['mccs'], key=c['mccs'].get) if c['mccs'] else ''
        country  = MCC_COUNTRY.get(top_mcc, top_mcc or '—')
        avg_range = (
            round(c['range_sum'] / c['range_count'])
            if c['range_count'] else None
        )
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {
                'count':     c['count'],
                'coverage':  radio_label(c['radios']),
                'avg_range': avg_range,
                'samples':   c['samples'],
                'country':   country,
                'updated':   ts_to_date(c['max_updated']) if c['max_updated'] else '—',
            },
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, 'cell_towers.geojson')
    with open(out, 'w') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f,
                  separators=(',', ':'))

    size_mb = os.path.getsize(out) / 1_048_576
    print(f"\ncell_towers.geojson: {len(features):,} cells  →  {out}  ({size_mb:.1f} MB)")
    print("Done.")


if __name__ == '__main__':
    main()
