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
| `ChatWorkspace` | `ChatView.jsx` | Transcript + composer |
| `ChatBubble` | `ChatView.jsx` | Role-tinted message bubbles |
| `ChatInspector` | `ChatView.jsx` | Session meta, capabilities, runtime |
| `GroupBox` | `ChatView.jsx` | Shared section container |
| `ServerView` | `ServerView.jsx` | Split session list + detail |
| `ToolsView` | `ToolsView.jsx` | Model ops, bench, adapters |
| `MelixTokens` | `Tokens.js` | JS design token constants |

## Usage

Open `index.html` directly — it loads all components via Babel in-browser.
LocalStorage persists active tab, sidebar, and inspector state across reloads.
Toggle **Tweaks** in the toolbar to control the active tab, sidebar visibility, and inspector visibility.

## Design Source

- SwiftUI codebase: `github.com/Keith-CY/melix`, `apps/macos-menubar/Sources/AppMain/`
- Design brief: "Digital Broadsheet" — see root `README.md`
- Tokens: `../../colors_and_type.css`
