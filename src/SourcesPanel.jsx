import { useState } from 'react';
import { MONO_FONT, C } from './ui-shared';

const SOURCES = [
  {
    category: 'SUBMARINE CABLES',
    items: [
      { name: 'TeleGeography — Submarine Cable Map', url: 'https://www.submarinecablemap.com' },
    ],
  },
  {
    category: 'DATA CENTERS',
    items: [
      { name: 'PeeringDB — Facility Database', url: 'https://www.peeringdb.com' },
    ],
  },
  {
    category: 'INTERNET EXCHANGES',
    items: [
      { name: 'PeeringDB — Exchange Database', url: 'https://www.peeringdb.com' },
      { name: 'Euro-IX — IXP Directory', url: 'https://www.euro-ix.net' },
    ],
  },
  {
    category: 'CDN EDGE NETWORK',
    items: [
      { name: 'Cloudflare — Network Map', url: 'https://www.cloudflare.com/network' },
      { name: 'Amazon CloudFront — Edge Locations', url: 'https://aws.amazon.com/cloudfront/features' },
      { name: 'Fastly — Network Map', url: 'https://www.fastly.com/network-map' },
      { name: 'Akamai — Network Visualization', url: 'https://www.akamai.com/visualizations/real-time-web-monitor' },
    ],
  },
  {
    category: 'DNS INFRASTRUCTURE',
    items: [
      { name: 'Root Server Technical Operations Assn. (RSSAC)', url: 'https://www.icann.org/groups/rssac' },
      { name: 'Root Server Operator Network', url: 'https://root-servers.org' },
    ],
  },
  {
    category: 'TERRESTRIAL FIBER',
    items: [
      { name: 'OpenStreetMap — Verified Routes', url: 'https://www.openstreetmap.org' },
      { name: 'Estimated routes via MST on IXP / DC / landing point nodes', url: null },
    ],
  },
  {
    category: 'CELL TOWERS',
    items: [
      { name: 'OpenCelliD — Global Cell Tower Database', url: 'https://opencellid.org' },
    ],
  },
  {
    category: 'SATELLITES — ORBITAL DATA',
    items: [
      { name: 'CelesTrak — TLE Data (Starlink, OneWeb, GEO, ISS)', url: 'https://celestrak.org' },
      { name: 'Amazon Project Kuiper — FCC Filings', url: 'https://www.fcc.gov' },
    ],
  },
  {
    category: 'TRAFFIC & CAPACITY ESTIMATES',
    items: [
      { name: 'TeleGeography — Global Internet Geography', url: 'https://www.telegeography.com' },
      { name: 'Cisco Visual Networking Index (VNI)', url: 'https://www.cisco.com/c/en/us/solutions/collateral/executive-perspectives/annual-internet-report/white-paper-c11-741490.html' },
      { name: 'Euro-IX — IXP Traffic Statistics', url: 'https://www.euro-ix.net/en/statistics' },
    ],
  },
  {
    category: 'MASS ESTIMATES',
    items: [
      { name: 'ITU — ICT Infrastructure Reports', url: 'https://www.itu.int' },
      { name: 'GSMA — Mobile Economy Reports', url: 'https://www.gsma.com/mobileeconomy' },
      { name: 'IEA — Data Centres & Data Transmission Networks', url: 'https://www.iea.org/energy-system/buildings/data-centres-and-data-transmission-networks' },
      { name: 'SpaceX, OneWeb & Amazon — Regulatory Filings', url: null },
    ],
  },
];

export default function SourcesPanel() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Tab button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          position: 'absolute',
          top: 20,
          right: 20,
          fontFamily: MONO_FONT,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.18em',
          color: open ? C.signalOrange : C.photogray,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
          userSelect: 'none',
          zIndex: 60,
          transition: 'color 0.2s',
          whiteSpace: 'nowrap',
        }}
      >
        SOURCES
      </button>

      {/* Modal overlay */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 40,
            background: 'rgba(13, 13, 20, 0.55)',
            backdropFilter: 'blur(3px)',
          }}
        />
      )}

      {/* Panel */}
      {open && (
        <div
          onClick={e => e.stopPropagation()}
          style={{
            position: 'absolute',
            top: 52,
            right: 20,
            width: 440,
            maxHeight: 'calc(100vh - 80px)',
            overflowY: 'auto',
            background: 'rgba(13, 13, 20, 0.97)',
            border: '1px solid rgba(255, 79, 0, 0.3)',
            borderRadius: 4,
            padding: '20px 22px 24px',
            fontFamily: MONO_FONT,
            fontSize: 11,
            color: C.newsprint,
            zIndex: 50,
            boxShadow: '0 8px 40px rgba(0,0,0,0.7), 0 0 16px rgba(255,79,0,0.07)',
            userSelect: 'none',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 16 }}>
            <div>
              <span style={{ color: C.signalOrange, marginRight: 8 }}>◈</span>
              <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.18em', color: C.lunarWhite }}>
                DATA SOURCES
              </span>
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{
                background: 'none',
                border: 'none',
                color: '#556070',
                cursor: 'pointer',
                fontSize: 16,
                lineHeight: 1,
                padding: '0 2px',
                fontFamily: MONO_FONT,
              }}
            >✕</button>
          </div>

          <div style={{ borderTop: '1px solid rgba(255,79,0,0.18)', marginBottom: 16 }} />

          {SOURCES.map((section, i) => (
            <div key={i} style={{ marginBottom: 16 }}>
              <div style={{
                fontSize: 9,
                letterSpacing: '0.22em',
                color: C.signalOrange,
                marginBottom: 7,
              }}>
                {section.category}
              </div>
              {section.items.map((item, j) => (
                <div key={j} style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 5, paddingLeft: 10 }}>
                  <span style={{ color: '#556070', flexShrink: 0 }}>·</span>
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: C.celestialBlue, textDecoration: 'none', lineHeight: 1.5 }}
                    >
                      {item.name}
                    </a>
                  ) : (
                    <span style={{ color: C.photogray, lineHeight: 1.5 }}>{item.name}</span>
                  )}
                </div>
              ))}
            </div>
          ))}

          <div style={{ borderTop: '1px solid rgba(255,79,0,0.12)', marginTop: 8, paddingTop: 12 }}>
            <span style={{ fontSize: 9, color: '#556070', letterSpacing: '0.08em', lineHeight: 1.6 }}>
              Mass estimates use published hardware specifications and infrastructure filings.
              Traffic figures are industry estimates and subject to revision.
              Satellite positions computed via SGP4 propagation from live TLE data.
            </span>
          </div>
        </div>
      )}
    </>
  );
}
