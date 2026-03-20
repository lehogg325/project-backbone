/**
 * useSatellitePositions
 *
 * Loads pre-fetched TLE JSON files from /public, pre-parses every satellite
 * record once, then runs SGP4 propagation on a fixed interval and returns
 * current geodetic positions.
 *
 * Static files, not live API
 * ──────────────────────────
 * TLE data is loaded from static JSON files bundled with the app (starlink-tle.json,
 * oneweb-tle.json, geo-commsats-tle.json). These are intentionally NOT fetched from
 * CelesTrak at runtime — the API does not set CORS headers, so browser requests would
 * be blocked. Run scripts/fetch_satellite_data.py periodically (daily for LEO,
 * weekly for GEO) to refresh the static files before deploying.
 *
 * Performance notes
 * ─────────────────
 * • satrecs are parsed once on mount (O(n) work, kept in a ref).
 * • Each tick writes lon/lat/alt into pre-allocated Float32Arrays (no GC pressure
 *   from allocating thousands of objects per update).
 * • A parallel names array (stable reference) lets callers pair Float32Array
 *   indices back to satellite names without re-creating objects.
 * • GEO satellites barely move; they share the same 2 s interval as LEO but
 *   could trivially be slowed further.
 * • If 9 000+ Starlink sats cause jank, reduce UPDATE_MS_LEO or move
 *   propagateGroup() into a Web Worker.
 *
 * Return shape
 * ────────────
 * {
 *   starlink : { positions: Float32Array([lon,lat,alt, …]), names: string[], count: number }
 *   oneweb   : { positions: Float32Array([lon,lat,alt, …]), names: string[], count: number }
 *   geo      : { positions: Float32Array([lon,lat,alt, …]), names: string[], count: number }
 *   kuiper   : { positions: Float32Array([lon,lat,alt, …]), names: string[], count: number }
 *   loading  : boolean
 * }
 *
 * Each satellite occupies 3 consecutive floats: [longitude, latitude, altitude_km].
 * `count` is the number of valid satellites this tick (≤ names.length).
 */

import { useEffect, useRef, useState } from 'react';
import * as sat from 'satellite.js';

const UPDATE_MS_LEO = 2000;   // Starlink / OneWeb  — positions shift visibly
const UPDATE_MS_GEO = 10000;  // GEO commsats       — near-stationary, update rarely

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Load a TLE group JSON file and parse satrecs.
 * Supports both:
 *   - Legacy flat array:  [{name, tle1, tle2}, …]
 *   - Envelope format:   {generatedAt: "ISO", satellites: [{name, tle1, tle2}, …]}
 *
 * Warns in the console if the data is older than maxAgeHours.
 */
async function loadGroup(url, { maxAgeHours = 48 } = {}) {
  const raw = await fetch(url).then(r => r.json());

  // Support both legacy flat array and envelope format
  const entries     = Array.isArray(raw) ? raw : (raw?.satellites ?? []);
  const generatedAt = Array.isArray(raw) ? null : (raw?.generatedAt ?? null);

  if (generatedAt) {
    const ageHours = (Date.now() - new Date(generatedAt).getTime()) / 3_600_000;
    if (ageHours > maxAgeHours) {
      console.warn(
        `[useSatellitePositions] TLE data at ${url} is ${ageHours.toFixed(0)} h old ` +
        `(recommended max: ${maxAgeHours} h). Run scripts/fetch_satellite_data.py to refresh.`
      );
    }
  }

  const names   = [];
  const satrecs = [];
  for (const { name, tle1, tle2 } of entries) {
    try {
      const rec = sat.twoline2satrec(tle1, tle2);
      names.push(name);
      satrecs.push(rec);
    } catch {
      // malformed TLE — skip
    }
  }
  // Pre-allocate output buffer: 3 floats per sat (lon, lat, alt)
  const positions = new Float32Array(names.length * 3);
  return { names, satrecs, positions };
}

/**
 * Propagate every satrec to `date`, writing results into the pre-allocated
 * Float32Array. Returns the number of valid entries written.
 */
function propagateGroup(group, date) {
  const { satrecs, names, positions } = group;
  const gmst = sat.gstime(date);
  let count  = 0;

  for (let i = 0; i < satrecs.length; i++) {
    const pv = sat.propagate(satrecs[i], date);
    if (!pv.position) continue;                         // bad TLE / re-entered

    const geo = sat.eciToGeodetic(pv.position, gmst);
    const lat  = sat.radiansToDegrees(geo.latitude);
    let   lon  = sat.radiansToDegrees(geo.longitude);
    const alt  = geo.height;                            // km above WGS84

    if (!isFinite(lat) || !isFinite(lon) || !isFinite(alt)) continue;
    if (alt < -100 || alt > 80000) continue;            // clearly invalid

    // Normalise longitude to [-180, 180]
    if (lon > 180)  lon -= 360;
    if (lon < -180) lon += 360;

    const base = count * 3;
    positions[base]     = lon;
    positions[base + 1] = lat;
    positions[base + 2] = alt;

    // Mirror the name into the packed position so callers can look it up
    // by the same index (names array is stable; we just track the count).
    if (count !== i) names[count] = names[i];  // compact valid entries

    count++;
  }

  return count;
}

