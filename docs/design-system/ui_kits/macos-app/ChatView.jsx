// ChatView.jsx — Chat tab: session sidebar, transcript workspace, inspector
// Depends on: Tokens.js, Shell.jsx

const T2 = window.MelixTokens;

const SESSIONS = [
  { id: 1, title: 'Chat 1', branch: 'gemma-4', summary: 'Review Thinking and Composer behavior', time: '2m ago' },
  { id: 2, title: 'LoRA training run', branch: 'lora-v2', summary: 'Train on custom dataset, 512 steps', time: '18m ago' },
  { id: 3, title: 'Benchmark matrix', branch: 'main', summary: 'p50/p95 across 4 model configs', time: '1h ago' },
];

const TRANSCRIPT = [
  { id: 1, kind: 'user', role: 'user', body: 'Run a bench matrix across the loaded models and export the results.' },
  { id: 2, kind: 'assistant', role: 'assistant', body: 'Starting bench matrix. I\'ll run p50 and p95 latency probes across 4 configurations and export a markdown artifact.' },
  { id: 3, kind: 'reasoning', role: 'reasoning', body: 'Selecting acceleration profiles and memory budgets for each model variant…' },
  { id: 4, kind: 'tool', role: 'tool', body: '{"op":"bench_matrix","configs":4,"probe":"latency","export":"markdown"}' },
  {
    id: 5,
    kind: 'assistant',
    role: 'assistant',
    body: 'Bench complete. p50: 42ms · p95: 88ms · 4 configs · report saved to ~/.melix/bench/2026-04-19.md',
    meta: '12 prompt · 24 completion',
  },
];

const COMPOSER_FIXTURES = {
  empty: '',
  draft: 'Compare the CLI and API Endpoint response contracts.',
  multiline: 'Check the active Provider.\nConfirm the public model identity.\nReview Thinking output.\nKeep this draft editable.\nReturn a concise conclusion.',
  streaming: 'Next draft: compare the CLI and API Endpoint after this response.',
  offline: 'Send this draft after the Provider is available again.',
};

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
      {entry.meta && (
        <div style={{ marginTop: 6, fontSize: 9, color: T2.fgQuaternary, fontFamily: T2.fontMono }}>
          {entry.meta}
        </div>
      )}
    </div>
  );
}

function ChatRouteIdentity() {
  const canonicalId = 'mlx-community/gemma-4-31b-it-4bit';
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  return (
    <div style={{ position: 'relative', minWidth: 0, marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
      <button
        type="button"
        aria-label="Primary Provider"
        title="Primary Provider · Running"
        style={{
          height: 28, maxWidth: 116, display: 'flex', alignItems: 'center', gap: 6,
          border: '1px solid rgba(0,0,0,0.08)', borderRadius: 7, padding: '0 8px',
          background: 'rgba(0,0,0,0.025)', color: T2.fgPrimary, cursor: 'pointer',
          fontFamily: T2.fontSans, fontSize: 10, fontWeight: 600,
        }}
      >
        <ChatIcon name="server" size={14} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Primary</span>
        <span aria-hidden="true" style={{ color: T2.fgQuaternary }}>⌄</span>
      </button>
      <button
        type="button"
        aria-label={`Model Gemma 4 31B IT, quantization 4-bit, canonical ID ${canonicalId}`}
        aria-haspopup="dialog"
        aria-expanded={detailsOpen}
        title={canonicalId}
        onClick={() => setDetailsOpen(value => !value)}
        style={{
          height: 28, minWidth: 0, maxWidth: 190, display: 'flex', alignItems: 'center', gap: 6,
          border: '1px solid rgba(0,0,0,0.08)', borderRadius: 7, padding: '0 8px',
          background: 'rgba(0,0,0,0.025)', color: T2.fgPrimary, cursor: 'pointer',
          fontFamily: T2.fontSans, fontSize: 10,
        }}
      >
        <span style={{ flex: '0 0 auto', color: T2.accent }}><ChatIcon name="model" size={14} /></span>
        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Gemma 4 31B IT</span>
        <span style={{
          flex: '0 0 auto', padding: '2px 4px', borderRadius: 4,
          color: T2.accent, background: T2.accentWeak,
          fontFamily: T2.fontMono, fontSize: 8,
        }}>4-bit</span>
      </button>
      {detailsOpen && (
        <div
          role="dialog"
          aria-label="Model identity details"
          style={{
            position: 'absolute', zIndex: 20, top: 36, right: 0, width: 308,
            padding: 12, border: '1px solid rgba(0,0,0,0.10)', borderRadius: 10,
            background: T2.bgSurface, boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: T2.fgPrimary }}>Gemma 4 31B IT</div>
          <div style={{ marginTop: 3, fontSize: 9, color: T2.fgTertiary }}>Primary Provider · Running</div>
          <div style={{ marginTop: 10, display: 'flex', alignItems: 'flex-start', gap: 7, padding: 8, borderRadius: 7, background: T2.bgElevated }}>
            <code style={{ minWidth: 0, flex: 1, overflowWrap: 'anywhere', fontSize: 9, lineHeight: 1.4, color: T2.fgSecondary }}>{canonicalId}</code>
            <button
              type="button"
              aria-label="Copy Model ID"
              title="Copy Model ID"
              onClick={() => navigator.clipboard?.writeText(canonicalId)}
              style={{ width: 24, height: 24, border: 0, borderRadius: 5, color: T2.accent, background: T2.bgSurface, cursor: 'pointer' }}
            >
              <ChatIcon name="copy" size={13} />
            </button>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 9, color: T2.fgTertiary, fontSize: 9 }}>
            <span>Canonical ID</span><span>Local trust</span><span>Quantization 4-bit</span>
          </div>
        </div>
      )}
    </div>
  );
}

