// Shell.jsx — macOS Operator App shell: window chrome, tab strip, sidebar rail
// Depends on: Tokens.js

const { useState, useEffect } = React;
const T = window.MelixTokens;

const shellStyles = {
  root: {
    width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
    background: T.bgBase, fontFamily: T.fontSans, overflow: 'hidden',
  },
  titlebar: {
    height: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 14px', background: T.bgBase, userSelect: 'none',
    WebkitAppRegion: 'drag', flexShrink: 0,
    borderBottom: `1px solid rgba(0,0,0,0.06)`,
  },
  trafficLights: {
    display: 'flex', gap: 6, alignItems: 'center',
  },
  dot: (color) => ({
    width: 12, height: 12, borderRadius: '50%', background: color,
  }),
  tabStrip: {
    display: 'flex', gap: 3, alignItems: 'center',
    background: T.bgSurface, borderRadius: T.radiusFull,
    padding: 3, boxShadow: `inset 0 0 0 1px rgba(0,0,0,0.06)`,
  },
  tab: (active) => ({
    padding: '4px 12px', borderRadius: T.radiusFull, border: 'none', cursor: 'pointer',
    fontSize: 11, fontWeight: active ? 600 : 500, fontFamily: T.fontSans,
    color: active ? T.fgPrimary : T.fgSecondary,
    background: active ? T.accentWeak : 'transparent',
    transition: 'background 0.12s, color 0.12s',
  }),
  cmdBtn: {
    width: 28, height: 28, borderRadius: T.radiusMd, border: 'none',
    background: 'transparent', cursor: 'pointer', display: 'flex',
    alignItems: 'center', justifyContent: 'center', color: T.fgSecondary,
    fontSize: 16,
  },
  body: {
    flex: 1, display: 'flex', overflow: 'hidden',
  },
  sidebar: (visible) => ({
    width: visible ? 220 : 28, minWidth: visible ? 220 : 28, maxWidth: visible ? 220 : 28,
    background: T.bgElevated, display: 'flex', flexDirection: 'column',
    overflow: 'hidden', transition: 'width 0.18s ease, min-width 0.18s, max-width 0.18s',
    flexShrink: 0,
  }),
  inspector: (visible) => ({
    width: visible ? 232 : 28, minWidth: visible ? 232 : 28, maxWidth: visible ? 232 : 28,
    background: T.bgElevated, display: 'flex', flexDirection: 'column',
    overflow: 'hidden', transition: 'width 0.18s ease, min-width 0.18s, max-width 0.18s',
    flexShrink: 0,
  }),
  rail: {
    width: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
    flex: 1, cursor: 'pointer', background: `rgba(0,0,0,0.02)`, color: T.fgTertiary,
    fontSize: 13,
  },
  workspace: {
    flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column',
  },
};

function TrafficLights() {
  return (
    <div style={shellStyles.trafficLights}>
      <div style={shellStyles.dot('#FF5F57')} />
      <div style={shellStyles.dot('#FFBD2E')} />
      <div style={shellStyles.dot('#28C840')} />
    </div>
  );
}

const TABS = ['Chat', 'Image', 'Server', 'Tools', 'API'];

function TabStrip({ active, onSelect }) {
  return (
    <div style={shellStyles.tabStrip}>
      {TABS.map(t => (
        <button key={t} style={shellStyles.tab(active === t)} onClick={() => onSelect(t)}>
          {t}
        </button>
      ))}
    </div>
  );
}

function PaneToggleBtn({ onClick, title }) {
  return (
    <button style={shellStyles.cmdBtn} onClick={onClick} title={title}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>
      </svg>
    </button>
  );
}

function AppShell({ activeTab, onTabSelect, showSidebar, showInspector,
                    onToggleSidebar, onToggleInspector, sidebarContent,
                    inspectorContent, children }) {
  return (
    <div style={shellStyles.root}>
      {/* Title bar */}
      <div style={shellStyles.titlebar}>
        <TrafficLights />
        <TabStrip active={activeTab} onSelect={onTabSelect} />
        <div style={{ display: 'flex', gap: 4 }}>
          <PaneToggleBtn onClick={onToggleSidebar} title="Toggle Sidebar" />
          <PaneToggleBtn onClick={onToggleInspector} title="Toggle Inspector" />
          <button style={{ ...shellStyles.cmdBtn, fontSize: 14 }} title="Command Center (⌘K)">⌘</button>
        </div>
      </div>
      {/* Body */}
      <div style={shellStyles.body}>
        {/* Sidebar */}
        <div style={shellStyles.sidebar(showSidebar)}>
          {showSidebar
            ? <div style={{ flex: 1, overflow: 'hidden' }}>{sidebarContent}</div>
            : <div style={shellStyles.rail} onClick={onToggleSidebar} title="Show Sidebar">‹</div>
          }
        </div>
        {/* Main workspace */}
        <div style={shellStyles.workspace}>{children}</div>
        {/* Inspector */}
        <div style={shellStyles.inspector(showInspector)}>
          {showInspector
            ? <div style={{ flex: 1, overflow: 'hidden' }}>{inspectorContent}</div>
            : <div style={shellStyles.rail} onClick={onToggleInspector} title="Show Inspector">›</div>
          }
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AppShell, TabStrip, TABS });
