// ToolsView.jsx — Tools tab: model operations, adapter registry, bench report
// Depends on: Tokens.js

const T4 = window.MelixTokens;

const ADAPTERS = [
  { name: 'lora-llama-3b-v1', source: 'mlx-community/Llama-3.2-3B-Instruct-4bit', dataset: 'data/train.jsonl', status: 'published', steps: 512, duration: '4m 18s' },
  { name: 'lora-llama-3b-v2', source: 'mlx-community/Llama-3.2-3B-Instruct-4bit', dataset: 'data/train-v2.jsonl', status: 'active', steps: 1024, duration: '8m 52s' },
];

const BENCH = [
  { name: 'prompt_tps', value: '1,847 t/s' },
  { name: 'gen_tps', value: '42.3 t/s' },
  { name: 'p50_latency', value: '42ms' },
  { name: 'p95_latency', value: '88ms' },
  { name: 'ttft', value: '31ms' },
  { name: 'peak_memory', value: '3.8 GB' },
];

function AdapterRow({ adapter }) {
  const statusColor = adapter.status === 'published' ? '#14A05A' : adapter.status === 'active' ? T4.accent : T4.fgQuaternary;
  return (
    <div style={{ padding: '10px 0', borderBottom: 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: T4.fgPrimary, fontFamily: T4.fontMono }}>{adapter.name}</div>
        <div style={{ fontSize: 10, color: T4.fgTertiary, marginTop: 2 }}>{adapter.source}</div>
        <div style={{ fontSize: 10, color: T4.fgTertiary, fontFamily: T4.fontMono, marginTop: 1 }}>{adapter.dataset} · {adapter.steps} steps · {adapter.duration}</div>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0, marginLeft: 12 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: statusColor }}>{adapter.status}</span>
        <button style={toolsBtnBordered}>Activate</button>
        <button style={toolsBtnBordered}>Publish</button>
      </div>
    </div>
  );
}

function ToolsView() {
  return (
    <div style={{ padding: 20, overflowY: 'auto', height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Primary Model */}
      <ToolsGroupBox title="Primary Model">
        <div style={{ fontSize: 13, fontWeight: 600, color: T4.fgPrimary }}>mlx-community/Llama-3.2-3B-Instruct-4bit</div>
        <div style={{ fontSize: 11, color: T4.fgTertiary, marginTop: 2 }}>Melix Text Turbo · loaded · 8192 ctx</div>
        <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['Inspect', 'Doctor', 'Bench', 'Convert', 'Quantize'].map(l => (
            <button key={l} style={toolsBtnBordered}>{l}</button>
          ))}
          <button style={toolsBtnAccent}>Train LoRA</button>
        </div>
      </ToolsGroupBox>

      {/* Bench Report */}
      <ToolsGroupBox title="Bench Report">
        <div style={{ fontSize: 10, fontFamily: T4.fontMono, color: T4.fgTertiary, marginBottom: 10 }}>~/.melix/bench/2026-04-19.md · Llama-3.2-3B · speculative_decode</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 24px' }}>
          {BENCH.map(m => (
            <div key={m.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '4px 0' }}>
              <span style={{ fontSize: 11, color: T4.fgSecondary }}>{m.name}</span>
              <span style={{ fontSize: 12, fontFamily: T4.fontMono, color: T4.fgPrimary, fontVariantNumeric: 'tabular-nums' }}>{m.value}</span>
            </div>
          ))}
        </div>
      </ToolsGroupBox>

      {/* Adapter Registry */}
      <ToolsGroupBox title="Adapter Registry">
        {ADAPTERS.map(a => <AdapterRow key={a.name} adapter={a} />)}
      </ToolsGroupBox>

      {/* Training History */}
      <ToolsGroupBox title="Training History">
        {ADAPTERS.map(a => (
          <div key={a.name} style={{ padding: '6px 0', marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: T4.fgPrimary, fontFamily: T4.fontMono }}>{a.name}</span>
              <span style={{ fontSize: 10, color: T4.fgTertiary }}>{a.duration}</span>
            </div>
            <div style={{ fontSize: 10, color: T4.fgTertiary, marginTop: 1 }}>{a.source} · {a.dataset}</div>
          </div>
        ))}
      </ToolsGroupBox>
    </div>
  );
}

function ToolsGroupBox({ title, children }) {
  return (
    <div style={{ background: T4.bgCard, borderRadius: T4.radiusXl, padding: '14px 16px' }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: T4.fgTertiary, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>{title}</div>
      {children}
    </div>
  );
}

const toolsBtnBordered = {
  background: 'transparent', color: T4.fgSecondary,
  border: `1px solid ${T4.neutral300}`, borderRadius: T4.radiusMd,
  padding: '4px 10px', fontSize: 11, fontWeight: 500,
  fontFamily: T4.fontSans, cursor: 'pointer',
};
const toolsBtnAccent = {
  background: T4.accent, color: '#fff', border: 'none',
  borderRadius: T4.radiusMd, padding: '4px 12px', fontSize: 11, fontWeight: 600,
  fontFamily: T4.fontSans, cursor: 'pointer',
};

Object.assign(window, { ToolsView });
