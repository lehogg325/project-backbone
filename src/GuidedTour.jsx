import { useState, useEffect } from 'react';
import { MONO_FONT, C } from './ui-shared';

const BASE_VISIBILITY = {
  cables: false, datacenters: false, ixps: false, dns: false,
  cdn: false, fiber: false, backbone: false, cellTowers: false,
  iss: false, starlink: false, oneweb: false, kuiper: false,
  geoSats: false, groundStations: false,
};

const TOUR_STEPS = [
  {
    title: 'You Hit Search',
    subtitle: 'Step 1 of 8',
    body: "You're in Dallas, Texas. You tap Search. Your phone connects to the nearest cell tower — the density clusters visible here. In milliseconds, that tower hands your data off to a wired network. This first hop, from wireless to wire, is where your packet enters the global internet.",
    layers: { cellTowers: true },
    flyTo: { longitude: -96.8, latitude: 32.8, zoom: 8 },
  },
  {
    title: 'The Internet Exchange',
    subtitle: 'Step 2 of 8',
    body: "Your packet travels east to Ashburn, Virginia — the internet exchange capital of the world. More traffic passes through this small suburb than almost anywhere else on Earth. At an IXP, hundreds of networks hand traffic directly to each other, keeping your request moving without unnecessary detours.",
    layers: { ixps: true },
    flyTo: { longitude: -77.5, latitude: 38.9, zoom: 6 },
  },
  {
    title: 'The Terrestrial Backbone',
    subtitle: 'Step 3 of 8',
    body: "Your packet joins the backbone — high-capacity fiber highways running along highways, rail lines, and power corridors across the continent. These dashed lines are estimated long-haul routes. Brighter lines carry international traffic; dimmer ones connect cities within the country. Your packet heads for the coast.",
    layers: { backbone: true },
    flyTo: { longitude: -82, latitude: 37, zoom: 3.2 },
  },
  {
    title: 'The Ocean Floor',
    subtitle: 'Step 4 of 8',
    body: "At a coastal landing station, your packet enters a submarine cable and dives under the Atlantic. Each cable is roughly the width of a garden hose, sheathed in steel and buried in the seabed. The crossing takes about 70 milliseconds. A single anchor cut can knock millions of users offline for weeks.",
    layers: { cables: true },
    flyTo: { longitude: -35, latitude: 40, zoom: 2.5 },
  },
  {
    title: 'Terrestrial Fiber',
    subtitle: 'Step 5 of 8',
    body: "Your packet surfaces on the European coast and immediately enters a land-based fiber network. Solid lines are verified routes; dashed lines are estimated from network topology. This dense web of glass threads carries your packet east through the continent toward its destination.",
    layers: { fiber: true },
    flyTo: { longitude: 2, latitude: 50, zoom: 4.5 },
    callout: { direction: 'right', label: 'EXPLORE LAYERS', bottom: 215, right: 272 },
  },
  {
    title: 'The Data Center',
    subtitle: 'Step 6 of 8',
    body: "Your packet arrives at a data center in Frankfurt — one of Europe's densest clusters of internet infrastructure. Servers here receive your request, find the answer, and immediately begin sending it back. The same route in reverse: fiber → cable → backbone → cell tower → your screen.",
    layers: { datacenters: true },
    flyTo: { longitude: 8.7, latitude: 50.1, zoom: 7 },
  },
  {
    title: 'And Back Again',
    subtitle: 'Step 7 of 8',
    body: "The full round trip — Dallas to Frankfurt and back — takes roughly 100–150 milliseconds. Every layer visible here was part of that journey. Cell tower, backbone, cable, fiber, data center. Billions of these trips happen every second, right now, beneath your feet and across the ocean floor.",
    layers: { cables: true, backbone: true, fiber: true, datacenters: true },
    flyTo: { longitude: -30, latitude: 42, zoom: 2.2 },
  },
  {
    title: 'The Satellite Layer',
    subtitle: 'Step 8 of 8',
    body: "Not all internet travels through cables. SpaceX's Starlink and other constellations provide coverage for ships, planes, and regions cables can't reach. A new orbital infrastructure is being built above us in real time. Click any satellite to see its live orbit and flight data.",
    layers: { iss: true, starlink: true },
    flyTo: { longitude: 0, latitude: 20, zoom: 1.5 },
  },
];

