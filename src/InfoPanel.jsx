import { useState } from 'react';
import { MONO_FONT, C } from './ui-shared';

// ── Mass estimates (kg per unit) ──────────────────────────────────────────────
// Sources: TeleGeography, ITU, GSMA, IEA, SpaceX/OneWeb/Amazon filings
const MI_TO_KM           = 1.60934;
const KG_PER_CABLE_KM    = 1_500;      // avg submarine cable (deep + armoured coastal)
const KG_PER_BACKBONE_KM = 800;        // fiber + conduit per km
const KG_PER_IXP         = 80_000;     // switching/routing gear per IXP
const KG_PER_DC          = 2_300_000;  // building + equipment + cooling per facility
const KG_PER_CDN_POP     = 15_000;     // edge servers + gear per PoP
const KG_PER_DNS_NODE    = 300;        // server hardware per instance/resolver
const KG_PER_CELL_SITE   = 7_000;      // tower + base station + antennas
const KG_STARLINK        = 260;        // v1.5 satellite bus
const KG_ONEWEB          = 150;
const KG_KUIPER          = 450;        // estimated bus mass
const KG_GEO             = 4_000;      // average GEO comsat

function formatMass(kg) {
  if (kg == null) return null;
  const t = kg / 1000;
  if (t >= 1e6) return '~' + (t / 1e6).toFixed(1) + ' M t';
  if (t >= 1e3) return '~' + Math.round(t / 1e3).toLocaleString() + ' K t';
  return '~' + Math.round(t).toLocaleString() + ' t';
}

const SECTION_COLORS = {
  cables:   C.celestialBlue,   // sky/ocean — Celestial Blue
  ixp:      C.signalOrange,    // exchange hubs — Signal Orange
  dc:       C.vacuumAmber,     // machine warmth — Vacuum Tube Amber
  cdn:      C.chromeYellow,    // delivery network — Chrome Yellow
  dns:      C.oxidizedCopper,  // aged infrastructure — Oxidized Copper
  cell:     C.photogray,       // ground-level grid — Photographic Gray
};

const SAT_COLORS = {
  starlink: C.celestialBlue,  // SpaceX — sky blue
  oneweb:   C.oxidizedCopper, // OneWeb — copper green
  kuiper:   C.chromeYellow,   // Amazon — chrome yellow
  geo:      C.vacuumAmber,    // GEO — amber warmth
};

const styles = {
  panel: {
    position: 'absolute',
    top: 62,
    left: 20,
    background: 'rgba(13, 13, 20, 0.92)',
    border: '1px solid rgba(255, 79, 0, 0.28)',
    borderRadius: 4,
    padding: '12px 16px',
    fontFamily: MONO_FONT,
    fontSize: 12,
    color: C.newsprint,
    minWidth: 220,
    maxHeight: 'calc(100vh - 82px)',
    overflowY: 'auto',
    backdropFilter: 'blur(8px)',
    boxShadow: '0 0 28px rgba(255, 79, 0, 0.07), inset 0 0 0 1px rgba(255, 79, 0, 0.05)',
    userSelect: 'none',
    pointerEvents: 'auto',
    zIndex: 10,
  },
  title: {
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: '0.18em',
    color: C.lunarWhite,
    marginBottom: 10,
  },
  accent: { color: C.signalOrange },
  divider: {
    borderTop: '1px solid rgba(255, 79, 0, 0.18)',
    margin: '6px 0',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 10,
    letterSpacing: '0.2em',
    marginBottom: 4,
    marginTop: 2,
  },
  sectionIcon: {
    display: 'flex',
    alignItems: 'center',
    flexShrink: 0,
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: 16,
    marginBottom: 3,
  },
  label: {
    letterSpacing: '0.1em',
    color: C.photogray,
    fontSize: 11,
  },
  note: {
    fontSize: 10,
    color: '#556070',
    marginTop: 8,
    letterSpacing: '0.06em',
  },
};

// ── Blip legend icons ─────────────────────────────────────────────────────────

