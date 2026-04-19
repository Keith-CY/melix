// Melix Design System — Shared Tokens
// Translates colors_and_type.css vars into JS constants for React components

window.MelixTokens = {
  accent: '#0F766E',
  accentWeak: 'rgba(15,118,110,0.12)',
  accentMedium: 'rgba(15,118,110,0.32)',
  accentFaint: 'rgba(15,118,110,0.06)',

  fgPrimary: '#0A0A0A',
  fgSecondary: '#3A3A3A',
  fgTertiary: '#6B6B6B',
  fgQuaternary: '#9A9A9A',
  fgInverse: '#FDFDFD',

  bgBase: '#FAFAFA',
  bgSurface: '#FFFFFF',
  bgElevated: '#F5F5F5',
  bgSunken: '#F0F0F0',

  neutral200: '#E8E8E8',
  neutral300: '#D4D4D4',

  fontSans: 'system-ui, "SF Pro Display", "Inter", -apple-system, sans-serif',
  fontMono: 'ui-monospace, "SF Mono", "JetBrains Mono", monospace',

  radiusSm: '6px',
  radiusMd: '8px',
  radiusLg: '10px',
  radiusXl: '12px',
  radiusFull: '9999px',

  // Chat bubble tints
  bgUser:      'rgba(0,100,220,0.10)',
  bgAssistant: 'rgba(20,160,80,0.09)',
  bgReasoning: 'rgba(220,110,20,0.09)',
  bgTool:      'rgba(120,60,200,0.09)',
  bgError:     'rgba(210,40,40,0.09)',
  bgSelected:  'rgba(15,118,110,0.12)',
  bgCard:      'rgba(0,0,0,0.04)',
};

// Export components to window
Object.assign(window, { MelixTokens: window.MelixTokens });
