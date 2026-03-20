import { useState, useEffect } from 'react';
import { panelStyle, Toggle } from './LayerToggle';

const LAYERS = [
  { id: 'iss',            label: 'ISS',                   description: 'Int\'l Space Station · ~420 km' },
  { id: 'starlink',       label: 'Starlink Satellites',   description: 'SpaceX LEO · ~550 km' },
  { id: 'oneweb',         label: 'OneWeb Satellites',     description: 'LEO · ~1,200 km' },
  { id: 'kuiper',         label: 'Kuiper Satellites',     description: 'Amazon LEO · ~590-630 km' },
  { id: 'geoSats',        label: 'GEO Comm Satellites',   description: 'Geostationary · 35,786 km' },
  { id: 'groundStations', label: 'Ground Stations',       description: 'Starlink & OneWeb gateways' },
];

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
};

function UtcClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const h   = String(time.getUTCHours()).padStart(2, '0');
  const m   = String(time.getUTCMinutes()).padStart(2, '0');
  const sec = String(time.getUTCSeconds()).padStart(2, '0');
  return <span>{h}:{m}:{sec} UTC</span>;
}

export default function SpaceLayerToggle({ visible, onToggle }) {
  const anyOn = LAYERS.some(l => visible[l.id]);

  return (
    <div style={s.panel}>
      <div style={s.title}>
        <span style={s.accent}>▸ </span>SPACE LAYER
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

      {anyOn && (
        <>
          <div style={s.divider} />
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            fontSize: 11,
            letterSpacing: '0.08em',
          }}>
            <span style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#00c8ff',
              boxShadow: '0 0 6px rgba(0,200,255,0.9)',
              flexShrink: 0,
            }} />
            <span style={{ color: '#00c8ff', fontWeight: 600 }}>LIVE</span>
            <span style={{ color: '#5a8a9a', marginLeft: 4 }}><UtcClock /></span>
          </div>
        </>
      )}
    </div>
  );
}