function IconCables({ color }) {
  return (
    <svg width="22" height="10" viewBox="0 0 22 10">
      <line x1="0" y1="5" x2="14" y2="5" stroke={color} strokeWidth="2"/>
      <polygon points="14,2 20,5 14,8" fill={color}/>
    </svg>
  );
}


function IconIXP({ color }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12">
      <polygon points="6,1 11,3.5 11,8.5 6,11 1,8.5 1,3.5" fill="none"
               stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

function IconDC({ color }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10">
      <rect x="1" y="1" width="8" height="8" fill={color}/>
    </svg>
  );
}

function IconCDN({ color }) {
  return (
    <svg width="12" height="11" viewBox="0 0 12 11">
      <polygon points="6,1 11,10 1,10" fill={color}/>
    </svg>
  );
}

function IconDNS({ color }) {
  return (
    <svg width="20" height="12" viewBox="0 0 20 12">
      {/* cross for root servers */}
      <rect x="4" y="2" width="2" height="8" fill={color}/>
      <rect x="1" y="5" width="8" height="2" fill={color}/>
      {/* circle for resolver POPs */}
      <circle cx="16" cy="6" r="4" fill="none" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

function IconCell({ color }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12">
      <circle cx="6" cy="6" r="5" fill="none" stroke={color} strokeWidth="1.5"/>
      <circle cx="6" cy="6" r="2" fill={color}/>
    </svg>
  );
}

function IconSat({ colors }) {
  // four dots, one per constellation
  const cx = [3, 9, 3, 9];
  const cy = [3, 3, 9, 9];
  return (
    <svg width="14" height="14" viewBox="0 0 14 14">
      {colors.map((c, i) => (
        <circle key={i} cx={cx[i]} cy={cy[i]} r="2.2" fill={c}/>
      ))}
    </svg>
  );
}

// ── SectionHeader ─────────────────────────────────────────────────────────────

function SectionHeader({ label, color, icon }) {
  return (
    <div style={{ ...styles.sectionHeader, color }}>
      <span style={styles.sectionIcon}>{icon}</span>
      {label}
    </div>
  );
}

// ── Counter ───────────────────────────────────────────────────────────────────

function Counter({ value, hex, suffix = '' }) {
  const s = {
    fontSize: 13,
    fontWeight: 600,
    color: hex || C.chromeYellow,
  };
  if (value == null) return <span style={{ ...s, color: C.blueprintIndigo }}>LOADING…</span>;
  return <span style={s}>{value.toLocaleString()}{suffix}</span>;
}

// ── InfoPanel ─────────────────────────────────────────────────────────────────

export default function InfoPanel({
  mobileSheet = false,
  cableCount,
  cableMiles,
  landingPointCount,
  dcCount,
  dcNetworkTotal,
  dcCountryCount,
  ixpCount,
  dnsRootCount,
  dnsResolverCount,
  cdnPopCount,
  cdnCountryCount,
  backboneCount,
  backboneMiles,
  cellTowerCount,
  cellSiteCount,
  starlinkCount,
  onewebCount,
  kuiperCount,
  geoSatCount,
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [massOpen, setMassOpen] = useState(false);

  // ── per-section mass (kg), null while props still loading ─────────────────
  const mCables   = cableMiles    != null ? cableMiles    * MI_TO_KM * KG_PER_CABLE_KM    : null;
  const mBackbone = backboneMiles != null ? backboneMiles * MI_TO_KM * KG_PER_BACKBONE_KM : null;
  const mIXP      = ixpCount      != null ? ixpCount      * KG_PER_IXP                    : null;
  const mDC       = dcCount       != null ? dcCount       * KG_PER_DC                     : null;
  const mCDN      = cdnPopCount   != null ? cdnPopCount   * KG_PER_CDN_POP                : null;
  const mDNS      = (dnsRootCount != null && dnsResolverCount != null)
                    ? (dnsRootCount + dnsResolverCount) * KG_PER_DNS_NODE : null;
  const mCell     = cellSiteCount != null ? cellSiteCount * KG_PER_CELL_SITE               : null;
  const mSats     = (starlinkCount != null && onewebCount != null && kuiperCount != null && geoSatCount != null)
                    ? starlinkCount * KG_STARLINK + onewebCount * KG_ONEWEB
                      + kuiperCount * KG_KUIPER   + geoSatCount * KG_GEO : null;

  const allLoaded = [mCables, mBackbone, mIXP, mDC, mCDN, mDNS, mCell, mSats].every(v => v != null);
  const mTotal    = allLoaded
                    ? mCables + mBackbone + mIXP + mDC + mCDN + mDNS + mCell + mSats : null;

  const mobileSheetOverride = mobileSheet ? {
    position: 'relative', top: 'auto', left: 'auto',
    width: '100%', minWidth: 0, borderRadius: 0,
    border: 'none', boxShadow: 'none', maxHeight: 'none',
  } : { maxHeight: collapsed ? 'none' : 'calc(100vh - 82px)' };

  return (
    <div style={{ ...styles.panel, ...mobileSheetOverride }}
         onWheel={e => e.stopPropagation()}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{ ...styles.title, cursor: 'pointer', marginBottom: collapsed ? 0 : 10 }}
      >
        <span style={styles.accent}>◈ </span>THE WEIGHT OF THE CLOUD
      </div>

      {!collapsed && (<>

      {/* ── 0. Estimated mass summary ─────────────────────────────────────── */}
      <div style={styles.divider} />
      <div
        onClick={() => setMassOpen(o => !o)}
        style={{ ...styles.sectionHeader, color: C.lunarWhite, cursor: 'pointer', userSelect: 'none' }}
      >
        ESTIMATED MASS
        <span style={{ marginLeft: 'auto', fontSize: 9, color: C.photogray }}>{massOpen ? '▲' : '▼'}</span>
      </div>
      <div style={{ ...styles.row, marginBottom: massOpen ? 4 : 0 }}>
        <span style={{ ...styles.label, color: C.lunarWhite, fontWeight: 700 }}>TOTAL</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: C.lunarWhite, letterSpacing: '0.04em' }}>
          {mTotal == null ? <span style={{ color: C.blueprintIndigo }}>LOADING…</span> : formatMass(mTotal)}
        </span>
      </div>
      {massOpen && (<>
        <div style={{ borderTop: '1px solid rgba(255, 79, 0, 0.1)', margin: '2px 0 4px' }} />
        {[
          ['CABLES',     mCables,   SECTION_COLORS.cables],
          ['BACKBONE',   mBackbone, SECTION_COLORS.backbone],
          ['IXPs',       mIXP,      SECTION_COLORS.ixp],
          ['DATA CTRS',  mDC,       SECTION_COLORS.dc],
          ['CDN EDGE',   mCDN,      SECTION_COLORS.cdn],
          ['DNS',        mDNS,      SECTION_COLORS.dns],
          ['CELL TOWERS',mCell,     SECTION_COLORS.cell],
          ['SATELLITES', mSats,     '#a0c8e0'],
        ].map(([label, mass, color]) => (
          <div key={label} style={{ ...styles.row, marginBottom: 2 }}>
            <span style={{ ...styles.label, fontSize: 10 }}>{label}</span>
            <span style={{ fontSize: 11, fontWeight: 600, color }}>
              {mass == null ? <span style={{ color: C.blueprintIndigo }}>…</span> : formatMass(mass)}
            </span>
          </div>
        ))}
      </>)}

      {/* ── 1. Submarine cables ───────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="SUBMARINE CABLES"
        color={SECTION_COLORS.cables}
        icon={<IconCables color={SECTION_COLORS.cables} />}
      />
      <div style={styles.row}>
        <span style={styles.label}>CABLES</span>
        <Counter value={cableCount} hex={SECTION_COLORS.cables} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>LANDING PTS</span>
        <Counter value={landingPointCount} hex={SECTION_COLORS.cables} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>TOTAL LENGTH</span>
        <Counter value={cableMiles} hex={SECTION_COLORS.cables} suffix=" mi" />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>EST. CAPACITY</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: SECTION_COLORS.cables }}>~1.3 Pbps</span>
      </div>

      {/* ── 2. Internet exchanges ─────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="INTERNET EXCHANGES"
        color={SECTION_COLORS.ixp}
        icon={<IconIXP color={SECTION_COLORS.ixp} />}
      />
      <div style={styles.row}>
        <span style={styles.label}>IXPs</span>
        <Counter value={ixpCount} hex={SECTION_COLORS.ixp} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>PEAK TRAFFIC</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: SECTION_COLORS.ixp }}>~150 Tbps</span>
      </div>

      {/* ── 3. Data centers ───────────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="DATA CENTERS"
        color={SECTION_COLORS.dc}
        icon={<IconDC color={SECTION_COLORS.dc} />}
      />
      <div style={styles.row}>
        <span style={styles.label}>FACILITIES</span>
        <Counter value={dcCount} hex={SECTION_COLORS.dc} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>COLOCATED NETWORKS</span>
        <Counter value={dcNetworkTotal} hex={SECTION_COLORS.dc} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>COUNTRIES</span>
        <Counter value={dcCountryCount} hex={SECTION_COLORS.dc} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>TRAFFIC</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: SECTION_COLORS.dc }}>~500 Tbps</span>
      </div>

      {/* ── 4. CDN edge network ───────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="CDN EDGE NETWORK"
        color={SECTION_COLORS.cdn}
        icon={<IconCDN color={SECTION_COLORS.cdn} />}
      />
      <div style={styles.row}>
        <span style={styles.label}>EDGE LOCATIONS</span>
        <Counter value={cdnPopCount} hex={SECTION_COLORS.cdn} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>COUNTRIES</span>
        <Counter value={cdnCountryCount} hex={SECTION_COLORS.cdn} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>EST. TRAFFIC</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: SECTION_COLORS.cdn }}>~700 Tbps</span>
      </div>

      {/* ── 5. DNS infrastructure ─────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="DNS INFRASTRUCTURE"
        color={SECTION_COLORS.dns}
        icon={<IconDNS color={SECTION_COLORS.dns} />}
      />
      <div style={styles.row}>
        <span style={styles.label}>ROOT INSTANCES</span>
        <Counter value={dnsRootCount} hex={SECTION_COLORS.dns} />
      </div>
      <div style={styles.row}>
        <span style={styles.label}>RESOLVER POPS</span>
        <Counter value={dnsResolverCount} hex={SECTION_COLORS.dns} />
      </div>

      {/* ── 6. Cell towers ────────────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="CELL TOWERS"
        color={SECTION_COLORS.cell}
        icon={<IconCell color={SECTION_COLORS.cell} />}
      />
      <div style={styles.row}>
        <span style={styles.label}>TOTAL SITES</span>
        <Counter value={cellSiteCount} hex={SECTION_COLORS.cell} />
      </div>

      {/* ── 7. Satellites (live) ──────────────────────────────────────────── */}
      <div style={styles.divider} />
      <SectionHeader
        label="SATELLITES (LIVE)"
        color="#a0c8e0"
        icon={<IconSat colors={[SAT_COLORS.starlink, SAT_COLORS.oneweb, SAT_COLORS.kuiper, SAT_COLORS.geo]} />}
      />
      {[
        ['STARLINK',  starlinkCount, SAT_COLORS.starlink],
        ['ONEWEB',    onewebCount,   SAT_COLORS.oneweb],
        ['KUIPER',    kuiperCount,   SAT_COLORS.kuiper],
        ['GEO COMM',  geoSatCount,   SAT_COLORS.geo],
      ].map(([label, count, color]) => (
        <div key={label} style={styles.row}>
          <span style={styles.label}>{label}</span>
          {count == null
            ? <span style={{ fontSize: 13, fontWeight: 600, color: C.blueprintIndigo }}>LOADING…</span>
            : <span style={{ fontSize: 13, fontWeight: 600, color }}>{count.toLocaleString()}</span>
          }
        </div>
      ))}
      </>)}
    </div>
  );
}
