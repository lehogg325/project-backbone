import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { _GlobeView as GlobeView, FlyToInterpolator } from '@deck.gl/core';
import { GeoJsonLayer, BitmapLayer, ScatterplotLayer, ArcLayer, IconLayer } from '@deck.gl/layers';
import { TileLayer } from '@deck.gl/geo-layers';
import { PathStyleExtension } from '@deck.gl/extensions';
import InfoPanel from './InfoPanel';
import LayerToggle from './LayerToggle';
import SpaceLayerToggle from './SpaceLayerToggle';
import DetailPanel from './DetailPanel';
import { useSatellitePositions } from './useSatellitePositions';
import * as sat from 'satellite.js';

/** Return features array only if d looks like a valid FeatureCollection. */
function safeFeatures(d) {
  return Array.isArray(d?.features) ? d.features : [];
}

/**
 * Fetch wrapper that logs the URL, response status, CSP headers, and any
 * errors to the console. Temporary debugging aid for GitHub Pages diagnosis.
 */
async function debugFetch(url) {
  console.log(`[fetch] → ${url}`);
  let r;
  try {
    r = await fetch(url);
  } catch (err) {
    console.error(`[fetch] NETWORK ERROR ${url}`, err);
    throw err;
  }
  const csp = r.headers.get('content-security-policy');
  const ct  = r.headers.get('content-type');
  const cl  = r.headers.get('content-length');
  console.log(
    `[fetch] ← ${url} | status: ${r.status} ${r.statusText}` +
    ` | content-type: ${ct}` +
    (cl ? ` | size: ${(parseInt(cl) / 1024).toFixed(1)} KB` : '') +
    (csp ? ` | CSP: ${csp}` : ''),
  );
  if (!r.ok) {
    const err = new Error(`HTTP ${r.status} ${r.statusText}: ${url}`);
    console.error(`[fetch] ERROR`, err);
    throw err;
  }
  return r.json();
}

// ── Icon atlases ───────────────────────────────────────────────────────────────
// Each is a 32×32 white-on-transparent SVG. deck.gl IconLayer uses mask:true so
// the white pixels are filled with getColor at render time — one atlas per shape.

function _svgAtlas(body) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">${body}</svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

const ICON_MAPPING = { icon: { x: 0, y: 0, width: 32, height: 32, anchorX: 16, anchorY: 16, mask: true } };

// Diamond — Landing Points (rotated square, maritime junction symbol)
const ATLAS_DIAMOND  = _svgAtlas('<polygon points="16,3 29,16 16,29 3,16" fill="white"/>');

// Square — Data Centers (cartographic facility/building symbol)
const ATLAS_SQUARE   = _svgAtlas('<rect x="8" y="8" width="16" height="16" fill="white"/>');

// Flat-top hexagon — IXPs (network exchange / node symbol)
const ATLAS_HEX      = _svgAtlas('<polygon points="29,16 22.5,4.8 9.5,4.8 3,16 9.5,27.2 22.5,27.2" fill="white"/>');

// Upward triangle — CDN PoPs (broadcast / distribution vector)
const ATLAS_TRIANGLE = _svgAtlas('<polygon points="16,3 30,29 2,29" fill="white"/>');

// Cross / plus — DNS Root Servers (namespace crossroads symbol)
const ATLAS_CROSS    = _svgAtlas('<rect x="14" y="4" width="4" height="24" fill="white"/><rect x="4" y="14" width="24" height="4" fill="white"/>');

// Uplink chevron ∧ — Ground Stations (dish pointing skyward)
const ATLAS_CHEVRON  = _svgAtlas('<path d="M3,26 L16,6 L29,26 L25,26 L16,11 L7,26 Z" fill="white"/>');

// ISS silhouette viewed from above:
//   long horizontal truss · central module cluster · 4×2 solar panel arrays
const ATLAS_ISS = _svgAtlas(`
  <rect x="1"  y="14" width="30" height="4"  fill="white"/>
  <rect x="12" y="10" width="8"  height="12" fill="white"/>
  <rect x="1"  y="6"  width="9"  height="4"  fill="white"/>
  <rect x="1"  y="11" width="9"  height="3"  fill="white"/>
  <rect x="1"  y="18" width="9"  height="3"  fill="white"/>
  <rect x="1"  y="22" width="9"  height="4"  fill="white"/>
  <rect x="22" y="6"  width="9"  height="4"  fill="white"/>
  <rect x="22" y="11" width="9"  height="3"  fill="white"/>
  <rect x="22" y="18" width="9"  height="3"  fill="white"/>
  <rect x="22" y="22" width="9"  height="4"  fill="white"/>
`);

const INITIAL_VIEW_STATE = {
  longitude: 0,
  latitude: 20,
  zoom: 1.5,
  minZoom: 1,
  maxZoom: 20,
};

const GLOBE_VIEW = new GlobeView({ id: 'globe', controller: true });
const ZOOM_THRESHOLD      = 6;
const CELL_ZOOM_THRESHOLD = 5;
const DNS_ZOOM_THRESHOLD  = 4;
const CDN_ZOOM_THRESHOLD  = 3;
const FIBER_ZOOM_THRESHOLD = 3;

// CDN provider colours — orange/gold/pink/blue
const CDN_PROVIDER_COLORS = {
  Cloudflare:  [243, 128,  32],
  CloudFront:  [255, 200,  50],
  Fastly:      [255,  90, 180],
  Akamai:      [ 30, 150, 255],
};

// One distinct colour per root server letter A–M
const DNS_ROOT_COLORS = {
  A: [255,  68,  68], B: [255, 136,   0], C: [255, 221,   0],
  D: [136, 204,   0], E: [  0, 204, 136], F: [  0, 204, 255],
  G: [  0, 136, 255], H: [ 68,  68, 255], I: [136,   0, 255],
  J: [204,   0, 255], K: [255,   0, 170], L: [255,   0,  85],
  M: [  0, 255, 170],
};

const DNS_RESOLVER_COLORS = {
  Cloudflare: [255, 107,  53],
  Google:     [ 66, 133, 244],
  Quad9:      [155,  89, 182],
  OpenDNS:    [ 39, 174,  96],
};

const GEO_COMM_KEYWORDS = [
  'INTELSAT', 'SES', 'EUTELSAT', 'VIASAT', 'HUGHES', 'ARABSAT',
  'JSAT', 'TURKSAT', 'MEASAT', 'TELESAT', 'DIRECTV', 'AMC-', 'GALAXY',
];

const CARTO_TILES = [
  'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
  'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
  'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
  'https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
];

function hexToRgb(hex) {
  const r = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return r ? [parseInt(r[1], 16), parseInt(r[2], 16), parseInt(r[3], 16)] : [79, 195, 247];
}

// Heat-style colour ramp for cell tower density (log-scaled count → RGBA)
function cellColor(count) {
  const t = Math.min(1, Math.log2(count + 1) / Math.log2(81)); // 80+ towers = max
  if (t < 0.33) {
    const s = t / 0.33;
    return [Math.round(s * 60), Math.round(s * 200 + 55), 255, 160];
  }
  if (t < 0.67) {
    const s = (t - 0.33) / 0.34;
    return [Math.round(60 + s * 195), 255, Math.round(255 * (1 - s)), 170];
  }
  const s = (t - 0.67) / 0.33;
  return [255, Math.round(255 * (1 - s * 0.85)), 0, 190];
}

