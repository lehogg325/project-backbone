import { useState, useRef } from 'react';
import { panelStyle, C, MONO_FONT } from './ui-shared';

const LAYERS = [
  {
    id: 'cables',
    label: 'Submarine Cables',
    description: 'Cables · Landing pts',
    tooltip: 'Fiber-optic cables laid on the ocean floor that carry ~99% of international internet traffic. Each line represents a cable system, often owned by consortiums of telecom companies.',
  },
  {
    id: 'datacenters',
    label: 'Data Centers',
    description: '5,255 facilities',
    tooltip: 'Large facilities housing servers, storage, and networking equipment. They are the physical homes of the cloud — where websites, apps, and data actually live.',
  },
  {
    id: 'ixps',
    label: 'Internet Exchanges',
    description: '898 IXPs',
    tooltip: 'Neutral locations where different networks (ISPs, CDNs, cloud providers) connect and exchange traffic directly. IXPs reduce latency and cost by keeping local traffic local.',
  },
  {
    id: 'dns',
    label: 'DNS Infrastructure',
    description: 'Root servers · Resolvers',
    tooltip: 'The internet\'s address book. Root servers answer queries for the top-level structure of domain names; resolvers (run by Google, Cloudflare, etc.) translate domain names into IP addresses for end users.',
  },
  {
    id: 'cdn',
    label: 'CDN Edge Network',
    description: 'Cloudflare · AWS · Fastly · Akamai',
    tooltip: 'Content Delivery Networks cache web content — images, video, scripts — at hundreds of locations worldwide. By serving files from a nearby edge node, they dramatically cut load times.',
  },
  {
    id: 'fiber',
    label: 'Terrestrial Fiber',
    description: 'Verified + estimated · zoom 3+',
    tooltip: 'Land-based fiber-optic routes that form the backbone of national and regional internet networks. Verified routes are sourced from OpenStreetMap; estimated routes are inferred from network topology.',
  },
  {
    id: 'backbone',
    label: 'Terrestrial Backbone (est.)',
    description: 'Approx. fiber routes',
    tooltip: 'Estimated high-capacity trunk routes connecting major cities and internet hubs. These long-haul links carry bulk traffic across continents between data centers and exchanges.',
  },
  {
    id: 'cellTowers',
    label: 'Cell Towers',
    description: 'OpenCelliD · zoom 5+',
    tooltip: 'Density of cellular base stations from the OpenCelliD dataset. Brighter areas have more towers and better mobile coverage. Visible when zoomed in to zoom level 5 or closer.',
  },
];

const s = {
  panel: panelStyle,
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
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '5px 0',
  },
  labelBlock: { flex: 1 },
  label: {
    fontSize: 12,
    transition: 'color 0.2s',
  },
  labelOn:  { color: C.lunarWhite },
  labelOff: { color: '#556070' },
  desc: {
    fontSize: 10,
    letterSpacing: '0.06em',
    marginTop: 2,
    color: '#556070',
  },
  track: {
    position: 'relative',
    width: 36,
    height: 18,
    borderRadius: 9,
    flexShrink: 0,
    cursor: 'pointer',
    transition: 'background 0.25s, box-shadow 0.25s',
  },
  trackOn: {
    background: 'rgba(255, 79, 0, 0.22)',
    boxShadow: '0 0 8px rgba(255, 79, 0, 0.45), inset 0 0 0 1px rgba(255, 79, 0, 0.55)',
  },
  trackOff: {
    background: 'rgba(255,255,255,0.04)',
    boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)',
  },
  thumb: {
    position: 'absolute',
    top: 3,
    width: 12,
    height: 12,
    borderRadius: '50%',
    transition: 'left 0.2s, background 0.2s, box-shadow 0.2s',
  },
  thumbOn: {
    left: 21,
    background: C.signalOrange,
    boxShadow: '0 0 6px rgba(255, 79, 0, 0.9)',
  },
  thumbOff: {
    left: 3,
    background: '#3a3a4a',
    boxShadow: 'none',
  },
};

const tooltipPopStyle = {
  position: 'absolute',
  right: 'calc(100% + 12px)',
  top: '50%',
  transform: 'translateY(-50%)',
  width: 220,
  background: 'rgba(13, 13, 20, 0.97)',
  border: '1px solid rgba(255, 79, 0, 0.3)',
  borderRadius: 4,
  padding: '10px 13px',
  fontFamily: MONO_FONT,
  fontSize: 11,
  color: C.newsprint,
  lineHeight: 1.6,
  pointerEvents: 'none',
  boxShadow: '0 4px 20px rgba(0,0,0,0.6), 0 0 12px rgba(255,79,0,0.06)',
  zIndex: 100,
};

function HoverTooltip({ text }) {
  return <div style={tooltipPopStyle}>{text}</div>;
}

export function Toggle({ on, onToggle }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      style={{
        ...s.track,
        ...(on ? s.trackOn : s.trackOff),
        ...(hovered ? { opacity: 0.85 } : {}),
      }}
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      role="switch"
      aria-checked={on}
    >
      <div style={{ ...s.thumb, ...(on ? s.thumbOn : s.thumbOff) }} />
    </div>
  );
}

function LayerRow({ layer, on, onToggle }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const timerRef = useRef(null);

  function handleMouseEnter() {
    timerRef.current = setTimeout(() => setShowTooltip(true), 1000);
  }

  function handleMouseLeave() {
    clearTimeout(timerRef.current);
    setShowTooltip(false);
  }

  return (
    <div style={{ ...s.row, position: 'relative' }}>
      <div
        style={{ ...s.labelBlock, cursor: 'default' }}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <div style={{ ...s.label, ...(on ? s.labelOn : s.labelOff) }}>
          {layer.label}
        </div>
        {showTooltip && <HoverTooltip text={layer.tooltip} />}
      </div>
      <Toggle on={on} onToggle={onToggle} />
    </div>
  );
}

export default function LayerToggle({ visible, onToggle }) {
  const [collapsed, setCollapsed] = useState(false); // starts open

  return (
    <div style={s.panel}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{ ...s.title, cursor: 'pointer', marginBottom: collapsed ? 0 : 10 }}
      >
        <span style={s.accent}>◈ </span>MAP LAYERS
      </div>

      {!collapsed && (
        <>
          <div style={s.divider} />
          {LAYERS.map(layer => (
            <LayerRow
              key={layer.id}
              layer={layer}
              on={visible[layer.id]}
              onToggle={() => onToggle(layer.id)}
            />
          ))}
        </>
      )}
    </div>
  );
}