function ChatWorkspace({ sessionId }) {
  const requestedState = new URLSearchParams(window.location.search).get('composer');
  const fixtureState = Object.hasOwn(COMPOSER_FIXTURES, requestedState) ? requestedState : 'empty';
  const [composer, setComposer] = React.useState(COMPOSER_FIXTURES[fixtureState]);
  const [composerState, setComposerState] = React.useState(
    fixtureState === 'streaming' || fixtureState === 'offline' ? fixtureState : 'ready'
  );
  const generationTimer = React.useRef(null);
  const session = SESSIONS.find(s => s.id === sessionId) || SESSIONS[0];

  React.useEffect(() => () => {
    if (generationTimer.current) window.clearTimeout(generationTimer.current);
  }, []);

  const submitComposer = () => {
    if (!composer.trim() || composerState !== 'ready') return;
    setComposer('');
    setComposerState('streaming');
    if (generationTimer.current) window.clearTimeout(generationTimer.current);
    generationTimer.current = window.setTimeout(() => {
      setComposerState('ready');
      generationTimer.current = null;
    }, 1800);
  };

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ marginBottom: 12, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ minWidth: 0, fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em', color: T2.fgPrimary }}>{session.title}</div>
        <ChatRouteIdentity />
      </div>
      {/* Transcript */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingRight: 4 }}>
        {TRANSCRIPT.map(e => <ChatBubble key={e.id} entry={e} />)}
      </div>
      {/* Composer */}
      <ChatComposer
        value={composer}
        state={composerState}
        onChange={setComposer}
        onSubmit={submitComposer}
        onStartProvider={() => setComposerState('ready')}
      />
    </div>
  );
}

