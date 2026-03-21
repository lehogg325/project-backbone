export const MONO_FONT = '"IBM Plex Mono", "Courier Prime", "Courier New", monospace';

// ── Ansible palette tokens ─────────────────────────────────────────────────────
export const C = {
  signalOrange:    '#FF4F00',
  chromeYellow:    '#FFA300',
  celestialBlue:   '#4997D0',
  lunarWhite:      '#F5F2EC',
  newsprint:       '#EDE8DC',
  deepSpace:       '#0D0D14',
  teletypeInk:     '#1A1A1A',
  photogray:       '#8C8C8C',
  vacuumAmber:     '#C97B2F',
  oxidizedCopper:  '#5F8A6E',
  blueprintIndigo: '#263D6B',
};

export const panelStyle = {
  background: 'rgba(13, 13, 20, 0.92)',
  border: `1px solid rgba(255, 79, 0, 0.28)`,
  borderRadius: 4,
  padding: '14px 18px',
  fontFamily: MONO_FONT,
  fontSize: 12,
  color: C.newsprint,
  minWidth: 220,
  backdropFilter: 'blur(8px)',
  boxShadow: '0 0 28px rgba(255, 79, 0, 0.07), inset 0 0 0 1px rgba(255, 79, 0, 0.05)',
  userSelect: 'none',
};