// Log-scaled radius in metres for data center icons, by network count
function dcRadius(networkCount) {
  const n = Math.max(1, networkCount || 1);
  return Math.round(Math.max(10000, Math.min(60000, 10000 + Math.log2(n) * 7000)));
}

const tooltipStyle = {
  position: 'absolute',
  background: 'rgba(8, 12, 22, 0.92)',
  color: '#d0eeff',
  padding: '8px 12px',
  borderRadius: 6,
  fontSize: 13,
  pointerEvents: 'none',
  border: '1px solid rgba(80, 200, 255, 0.25)',
  maxWidth: 240,
  lineHeight: 1.6,
  fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
  boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
};

function lineKm(coords) {
  let km = 0;
  for (let i = 1; i < coords.length; i++) {
    const [lon1, lat1] = coords[i - 1];
    const [lon2, lat2] = coords[i];
    const R = 6371;
    const dlat = (lat2 - lat1) * Math.PI / 180;
    const dlon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dlat / 2) ** 2 +
      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dlon / 2) ** 2;
    km += R * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  return km;
}

/** Point-to-point great-circle distance in km. */
function haversineKm(lon1, lat1, lon2, lat2) {
  const R = 6371;
  const dlat = (lat2 - lat1) * Math.PI / 180;
  const dlon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dlat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dlon / 2) ** 2;
  return R * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
}

/**
 * Propagate one full orbit (period derived from mean motion) at 1-minute steps.
 * Returns a GeoJSON Feature<MultiLineString> split at antimeridian crossings.
 */
function computeOrbitPath(satrec) {
  const periodMin = Math.round((2 * Math.PI) / satrec.no); // minutes per orbit
  const now = new Date();
  const pts = [];

  for (let t = 0; t <= periodMin; t++) {
    const d = new Date(now.getTime() + t * 60_000);
    const pv = sat.propagate(satrec, d);
    if (!pv.position) continue;
    const gmst = sat.gstime(d);
    const geo  = sat.eciToGeodetic(pv.position, gmst);
    let   lon  = sat.radiansToDegrees(geo.longitude);
    const lat  = sat.radiansToDegrees(geo.latitude);
    if (lon > 180)  lon -= 360;
    if (lon < -180) lon += 360;
    if (!isFinite(lon) || !isFinite(lat)) continue;
    pts.push([lon, lat]);
  }

  if (pts.length === 0) return null;

  // Split into segments at antimeridian jumps (>180° lon change)
  const segments = [];
  let seg = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    if (Math.abs(pts[i][0] - pts[i - 1][0]) > 180) {
      if (seg.length > 1) segments.push(seg);
      seg = [pts[i]];
    } else {
      seg.push(pts[i]);
    }
  }
  if (seg.length > 1) segments.push(seg);

  return {
    type: 'Feature',
    geometry: { type: 'MultiLineString', coordinates: segments },
    properties: {},
  };
}