function ChatComposer({ value, state, onChange, onSubmit, onStartProvider }) {
  const [thinkingEnabled, setThinkingEnabled] = React.useState(true);
  const [isFocused, setIsFocused] = React.useState(false);
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [isAtLineCap, setIsAtLineCap] = React.useState(false);
  const textareaRef = React.useRef(null);
  const isComposing = React.useRef(false);
  const compositionGuardUntil = React.useRef(0);
  const isStreaming = state === 'streaming';
  const needsRepair = state === 'offline';
  const isBlocked = isStreaming || needsRepair;
  const hasDraft = Boolean(value.trim());
  const statusText = isStreaming
    ? 'Generating · draft saved'
    : (!hasDraft && isFocused ? '↵ Send · ⌘↵ New line' : '');

  const resizeEditor = React.useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const collapsedMaximum = 99;
    textarea.style.height = '40px';
    const contentHeight = textarea.scrollHeight;
    const explicitLineCount = value ? value.split('\n').length : 0;
    setIsAtLineCap(explicitLineCount >= 5 || contentHeight > 83);
    textarea.style.height = `${Math.min(isExpanded ? 220 : collapsedMaximum, Math.max(40, contentHeight))}px`;
  }, [isExpanded, value]);

  React.useEffect(resizeEditor, [resizeEditor, value]);

  const startProvider = () => {
    onStartProvider();
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleKeyDown = event => {
    if (event.key !== 'Enter') return;
    if (isComposing.current || event.nativeEvent.isComposing || performance.now() < compositionGuardUntil.current) return;

    const commandReturn = event.metaKey && !event.shiftKey && !event.altKey && !event.ctrlKey;
    const plainReturn = !event.metaKey && !event.shiftKey && !event.altKey && !event.ctrlKey;
    if (commandReturn) {
      event.preventDefault();
      const textarea = event.currentTarget;
      const selectionStart = textarea.selectionStart;
      const selectionEnd = textarea.selectionEnd;
      onChange(`${value.slice(0, selectionStart)}\n${value.slice(selectionEnd)}`);
      window.requestAnimationFrame(() => {
        textarea.selectionStart = selectionStart + 1;
        textarea.selectionEnd = selectionStart + 1;
      });
    } else if (plainReturn) {
      event.preventDefault();
      if (!event.repeat) onSubmit();
    }
  };

  return (
    <form
      aria-label="Chat Composer"
      onSubmit={event => { event.preventDefault(); onSubmit(); }}
      style={{
        marginTop: 12, flexShrink: 0, overflow: 'hidden',
        background: 'rgba(255,255,255,0.96)',
        border: `1px solid ${isFocused ? T2.accentMedium : 'rgba(0,0,0,0.10)'}`,
        borderRadius: T2.radiusComposer,
        boxShadow: isFocused ? `0 0 0 3px ${T2.accentWeak}` : 'none',
      }}
    >
      {needsRepair && (
        <div
          role="group"
          aria-label="Provider stopped. Draft preserved."
          style={{
            minHeight: 34, display: 'flex', alignItems: 'center', gap: 7,
            padding: '5px 8px 5px 11px', color: T2.warning,
            background: T2.warningWeak, fontSize: 10,
          }}
        >
          <ChatIcon name="power" size={14} />
          <span style={{ color: T2.warningText }}>Provider stopped</span>
          <button type="button" onClick={startProvider} style={{ ...chatRepairButton }}>Start</button>
        </div>
      )}

      <div style={{ position: 'relative', padding: '12px 14px 3px' }}>
        <label htmlFor="melix-chat-composer" style={chatVisuallyHidden}>Message Melix</label>
        <textarea
          id="melix-chat-composer"
          ref={textareaRef}
          value={value}
          rows={1}
          aria-describedby="melix-composer-keyboard-help melix-composer-live-status"
          placeholder="Message Melix…"
          onChange={event => onChange(event.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onCompositionStart={() => { isComposing.current = true; }}
          onCompositionEnd={() => {
            isComposing.current = false;
            compositionGuardUntil.current = performance.now() + 50;
          }}
          onKeyDown={handleKeyDown}
          style={{
            width: '100%', minHeight: 40, maxHeight: isExpanded ? 220 : 99,
            display: 'block', resize: 'none', overflowY: 'auto', padding: '1px 0 2px',
            border: 0, outline: 0, color: T2.fgPrimary, background: 'transparent',
            fontFamily: T2.fontSans, fontSize: 12, lineHeight: '19px',
          }}
        />
        {isAtLineCap && (
          <button
            type="button"
            aria-label={isExpanded ? 'Collapse message editor' : 'Expand message editor'}
            aria-expanded={isExpanded}
            aria-controls="melix-chat-composer"
            title={isExpanded ? 'Collapse editor' : 'Expand editor'}
            onClick={() => {
              setIsExpanded(current => !current);
              window.requestAnimationFrame(() => textareaRef.current?.focus());
            }}
            style={{ ...chatExpandButton }}
          >
            <ChatIcon name={isExpanded ? 'collapse' : 'expand'} size={14} />
          </button>
        )}
      </div>

      <div style={{
        minHeight: 42, display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr) auto',
        alignItems: 'center', gap: 8, padding: '4px 8px 7px',
      }}>
        <button
          type="button"
          aria-label={`Thinking, ${thinkingEnabled ? 'on' : 'off'}${isStreaming ? ', locked while generating' : ''}`}
          aria-pressed={thinkingEnabled}
          disabled={isStreaming}
          title={`Thinking ${thinkingEnabled ? 'On' : 'Off'}`}
          onClick={() => setThinkingEnabled(current => !current)}
          style={{
            ...chatThinkingButton,
            color: thinkingEnabled ? T2.accent : T2.fgSecondary,
            opacity: isStreaming ? 0.45 : 1,
          }}
        >
          <ChatIcon name="thinking" size={14} />
          <span>Thinking</span>
        </button>

        <span
          id="melix-composer-live-status"
          role="status"
          aria-live="polite"
          aria-atomic="true"
          style={{
            minWidth: 0, overflow: 'hidden', color: isStreaming ? T2.fgSecondary : T2.fgTertiary,
            fontSize: 9, textAlign: 'right', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {statusText}
        </span>

        <button
          type="submit"
          aria-label={isStreaming ? 'Send unavailable while generating' : needsRepair ? 'Send unavailable, Provider stopped' : hasDraft ? 'Send' : 'Send unavailable, empty message'}
          disabled={isBlocked || !hasDraft}
          title="Send"
          style={{
            ...chatSendButton,
            color: isBlocked || !hasDraft ? T2.fgQuaternary : T2.fgInverse,
            background: isBlocked || !hasDraft ? T2.neutral200 : T2.accent,
          }}
        >
          <ChatIcon name="send" size={15} />
        </button>
      </div>

      <span id="melix-composer-keyboard-help" style={chatVisuallyHidden}>
        Return sends. Command Return inserts a new line. Other modified Return keys follow the platform.
      </span>
    </form>
  );
}

function ChatIcon({ name, size }) {
  const common = {
    width: size, height: size, display: 'block', fill: 'none', stroke: 'currentColor',
    strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round',
  };
  if (name === 'server') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><rect x="4" y="4" width="16" height="6" rx="2"/><rect x="4" y="14" width="16" height="6" rx="2"/><path d="M8 7h.01M8 17h.01"/></svg>;
  }
  if (name === 'model') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12v9"/></svg>;
  }
  if (name === 'copy') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>;
  }
  if (name === 'text') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M5 5h14v11H9l-4 3V5Z"/><path d="M8 9h8M8 12h5"/></svg>;
  }
  if (name === 'vision') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>;
  }
  if (name === 'activity') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M3 12h4l2-6 4 12 2-6h6"/></svg>;
  }
  if (name === 'network') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><circle cx="6" cy="12" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="m8 11 8-4M8 13l8 4"/></svg>;
  }
  if (name === 'token') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M9 3 7 21M17 3l-2 18M4 9h16M3 15h16"/></svg>;
  }
  if (name === 'shield') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M12 3 20 6v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-3Z"/><path d="m9 12 2 2 4-4"/></svg>;
  }
  if (name === 'clock') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
  }
  if (name === 'command') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M9 8V5a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v14a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V5"/></svg>;
  }
  if (name === 'diagnostics') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M6 3v6a4 4 0 0 0 8 0V3M4 3h4M12 3h4M14 13v2a4 4 0 0 0 8 0v-2"/><circle cx="20" cy="11" r="2"/></svg>;
  }
  if (name === 'thinking') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M9 18h6M10 22h4M8.3 14.8A7 7 0 1 1 15.7 14.8C14.8 15.5 14.5 16.1 14.5 17h-5c0-.9-.3-1.5-1.2-2.2Z" /></svg>;
  }
  if (name === 'power') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M12 2v10M5.6 5.6a9 9 0 1 0 12.8 0" /></svg>;
  }
  if (name === 'expand') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" /></svg>;
  }
  if (name === 'collapse') {
    return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M3 8h5V3M21 8h-5V3M3 16h5v5M21 16h-5v5" /></svg>;
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true" style={common}><path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" /></svg>;
}