// ── State shape (one per group) ───────────────────────────────────────────────
// We box into an object so we can trigger a state update by swapping the
// reference while keeping the Float32Array buffer itself in a ref (no copy).

function makeSnapshot(group, count) {
  return { positions: group.positions, names: group.names, count };
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useSatellitePositions() {
  const starlinkGroup = useRef(null);
  const onewebGroup   = useRef(null);
  const geoGroup      = useRef(null);
  const issGroup      = useRef(null);
  const kuiperGroup   = useRef(null);

  const [starlink, setStarlink] = useState(null);
  const [oneweb,   setOneweb]   = useState(null);
  const [geo,      setGeo]      = useState(null);
  const [iss,      setIss]      = useState(null);
  const [kuiper,   setKuiper]   = useState(null);
  const [loading,  setLoading]  = useState(true);

  const leoTimer = useRef(null);
  const geoTimer = useRef(null);

  useEffect(() => {
    let cancelled = false;

    // ISS is loaded separately so a missing/stale iss-tle.json cannot block
    // Starlink, OneWeb, or GEO from initialising.
    Promise.all([
      loadGroup('/starlink-tle.json',     { maxAgeHours: 48  })
        .catch(err => { console.error('[TLE] starlink failed to load:', err?.message ?? err); return null; }),
      loadGroup('/oneweb-tle.json',       { maxAgeHours: 48  })
        .catch(err => { console.error('[TLE] oneweb failed to load:', err?.message ?? err);   return null; }),
      loadGroup('/geo-commsats-tle.json', { maxAgeHours: 168 })
        .catch(err => { console.error('[TLE] geo failed to load:', err?.message ?? err);      return null; }),
      // Kuiper loaded alongside LEO groups; empty file is handled gracefully
      loadGroup('/kuiper-tle.json',       { maxAgeHours: 48  })
        .catch(err => { console.warn('[TLE] kuiper failed to load:', err?.message ?? err); return { names: [], satrecs: [], positions: new Float32Array(0) }; }),
    ]).then(([sl, ow, ge, kp]) => {
      if (cancelled) return;

      if (!sl || !ow || !ge) {
        console.error('[useSatellitePositions] One or more critical TLE files failed to load. Check the console for details.');
        setLoading(false);
        return;
      }

      starlinkGroup.current = sl;
      onewebGroup.current   = ow;
      geoGroup.current      = ge;
      kuiperGroup.current   = kp;

      // ── Initial propagation ──────────────────────────────────────────────
      const now = new Date();
      const slCount = propagateGroup(sl, now);
      const owCount = propagateGroup(ow, now);
      const geCount = propagateGroup(ge, now);
      const kpCount = propagateGroup(kp, now);

      setStarlink(makeSnapshot(sl, slCount));
      setOneweb(makeSnapshot(ow, owCount));
      setGeo(makeSnapshot(ge, geCount));
      setKuiper(makeSnapshot(kp, kpCount));
      setLoading(false);

      // ── LEO update loop (Starlink + OneWeb + Kuiper) ─────────────────────
      leoTimer.current = setInterval(() => {
        if (!starlinkGroup.current || !onewebGroup.current) return;
        const d = new Date();
        const sc = propagateGroup(starlinkGroup.current, d);
        const oc = propagateGroup(onewebGroup.current, d);
        // Swap object reference to trigger React re-render; buffer is reused.
        setStarlink(makeSnapshot(starlinkGroup.current, sc));
        setOneweb(makeSnapshot(onewebGroup.current, oc));
        // Kuiper — small constellation for now; same interval as other LEO
        // TODO: move to Web Worker when constellation exceeds ~100 satellites
        if (kuiperGroup.current) {
          const kc = propagateGroup(kuiperGroup.current, d);
          setKuiper(makeSnapshot(kuiperGroup.current, kc));
        }
        // ISS is updated in its own interval below if loaded
        if (issGroup.current) {
          const ic = propagateGroup(issGroup.current, d);
          setIss(makeSnapshot(issGroup.current, ic));
        }
      }, UPDATE_MS_LEO);

      // ── GEO update loop ──────────────────────────────────────────────────
      geoTimer.current = setInterval(() => {
        if (!geoGroup.current) return;
        const d  = new Date();
        const gc = propagateGroup(geoGroup.current, d);
        setGeo(makeSnapshot(geoGroup.current, gc));
      }, UPDATE_MS_GEO);
    });

    // ── ISS — loaded independently; failure does not affect other groups ──
    loadGroup('/iss-tle.json', { maxAgeHours: 48 }).then(is => {
      if (cancelled) return;
      issGroup.current = is;
      const ic = propagateGroup(is, new Date());
      setIss(makeSnapshot(is, ic));
    }).catch(err => {
      // A 404 is expected in dev before running the fetch script; log other failures.
      if (err?.name !== 'SyntaxError') {
        console.warn('[useSatellitePositions] ISS TLE load failed:', err?.message ?? err,
          '— run scripts/fetch_satellite_data.py to generate iss-tle.json');
      }
    });

    return () => {
      cancelled = true;
      clearInterval(leoTimer.current);
      clearInterval(geoTimer.current);
    };
  }, []);

  return { starlink, oneweb, geo, iss, kuiper, loading, starlinkGroup, onewebGroup, geoGroup, issGroup, kuiperGroup };
}
