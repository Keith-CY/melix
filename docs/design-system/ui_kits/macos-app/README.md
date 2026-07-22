# Melix macOS App — UI Kit

High-fidelity prototype of the Melix macOS menubar operator app.

## Screens / Tabs

| Tab | File | Notes |
|---|---|---|
| Chat | `ChatView.jsx` | Session sidebar, transcript, composer, inspector |
| Server | `ServerView.jsx` | Session list + detail panel with actions |
| Tools | `ToolsView.jsx` | Model ops, bench report, adapter registry |
| Image | — | Placeholder (not yet prototyped) |
| API | — | Placeholder (not yet prototyped) |

## Component Map

| Component | File | Purpose |
|---|---|---|
| `AppShell` | `Shell.jsx` | Window chrome, titlebar, tab strip, sidebar/inspector rails |
| `TabStrip` | `Shell.jsx` | Capsule tab switcher (Chat → API) |
| `ChatSidebar` | `ChatView.jsx` | Session list with selection state |
| `ChatWorkspace` | `ChatView.jsx` | Transcript + Hybrid A Composer |
| `ChatRouteIdentity` | `ChatView.jsx` | Human-readable model identity, quantization badge, canonical-ID disclosure |
| `ChatComposer` | `ChatView.jsx` | Stable editor/action shell with Thinking, generation status, and Provider repair |
| `ChatBubble` | `ChatView.jsx` | Role-tinted message bubbles |
| `ChatInspector` | `ChatView.jsx` | 232-point icon-first Precision Ledger and Inline Glyph Cluster |
| `GroupBox` | `ChatView.jsx` | Shared section container |
| `ServerView` | `ServerView.jsx` | Split session list + detail |
| `ToolsView` | `ToolsView.jsx` | Model ops, bench, adapters |
| `MelixTokens` | `Tokens.js` | JS design token constants |

## Usage

Serve the repository root with a local static server, then open
`/docs/design-system/ui_kits/macos-app/index.html`. The prototype loads sibling
JSX files through Babel in-browser, so Chromium blocks a direct `file://` launch.
LocalStorage persists active tab, sidebar, and inspector state across reloads.
Toggle **Tweaks** in the toolbar to control the active tab, sidebar visibility, and inspector visibility.

The Chat Composer defaults to its empty state. Append `?composer=draft`,
`?composer=multiline`, `?composer=streaming`, or `?composer=offline` to inspect
deterministic Hybrid A fixtures. The fixtures preserve the production contract:

| State | Center lane | Editing and actions |
|---|---|---|
| Empty, unfocused | Empty | Send unavailable |
| Empty, focused | `↵ Send · ⌘↵ New line` | Return sends; Command-Return inserts a newline |
| Draft / multiline | Empty | Editor grows to five lines; Expand appears at the cap |
| Streaming | `Generating · draft saved` | Draft remains editable; Thinking and Send are unavailable |
| Provider offline | Empty | Warning repair rail appears; draft remains editable; Start restores editor focus |

The Composer does not carry model identity, token usage, Clear, or a simulated
Stop action. Model identity belongs in the Chat header, usage belongs to response
metadata, and clearing a draft belongs to session actions.

The Chat header keeps Provider selection separate from its Human-readable Model
Identity control. The resting model label hides the repository namespace and
retains a compact quantization badge; tooltip, accessibility, and one-step
detail/copy disclosure preserve the canonical ID. The Chat Inspector uses the
accepted Precision Ledger and a capability glyph cluster no taller than 30
points instead of repeated section headings, full-width destination labels, or
large Text/Vision tiles.

## Design Source

- SwiftUI codebase: `github.com/Keith-CY/melix`, `apps/macos-menubar/Sources/AppMain/`
- Design brief: "Digital Broadsheet" — see root `README.md`
- Tokens: `../../colors_and_type.css`
