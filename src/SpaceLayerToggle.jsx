import { useState, useEffect, useRef } from 'react';
import { panelStyle, C, MONO_FONT } from './ui-shared';
import { Toggle } from './LayerToggle';

const LAYERS = [
  {
    id: 'iss',
    label: 'ISS',
    description: 'Int\'l Space Station · ~420 km',
    tooltip: 'The International Space Station orbits at ~420 km altitude and completes a full lap of the Earth every 90 minutes. Its position is tracked in real time using live TLE data.',
  },
  {
    id: 'starlink',
    label: 'Starlink Satellites',
    description: 'SpaceX LEO · ~550 km',
    tooltip: 'SpaceX\'s low Earth orbit constellation providing global broadband internet. With thousands of satellites active, Starlink is the largest satellite network ever deployed.',
  },
  {
    id: 'oneweb',
    label: 'OneWeb Satellites',
    description: 'LEO · ~1,200 km',
    tooltip: 'OneWeb operates a LEO constellation at ~1,200 km, focused on connecting businesses, governments, and remote communities. Backed by the UK government and Bharti Global.',
  },
  {
    id: 'kuiper',
    label: 'Kuiper Satellites',
    description: 'Amazon LEO · ~590-630 km',
    tooltip: 'Amazon\'s Project Kuiper aims to deploy over 3,200 satellites to deliver broadband internet globally, competing directly with Starlink in the low Earth orbit market.',
  },
  {
    id: 'geoSats',
    label: 'GEO Comm Satellites',
    description: 'Geostationary · 35,786 km',
    tooltip: 'Geostationary satellites orbit at 35,786 km — high enough to remain fixed over one spot on Earth. They provide broadcast TV, weather data, and legacy internet to regions unreachable by fiber.',
  },
  {
    id: 'groundStations',
    label: 'Ground Stations',
    description: 'Starlink & OneWeb gateways',
    tooltip: 'Uplink facilities that connect satellite constellations to the terrestrial internet. Ground stations relay traffic between orbiting satellites and the fiber networks on the ground.',
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
        {showTooltip && <div style={tooltipPopStyle}>{layer.tooltip}</div>}
      </div>
      <Toggle on={on} onToggle={onToggle} />
    </div>
  );
}

export default function SpaceLayerToggle({ visible, onToggle }) {
  const [collapsed, setCollapsed] = useState(true);
  const anyOn = LAYERS.some(l => visible[l.id]);

  return (
    <div style={s.panel}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{ ...s.title, cursor: 'pointer', marginBottom: collapsed ? 0 : 10 }}
      >
        <span style={s.accent}>◈ </span>SPACE LAYER
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
                  background: C.signalOrange,
                  boxShadow: '0 0 6px rgba(255, 79, 0, 0.9)',
                  flexShrink: 0,
                }} />
                <span style={{ color: C.signalOrange, fontWeight: 600 }}>LIVE</span>
                <span style={{ color: '#556070', marginLeft: 4 }}><UtcClock /></span>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
