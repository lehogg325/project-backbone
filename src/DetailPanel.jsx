import { useEffect, useState } from 'react';

const FONT = '"JetBrains Mono", "Fira Code", "Courier New", monospace';

const s = {
  panel: {
    position: 'absolute',
    right: 0,
    top: 0,
    width: 300,
    height: '100%',
    background: 'rgba(4, 10, 20, 0.96)',
    borderLeft: '1px solid rgba(0, 180, 255, 0.18)',
    fontFamily: FONT,
    fontSize: 12,
    color: '#8ab8cc',
    zIndex: 20,
    overflowY: 'auto',
    transition: 'transform 0.26s cubic-bezier(0.4, 0, 0.2, 1)',
    boxShadow: '-6px 0 32px rgba(0, 0, 0, 0.7)',
    userSelect: 'none',
  },
  header: {
    padding: '16px 18px 12px',
    borderBottom: '1px solid rgba(0, 180, 255, 0.13)',
    position: 'sticky',
    top: 0,
    background: 'rgba(4, 10, 20, 0.99)',
    zIndex: 1,
  },
  closeBtn: {
    position: 'absolute',
    top: 13,
    right: 14,
    background: 'none',
    border: 'none',
    color: '#3a6070',
    cursor: 'pointer',
    fontSize: 18,
    lineHeight: 1,
    padding: '2px 4px',
    fontFamily: FONT,
  },
  badge: {
    fontSize: 9,
    letterSpacing: '0.22em',
    color: '#2a5a6a',
    marginBottom: 5,
  },
  title: {
    fontSize: 13,
    fontWeight: 700,
    color: '#d0eeff',
    letterSpacing: '0.04em',
    paddingRight: 24,
    lineHeight: 1.4,
  },
  body: {
    padding: '14px 18px 24px',
  },
  divider: {
    borderTop: '1px solid rgba(0, 180, 255, 0.12)',
    margin: '12px 0',
  },
  sectionLabel: {
    fontSize: 9,
    letterSpacing: '0.22em',
    color: '#2a5a6a',
    marginBottom: 8,
    marginTop: 2,
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: 10,
    marginBottom: 7,
  },
  label: {
    color: '#3a6070',
    fontSize: 10,
    letterSpacing: '0.1em',
    flexShrink: 0,
  },
  value: {
    color: '#a8dff0',
    fontSize: 11,
    textAlign: 'right',
  },
  listItem: {
    color: '#6ab8d0',
    fontSize: 11,
    paddingLeft: 10,
    marginBottom: 4,
    lineHeight: 1.5,
  },
  linkItem: {
    color: '#4fc3f7',
    fontSize: 11,
    paddingLeft: 10,
    marginBottom: 5,
    cursor: 'pointer',
    letterSpacing: '0.02em',
  },
  website: {
    color: '#4fc3f7',
    fontSize: 11,
    textDecoration: 'none',
    wordBreak: 'break-all',
  },
  note: {
    fontSize: 9,
    color: '#2a4a5a',
    marginTop: 10,
    letterSpacing: '0.06em',
    lineHeight: 1.6,
  },
};

function Row({ label, value }) {
  if (value == null || value === '' || value === '—') return null;
  return (
    <div style={s.row}>
      <span style={s.label}>{label}</span>
      <span style={s.value}>{value}</span>
    </div>
  );
}

function SectionLabel({ children }) {
  return <div style={s.sectionLabel}>{children}</div>;
}

function Divider() {
  return <div style={s.divider} />;
}

// ── Feature-type content ──────────────────────────────────────────────────────

function CableDetail({ p, landingPoints, onLandingPointClick }) {
  return (
    <>
      <SectionLabel>ROUTE INFO</SectionLabel>
      <Row label="RFS YEAR" value={p.rfs_year} />
      <Row label="LENGTH"   value={p.length_km ? `${p.length_km.toLocaleString()} km` : null} />

      {p.owners?.length > 0 && (
        <>
          <Divider />
          <SectionLabel>CONSORTIUM ({p.owners.length})</SectionLabel>
          {p.owners.map((o, i) => (
            <div key={i} style={s.listItem}>· {o}</div>
          ))}
        </>
      )}

      {landingPoints.length > 0 && (
        <>
          <Divider />
          <SectionLabel>LANDING POINTS ({landingPoints.length})</SectionLabel>
          {landingPoints.map((lp, i) => (
            <LandingPointLink key={i} name={lp.properties.name} onClick={() => onLandingPointClick(lp)} />
          ))}
        </>
      )}
    </>
  );
}

function LandingPointLink({ name, onClick }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      style={{ ...s.linkItem, color: hov ? '#80d8ff' : '#4fc3f7' }}
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      ↳ {name}
    </div>
  );
}