function ChatCapabilityGlyph({ name, label, ready, detail }) {
  return (
    <button
      type="button"
      aria-label={`${label}, ${ready ? 'Ready' : 'Unavailable'}`}
      title={`${label} · ${ready ? 'Ready' : 'Unavailable'} · ${detail}`}
      style={{
        position: 'relative', width: 28, height: 28, flex: '0 0 auto', display: 'grid', placeItems: 'center',
        border: '1px solid rgba(0,0,0,0.08)', borderRadius: 7, padding: 0, cursor: 'pointer',
        color: ready ? T2.accent : T2.fgQuaternary,
        background: ready ? T2.accentWeak : 'rgba(0,0,0,0.025)',
      }}
    >
      <ChatIcon name={name} size={15} />
      {!ready && <span aria-hidden="true" style={{ position: 'absolute', width: 16, height: 1, background: T2.fgQuaternary, transform: 'rotate(-42deg)' }} />}
      <span aria-hidden="true" style={{
        position: 'absolute', right: 3, top: 3, width: 6, height: 6, borderRadius: '50%',
        background: ready ? '#14A05A' : T2.fgQuaternary,
      }} />
    </button>
  );
}

function ChatLedgerRow({ icon, value, tail, title }) {
  return (
    <div
      title={title}
      aria-label={`${tail}, ${value}. ${title}`}
      style={{ minHeight: 31, display: 'grid', gridTemplateColumns: '25px minmax(0,1fr) auto', alignItems: 'center', gap: 5, padding: '0 5px' }}
    >
      <span style={{ color: T2.accent }}><ChatIcon name={icon} size={14} /></span>
      <strong style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T2.fgPrimary, fontSize: 10, fontWeight: 590 }}>{value}</strong>
      <span style={{ color: T2.fgQuaternary, fontSize: 8 }}>{tail}</span>
    </div>
  );
}

