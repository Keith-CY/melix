# Server-Session-Centered Desktop Shell

## Status

Proposed architecture for the next desktop-shell migration slice.

## Purpose

Reframe the macOS operator shell around `Server Session` as the primary served-runtime object, remove the overloaded `Dashboard` tab, and separate global overview from object editing.

## Top-Level Information Architecture

The desktop shell uses a fixed top-level navigation order:

1. `Chat`
2. `Image`
3. `Server`
4. `Tools`
5. `API`

`Dashboard` is removed rather than renamed. Its required global-overview responsibilities move into:

- `Command Center` as an independent window for global health and recovery posture
- a top banner for critical or blocking states only
- a persistent `header shelf` for high-frequency global actions

The `header shelf` exposes exactly four global actions:

- `New Chat`
- `New Image Job`
- `New Server Session`
- `Open Command Center`

## Workspace Shell Pattern

Complex pages use a common three-column workspace:

- left sidebar for primary object lists or section lists
- center workspace for creation, editing, and main task execution
- right inspector for object status, derived metadata, and object-local actions

The left sidebar and right inspector are collapsible but default to expanded.

## Object Model

### Server Session

`Server Session` becomes a first-class product object. A server session represents one independent listener contract, not a loose collection of gateway defaults.

Required fields:

- `serverSessionID`
- `servedModelID`
- `host`
- `port`
- `authMode`
- `rateLimitPolicy`
- `requestTimeout`
- `servingDefaults`
- `lifecycleState`
- `healthState`
- `lastError`

Lifecycle states must be typed and operator-visible:

- `draft`
- `starting`
- `running`
- `stopping`
- `stopped`
- `failed`
- `unavailable`

### Chat Session

`Chat Session` is the primary chat object shown in the Chat sidebar. Every chat session binds to exactly one `Server Session`.

Required fields:

- `chatSessionID`
- `serverSessionID`
- `title`
- `transcript`
- `streamStatus`
- `usageSummary`
- `exportMetadata`
- `activeBranch`

Changing the bound server is not an in-place mutation of the same chat session. The operator must create or fork a new chat session for a different server session.

### Branch

`Branch` remains an advanced continuation concept inside a chat session. It is not elevated to a sidebar tree peer of `Chat Session`.

Branch visibility rules:

- visible in chat header metadata
- visible in chat inspector
- not shown as the main left-list unit

## Command Center

`Command Center` is an independent window and does not belong to any top-level tab.

It owns global overview only:

- global health
- resource and queue pressure
- recovery items
- recent activity

It does not own object editing for chat, server, image, or tooling objects.

## Page Skeletons

### Chat

Left sidebar:

- primary unit is `Chat Session`

Center workspace:

- transcript
- composer
- session-local controls

Right inspector:

- bound `Server Session`
- branch metadata
- runtime metadata
- `Export`

Rules:

- `Branch` appears only in header or inspector
- `Export` is a chat-session-local action
- if no running `Server Session` is available, Chat must show a blocking empty state that routes the operator to `Server`

### Image

Left sidebar:

- primary unit is `Image Job`

Center workspace:

- `Generate / Edit` mode switch
- parameters
- output results

Right inspector:

- selected job state
- progress
- artifact metadata

Rules:

- Image remains model and job oriented
- Image does not bind to `Server Session`

### Server

Left sidebar:

- primary unit is `Server Session`

Center workspace:

- creation and edit flow
- basic configuration visible by default
- advanced configuration behind disclosure panels

Right inspector:

- lifecycle state
- URL
- last error
- copy actions
- object-level shortcuts

Creation order:

1. choose model
2. configure host, port, auth, limits, and defaults
3. start the server session
4. inspect URL and live status

### Tools

Left sidebar uses direct object names, not abstract category names:

- `Models Library`
- `Downloads`
- `Training`
- `Diagnostics`
- `Logs`
- `Settings`

Default selection is `Models Library`.

### API

The API page remains reference only.

Required sections:

- base URL
- auth explanation
- endpoint reference
- curl quick start
- Python quick start
- JavaScript quick start

Explicit non-goal:

- no try-it console

## Cross-Page Rules

### Banner

Escalate only critical or blocking runtime states to the top banner.

Examples:

- failed control-plane connection
- blocking recovery-needed state
- failed server-session startup

Routine object state remains in the inspector or Command Center.

### Header Shelf

The header shelf is global and action-oriented. It must not accumulate page-local actions such as `Chat Export`.

### Inspector

The inspector is object local. It should not become a second global dashboard.

### Export

Export remains local to the owning object. For the current shell migration, `Chat Export` is explicitly local to `Chat Session`.

## Derived Interface Changes

This shell migration requires explicit interface evolution rather than UI-only renaming.

### Control-Plane And Desktop-State Changes

- add a typed `Server Session` lifecycle and status model
- evolve from one global gateway configuration toward per-server listener configuration
- add explicit `Chat Session -> Server Session` binding
- add a dedicated `Command Center` window contract and view model

### Desktop Read Models

The macOS app must expose typed shell state for:

- selected top-level surface
- selected tools section
- server-session list and selection
- chat-session list and selection
- command-center summaries

### Protocol Direction

The repository does not yet fully implement multi-listener backend behavior. The shell and plan documents must describe this as forward interface work:

- protocol additions are required for typed server-session lifecycle truth
- control-plane state must eventually store multiple listener instances
- per-server listener config replaces the current single gateway-default mental model

## Non-Goals

- turning the macOS shell into a second control plane
- rebinding Image onto server-session semantics
- keeping a renamed `Dashboard` tab
- embedding Command Center inside the main tab strip
