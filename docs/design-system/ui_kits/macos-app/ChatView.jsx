// ChatView.jsx — Chat tab: session sidebar, transcript workspace, inspector
// Depends on: Tokens.js, Shell.jsx

const T2 = window.MelixTokens;

const SESSIONS = [
  { id: 1, title: 'Llama 3.2 3B eval', branch: 'main', summary: 'Compare base vs LoRA adapter outputs', time: '2m ago' },
  { id: 2, title: 'LoRA training run', branch: 'lora-v2', summary: 'Train on custom dataset, 512 steps', time: '18m ago' },
  { id: 3, title: 'Benchmark matrix', branch: 'main', summary: 'p50/p95 across 4 model configs', time: '1h ago' },
];

const TRANSCRIPT = [
  { id: 1, kind: 'user', role: 'user', body: 'Run a bench matrix across the loaded models and export the results.' },
  { id: 2, kind: 'assistant', role: 'assistant', body: 'Starting bench matrix. I\'ll run p50 and p95 latency probes across 4 configurations and export a markdown artifact.' },
  { id: 3, kind: 'reasoning', role: 'reasoning', body: 'Selecting acceleration profiles and memory budgets for each model variant…' },
  { id: 4, kind: 'tool', role: 'tool', body: '{"op":"bench_matrix","configs":4,"probe":"latency","export":"markdown"}' },
  { id: 5, kind: 'assistant', role: 'assistant', body: 'Bench complete. p50: 42ms · p95: 88ms · 4 configs · report saved to ~/.melix/bench/2026-04-19.md' },
];

const BUBBLE_BG = {
  user: T2.bgUser, assistant: T2.bgAssistant,
  reasoning: T2.bgReasoning, tool: T2.bgTool, error: T2.bgError,
};