function ChatInspector() {
  const capabilities = [
    { name: 'text', label: 'Interactive Text', ready: true, detail: 'Gemma 4 31B IT · model ready' },
    { name: 'vision', label: 'Vision Analysis', ready: false, detail: 'Vision route unavailable' },
  ];
  const rows = [
    { icon: 'activity', value: 'Running', tail: 'Active', title: 'Provider health · Running · Active' },
    { icon: 'network', value: '127.0.0.1:12436', tail: '/v1', title: 'http://127.0.0.1:12436/v1' },
    { icon: 'token', value: '12 in · 24 out', tail: 'tokens', title: 'Last response token usage' },
    { icon: 'shield', value: 'Local only', tail: 'trust', title: 'Local trust only' },
    { icon: 'clock', value: 'Idle', tail: 'timer', title: 'Auto sleep disabled' },
  ];
  const actions = [
    { icon: 'command', label: 'Open Command Center' },
    { icon: 'server', label: 'Open Providers' },
    { icon: 'diagnostics', label: 'Open Diagnostics' },
  ];
  return (
    <aside aria-label="Chat Inspector" style={{ padding: 12, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '8px minmax(0,1fr) auto', alignItems: 'start', gap: 7, padding: '2px 0 12px' }}>
        <span aria-hidden="true" style={{ width: 7, height: 7, marginTop: 4, borderRadius: '50%', background: '#14A05A' }} />
        <div style={{ minWidth: 0 }} title="mlx-community/gemma-4-31b-it-4bit" aria-label="Primary Provider, model Gemma 4 31B IT, quantization 4-bit, canonical ID mlx-community/gemma-4-31b-it-4bit">
          <strong style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T2.fgPrimary, fontSize: 11 }}>Primary Provider</strong>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 3 }}>
            <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T2.fgTertiary, fontSize: 9 }}>Gemma 4 31B IT</span>
            <span style={{ flex: '0 0 auto', padding: '2px 4px', borderRadius: 4, color: T2.accent, background: T2.accentWeak, fontFamily: T2.fontMono, fontSize: 8 }}>4-bit</span>
          </div>
        </div>
        <div aria-label="Model Capabilities" style={{ display: 'flex', alignItems: 'center', gap: 4, maxHeight: 30 }}>
          {capabilities.map(capability => <ChatCapabilityGlyph key={capability.label} {...capability} />)}
        </div>
      </div>
      <div style={{ height: 1, marginBottom: 7, background: 'rgba(0,0,0,0.08)' }} />
      <div>{rows.map(row => <ChatLedgerRow key={row.tail} {...row} />)}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 9, paddingTop: 9, borderTop: '1px solid rgba(0,0,0,0.08)' }}>
        {actions.map(action => (
          <button
            key={action.label}
            type="button"
            aria-label={action.label}
            title={action.label}
            style={{ width: 30, height: 28, display: 'grid', placeItems: 'center', border: '1px solid rgba(0,0,0,0.08)', borderRadius: 6, padding: 0, color: T2.accent, background: 'rgba(0,0,0,0.025)', cursor: 'pointer' }}
          >
            <ChatIcon name={action.icon} size={14} />
          </button>
        ))}
      </div>
    </aside>
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

const chatThinkingButton = {
  minHeight: 28, display: 'inline-flex', alignItems: 'center', gap: 6,
  border: 0, borderRadius: T2.radiusMd, padding: '0 8px',
  background: 'transparent', cursor: 'pointer', fontFamily: T2.fontSans,
  fontSize: 10, fontWeight: 600,
};
const chatSendButton = {
  width: 34, height: 30, display: 'grid', placeItems: 'center',
  border: 0, borderRadius: T2.radiusLg, padding: 0, cursor: 'pointer',
};
const chatRepairButton = {
  minHeight: 24, marginLeft: 'auto', border: 0, borderRadius: T2.radiusSm,
  padding: '0 9px', color: T2.fgInverse, background: T2.accent,
  cursor: 'pointer', fontFamily: T2.fontSans, fontSize: 9, fontWeight: 600,
};
const chatExpandButton = {
  position: 'absolute', top: 8, right: 9, width: 28, height: 28,
  display: 'grid', placeItems: 'center', border: 0, borderRadius: T2.radiusMd,
  padding: 0, color: T2.fgSecondary, background: 'rgba(245,245,245,0.92)',
  cursor: 'pointer',
};
const chatVisuallyHidden = {
  position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
  overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0,
};

Object.assign(window, { ChatSidebar, ChatWorkspace, ChatComposer, ChatInspector, GroupBox });
