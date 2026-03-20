import { useState } from 'react';

const LAYERS = [
  { id: 'cables',      label: 'Submarine Cables',            description: 'Cables · Landing pts' },
  { id: 'datacenters', label: 'Data Centers',                description: '5,255 facilities' },
  { id: 'ixps',        label: 'Internet Exchanges',          description: '898 IXPs' },
  { id: 'dns',         label: 'DNS Infrastructure',          description: 'Root servers · Resolvers' },
  { id: 'cdn',         label: 'CDN Edge Network',            description: 'Cloudflare · AWS · Fastly · Akamai' },
  { id: 'fiber',       label: 'Terrestrial Fiber',           description: 'Verified + estimated · zoom 3+' },
  { id: 'backbone',    label: 'Terrestrial Backbone (est.)', description: 'Approx. fiber routes' },
  { id: 'cellTowers',  label: 'Cell Towers',                 description: 'OpenCelliD · zoom 5+' },
];

export const panelStyle = {
  background: 'rgba(4, 10, 20, 0.88)',
  border: '1px solid rgba(0, 180, 255, 0.2)',
  borderRadius: 4,
  padding: '14px 18px',
  fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
  fontSize: 12,
  color: '#8ab8cc',
  minWidth: 220,
  backdropFilter: 'blur(6px)',
  boxShadow: '0 0 24px rgba(0,140,220,0.08), inset 0 0 0 1px rgba(0,180,255,0.05)',
  userSelect: 'none',
};

const s = {
  panel: panelStyle,
  title: {
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: '0.18em',
    color: '#d0eeff',
    marginBottom: 10,
  },
  accent: { color: '#00c8ff' },
  divider: {
    borderTop: '1px solid rgba(0,180,255,0.15)',
    margin: '10px 0',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '7px 0',
  },
  labelBlock: { flex: 1 },
  label: {
    fontSize: 12,
    transition: 'color 0.2s',
  },
  labelOn:  { color: '#c8e8f5' },
  labelOff: { color: '#6a8a9a' },
  desc: {
    fontSize: 10,
    letterSpacing: '0.06em',
    marginTop: 2,
    color: '#5a7a8a',
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
    background: 'rgba(0,180,255,0.25)',
    boxShadow: '0 0 8px rgba(0,180,255,0.4), inset 0 0 0 1px rgba(0,200,255,0.5)',
  },
  trackOff: {
    background: 'rgba(255,255,255,0.04)',
    boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.1)',
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
    background: '#00c8ff',
    boxShadow: '0 0 6px rgba(0,200,255,0.9)',
  },
  thumbOff: {
    left: 3,
    background: '#2a4a5a',
    boxShadow: 'none',
  },
};

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

export default function LayerToggle({ visible, onToggle }) {
  return (
    <div style={s.panel}>
      <div style={s.title}>
        <span style={s.accent}>▸ </span>MAP LAYERS
      </div>
      <div style={s.divider} />

      {LAYERS.map(layer => {
        const on = visible[layer.id];
        return (
          <div key={layer.id} style={s.row}>
            <div style={s.labelBlock}>
              <div style={{ ...s.label, ...(on ? s.labelOn : s.labelOff) }}>
                {layer.label}
              </div>
              <div style={s.desc}>{layer.description}</div>
            </div>
            <Toggle on={on} onToggle={() => onToggle(layer.id)} />
          </div>
        );
      })}
    </div>
  );
}