const SUGGESTIONS = [
  {
    label: 'DATA CENTERS + IXPS',
    body: 'Turn both on to see where internet traffic concentrates — US East Coast and Western Europe dominate.',
  },
  {
    label: 'CELL TOWERS',
    body: 'Enable and zoom into any city to see mobile tower density as a heat map.',
  },
  {
    label: 'SATELLITES',
    body: 'Turn on Starlink, then click any dot to see its live orbit path and flight data.',
  },
];

const panelStyle = {
  position: 'absolute',
  bottom: 28,
  left: '50%',
  transform: 'translateX(-50%)',
  width: 'clamp(300px, 44vw, 520px)',
  background: 'rgba(13, 13, 20, 0.97)',
  border: '1px solid rgba(255, 79, 0, 0.35)',
  borderRadius: 4,
  padding: '20px 24px 18px',
  fontFamily: MONO_FONT,
  color: C.newsprint,
  zIndex: 30,
  backdropFilter: 'blur(10px)',
  boxShadow: '0 8px 40px rgba(0,0,0,0.75), 0 0 24px rgba(255, 79, 0, 0.08)',
  userSelect: 'none',
};

function Dots({ total, current }) {
  return (
    <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
      {Array.from({ length: total }, (_, i) => (
        <div key={i} style={{
          width: i === current ? 16 : 6,
          height: 6,
          borderRadius: 3,
          background: i === current ? C.signalOrange : 'rgba(255,79,0,0.2)',
          transition: 'width 0.3s, background 0.3s',
        }} />
      ))}
    </div>
  );
}

function Btn({ onClick, children, primary }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        fontFamily: MONO_FONT,
        fontSize: 11,
        letterSpacing: '0.14em',
        fontWeight: 600,
        padding: '7px 16px',
        borderRadius: 3,
        cursor: 'pointer',
        transition: 'background 0.2s, color 0.2s, border-color 0.2s',
        background: primary
          ? (hov ? C.signalOrange : 'rgba(255, 79, 0, 0.15)')
          : 'transparent',
        color: primary
          ? (hov ? '#fff' : C.signalOrange)
          : (hov ? C.newsprint : C.photogray),
        border: primary
          ? `1px solid ${hov ? C.signalOrange : 'rgba(255, 79, 0, 0.45)'}`
          : '1px solid rgba(255,255,255,0.08)',
      }}
    >
      {children}
    </button>
  );
}

function Callout({ direction, label, bottom, right }) {
  const arrowSize = 7;
  const borderColor = 'rgba(255, 79, 0, 0.45)';

  const arrowStyle = direction === 'right' ? {
    position: 'absolute',
    right: -arrowSize,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 0,
    height: 0,
    borderTop: `${arrowSize}px solid transparent`,
    borderBottom: `${arrowSize}px solid transparent`,
    borderLeft: `${arrowSize}px solid rgba(255, 79, 0, 0.6)`,
  } : {};

  return (
    <div style={{
      position: 'absolute',
      bottom,
      right,
      zIndex: 31,
      pointerEvents: 'none',
    }}>
      <div style={{
        position: 'relative',
        background: 'rgba(13, 13, 20, 0.92)',
        border: `1px solid ${borderColor}`,
        borderRadius: 3,
        padding: '6px 11px',
        fontFamily: MONO_FONT,
        fontSize: 9,
        letterSpacing: '0.18em',
        color: C.signalOrange,
        whiteSpace: 'nowrap',
        boxShadow: '0 0 12px rgba(255,79,0,0.12)',
      }}>
        {label}
        <div style={arrowStyle} />
      </div>
    </div>
  );
}