function LandingPointDetail({ p }) {
  return (
    <>
      <SectionLabel>CONNECTED CABLES ({p.cables?.length ?? 0})</SectionLabel>
      {(p.cables || []).map((c, i) => (
        <div key={i} style={s.listItem}>· {c}</div>
      ))}
    </>
  );
}

function DatacenterDetail({ p }) {
  const location = [p.city, p.state, p.country].filter(Boolean).join(', ');
  return (
    <>
      <SectionLabel>FACILITY INFO</SectionLabel>
      {p.aka && <Row label="AKA"      value={p.aka} />}
      <Row label="LOCATION"  value={location || null} />
      <Row label="NETWORKS"  value={p.network_count > 0 ? `${p.network_count.toLocaleString()} colocated` : null} />
      {p.website && (
        <>
          <Divider />
          <SectionLabel>LINKS</SectionLabel>
          <div style={{ paddingLeft: 10 }}>
            <a href={p.website} target="_blank" rel="noreferrer" style={s.website}>
              {p.website.replace(/^https?:\/\//, '')}
            </a>
          </div>
        </>
      )}
    </>
  );
}

function IxpDetail({ p }) {
  const location = [p.city, p.country].filter(Boolean).join(', ');
  return (
    <>
      <SectionLabel>EXCHANGE INFO</SectionLabel>
      {p.aka && <Row label="AKA"         value={p.aka} />}
      <Row label="LOCATION"    value={location || null} />
      <Row label="REGION"      value={p.region || null} />
      <Row label="PARTICIPANTS" value={p.participants > 0 ? p.participants.toLocaleString() : null} />
      {p.website && (
        <>
          <Divider />
          <SectionLabel>LINKS</SectionLabel>
          <div style={{ paddingLeft: 10 }}>
            <a href={p.website} target="_blank" rel="noreferrer" style={s.website}>
              {p.website.replace(/^https?:\/\//, '')}
            </a>
          </div>
        </>
      )}
      <div style={s.note}>↳ detailed traffic volume data is proprietary (Euro-IX)</div>
    </>
  );
}

function CellTowerDetail({ p }) {
  return (
    <>
      <SectionLabel>DENSITY CELL</SectionLabel>
      <Row label="TOWERS"    value={p.count?.toLocaleString()} />
      <Row label="COVERAGE"  value={p.coverage} />
      <Row label="AVG RANGE" value={p.avg_range != null ? `${p.avg_range.toLocaleString()} m` : null} />
      <Row label="SAMPLES"   value={p.samples?.toLocaleString()} />
      <Row label="COUNTRY"   value={p.country} />
      <Row label="UPDATED"   value={p.updated} />
      <div style={s.note}>↳ 0.1° grid cell · source: OpenCelliD</div>
    </>
  );
}

const CDN_COLORS = {
  Cloudflare: '#f38020',
  CloudFront: '#ffc832',
  Fastly:     '#ff5ab4',
  Akamai:     '#1e96ff',
};

function CdnDetail({ p }) {
  const providers = p.providers || [];
  return (
    <>
      <SectionLabel>CDN PROVIDERS ({providers.reduce((n, pr) => n + pr.count, 0)} PoPs within 50 km)</SectionLabel>
      {providers.map(({ name, count, cities }) => {
        const color = CDN_COLORS[name] || '#a8dff0';
        return (
          <div key={name} style={{ marginBottom: 10 }}>
            <div style={{ ...s.row, marginBottom: 3 }}>
              <span style={{ ...s.label, color, fontSize: 11, letterSpacing: '0.14em' }}>
                {name.toUpperCase()}
              </span>
              <span style={{ ...s.value, color, fontSize: 12 }}>
                {count} PoP{count !== 1 ? 's' : ''}
              </span>
            </div>
            {cities.length > 0 && (
              <div style={{ ...s.listItem, color: '#4a7a8a', fontSize: 10, paddingLeft: 14 }}>
                {cities.slice(0, 4).join(' · ')}
                {cities.length > 4 ? ` +${cities.length - 4} more` : ''}
              </div>
            )}
          </div>
        );
      })}
      {providers.length === 0 && (
        <div style={s.note}>No CDN PoPs found within 50 km</div>
      )}
      <div style={s.note}>↳ click radius ~50 km · data: provider network maps</div>
    </>
  );
}

function DnsRootDetail({ p }) {
  return (
    <>
      <SectionLabel>ROOT SERVER INFO</SectionLabel>
      <Row label="LETTER"   value={p.letter} />
      <Row label="OPERATOR" value={p.operator} />
      <Row label="CITY"     value={p.city} />
      <Row label="COUNTRY"  value={p.country} />
      {p.isGlobal && (
        <div style={{ ...s.note, color: '#4a9a7a', marginTop: 8 }}>↳ global anycast instance</div>
      )}
    </>
  );
}

function FiberRouteDetail({ p }) {
  const isVerified = p.source === 'verified' || p.type === 'verified';
  return (
    <>
      <SectionLabel>ROUTE INFO</SectionLabel>
      <Row label="SOURCE"     value={isVerified ? 'Verified (OSM)' : 'Estimated (MST)'} />
      <Row label="ROUTE TYPE" value={p.route_type ? p.route_type.charAt(0).toUpperCase() + p.route_type.slice(1) : null} />
      {p.length_km > 0 && <Row label="LENGTH" value={`${Math.round(p.length_km).toLocaleString()} km`} />}
      {(p.from || p.to) && (
        <>
          <Divider />
          <SectionLabel>ENDPOINTS</SectionLabel>
          {p.from && <Row label="FROM" value={p.from} />}
          {p.to   && <Row label="TO"   value={p.to}   />}
        </>
      )}
      {p.operator && (
        <>
          <Divider />
          <SectionLabel>OPERATOR</SectionLabel>
          <Row label="NAME" value={p.operator} />
        </>
      )}
      {p.country && <Row label="COUNTRY" value={p.country} />}
      <div style={s.note}>
        {isVerified
          ? '↳ route geometry from OpenStreetMap'
          : '↳ estimated via MST on IXP / DC / landing point nodes'}
      </div>
    </>
  );
}

function DnsResolverDetail({ p }) {
  const PROVIDER_COLORS = {
    Cloudflare: '#ff6b35',
    Google:     '#4285f4',
    Quad9:      '#9b59b6',
    OpenDNS:    '#27ae60',
  };
  const color = PROVIDER_COLORS[p.provider] || '#a8dff0';
  return (
    <>
      <SectionLabel>RESOLVER INFO</SectionLabel>
      <Row label="PROVIDER" value={<span style={{ color }}>{p.provider}</span>} />
      {p.ip && <Row label="IP / ANYCAST" value={p.ip} />}
      <Row label="CITY"     value={p.city} />
      <Row label="COUNTRY"  value={p.country} />
      <div style={s.note}>↳ public recursive resolver PoP</div>
    </>
  );
}

// ── Type metadata ─────────────────────────────────────────────────────────────

const TYPE_META = {
  cable:          { badge: 'SUBMARINE CABLE',        accent: '#4fc3f7' },
  'landing-point':{ badge: 'CABLE LANDING POINT',    accent: '#64d8f5' },
  datacenter:     { badge: 'DATA CENTER',             accent: '#4ddb8a' },
  ixp:            { badge: 'INTERNET EXCHANGE',       accent: '#ffd740' },
  'cell-tower':   { badge: 'CELL TOWER DENSITY',      accent: '#ff80d8' },
  'fiber-route':  { badge: 'TERRESTRIAL FIBER ROUTE',   accent: '#00d2c8' },
  'dns-root':     { badge: 'DNS ROOT SERVER',          accent: '#a0e0ff' },
  'dns-resolver': { badge: 'PUBLIC DNS RESOLVER',      accent: '#ff9060' },
  'cdn-edge':     { badge: 'CDN EDGE LOCATION',        accent: '#f38020' },
};

// ── Main component ────────────────────────────────────────────────────────────

export default function DetailPanel({ feature, onClose, landingPointFeatures, onLandingPointClick }) {
  const visible = feature != null;
  const meta = feature ? TYPE_META[feature.type] : null;
  const p    = feature || {};

  const cableLandingPoints = feature?.type === 'cable'
    ? (landingPointFeatures || []).filter(lp =>
        (lp.properties.cables || []).includes(p.name)
      )
    : [];

  return (
    <div style={{
      ...s.panel,
      transform: visible ? 'translateX(0)' : 'translateX(100%)',
      pointerEvents: visible ? 'auto' : 'none',
    }}>
      {feature && (
        <>
          <div style={s.header}>
            <div style={{ ...s.badge, color: meta?.accent }}>{meta?.badge}</div>
            <div style={s.title}>{p.name || 'Cell Tower Density'}</div>
            <button style={s.closeBtn} onClick={onClose}>✕</button>
          </div>

          <div style={s.body}>
            {feature.type === 'fiber-route'   && <FiberRouteDetail   p={p} />}
            {feature.type === 'cable' && (
              <CableDetail
                p={p}
                landingPoints={cableLandingPoints}
                onLandingPointClick={onLandingPointClick}
              />
            )}
            {feature.type === 'landing-point' && <LandingPointDetail p={p} />}
            {feature.type === 'datacenter'    && <DatacenterDetail   p={p} />}
            {feature.type === 'ixp'           && <IxpDetail          p={p} />}
            {feature.type === 'cell-tower'    && <CellTowerDetail    p={p} />}
            {feature.type === 'dns-root'      && <DnsRootDetail      p={p} />}
            {feature.type === 'dns-resolver'  && <DnsResolverDetail  p={p} />}
            {feature.type === 'cdn-edge'      && <CdnDetail          p={p} />}
          </div>
        </>
      )}
    </div>
  );
}