export default function App() {
  const [tooltip, setTooltip] = useState(null);
  const [cableCount, setCableCount] = useState(null);
  const [cableMiles, setCableMiles] = useState(null);
  const [landingPointCount, setLandingPointCount] = useState(null);
  const [backboneCount, setBackboneCount] = useState(null);
  const [backboneMiles, setBackboneMiles] = useState(null);
  const [dcFeatures, setDcFeatures] = useState([]);
  const [dcNetworkTotal, setDcNetworkTotal] = useState(null);
  const [dcCountryCount, setDcCountryCount] = useState(null);
  const [ixpFeatures, setIxpFeatures] = useState([]);
  const [cellFeatures, setCellFeatures] = useState([]);
  const [cellTowerCount, setCellTowerCount] = useState(null);
  const [cellSiteCount, setCellSiteCount] = useState(null);
  const [landingPointFeatures, setLandingPointFeatures] = useState([]);
  const [detailFeature, setDetailFeature] = useState(null);
  const [groundStationFeatures, setGroundStationFeatures] = useState([]);
  const [dnsRootFeatures, setDnsRootFeatures] = useState([]);
  const [dnsResolverFeatures, setDnsResolverFeatures] = useState([]);
  const [cdnFeatures, setCdnFeatures] = useState([]);
  const [fiberVerifiedFeatures, setFiberVerifiedFeatures] = useState([]);
  const [fiberEstimatedFeatures, setFiberEstimatedFeatures] = useState([]);
  const [orbitFeature, setOrbitFeature] = useState(null);
  const [orbitSatInfo, setOrbitSatInfo] = useState(null);

  const { starlink, oneweb, geo, iss, kuiper, starlinkGroup, onewebGroup, geoGroup, issGroup, kuiperGroup } = useSatellitePositions();

  // Only re-render when zoom crosses a threshold, not on every frame
  const zoomRef = useRef(INITIAL_VIEW_STATE.zoom);
  const [zoomed, setZoomed] = useState(false);
  const [cellZoomed, setCellZoomed] = useState(false);
  const [dnsZoomed, setDnsZoomed] = useState(false);
  const [cdnZoomed, setCdnZoomed] = useState(false);
  const [fiberZoomed, setFiberZoomed] = useState(false);

  const [layerVisibility, setLayerVisibility] = useState({
    cables: true,
    datacenters: false,
    ixps: false,
    dns: false,
    cdn: false,
    fiber: false,
    backbone: false,
    cellTowers: false,
    iss: true,
    starlink: false,
    oneweb: false,
    kuiper: false,
    geoSats: false,
    groundStations: false,
  });

  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const issFlyDone = useRef(false);

  // Lazy-load tracking — prevent re-fetching when a layer is toggled off then back on
  const dcFetchedRef           = useRef(false);
  const cellFetchedRef         = useRef(false);
  const fiberFetchedRef        = useRef(false);
  const groundStationFetchedRef = useRef(false);
  const dnsFetchedRef          = useRef(false);
  const cdnFetchedRef          = useRef(false);
  const [taglineVisible, setTaglineVisible] = useState(true);
  const [taglineMounted, setTaglineMounted] = useState(true);

  // ISS auto-fly consent — persisted to localStorage so returning visitors aren't asked again
  const [issAutoFly, setIssAutoFly] = useState(
    () => localStorage.getItem('pb_iss_autofly') !== 'false'
  );
  const [issConsentAsked, setIssConsentAsked] = useState(
    () => localStorage.getItem('pb_iss_consent_asked') === 'true'
  );
  const confirmIssAutoFly = useCallback((value) => {
    setIssAutoFly(value);
    setIssConsentAsked(true);
    localStorage.setItem('pb_iss_autofly', value ? 'true' : 'false');
    localStorage.setItem('pb_iss_consent_asked', 'true');
  }, []);

  // Fly to ISS once on first position fix (only if user has opted in)
  useEffect(() => {
    if (!issAutoFly || issFlyDone.current || !iss || iss.count === 0) return;
    issFlyDone.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setViewState(v => ({
      ...v,
      longitude: iss.positions[0],
      latitude: iss.positions[1],
      zoom: 2.5,
      transitionDuration: 2000,
      transitionInterpolator: new FlyToInterpolator({ speed: 1.5 }),
    }));
  }, [iss, issAutoFly]);

  useEffect(() => {
    const dismiss = () => {
      setTaglineVisible(false);
      setTimeout(() => setTaglineMounted(false), 6000);
    };
    window.addEventListener('mousedown', dismiss, { once: true });
    return () => window.removeEventListener('mousedown', dismiss);
  }, []);

  // Eagerly load only what's visible on startup (cables needs landing-points for
  // connection arcs; ixps is small and feeds the info-panel count).
  useEffect(() => {
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}ixps.geojson`).then(d => setIxpFeatures(safeFeatures(d))).catch(console.error);
    debugFetch(`${base}landing-points.geojson`).then(d => {
      const features = safeFeatures(d);
      setLandingPointFeatures(features);
      setLandingPointCount(features.length);
    }).catch(console.error);
  }, []);

  // Lazy: data centers — 1.5 MB, only needed when layer is on
  useEffect(() => {
    if (!layerVisibility.datacenters || dcFetchedRef.current) return;
    dcFetchedRef.current = true;
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}data-centers.geojson`).then(d => {
      const features = safeFeatures(d);
      setDcFeatures(features);
      setDcNetworkTotal(features.reduce((s, f) => s + (f.properties.network_count || 0), 0));
      setDcCountryCount(new Set(features.map(f => f.properties.country).filter(Boolean)).size);
    }).catch(console.error);
  }, [layerVisibility.datacenters]);

  // Lazy: cell towers — 18 MB, only needed when layer is on
  useEffect(() => {
    if (!layerVisibility.cellTowers || cellFetchedRef.current) return;
    cellFetchedRef.current = true;
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}cell_towers.geojson`).then(d => {
      const features = safeFeatures(d);
      setCellFeatures(features);
      setCellTowerCount(features.length);
      setCellSiteCount(features.reduce((s, f) => s + (f.properties.count || 0), 0));
    }).catch(console.error);
  }, [layerVisibility.cellTowers]);

  // Lazy: fiber routes — 2.2 MB each, only needed when fiber layer is on
  useEffect(() => {
    if (!layerVisibility.fiber || fiberFetchedRef.current) return;
    fiberFetchedRef.current = true;
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}fiber-routes-verified.geojson`).then(d => setFiberVerifiedFeatures(safeFeatures(d))).catch(console.error);
    debugFetch(`${base}fiber-routes-estimated.geojson`).then(d => setFiberEstimatedFeatures(safeFeatures(d))).catch(console.error);
  }, [layerVisibility.fiber]);

  // Lazy: ground stations — only needed when layer is on
  useEffect(() => {
    if (!layerVisibility.groundStations || groundStationFetchedRef.current) return;
    groundStationFetchedRef.current = true;
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}ground-stations.geojson`).then(d => setGroundStationFeatures(safeFeatures(d))).catch(console.error);
  }, [layerVisibility.groundStations]);

  // Lazy: DNS — only needed when layer is on
  useEffect(() => {
    if (!layerVisibility.dns || dnsFetchedRef.current) return;
    dnsFetchedRef.current = true;
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}dns-root-instances.geojson`).then(d => setDnsRootFeatures(safeFeatures(d))).catch(console.error);
    debugFetch(`${base}dns-resolvers.geojson`).then(d => setDnsResolverFeatures(safeFeatures(d))).catch(console.error);
  }, [layerVisibility.dns]);

  // Lazy: CDN — only needed when layer is on
  useEffect(() => {
    if (!layerVisibility.cdn || cdnFetchedRef.current) return;
    cdnFetchedRef.current = true;
    const base = import.meta.env.BASE_URL;
    debugFetch(`${base}cdn-edge-locations.geojson`).then(d => setCdnFeatures(safeFeatures(d))).catch(console.error);
  }, [layerVisibility.cdn]);

  // Index arrays for satellite ScatterplotLayers — recreated each tick when snapshot changes
  const starlinkData = useMemo(
    () => starlink ? Array.from({ length: starlink.count }, (_, i) => i) : [],
    [starlink],
  );
  const onewebData = useMemo(
    () => oneweb ? Array.from({ length: oneweb.count }, (_, i) => i) : [],
    [oneweb],
  );
  // Project Kuiper — Amazon LEO broadband constellation
  // Planned orbital shells: 590 km (784 sats), 610 km (1,296 sats), 630 km (1,156 sats)
  // TODO: move propagation to Web Worker when constellation exceeds ~100 satellites
  const kuiperData = useMemo(
    () => kuiper ? Array.from({ length: kuiper.count }, (_, i) => i) : [],
    [kuiper],
  );

  const geoData = useMemo(() => {
    if (!geo) return [];
    return Array.from({ length: geo.count }, (_, i) => i)
      .filter(i => GEO_COMM_KEYWORDS.some(kw => geo.names[i]?.toUpperCase().includes(kw)));
  }, [geo]);

  function toggleLayer(id) {
    setLayerVisibility(prev => ({ ...prev, [id]: !prev[id] }));
  }

  function handleViewStateChange({ viewState }) {
    setViewState(viewState);
    const prev = zoomRef.current;
    zoomRef.current = viewState.zoom;
    if ((prev >= ZOOM_THRESHOLD) !== (viewState.zoom >= ZOOM_THRESHOLD))
      setZoomed(viewState.zoom >= ZOOM_THRESHOLD);
    if ((prev >= CELL_ZOOM_THRESHOLD) !== (viewState.zoom >= CELL_ZOOM_THRESHOLD))
      setCellZoomed(viewState.zoom >= CELL_ZOOM_THRESHOLD);
    if ((prev >= DNS_ZOOM_THRESHOLD) !== (viewState.zoom >= DNS_ZOOM_THRESHOLD))
      setDnsZoomed(viewState.zoom >= DNS_ZOOM_THRESHOLD);
    if ((prev >= CDN_ZOOM_THRESHOLD) !== (viewState.zoom >= CDN_ZOOM_THRESHOLD))
      setCdnZoomed(viewState.zoom >= CDN_ZOOM_THRESHOLD);
    if ((prev >= FIBER_ZOOM_THRESHOLD) !== (viewState.zoom >= FIBER_ZOOM_THRESHOLD))
      setFiberZoomed(viewState.zoom >= FIBER_ZOOM_THRESHOLD);
  }

  const CLICK_TYPE = {
    'cables':         'cable',
    'landing-points': 'landing-point',
    'datacenters':    'datacenter',
    'ixps':           'ixp',
    'cell-towers':    'cell-tower',
    'dns-root-points':'dns-root',
    'dns-resolvers':  'dns-resolver',
    'fiber-verified': 'fiber-route',
    'fiber-estimated':'fiber-route',
  };

  const SAT_LAYERS = new Set(['iss', 'starlink-sats', 'oneweb-sats', 'kuiper-sats', 'geo-commsats']);

  // ── Connection arcs: cable landing points ↔ nearby fiber endpoints (≤20km) ──
  const connectionArcs = useMemo(() => {
    if (!layerVisibility.fiber || !layerVisibility.cables) return [];
    const allFiber = [...fiberVerifiedFeatures, ...fiberEstimatedFeatures];
    if (allFiber.length === 0 || landingPointFeatures.length === 0) return [];

    // Build grid index of landing points (0.5° cell ≈ 55 km at equator)
    const CELL = 0.5;
    const grid = new Map();
    for (const lp of landingPointFeatures) {
      const [lon, lat] = lp.geometry.coordinates;
      const key = `${Math.floor(lon / CELL)},${Math.floor(lat / CELL)}`;
      if (!grid.has(key)) grid.set(key, []);
      grid.get(key).push([lon, lat]);
    }

    const RADIUS_KM = 20;
    const arcs = [];
    const seen = new Set();

    const tryEndpoint = (epLon, epLat) => {
      const cx = Math.floor(epLon / CELL);
      const cy = Math.floor(epLat / CELL);
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          const cell = grid.get(`${cx + dx},${cy + dy}`);
          if (!cell) continue;
          for (const [lpLon, lpLat] of cell) {
            if (haversineKm(epLon, epLat, lpLon, lpLat) <= RADIUS_KM) {
              const key = `${epLon.toFixed(3)},${epLat.toFixed(3)}-${lpLon.toFixed(3)},${lpLat.toFixed(3)}`;
              if (!seen.has(key)) {
                seen.add(key);
                arcs.push({ source: [epLon, epLat], target: [lpLon, lpLat] });
                if (arcs.length >= 1500) return true;
              }
            }
          }
        }
      }
      return false;
    };

    outer: for (const f of allFiber) {
      const coords = f.geometry?.coordinates;
      if (!coords || coords.length < 2) continue;
      if (tryEndpoint(coords[0][0], coords[0][1])) break outer;
      if (tryEndpoint(coords[coords.length - 1][0], coords[coords.length - 1][1])) break outer;
    }

    return arcs;
  }, [fiberVerifiedFeatures, fiberEstimatedFeatures, landingPointFeatures, layerVisibility.fiber, layerVisibility.cables]);

  function handleMapClick({ object, layer }) {
    if (!object || !layer) {
      setDetailFeature(null);
      setOrbitFeature(null);
      setOrbitSatInfo(null);
      return;
    }

    // ── Satellite orbit on click ──────────────────────────────
    if (SAT_LAYERS.has(layer.id)) {
      const idx = object; // integer index into the group
      let group, groupRef, operator, color;
      if (layer.id === 'iss') {
        group = iss; groupRef = issGroup.current;
        operator = 'ISS'; color = 'red';
      } else if (layer.id === 'starlink-sats') {
        group = starlink; groupRef = starlinkGroup.current;
        operator = 'SpaceX Starlink'; color = 'blue';
      } else if (layer.id === 'oneweb-sats') {
        group = oneweb; groupRef = onewebGroup.current;
        operator = 'OneWeb'; color = 'green';
      } else if (layer.id === 'kuiper-sats') {
        group = kuiper; groupRef = kuiperGroup.current;
        operator = 'Amazon Kuiper'; color = 'orange';
      } else {
        group = geo; groupRef = geoGroup.current;
        operator = 'GEO Comm Sat'; color = 'amber';
      }
      if (!groupRef?.satrecs[idx]) return;

      const satrec = groupRef.satrecs[idx];
      const name   = group.names[idx];
      const alt    = Math.round(group.positions[idx * 3 + 2]);

      const pv = sat.propagate(satrec, new Date());
      const velocity = pv.velocity
        ? +Math.sqrt(pv.velocity.x ** 2 + pv.velocity.y ** 2 + pv.velocity.z ** 2).toFixed(2)
        : null;
      const inclination = +sat.radiansToDegrees(satrec.inclo).toFixed(1);

      setOrbitFeature(computeOrbitPath(satrec));
      setOrbitSatInfo({ name, altitude: alt, velocity, inclination, operator, color });
      setDetailFeature(null);
      return;
    }

    // ── CDN click — aggregate nearby PoPs within 50 km ───────
    if (layer.id === 'cdn-points') {
      const [cLon, cLat] = object.geometry.coordinates;
      const nearby = cdnFeatures.filter(f => {
        const [lon, lat] = f.geometry.coordinates;
        return haversineKm(cLon, cLat, lon, lat) <= 50;
      });
      const byProvider = {};
      for (const f of nearby) {
        const p = f.properties.provider;
        if (!byProvider[p]) byProvider[p] = [];
        byProvider[p].push(f.properties.city);
      }
      const providers = Object.entries(byProvider).map(([name, cities]) => ({
        name,
        count: cities.length,
        cities: [...new Set(cities)].sort(),
      }));
      setDetailFeature({
        type: 'cdn-edge',
        name: `${object.properties.city}, ${object.properties.country}`,
        city: object.properties.city,
        country: object.properties.country,
        providers,
      });
      setOrbitFeature(null);
      setOrbitSatInfo(null);
      return;
    }

    const type = CLICK_TYPE[layer.id];
    if (type) {
      setDetailFeature({ type, ...object.properties });
      setOrbitFeature(null);
      setOrbitSatInfo(null);
    }
  }

  const layers = [
    // ── Basemap ───────────────────────────────────────────────
    new TileLayer({
      id: 'basemap',
      data: CARTO_TILES,
      minZoom: 0,
      maxZoom: 14,
      tileSize: 256,
      refinementStrategy: 'no-overlap',
      renderSubLayers: props => {
        const { boundingBox } = props.tile;
        return new BitmapLayer(props, {
          data: null,
          image: props.data,
          bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
        });
      },
    }),

    // ── Border brightener ─────────────────────────────────────
    new GeoJsonLayer({
      id: 'borders-bright',
      data: `${import.meta.env.BASE_URL}borders.geojson`,
      stroked: true,
      filled: false,
      getLineColor: [200, 215, 230, 90],
      getLineWidth: 1,
      lineWidthMinPixels: 0.6,
      lineWidthMaxPixels: 1,
      pickable: false,
    }),

    // ── Selected satellite orbit path ─────────────────────────
    new GeoJsonLayer({
      id: 'orbit-path',
      data: orbitFeature
        ? { type: 'FeatureCollection', features: [orbitFeature] }
        : { type: 'FeatureCollection', features: [] },
      stroked: true,
      filled: false,
      getLineColor: orbitSatInfo?.color === 'red'    ? [255, 100, 100, 160]
                  : orbitSatInfo?.color === 'blue'   ? [160, 200, 255, 140]
                  : orbitSatInfo?.color === 'green'  ? [160, 255, 200, 140]
                  : orbitSatInfo?.color === 'orange' ? [255, 160,  40, 140]
                  :                                    [255, 200,  80, 140],
      getLineWidth: 1.5,
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 2,
      pickable: false,
    }),

    // ── Cell towers: heat-density (zoom 5+) ──────────────────
    // Note: deck.gl HeatmapLayer is screen-space and incompatible with
    // GlobeView's sphere projection. ScatterplotLayer with a colour ramp
    // produces the same density-map effect and renders correctly on globe.
    new ScatterplotLayer({
      id: 'cell-towers',
      data: cellFeatures,
      visible: layerVisibility.cellTowers && cellZoomed,
      getPosition: f => f.geometry.coordinates,
      getRadius: f => Math.max(6000, Math.min(22000, 6000 + Math.log2(f.properties.count + 1) * 2500)),
      getFillColor: f => cellColor(f.properties.count),
      stroked: false,
      radiusUnits: 'meters',
      radiusMinPixels: 1,
      radiusMaxPixels: 10,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'cell-tower', ...object.properties } : null),
    }),

    // ── Data centers: density blobs zoomed out ────────────────
    new ScatterplotLayer({
      id: 'dc-density',
      data: dcFeatures,
      visible: layerVisibility.datacenters && !zoomed,
      getPosition: f => f.geometry.coordinates,
      getRadius: f => dcRadius(f.properties.network_count) * 2.5,
      getFillColor: [0, 220, 100, 45],
      stroked: false,
      radiusUnits: 'meters',
      pickable: false,
    }),

    // ── Data centers: scaled squares zoomed in ────────────────
    new IconLayer({
      id: 'datacenters',
      data: dcFeatures,
      visible: layerVisibility.datacenters && zoomed,
      iconAtlas: ATLAS_SQUARE,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: f => f.geometry.coordinates,
      getSize: f => Math.max(8, Math.min(22, 5 + Math.log2((f.properties.network_count || 1) + 1) * 2.2)),
      getColor: [0, 230, 118, 210],
      sizeUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'datacenter', ...object.properties } : null),
    }),

    // ── IXPs — lime-yellow hexagons ───────────────────────────
    new IconLayer({
      id: 'ixps',
      data: ixpFeatures,
      visible: layerVisibility.ixps,
      iconAtlas: ATLAS_HEX,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: f => f.geometry.coordinates,
      getSize: 13,
      getColor: [200, 230, 0, 220],
      sizeUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'ixp', ...object.properties } : null),
    }),

    // ── CDN PoPs — density blobs (zoom < 3) ──────────────────
    // Note: HeatmapLayer is screen-space and incompatible with GlobeView.
    // ScatterplotLayer with large soft radii produces an equivalent density
    // effect and renders correctly on the globe projection.
    new ScatterplotLayer({
      id: 'cdn-density',
      data: cdnFeatures,
      visible: layerVisibility.cdn && !cdnZoomed,
      getPosition: f => f.geometry.coordinates,
      getRadius: 400000,
      getFillColor: f => [...(CDN_PROVIDER_COLORS[f.properties.provider] || [200, 200, 200]), 40],
      stroked: false,
      radiusUnits: 'meters',
      radiusMinPixels: 6,
      radiusMaxPixels: 60,
      pickable: false,
    }),

    // ── CDN PoPs — per-provider triangles (zoom 3+) ──────────
    new IconLayer({
      id: 'cdn-points',
      data: cdnFeatures,
      visible: layerVisibility.cdn && cdnZoomed,
      iconAtlas: ATLAS_TRIANGLE,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: f => f.geometry.coordinates,
      getSize: 11,
      getColor: f => [...(CDN_PROVIDER_COLORS[f.properties.provider] || [200, 200, 200]), 220],
      sizeUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'cdn', ...object.properties } : null),
    }),

    // ── Fiber routes: verified (solid cyan/teal, zoom 3+) ────
    new GeoJsonLayer({
      id: 'fiber-verified',
      data: fiberVerifiedFeatures,
      visible: layerVisibility.fiber && fiberZoomed && fiberVerifiedFeatures.length > 0,
      stroked: false,
      filled: false,
      getLineColor: [0, 210, 200, 220],
      getLineWidth: 2,
      lineWidthMinPixels: 1.5,
      lineWidthMaxPixels: 3,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'fiber-route', source: 'verified', ...object.properties } : null),
    }),

    // ── Fiber routes: estimated (dashed grey-blue, zoom 3+) ──
    new GeoJsonLayer({
      id: 'fiber-estimated',
      data: fiberEstimatedFeatures,
      visible: layerVisibility.fiber && fiberZoomed,
      stroked: false,
      filled: false,
      getLineColor: [100, 150, 170, 100],
      getLineWidth: 1,
      lineWidthMinPixels: 0.8,
      lineWidthMaxPixels: 2,
      getDashArray: [4, 3],
      dashJustified: true,
      extensions: [new PathStyleExtension({ dash: true })],
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'fiber-route', ...object.properties } : null),
    }),

    // ── Connection arcs: landing points ↔ fiber endpoints ────
    new ArcLayer({
      id: 'fiber-connections',
      data: connectionArcs,
      visible: layerVisibility.fiber && layerVisibility.cables && fiberZoomed,
      getSourcePosition: d => d.source,
      getTargetPosition: d => d.target,
      getSourceColor: [0, 180, 240, 50],
      getTargetColor: [0, 180, 240, 50],
      getWidth: 1,
      widthMinPixels: 0.5,
      widthMaxPixels: 1.5,
      getHeight: 0.25,
      pickable: false,
    }),

    // ── Terrestrial backbone (estimated) ─────────────────────
    new GeoJsonLayer({
      id: 'backbone',
      data: layerVisibility.backbone ? `${import.meta.env.BASE_URL}backbone.geojson` : [],
      visible: layerVisibility.backbone,
      onDataLoad: data => {
        setBackboneCount(data.features?.length ?? 0);
        const totalKm = (data.features || []).reduce(
          (sum, f) => sum + lineKm(f.geometry?.coordinates || []), 0
        );
        setBackboneMiles(Math.round(totalKm * 0.621371));
      },
      stroked: false,
      filled: false,
      getLineColor: f =>
        f.properties.route_type === 'international'
          ? [255, 160, 60, 110]
          : [255, 200, 80, 75],
      getLineWidth: f => f.properties.route_type === 'international' ? 3 : 2,
      lineWidthMinPixels: 1.5,
      lineWidthMaxPixels: 4,
      getDashArray: [4, 4],
      dashJustified: true,
      extensions: [new PathStyleExtension({ dash: true })],
      pickable: false,
    }),

    // ── Submarine cables ──────────────────────────────────────
    new GeoJsonLayer({
      id: 'cables',
      data: `${import.meta.env.BASE_URL}cables.geojson`,
      visible: layerVisibility.cables,
      onDataLoad: data => {
        setCableCount(data.features?.length ?? 0);
        const totalKm = (data.features || []).reduce((sum, f) => {
          const lines = f.geometry?.coordinates || [];
          // MultiLineString: coordinates is an array of line arrays
          return sum + lines.reduce((s, line) => s + lineKm(line), 0);
        }, 0);
        setCableMiles(Math.round(totalKm * 0.621371));
      },
      stroked: false,
      filled: false,
      getLineColor: f => [...hexToRgb(f.properties.color || '#4fc3f7'), 180],
      getLineWidth: 2,
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 3,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'cable', ...object.properties } : null),
    }),

    // ── ISS (~420 km) — glow halo + SVG silhouette icon ──────
    new ScatterplotLayer({
      id: 'iss-glow',
      data: iss && iss.count > 0 ? [0] : [],
      visible: layerVisibility.iss && !!iss,
      getPosition: () => [iss.positions[0], iss.positions[1], 0],
      getRadius: 22,
      getFillColor: [255, 32, 32, 55],
      radiusUnits: 'pixels',
      stroked: false,
      pickable: false,
      parameters: { depthTest: false },
    }),
    new IconLayer({
      id: 'iss',
      data: iss && iss.count > 0 ? [0] : [],
      visible: layerVisibility.iss && !!iss,
      iconAtlas: ATLAS_ISS,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: () => [iss.positions[0], iss.positions[1], 0],
      getSize: 26,
      getColor: [255, 32, 32, 255],
      sizeUnits: 'pixels',
      billboard: true,
      parameters: { depthTest: false },
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object != null
          ? { x, y, type: 'satellite', name: iss?.names[0] ?? 'ISS', operator: 'ISS' }
          : null),
    }),

    // ── Starlink satellites (LEO ~550 km) ─────────────────────
    new ScatterplotLayer({
      id: 'starlink-sats',
      data: starlinkData,
      visible: layerVisibility.starlink && !!starlink,
      getPosition: i => [
        starlink.positions[i * 3],
        starlink.positions[i * 3 + 1],
        starlink.positions[i * 3 + 2] * 1000,
      ],
      getRadius: 2,
      getFillColor: [180, 210, 255, 210],
      radiusUnits: 'pixels',
      stroked: false,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object != null
          ? { x, y, type: 'satellite', name: starlink.names[object], operator: 'SpaceX Starlink' }
          : null),
    }),

    // ── OneWeb satellites (LEO ~1200 km) ──────────────────────
    new ScatterplotLayer({
      id: 'oneweb-sats',
      data: onewebData,
      visible: layerVisibility.oneweb && !!oneweb,
      getPosition: i => [
        oneweb.positions[i * 3],
        oneweb.positions[i * 3 + 1],
        oneweb.positions[i * 3 + 2] * 1000,
      ],
      getRadius: 2,
      getFillColor: [180, 255, 200, 210],
      radiusUnits: 'pixels',
      stroked: false,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object != null
          ? { x, y, type: 'satellite', name: oneweb.names[object], operator: 'OneWeb' }
          : null),
    }),

    // ── Kuiper satellites (LEO ~590-630 km) ───────────────────
    // Project Kuiper — Amazon's LEO broadband constellation
    // Planned shells: 590 km (784 sats), 610 km (1,296 sats), 630 km (1,156 sats)
    // Color: Amazon brand orange #FF9900 = [255, 153, 0]
    // TODO: add Web Worker optimisation when constellation exceeds ~100 satellites
    new ScatterplotLayer({
      id: 'kuiper-sats',
      data: kuiperData,
      visible: layerVisibility.kuiper && !!kuiper,
      getPosition: i => [
        kuiper.positions[i * 3],
        kuiper.positions[i * 3 + 1],
        kuiper.positions[i * 3 + 2] * 1000,
      ],
      getRadius: 2,
      getFillColor: [255, 190, 80, 210],
      radiusUnits: 'pixels',
      stroked: false,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object != null
          ? { x, y, type: 'satellite', name: kuiper.names[object], operator: 'Amazon Kuiper' }
          : null),
    }),

    // ── GEO comm satellites (~35,786 km) ──────────────────────
    new ScatterplotLayer({
      id: 'geo-commsats',
      data: geoData,
      visible: layerVisibility.geoSats && !!geo,
      getPosition: i => [
        geo.positions[i * 3],
        geo.positions[i * 3 + 1],
        geo.positions[i * 3 + 2] * 1000,
      ],
      getRadius: 3,
      getFillColor: [255, 240, 120, 230],
      getLineColor: [255, 250, 180, 200],
      stroked: true,
      lineWidthMinPixels: 0.5,
      radiusUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object != null
          ? { x, y, type: 'satellite', name: geo.names[object], operator: 'GEO Comm Sat' }
          : null),
    }),

    // ── Ground stations — uplink chevron ∧ ───────────────────
    new IconLayer({
      id: 'ground-stations',
      data: groundStationFeatures,
      visible: layerVisibility.groundStations,
      iconAtlas: ATLAS_CHEVRON,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: f => f.geometry.coordinates,
      getSize: 14,
      getColor: f => f.properties.operator === 'SpaceX'
        ? [80, 160, 255, 230]
        : [80, 255, 160, 230],
      sizeUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object
          ? { x, y, type: 'ground-station', name: object.properties.name,
              operator: object.properties.operator, station_type: object.properties.type }
          : null),
    }),

    // ── DNS root server instances — density blobs (zoom < 4) ─
    // Note: HeatmapLayer is screen-space and incompatible with GlobeView.
    // ScatterplotLayer with large soft radii produces an equivalent density
    // effect and renders correctly on the globe projection.
    new ScatterplotLayer({
      id: 'dns-root-density',
      data: dnsRootFeatures,
      visible: layerVisibility.dns && !dnsZoomed,
      getPosition: f => f.geometry.coordinates,
      getRadius: 200000,
      getFillColor: f => [...(DNS_ROOT_COLORS[f.properties.letter] || [160, 224, 255]), 55],
      stroked: false,
      radiusUnits: 'meters',
      radiusMinPixels: 4,
      radiusMaxPixels: 40,
      pickable: false,
    }),

    // ── DNS root server instances — per-letter crosses (zoom 4+) ──
    new IconLayer({
      id: 'dns-root-points',
      data: dnsRootFeatures,
      visible: layerVisibility.dns && dnsZoomed,
      iconAtlas: ATLAS_CROSS,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: f => f.geometry.coordinates,
      getSize: 13,
      getColor: f => [...(DNS_ROOT_COLORS[f.properties.letter] || [160, 224, 255]), 220],
      sizeUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'dns-root', ...object.properties } : null),
    }),

    // ── Public DNS resolvers — hollow rings ───────────────────
    new ScatterplotLayer({
      id: 'dns-resolvers',
      data: dnsResolverFeatures,
      visible: layerVisibility.dns,
      getPosition: f => f.geometry.coordinates,
      getRadius: 18000,
      getFillColor: [0, 0, 0, 0],
      getLineColor: f => [...(DNS_RESOLVER_COLORS[f.properties.provider] || [160, 224, 255]), 200],
      stroked: true,
      filled: false,
      lineWidthMinPixels: 1.5,
      radiusUnits: 'meters',
      radiusMinPixels: 2,
      radiusMaxPixels: 10,
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'dns-resolver', ...object.properties } : null),
    }),

    // ── Landing points — cyan diamonds ───────────────────────
    new IconLayer({
      id: 'landing-points',
      data: landingPointFeatures,
      visible: layerVisibility.cables,
      iconAtlas: ATLAS_DIAMOND,
      iconMapping: ICON_MAPPING,
      getIcon: () => 'icon',
      getPosition: f => f.geometry.coordinates,
      getSize: 12,
      getColor: [100, 220, 255, 220],
      sizeUnits: 'pixels',
      pickable: true,
      onHover: ({ object, x, y }) =>
        setTooltip(object ? { x, y, type: 'landing-point', ...object.properties } : null),
    }),
  ];

  return (
    <>
      <InfoPanel
        cableCount={cableCount}
        cableMiles={cableMiles}
        landingPointCount={landingPointCount}
        dcCount={dcFeatures.length || null}
        dcNetworkTotal={dcNetworkTotal}
        dcCountryCount={dcCountryCount}
        ixpCount={ixpFeatures.length || null}
        dnsRootCount={dnsRootFeatures.length || null}
        dnsResolverCount={dnsResolverFeatures.length || null}
        cdnPopCount={cdnFeatures.length || null}
        cdnCountryCount={cdnFeatures.length ? new Set(cdnFeatures.map(f => f.properties.country)).size : null}
        backboneCount={backboneCount}
        backboneMiles={backboneMiles}
        cellTowerCount={cellTowerCount}
        cellSiteCount={cellSiteCount}
        starlinkCount={starlink?.count ?? null}
        onewebCount={oneweb?.count ?? null}
        kuiperCount={kuiper?.count ?? null}
        geoSatCount={geoData.length || null}
      />
      <div style={{
        position: 'absolute',
        top: 20,
        right: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        zIndex: 10,
      }}>
        <LayerToggle visible={layerVisibility} onToggle={toggleLayer} />
        <SpaceLayerToggle visible={layerVisibility} onToggle={toggleLayer} />
      </div>

      <DeckGL
        views={GLOBE_VIEW}
        viewState={viewState}
        controller={true}
        layers={layers}
        onViewStateChange={handleViewStateChange}
        onClick={handleMapClick}
        getCursor={({ isDragging, isHovering }) =>
          isDragging ? 'grabbing' : isHovering ? 'pointer' : 'grab'
        }
        style={{ width: '100%', height: '100%' }}
      />

      <div style={{
        position: 'absolute',
        top: 20,
        left: 20,
        fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
        fontSize: 18,
        fontWeight: 800,
        letterSpacing: '0.26em',
        color: '#e8f6ff',
        textShadow: '0 0 20px rgba(0,180,255,0.6), 0 0 6px rgba(0,180,255,0.3)',
        pointerEvents: 'none',
        userSelect: 'none',
        whiteSpace: 'nowrap',
        zIndex: 10,
      }}>
        PROJECT BACKBONE
      </div>

      {orbitSatInfo && (
        <div style={{
          position: 'absolute',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(4, 10, 20, 0.92)',
          border: '1px solid rgba(0, 180, 255, 0.22)',
          borderRadius: 6,
          padding: '12px 20px',
          fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
          fontSize: 12,
          color: '#8ab8cc',
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          gap: 28,
          boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
          backdropFilter: 'blur(6px)',
          userSelect: 'none',
          whiteSpace: 'nowrap',
        }}>
          <div>
            <div style={{ fontWeight: 700, color: '#d0eeff', fontSize: 13, letterSpacing: '0.08em', marginBottom: 3 }}>
              {orbitSatInfo.name}
            </div>
            <div style={{ color: '#5a8a9a', fontSize: 10, letterSpacing: '0.12em' }}>
              {orbitSatInfo.operator.toUpperCase()}
            </div>
          </div>
          <div style={{ borderLeft: '1px solid rgba(0,180,255,0.18)', height: 36 }} />
          {[
            ['ALT',   orbitSatInfo.altitude != null ? `${orbitSatInfo.altitude.toLocaleString()} km` : '—'],
            ['VEL',   orbitSatInfo.velocity  != null ? `${orbitSatInfo.velocity} km/s`                : '—'],
            ['INCL',  `${orbitSatInfo.inclination}°`],
          ].map(([label, value]) => (
            <div key={label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: '#4a7a8a', letterSpacing: '0.16em', marginBottom: 3 }}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#a8dff0' }}>{value}</div>
            </div>
          ))}
          <div style={{ borderLeft: '1px solid rgba(0,180,255,0.18)', height: 36 }} />
          <div
            onClick={() => { setOrbitFeature(null); setOrbitSatInfo(null); }}
            style={{ color: '#4a7a8a', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: '0 4px' }}
            title="Close"
          >✕</div>
        </div>
      )}

      <DetailPanel
        feature={detailFeature}
        onClose={() => setDetailFeature(null)}
        landingPointFeatures={landingPointFeatures}
        onLandingPointClick={lp => setDetailFeature({ type: 'landing-point', ...lp.properties })}
      />

      {tooltip && !detailFeature && (
        <div style={{ ...tooltipStyle, left: tooltip.x + 14, top: tooltip.y - 10 }}>
          <div style={{ fontWeight: 600, marginBottom: 2, color: '#fff' }}>
            {tooltip.type === 'cell-tower'    ? 'Cell Tower Density'
           : tooltip.type === 'dns-root'      ? `${tooltip.letter}-Root · ${tooltip.name}`
           : tooltip.type === 'dns-resolver'  ? (tooltip.name || tooltip.provider)
           : tooltip.type === 'cdn'           ? 'CDN Edge PoP'
           : tooltip.type === 'fiber-route'   ? 'Fiber Route'
           : tooltip.name}
          </div>

          {tooltip.type === 'cable' && (
            <>
              {tooltip.rfs_year && <div style={{ color: '#7ecfea' }}>RFS: {tooltip.rfs_year}</div>}
              {tooltip.length_km && (
                <div style={{ color: '#7ecfea' }}>
                  Length: {tooltip.length_km.toLocaleString()} km
                </div>
              )}
              {tooltip.owners?.length > 0 && (
                <div style={{ color: '#6ab8d0', fontSize: 11, marginTop: 2 }}>
                  {tooltip.owners.slice(0, 2).join(', ')}
                  {tooltip.owners.length > 2 && ` +${tooltip.owners.length - 2} more`}
                </div>
              )}
            </>
          )}

          {tooltip.type === 'landing-point' && tooltip.cables?.length > 0 && (
            <div style={{ color: '#7ecfea', fontSize: 11, marginTop: 2 }}>
              {tooltip.cables.slice(0, 3).join(', ')}
              {tooltip.cables.length > 3 && ` +${tooltip.cables.length - 3} more`}
            </div>
          )}

          {tooltip.type === 'datacenter' && (
            <>
              <div style={{ color: '#7ecfea' }}>
                {[tooltip.city, tooltip.state, tooltip.country].filter(Boolean).join(', ')}
              </div>
              {tooltip.network_count > 0 && (
                <div style={{ color: '#6ab8d0', fontSize: 11, marginTop: 2 }}>
                  {tooltip.network_count} colocated networks
                </div>
              )}
            </>
          )}

          {tooltip.type === 'ixp' && (
            <>
              <div style={{ color: '#7ecfea' }}>
                {[tooltip.city, tooltip.country].filter(Boolean).join(', ')}
              </div>
              {tooltip.participants > 0 && (
                <div style={{ color: '#6ab8d0', fontSize: 11, marginTop: 2 }}>
                  {tooltip.participants.toLocaleString()} participants
                </div>
              )}
            </>
          )}

          {tooltip.type === 'satellite' && (
            <div style={{ color: '#7ecfea', fontSize: 11, marginTop: 2 }}>{tooltip.operator}</div>
          )}

          {tooltip.type === 'ground-station' && (
            <>
              <div style={{ color: '#7ecfea' }}>{tooltip.operator}</div>
              {tooltip.station_type && (
                <div style={{ color: '#6ab8d0', fontSize: 11, marginTop: 2, textTransform: 'capitalize' }}>
                  {tooltip.station_type}
                </div>
              )}
            </>
          )}

          {tooltip.type === 'cdn' && (
            <>
              <div style={{ color: '#7ecfea' }}>
                {[tooltip.city, tooltip.country].filter(Boolean).join(', ')}
              </div>
              <div style={{
                display: 'inline-block',
                marginTop: 4,
                padding: '1px 7px',
                borderRadius: 3,
                fontSize: 10,
                fontWeight: 600,
                background: `rgba(${(CDN_PROVIDER_COLORS[tooltip.provider] || [200,200,200]).join(',')},0.18)`,
                color: `rgb(${(CDN_PROVIDER_COLORS[tooltip.provider] || [200,200,200]).join(',')})`,
                border: `1px solid rgba(${(CDN_PROVIDER_COLORS[tooltip.provider] || [200,200,200]).join(',')},0.4)`,
              }}>
                {tooltip.provider}
              </div>
            </>
          )}

          {tooltip.type === 'dns-root' && (
            <>
              <div style={{ color: '#7ecfea' }}>
                {[tooltip.city, tooltip.country].filter(Boolean).join(', ')}
              </div>
              <div style={{ color: '#6ab8d0', fontSize: 11, marginTop: 2 }}>
                {tooltip.operator}
              </div>
              {tooltip.isGlobal && (
                <div style={{ color: '#4a9a7a', fontSize: 10, marginTop: 2 }}>anycast instance</div>
              )}
            </>
          )}

          {tooltip.type === 'dns-resolver' && (
            <>
              <div style={{ color: '#7ecfea' }}>
                {[tooltip.city, tooltip.country].filter(Boolean).join(', ')}
              </div>
              <div style={{ color: '#6ab8d0', fontSize: 11, marginTop: 2 }}>{tooltip.provider}</div>
              {tooltip.ip && (
                <div style={{ color: '#5a7a8a', fontSize: 10, marginTop: 2 }}>{tooltip.ip}</div>
              )}
            </>
          )}

          {tooltip.type === 'fiber-route' && (
            <>
              {tooltip.from && tooltip.to && (
                <div style={{ color: '#7ecfea', fontSize: 11, marginTop: 2 }}>
                  {tooltip.from} → {tooltip.to}
                </div>
              )}
              <div style={{ display: 'flex', gap: 12, marginTop: 3 }}>
                {tooltip.route_type && (
                  <span style={{ color: '#6ab8d0', fontSize: 10, textTransform: 'capitalize' }}>
                    {tooltip.route_type}
                  </span>
                )}
                {tooltip.source === 'verified'
                  ? <span style={{ color: '#00d2c8', fontSize: 10 }}>verified</span>
                  : <span style={{ color: '#6496aa', fontSize: 10 }}>estimated</span>
                }
              </div>
            </>
          )}

          {tooltip.type === 'cell-tower' && (
            <>
              {[
                ['Towers',    tooltip.count?.toLocaleString()],
                ['Coverage',  tooltip.coverage],
                ['Avg range', tooltip.avg_range != null ? `${tooltip.avg_range.toLocaleString()} m` : null],
                ['Samples',   tooltip.samples?.toLocaleString()],
                ['Country',   tooltip.country],
                ['Updated',   tooltip.updated],
              ].filter(([, v]) => v).map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span style={{ color: '#9060b0', fontSize: 11 }}>{label}</span>
                  <span style={{ color: '#e080d8', fontSize: 11 }}>{value}</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {!issConsentAsked && iss?.count > 0 && (
        <div style={{
          position: 'absolute',
          bottom: 24,
          right: 24,
          background: 'rgba(4, 10, 20, 0.92)',
          border: '1px solid rgba(0, 180, 255, 0.25)',
          borderRadius: 4,
          padding: '12px 16px',
          fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
          fontSize: 12,
          color: '#d0eeff',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          zIndex: 20,
          backdropFilter: 'blur(6px)',
        }}>
          <span>Fly to the ISS?</span>
          <button onClick={() => confirmIssAutoFly(true)} style={{
            background: 'rgba(0,180,255,0.15)', border: '1px solid rgba(0,180,255,0.4)',
            borderRadius: 3, color: '#00c8ff', cursor: 'pointer', fontSize: 12, padding: '3px 10px',
          }}>Yes</button>
          <button onClick={() => confirmIssAutoFly(false)} style={{
            background: 'transparent', border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 3, color: '#8ab', cursor: 'pointer', fontSize: 12, padding: '3px 10px',
          }}>No thanks</button>
        </div>
      )}

      {taglineMounted && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 'clamp(360px, 42vw, 660px)',
          aspectRatio: '1 / 1',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(4, 10, 20, 0.88)',
          border: '1px solid rgba(0, 180, 255, 0.2)',
          borderRadius: 4,
          padding: '48px',
          boxSizing: 'border-box',
          fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
          fontSize: 'clamp(20px, 2.2vw, 34px)',
          fontWeight: 800,
          letterSpacing: '0.1em',
          lineHeight: 1.6,
          color: '#d0eeff',
          textAlign: 'center',
          textShadow: '0 0 20px rgba(0,180,255,0.5), 0 0 6px rgba(0,180,255,0.25)',
          backdropFilter: 'blur(6px)',
          boxShadow: '0 0 24px rgba(0,140,220,0.08), inset 0 0 0 1px rgba(0,180,255,0.05)',
          userSelect: 'none',
          pointerEvents: 'none',
          opacity: taglineVisible ? 1 : 0,
          transition: 'opacity 5s ease',
          zIndex: 10,
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2em' }}>
            <div>
              The internet isn't wireless<br />and it isn't weightless.<br />
              <span style={{ color: '#00c8ff' }}>Project Backbone</span> makes it visible.
            </div>
            <img
              src={`${import.meta.env.BASE_URL}logomark-white.png`}
              alt="Project Backbone"
              style={{
                height: 'clamp(32px, 3.5vw, 54px)',
                opacity: 0.85,
                filter: 'drop-shadow(0 0 12px rgba(0,180,255,0.5)) drop-shadow(0 0 4px rgba(0,180,255,0.25))',
                userSelect: 'none',
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}
