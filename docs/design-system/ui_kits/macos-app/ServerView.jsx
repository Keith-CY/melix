// ServerView.jsx — Server tab: session list + detail panel
// Depends on: Tokens.js

const T3 = window.MelixTokens;

const SERVER_SESSIONS = [
  { id: 1, model: 'mlx-community/Llama-3.2-3B-Instruct-4bit', alias: 'Melix Text Turbo', state: 'running', port: 11434, ctx: '8192', accel: 'speculative_decode' },
  { id: 2, model: 'mlx-community/Qwen2.5-7B-Instruct-4bit', alias: 'Qwen 7B', state: 'paused', port: 11435, ctx: '32768', accel: 'baseline' },
  { id: 3, model: 'mlx-community/whisper-large-v3-mlx', alias: 'Whisper Large', state: 'stopped', port: 11436, ctx: '—', accel: 'baseline' },
];

const STATE_COLORS = {
  running: T3.bgAssistant,
  paused: T3.bgReasoning,
  stopped: 'rgba(0,0,0,0.04)',
  error: T3.bgError,
};
const STATE_TEXT = {
  running: '#14A05A',
  paused: '#D97706',
  stopped: T3.fgQuaternary,
  error: '#DC2626',
};

function ServerSessionRow({ session, selected, onSelect }) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '10px 12px', borderRadius: T3.radiusLg, cursor: 'pointer', marginBottom: 4,
        background: selected ? T3.bgSelected : STATE_COLORS[session.state],
        transition: 'background 0.1s',
      }}
    >
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: T3.fgPrimary }}>{session.alias}</div>
        <div style={{ fontSize: 10, color: T3.fgTertiary, fontFamily: T3.fontMono, marginTop: 2 }}>{session.model}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: STATE_TEXT[session.state] }}>{session.state}</div>
        <div style={{ fontSize: 9, color: T3.fgQuaternary, fontFamily: T3.fontMono }}>:{session.port}</div>
      </div>
    </div>
  );
}

function ServerDetail({ session }) {
  if (!session) return (
    <div style={{ padding: 20, color: T3.fgTertiary, fontSize: 12 }}>Select a session to inspect.</div>
  );

  const actionBtn = (label, primary) => (
    <button key={label} style={primary ? serverBtnPrimary : serverBtnBordered}>{label}</button>
  );

  const actions = session.state === 'running'
    ? [['Pause', false], ['Stop', false], ['Wake', false]]
    : session.state === 'paused'
    ? [['Resume', true], ['Stop', false]]
    : [['Start', true]];

  return (
    <div style={{ padding: 16, overflowY: 'auto', height: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Header */}
      <div>
        <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', color: T3.fgPrimary }}>{session.alias}</div>
        <div style={{ fontSize: 11, color: T3.fgTertiary, fontFamily: T3.fontMono, marginTop: 3 }}>{session.model}</div>
        <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
          {actions.map(([l, p]) => actionBtn(l, p))}
        </div>
      </div>
      {/* Info grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {[
          ['Port', `:${session.port}`],
          ['Context', `${session.ctx} tokens`],
          ['Acceleration', session.accel],
          ['Memory Policy', 'pinned'],
          ['Cache Mode', 'tiered'],
          ['State', session.state],
        ].map(([k, v]) => (
          <div key={k} style={{ background: T3.bgCard, borderRadius: T3.radiusLg, padding: '8px 10px' }}>
            <div style={{ fontSize: 9, color: T3.fgQuaternary, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{k}</div>
            <div style={{ fontSize: 12, fontFamily: T3.fontMono, color: T3.fgPrimary }}>{v}</div>
          </div>
        ))}
      </div>
      {/* Base URL */}
      <div style={{ background: T3.bgCard, borderRadius: T3.radiusLg, padding: '8px 10px' }}>
        <div style={{ fontSize: 9, color: T3.fgQuaternary, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>Base URL</div>
        <div style={{ fontSize: 11, fontFamily: T3.fontMono, color: T3.accent }}>http://localhost:{session.port}/v1</div>
      </div>
    </div>
  );
}

function ServerView() {
  const [selected, setSelected] = React.useState(1);
  const session = SERVER_SESSIONS.find(s => s.id === selected);

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Session list */}
      <div style={{ width: 280, flexShrink: 0, background: T3.bgElevated, padding: 14, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: T3.fgPrimary }}>Server Sessions</span>
          <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: T3.fgSecondary, fontSize: 16 }}>+</button>
        </div>
        {SERVER_SESSIONS.map(s => (
          <ServerSessionRow key={s.id} session={s} selected={selected === s.id} onSelect={() => setSelected(s.id)} />
        ))}
      </div>
      {/* Detail */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <ServerDetail session={session} />
      </div>
    </div>
  );
}

const serverBtnPrimary = {
  background: T3.fgPrimary, color: T3.fgInverse, border: 'none',
  borderRadius: T3.radiusMd, padding: '5px 14px', fontSize: 11, fontWeight: 600,
  fontFamily: T3.fontSans, cursor: 'pointer',
};
const serverBtnBordered = {
  background: 'transparent', color: T3.fgSecondary,
  border: `1px solid ${T3.neutral300}`, borderRadius: T3.radiusMd,
  padding: '5px 14px', fontSize: 11, fontWeight: 500,
  fontFamily: T3.fontSans, cursor: 'pointer',
};

Object.assign(window, { ServerView });