function ChatSessionRow({ session, selected, onSelect }) {
  return (
    <div
      onClick={onSelect}
      style={{
        padding: '8px 10px', borderRadius: T2.radiusLg, cursor: 'pointer', marginBottom: 4,
        background: selected ? T2.bgSelected : 'rgba(0,0,0,0.03)',
        transition: 'background 0.1s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: T2.fgPrimary }}>{session.title}</span>
        <span style={{ fontSize: 9, color: T2.fgQuaternary, fontFamily: T2.fontMono }}>{session.time}</span>
      </div>
      <div style={{ marginTop: 2, display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{
          fontSize: 9, padding: '1px 6px', borderRadius: T2.radiusFull,
          background: 'rgba(0,0,0,0.06)', color: T2.fgTertiary, fontFamily: T2.fontMono,
        }}>{session.branch}</span>
        <span style={{ fontSize: 10, color: T2.fgTertiary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{session.summary}</span>
      </div>
    </div>
  );
}

function ChatSidebar({ selected, onSelect }) {
  return (
    <div style={{ padding: 14, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: T2.fgPrimary }}>Chat Sessions</span>
        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: T2.fgSecondary, fontSize: 16, lineHeight: 1 }}>+</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {SESSIONS.map(s => (
          <ChatSessionRow key={s.id} session={s} selected={selected === s.id} onSelect={() => onSelect(s.id)} />
        ))}
      </div>
    </div>
  );
}

function ChatBubble({ entry }) {
  const isMono = entry.kind === 'tool';
  return (
    <div style={{
      background: BUBBLE_BG[entry.kind] || T2.bgCard,
      borderRadius: T2.radiusXl, padding: '10px 12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: T2.fgTertiary, fontFamily: T2.fontMono }}>{entry.role}</span>
      </div>
      <div style={{
        fontSize: isMono ? 11 : 12, lineHeight: 1.55, color: T2.fgPrimary,
        fontFamily: isMono ? T2.fontMono : T2.fontSans,
        userSelect: 'text',
      }}>{entry.body}</div>
    </div>
  );
}

function ChatWorkspace({ sessionId }) {
  const [composer, setComposer] = React.useState('');
  const session = SESSIONS.find(s => s.id === sessionId) || SESSIONS[0];

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ marginBottom: 12, flexShrink: 0 }}>
        <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em', color: T2.fgPrimary }}>{session.title}</div>
        <div style={{ marginTop: 4, display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, padding: '2px 7px', borderRadius: T2.radiusFull, background: 'rgba(0,0,0,0.06)', color: T2.fgTertiary, fontFamily: T2.fontMono }}>{session.branch}</span>
          <span style={{ fontSize: 9, padding: '2px 7px', borderRadius: T2.radiusFull, background: 'rgba(0,0,0,0.06)', color: T2.fgTertiary, fontFamily: T2.fontMono }}>session-1 · running</span>
        </div>
      </div>
      {/* Transcript */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingRight: 4 }}>
        {TRANSCRIPT.map(e => <ChatBubble key={e.id} entry={e} />)}
      </div>
      {/* Composer */}
      <div style={{ marginTop: 12, flexShrink: 0 }}>
        <textarea
          value={composer}
          onChange={e => setComposer(e.target.value)}
          placeholder="Enter a prompt…"
          style={{
            width: '100%', height: 72, resize: 'none', padding: '8px 10px',
            fontFamily: T2.fontMono, fontSize: 12, color: T2.fgPrimary,
            background: 'rgba(0,0,0,0.03)', borderRadius: T2.radiusLg,
            border: '1px solid rgba(0,0,0,0.07)', outline: 'none', lineHeight: 1.55,
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
          <span style={{ fontSize: 10, color: T2.fgTertiary, fontFamily: T2.fontMono }}>session-1 · running · 1024 tokens</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={{ ...chatBtnBordered }}>Clear</button>
            <button style={{ ...chatBtnPrimary, opacity: composer.trim() ? 1 : 0.4 }} disabled={!composer.trim()}>Send ⌘↵</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatInspector() {
  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', height: '100%' }}>
      <GroupBox title="Session">
        <div style={{ fontSize: 12, fontWeight: 600, color: T2.fgPrimary, marginBottom: 4 }}>running</div>
        <div style={{ fontSize: 10, fontFamily: T2.fontMono, color: T2.fgTertiary }}>http://localhost:11434</div>
      </GroupBox>
      <GroupBox title="Analysis Routes">
        {[
          { label: 'Chat Completion', ready: true, detail: 'v1/chat/completions' },
          { label: 'LoRA Training', ready: true, detail: 'lora adapter pipeline' },
          { label: 'Bench Matrix', ready: true, detail: 'multi-config latency probe' },
          { label: 'Vision', ready: false, detail: 'no vision model loaded' },
        ].map(c => (
          <div key={c.label} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8 }}>
            <span style={{ color: c.ready ? '#14A05A' : T2.fgQuaternary, fontSize: 12, marginTop: 1 }}>{c.ready ? '●' : '○'}</span>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: T2.fgPrimary }}>{c.label}</div>
              <div style={{ fontSize: 10, color: T2.fgTertiary }}>{c.detail}</div>
            </div>
          </div>
        ))}
      </GroupBox>
      <GroupBox title="Runtime">
        <div style={{ fontSize: 10, fontFamily: T2.fontMono, color: T2.fgTertiary }}>req_8f2a9c · 1024 tokens · 42ms p50</div>
      </GroupBox>
    </div>
  );
}

function GroupBox({ title, children }) {
  return (
    <div style={{ background: T2.bgCard, borderRadius: T2.radiusXl, padding: 12 }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: T2.fgTertiary, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

const chatBtnPrimary = {
  background: T2.fgPrimary, color: T2.fgInverse, border: 'none',
  borderRadius: T2.radiusMd, padding: '5px 12px', fontSize: 11, fontWeight: 600,
  fontFamily: T2.fontSans, cursor: 'pointer',
};
const chatBtnBordered = {
  background: 'transparent', color: T2.fgSecondary,
  border: `1px solid ${T2.neutral300}`, borderRadius: T2.radiusMd,
  padding: '5px 12px', fontSize: 11, fontWeight: 500,
  fontFamily: T2.fontSans, cursor: 'pointer',
};

Object.assign(window, { ChatSidebar, ChatWorkspace, ChatInspector, GroupBox });