function StepCard({ step, stepIndex, total, onNext, onBack, onSkip }) {
  const isLast = stepIndex === total - 1;
  return (
    <div style={panelStyle}>
      <Dots total={total} current={stepIndex} />
      <div style={{
        fontSize: 8,
        letterSpacing: '0.22em',
        color: C.signalOrange,
        marginBottom: 6,
      }}>
        {step.subtitle.toUpperCase()}
      </div>
      <div style={{
        fontSize: 13,
        fontWeight: 700,
        color: C.lunarWhite,
        letterSpacing: '0.06em',
        marginBottom: 10,
      }}>
        {step.title.toUpperCase()}
      </div>
      <div style={{
        fontSize: 11,
        color: C.newsprint,
        lineHeight: 1.8,
        letterSpacing: '0.02em',
        marginBottom: 18,
      }}>
        {step.body}
      </div>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <Btn onClick={onSkip}>SKIP</Btn>
        <div style={{ display: 'flex', gap: 8 }}>
          {stepIndex > 0 && <Btn onClick={onBack}>← BACK</Btn>}
          <Btn primary onClick={onNext}>
            {isLast ? 'EXPLORE →' : 'NEXT →'}
          </Btn>
        </div>
      </div>
    </div>
  );
}

function SuggestionCard({ onDone }) {
  return (
    <div style={{
      ...panelStyle,
      width: 'clamp(300px, 50vw, 580px)',
    }}>
      <div style={{
        fontSize: 8,
        letterSpacing: '0.22em',
        color: C.signalOrange,
        marginBottom: 8,
      }}>
        TOUR COMPLETE — TRY THIS NEXT
      </div>
      <div style={{
        fontSize: 13,
        fontWeight: 700,
        color: C.lunarWhite,
        letterSpacing: '0.06em',
        marginBottom: 16,
      }}>
        THREE THINGS WORTH EXPLORING
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
        {SUGGESTIONS.map((s, i) => (
          <div key={i} style={{
            display: 'flex',
            gap: 14,
            padding: '10px 14px',
            background: 'rgba(255, 79, 0, 0.05)',
            border: '1px solid rgba(255, 79, 0, 0.15)',
            borderRadius: 3,
          }}>
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              color: C.signalOrange,
              letterSpacing: '0.12em',
              minWidth: 160,
              paddingTop: 1,
            }}>
              {s.label}
            </div>
            <div style={{
              fontSize: 11,
              color: C.photogray,
              lineHeight: 1.7,
              letterSpacing: '0.02em',
            }}>
              {s.body}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Btn primary onClick={onDone}>START EXPLORING →</Btn>
      </div>
    </div>
  );
}

export default function GuidedTour({ onSetLayers, onFlyTo, onDone }) {
  const [step, setStep] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => { applyStep(0); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function applyStep(i) {
    const s = TOUR_STEPS[i];
    onSetLayers({ ...BASE_VISIBILITY, ...s.layers });
    onFlyTo(s.flyTo);
  }

  function next() {
    if (step < TOUR_STEPS.length - 1) {
      const n = step + 1;
      setStep(n);
      applyStep(n);
    } else {
      setShowSuggestions(true);
    }
  }

  function back() {
    if (step > 0) {
      const p = step - 1;
      setStep(p);
      applyStep(p);
    }
  }

  function finish() {
    onDone();
  }

  if (showSuggestions) {
    return <SuggestionCard onDone={finish} />;
  }

  const currentStep = TOUR_STEPS[step];

  return (
    <>
      {currentStep.callout && (
        <Callout
          direction={currentStep.callout.direction}
          label={currentStep.callout.label}
          bottom={currentStep.callout.bottom}
          right={currentStep.callout.right}
        />
      )}
      <StepCard
        step={currentStep}
        stepIndex={step}
        total={TOUR_STEPS.length}
        onNext={next}
        onBack={back}
        onSkip={finish}
      />
    </>
  );
}
