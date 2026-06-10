# Melix Window UI Product Spec

Date: 2026-06-08

Status: Accepted product baseline for the chat-first five-domain desktop window
refresh.

Audience: Melix product, design, SwiftUI implementation, QA, and agentic
implementation workflows.

## Purpose

This specification defines the product contract for the Melix desktop operator
window after the chat-first Window UI refresh.

The goal is to make Melix read as a local-first AI runtime workbench where the
first useful action is Chat, while every execution path still makes clear:

- which provider will answer or execute;
- which model or adapter is bound to that provider;
- whether the current message, workflow, or request can run;
- what activity and runtime evidence explains the result;
- where the operator can recover from failure.

The desktop window must feel like a quiet native macOS tool, not a landing page,
grey dashboard, or card-heavy prototype. The production implementation should
reuse product decisions from walkthrough artifacts, but must not copy static
HTML, fake data, or prototype-only controls.

## Normative Language

The words `must`, `must not`, `required`, `should`, `should not`, and `may` are
normative in this document:

- `must` and `required` define behavior needed for conformance;
- `must not` defines explicitly rejected behavior;
- `should` defines preferred behavior and requires a documented reason when not
  followed;
- `may` defines optional behavior that is allowed only when it does not weaken
  the required IA, readiness, provider, security, Inspector, or accessibility
  contracts.

When this specification conflicts with an older walkthrough, implementation
plan, or product note, this specification wins unless the repository updates
this document again.

## Scope

This specification governs:

- top-level desktop navigation;
- titlebar and page-local chrome;
- Chat readiness and setup behavior;
- provider and model terminology;
- Thinking and compact runtime details;
- Servers, Models, Workflows, and Settings roles;
- Inspector behavior;
- provider creation, validation, and recovery;
- local model discovery and adapter use;
- workflow local-provider constraints;
- visual system constraints;
- accessibility and disabled-action behavior;
- security boundary language for inbound API credentials and outbound remote
  provider credentials.

This specification does not define:

- worker execution behavior;
- final SwiftUI component names;
- exact visual token values;
- a production web UI;
- a custom theme system;
- PR sequencing beyond the product baseline.

The Provider naming boundary below does define required protobuf, generated
artifact, and wire API renames for the refresh.

## Conformance Summary

A desktop implementation conforms to this specification only when these
conditions are true:

- the top-level IA is exactly five titlebar navigation pills:
  `Chat`, `Servers`, `Models`, `Workflows`, and `Settings`;
- the top-level navigation lives in the titlebar/toolbar, not in a left global
  sidebar;
- the titlebar does not show provider, model, queue, or runtime metrics;
- the old artificial 72px titlebar/content gap is removed or replaced with real
  compact chrome;
- Chat is the default first surface;
- Chat has no large `Ask Melix` hero and no suggestion prompt cards;
- Chat can preserve drafts while blocking Send until the selected provider and
  model are usable;
- the composer exposes the actionable readiness reason and disabled Send
  accessibility reason;
- `Set Up Local Runtime` opens a sheet wizard with real validation before
  declaring Chat ready;
- each Chat session stores its own selected provider context;
- each assistant message persists the provider, model, and adapter metadata
  used for that response;
- Thinking uses a safe user-visible process narrative plus compact Melix runtime
  details, not raw hidden chain-of-thought by default;
- Servers owns Providers, Default provider, Queue, Recovery, and provider API
  examples;
- Models owns local model assets, Hugging Face discovery, and adapters;
- Workflows owns local-provider-only runs, recipes, and training;
- Settings owns only global configuration and credential-vault management;
- Inspector is closed by default and opens as a right-side drawer or responsive
  overlay;
- every blocked primary action exposes a user-facing reason and recovery path.

## Product Principles

1. Chat is the default first surface.
2. The titlebar is for top-level navigation and window-level actions only.
3. Provider/model/queue context belongs inside the page surface, especially
   Chat, not in the titlebar.
4. The composer is the send-readiness truth source.
5. A Chat session stores its own selected provider and does not silently follow
   unrelated global provider changes.
6. `Default provider` means the provider preselected for new sessions or
   eligible defaults, not a forced global binding for existing sessions.
7. Servers owns local and remote Providers.
8. Models owns local model assets and adapter artifacts.
9. Workflows can only run against local providers.
10. Diagnostics, logs, API examples, and Jobs/Runs are contextual surfaces, not
    top-level navigation in this refresh.
11. The UI should favor white workbench surfaces, list/table rows, fine
    dividers, and restrained typography over grey card dashboards.
12. The first implementation should optimize for clarity and verified readiness
    before broad feature surface area.
13. Prototype controls may demonstrate state but must not ship as production
    shortcuts or fake manual state switches.

## Top-Level Information Architecture

The production desktop window uses these top-level titlebar navigation pills:

```text
Chat
Servers
Models
Workflows
Settings
```

Do not add another top-level domain in the first implementation phase.

Removed top-level labels are reassigned as follows:

| Old label | New location |
|---|---|
| Command Center | `Servers / Overview` |
| API | `Servers / Providers / <provider detail> / API` |
| Jobs | `Workflows / Runs` |
| Diagnostics | contextual trace, Recovery, evidence, logs, and Inspector drilldown |
| Image | Chat capability, Workflows, and Models rather than first-phase top-level navigation |

### Secondary Pages

Each top-level domain owns these secondary pages:

| Domain | Secondary pages |
|---|---|
| Chat | Session |
| Servers | Overview; Providers; Queue; Recovery; Add Provider; Provider Detail |
| Models | Library; Discover; Adapters |
| Workflows | Overview; Runs; Recipes; Training |
| Settings | Paths; Credentials; Preferences; Advanced |

`Downloads` is not a permanent Models secondary page. Download state appears
inline in `Models / Library` or `Models / Discover`.

### Canonical Route IDs

User-visible routes use stable lowercase route slugs. Labels may change; route
IDs should not change without a migration.

| Domain label | Route domain | Page IDs |
|---|---|---|
| Chat | `chat` | `session` |
| Servers | `servers` | `overview`, `providers`, `queue`, `recovery`, `add-provider`, `provider-detail` |
| Models | `models` | `library`, `discover`, `adapters` |
| Workflows | `workflows` | `overview`, `runs`, `recipes`, `training` |
| Settings | `settings` | `paths`, `credentials`, `preferences`, `advanced` |

The refreshed desktop UI must not keep legacy route aliases. UI state, support
links, command-palette targets, tests, and copied links use the canonical route
IDs above.

### Page Metadata Contract

Every route page must define these product-facing fields:

| Field | Contract |
|---|---|
| Domain label | Top-level product domain shown in titlebar navigation and breadcrumbs. |
| Page label | Secondary navigation or tab label. It may be concise. |
| Title | Main heading for the current workspace. It must be meaningful without reading the breadcrumb. |
| Subtitle | One-sentence page purpose, runtime boundary, or current operator contract. |
| Primary action | The single accent CTA for the page, when a concrete page-level action exists. |
| Secondary actions | Contextual navigation or low-risk commands that support the page primary action. |
| Inspector module | Page-level Inspector summary module used when no object is selected. |

Breadcrumb and title must not duplicate the same full route string. The
breadcrumb identifies the parent path; the title identifies the current
workspace or object context.

## Titlebar And Page Chrome

The titlebar must contain only:

- the five top-level navigation pills;
- the Inspector toggle;
- the Command Menu button;
- other window-level actions that are not page-local controls.

The titlebar must not contain:

- provider name;
- model name;
- queue state;
- runtime metrics;
- Chat session controls;
- provider setup buttons;
- page-local filters.

The old 72px artificial top content inset must be removed or converted into
real compact toolbar content. The target is:

- a titlebar height of roughly 40-48px;
- a hairline divider below titlebar chrome;
- page content beginning immediately below the divider;
- no unexplained blank band between titlebar and primary work area.

Top-level navigation remains text-based. In narrow windows, `Workflows` may
shorten to `Flows` and `Settings` may shorten to `Prefs`; the nav stays a
single row and must not wrap.

## Object Model

The first implementation phase distinguishes routable product objects from
supporting concepts. Object names in UI copy, route metadata, Inspector
modules, and tests should use canonical terms. Avoid generic labels such as
`item`, `resource`, or `asset` when a more specific product object is known.

| Object | Owner | Contract |
|---|---|---|
| Provider | Servers | A local or remote model server that Chat, provider API clients, and eligible workflows can use. `Provider` is the canonical product and app-domain term. New desktop UI state, route metadata, support links, command targets, and tests must not introduce `Server Session`, `Server Profile`, or `Endpoint` as app-facing concepts. |
| Model Asset | Models | A local model artifact on this Mac that can be downloaded, imported, validated, or used in a provider. Remote provider models are not local model assets. |
| Adapter Asset | Models / Workflows | Fine-tuned artifact that can be attached to a compatible base model and local provider after validation. |
| Workflow Run | Workflows | Durable execution state for training, dataset generation, batch jobs, capability validation, and other long-running local work. Existing implementation may continue to use job storage internally. |
| Artifact | Owner domain plus Workflows lineage | Durable output or referenced input produced, imported, or consumed by a workflow run. |
| Capability Receipt | Servers / Recovery / Inspector | Evidence that proves provider capability, unsupported routes, probe timing, and routing eligibility. |
| Credential | Settings plus owning provider | Stored secret for inbound API clients or outbound remote provider access. |

Supporting concepts:

| Concept | Owner | Contract |
|---|---|---|
| Chat Session | Chat | User interaction context with its own selected provider, model, optional adapter, draft state, and message metadata. |
| Default Provider | Servers | Provider preselected for new Chat sessions and eligible defaults. Existing sessions do not automatically follow it. |
| Remote Provider Credential | Servers / Settings | Outbound secret used by Melix to call a remote provider. It is configured primarily in provider creation/detail flows and managed globally in Settings. |
| Inbound API Credential | Servers / Settings | Credential for clients calling a Melix provider endpoint. It is separate from outbound remote provider credentials. |

### Object Relationships

These relationships are required across domains:

```text
Chat Session -> selects Provider
Chat Session -> may select Model Asset or remote provider model
Assistant Message -> records Provider, Model, and Adapter metadata
Provider -> may reference Model Asset and optional Adapter Asset
Provider -> has Queue and Recovery state
Provider -> may expose API examples and inbound credential requirements
Model Asset -> may be used in Provider
Adapter Asset -> references compatible base Model Asset
Workflow Run -> uses local Provider
Workflow Run -> may produce Adapter Asset or Artifact
Workflow Run -> owns execution state and evidence
```

### Provider Naming Migration Boundary

The Window UI refresh requires a full Provider naming migration before new
window shell implementation. This is not only a visible label replacement. The
migration boundary is:

- Control-plane protobuf schemas, generated Swift/Python artifacts, request and
  response names, and wire-facing runtime state use `Provider` names instead of
  `ServerSession`.
- SwiftUI desktop state, view model projections, fixtures, and tests use
  `Provider` names.
- Persisted operator state writes provider-named fields and collections. The
  refresh does not keep read compatibility for legacy `server_session` fields or
  files.
- User-visible routes, support links, Inspector labels, command-palette targets,
  screenshots, and accessibility labels use `Provider`.
- CLI commands, operator state, desktop routes, desktop state, and desktop tests
  use provider naming. Deprecated `server-session` aliases are not required.
- The implementation should split this into small verifiable slices: protocol
  rename first, persistence/CLI/app-domain rename second, and shell/titlebar UI
  implementation third.

## Readiness And Status Model

The desktop UI must not use a single ambiguous `Ready` label for unrelated
state. Readiness is layered:

```text
App running
Provider available
Model selected or loaded
Request routable
```

The Chat composer is the final truth source for request routability:

- if a message can be sent, the composer and Send button are enabled;
- if a message cannot be sent, the composer keeps the draft, disables Send, and
  exposes the reason plus recovery action.

User-visible status vocabularies:

```text
HealthStatus =
  ready
  degraded
  offline
  blocked
  unsupported
  failed

ExecutionStatus =
  draft
  queued
  running
  validating
  blocked
  completed
  recoverable
  failed

ReviewStatus =
  none
  pending_review
  reviewed
  rejected
```

Status words have one meaning:

- `blocked` means a required precondition prevents progress until cleared;
- `failed` means an operation or object reached terminal failure;
- `recoverable` applies only when a failed or interrupted execution has a known
  resume or repair path;
- `pending_review` is never a health status.

Blocked primary actions and row actions must expose:

- a user-facing reason;
- a recovery path;
- supporting evidence when available.

## Chat

Chat is the default first surface.

The Chat screen must not render:

- a large `Ask Melix` hero;
- suggestion prompt cards;
- a dashboard-like empty state;
- a permanent right Inspector by default.

Ready empty Chat shows a blank transcript, a page-local context strip, and a
bottom composer.

### Chat Layout

Desktop layout:

- titlebar with the five top-level navigation pills;
- left Sessions rail, default open at desktop sizes;
- center transcript with a constrained reading width of roughly 760-860px;
- bottom composer with the same width as the transcript;
- right Inspector drawer closed by default.

Responsive behavior:

- at widths >= 900px, the Sessions rail is open by default and is roughly
  220-260px wide;
- below 900px, Sessions is closed by default and opens as a left overlay;
- at widths >= 1100px, the Inspector drawer takes 320-380px and the transcript
  recenters inside the remaining area;
- below 1100px, Inspector opens as an overlay sheet.

### Chat Context Strip

The Chat context strip appears inside the Chat surface, not in the titlebar.

Ready state:

```text
Provider: Local MLX
Model: qwen3-8b-mlx
Queue: 0 / 0
```

Blocked states:

- no provider: the strip says `No provider configured`;
- no model: the strip says the selected provider has no model;
- provider error or busy state: the strip may show degraded state, but the
  composer remains the readiness truth source.

The strip should stay thin, roughly 32-38px, and must not become a dashboard
banner.

### Composer

The composer owns immediate send readiness.

Rules:

- ready: input enabled and Send enabled;
- no provider: input accepts a draft, Send disabled, inline note near the
  composer says `Set up a provider to send this message` and exposes
  `Set Up Local Runtime`;
- no model: input accepts a draft, Send disabled, inline note says
  `Choose a model for <provider> to send this message` and exposes
  `Choose Model`;
- streaming: the user may type the next draft, but Send becomes Stop and cannot
  submit a concurrent request in the same session;
- disabled Send must expose an accessibility reason and tooltip.

Placeholders:

- ready: `Ask the active model...`;
- no provider or no model: `Draft a message...`;
- streaming: `Draft the next message...`.

Stop belongs in the composer, not in the Thinking block.

### Chat Provider Binding

Each Chat session stores its own selected provider and model context. New Chat
sessions default to the Servers `Default provider` when one exists. Switching a
Chat session's provider does not automatically update the default provider. A
provider menu may expose an explicit `Set as Default Provider` action.

Each assistant message must persist provider, model, and adapter metadata used
to generate it. This metadata is visible in trace/detail surfaces, not as a
heavy permanent label on every message.

## Setup Wizard

`Set Up Local Runtime` opens a sheet from Chat. It does not navigate the user to
Servers by default.

The setup flow is a one-step-per-screen wizard:

1. Provider Type
2. Provider Details
3. Model
4. Validate
5. Review

### Provider Type

Default to `Local`.

Options:

- `Local`: run a model on this Mac;
- `Remote`: connect to an existing provider.

### Provider Details

For local providers:

- default provider name is `Local MLX`;
- duplicate names increment, for example `Local MLX 2`;
- runtime backend defaults to `MLX`;
- port, runtime directory, environment, and other operational fields are hidden
  under Advanced by default.

Remote provider setup collects endpoint and credentials through the remote
provider path. Remote provider API keys belong primarily to provider detail and
creation flows, while Settings offers global credential-vault management.

### Model

If no local model is available, the model step emphasizes Hugging Face search
and supports import:

- Hugging Face search is the primary discovery path;
- `Recommended for this Mac` is a supporting area;
- `Import local model` remains available;
- search results must show Melix compatibility, size, quantization, estimated
  memory, gated state, and unsupported/conversion needs.

The setup wizard may show at most three recommended models. It is not a model
marketplace. More browsing belongs in `Models / Discover`.

### Validate

Validation must make a real minimal request before declaring the setup ready:

- provider process or remote endpoint reachable;
- selected model loadable or reachable;
- chat completion route accepts a tiny prompt;
- queue accepts a request.

Validation failure stays in the Validate step. It exposes:

- `Validation failed` summary;
- the concrete blocker;
- `Retry Validation` as the primary action;
- `Open Recovery` as a secondary action;
- Back navigation to edit provider or model.

### Review

Review shows:

- Provider;
- Model;
- validated status;
- the fact that Chat will use this provider.

Advanced Summary is collapsed by default and may show:

- port;
- runtime directory;
- model path;
- cache directory.

Setup completion must not auto-send any preserved draft. Preserve the draft and
let the user send manually.

## Thinking And Runtime Details

Melix uses an Atomic-style Thinking disclosure, adapted to Melix runtime
evidence.

Behavior:

- streaming: current assistant message auto-expands the Thinking block;
- completed: auto-collapse to `Thought for Ns`;
- failed or stopped: keep the block expanded;
- streaming content max height is roughly 120-160px;
- manually opened completed details may be taller, roughly 280-360px, with
  internal scroll.

Content:

- use first-person user-visible process language;
- keep the streaming narrative to at most three lines;
- avoid hidden raw chain-of-thought by default;
- include compact runtime details as a single line, at most two lines.

Example:

```text
Thinking... 3s
I'm checking the selected provider...
I'm measuring prefill and decode progress...
I'm comparing this request with the last successful run...

Local MLX · qwen3-8b-mlx · Queue 0/0 · Decode 18 tok/s
```

Completed:

```text
Thought for 6s
```

Failure:

```text
Couldn't finish
I checked the selected provider.
The provider process exited while decoding.

Local MLX · qwen3-8b-mlx · Request failed
[Retry] [Open Recovery]
```

Raw model-provided reasoning may be considered later as an advanced setting,
but the first implementation should show safe user-visible Thinking narrative
plus Melix runtime details.

## Servers

Servers owns providers, queue state, recovery, default provider selection,
remote credentials, inbound provider API examples, and capability evidence.

Secondary pages:

```text
Overview
Providers
Queue
Recovery
```

### Terminology

Use `Provider` as the user-facing term for a local or remote model server that
Chat, provider API clients, and eligible workflows can use.

Provider types:

- `Local`;
- `Remote`.

Local and Remote are provider types, not separate secondary navigation pages.
The main creation entry is one `Add Provider` action. The creation wizard then
asks for Local or Remote.

### Overview

The old `Command Center` concept becomes `Servers / Overview`. It should not
render a large cockpit dashboard. It should show:

- `Default provider`, not `Active provider`;
- lightweight default-provider switch or selector;
- health summary;
- queue summary;
- recent activity;
- recovery banner only when action is needed.

`Default provider` means the provider preselected for new Chat sessions and
eligible defaults. Existing Chat sessions may use their own provider.

### Providers

Use a list/table view, not cards.

Suggested columns:

- Name;
- Type;
- Model;
- Status;
- Queue;
- Last request;
- Primary action.

Provider detail owns:

- local or remote configuration;
- remote credentials when the provider is remote;
- inbound API examples and auth guidance for clients calling that provider;
- capability evidence;
- model list for remote providers.

### Queue

Queue defaults to the current/default provider context and allows provider
switching. Avoid a global queue view as the first impression.

### Recovery

Recovery defaults to current actionable items, not historical logs:

- validation failures;
- provider start/stop failures;
- stuck queue;
- model load errors;
- restart, retry, open logs, and export debug bundle actions.

Historical errors belong in logs or detail views.

## Models

Models owns local model assets and adapters. It does not own remote provider
models as local assets.

Secondary pages:

```text
Library
Discover
Adapters
```

There is no permanent `Downloads` secondary page. Download state appears inline
in Library or Discover rows.

### Library

Library shows local model assets on this Mac. Use a list/table surface, not a
card wall.

The main row action is `Use in Provider`.

If no provider exists, `Use in Provider` reuses the provider setup wizard with
the selected model prefilled. If a provider exists, it lets the user choose or
create a provider and then validates the binding.

Remote provider models should appear in
`Servers / Providers / <provider detail>`, not in the local model Library.

### Discover

Discover's primary task is Hugging Face search.

It should also show `Recommended for this Mac` as a supporting area. Search
results must expose compatibility and resource fit rather than hiding
incompatible results.

After a model download completes, do not automatically navigate into
`Use in Provider`. Change the row state to `Ready` and expose
`Use in Provider`.

### Adapters

Adapters includes LoRA and other adapter artifacts.

Workflows creates adapter artifacts; Models / Adapters manages them after
creation. Adapter rows show:

- base model;
- compatibility;
- producing workflow run;
- `Use in Provider`;
- merge/export actions when available.

`Use in Provider` for an adapter means attach the adapter to a compatible local
provider, confirm or choose the base model, validate the adapter load, and make
the provider available to Chat. If the provider is already running another
model, the UI must make the switch/create-new-provider consequence explicit.

## Workflows

Workflows owns long-running local operations.

Secondary pages:

```text
Overview
Runs
Recipes
Training
```

Training is not the default Workflows page. Overview or Runs is the default.

Workflows can only use local providers. Remote providers must not appear in
workflow provider selectors. If no local provider exists, Workflows shows a
setup banner:

```text
Add a local provider to run workflows.
```

Workflow run records must persist:

- provider;
- base model;
- dataset;
- output adapter or model;
- status;
- evidence.

Training completion does not automatically navigate to `Models / Adapters`.
The run result exposes:

- `Open Adapter`;
- `Use in Provider`;
- `View Evidence`.

## Settings

Settings remains a top-level workspace but only owns global configuration:

- paths;
- credential vault;
- app preferences;
- update policy;
- advanced developer options.

Settings must not become the place for runtime health, provider queue, model
download progress, or provider creation.

Appearance follows macOS in the first implementation. Do not add a manual dark
mode toggle in this slice.

Settings may manage all credentials globally, but credential creation and
provider-specific credential use should happen primarily in provider setup and
provider detail flows.

## Inspector

Inspector is closed by default.

It opens as a right-side drawer:

- 320-380px on desktop widths;
- overlay sheet below 1100px;
- shared by Chat trace/details, provider detail, model detail, workflow
  evidence, and other selected-object details.

The titlebar keeps a fixed height when Inspector opens or closes.

Inspector content should not repeat the page. It should explain the selected
message, provider, model, adapter, run, or recovery item and expose evidence or
actions that are too detailed for the primary workspace.

## Routing And Selection

Production should preserve predictable route concepts:

```text
/<domain>/<page>
/<domain>/<page>?selected=<object-kind>:<object-id>
```

Canonical selected-object kinds are:

```text
provider
model
adapter
run
artifact
receipt
credential
```

Legacy selected-object aliases such as `server`, `job`, or `api-token` are not
part of the refreshed desktop route contract. Route parsing, persistence,
Inspector rendering, and new link generation use only the canonical selected
object kinds above.
| `token` | `credential` |
| `eval` | `artifact` or `diagnostic-report` when a later evidence spec defines that kind |

History behavior should match operator intent:

| Operation | History behavior |
|---|---|
| Switch primary domain or secondary tab | push |
| Select object row | replace |
| Open detail route | push |
| Use page primary action | push |
| Use row action navigation | push |

Row action routing must be object-aware:

- row actions always act on their row object;
- if an action navigates, carry the selected object into the destination only
  when that destination can display it meaningfully;
- if an action produces or repairs a more specific object, select that object
  instead;
- if the destination cannot display the row object or a more specific action
  object, clear selection to avoid stale Inspector context.

## Accessibility Contract

Production implementation must include:

- stable keyboard navigation for titlebar navigation, secondary tabs, rows, row
  actions, Inspector actions, and dialogs;
- platform-equivalent current-page semantics for the active titlebar nav pill;
- tabs with platform-equivalent selected state and controlled panels;
- visible focus rings that follow Melix design-system tokens;
- non-color status text for every health, execution, warning, and review state;
- disabled-action explanations for primary actions, row actions, and Send;
- screen-reader-visible names for icon-only controls;
- no interactive controls nested inside invalid accessibility composite roles.

SwiftUI implementation should use native accessibility modifiers rather than
copying HTML prototype roles directly.

## Security Boundary

Labels, settings, and Inspector copy must distinguish:

- Inbound API Credentials: credentials for clients calling a Melix provider
  endpoint.
- Remote Provider Credentials: outbound credentials used by Melix to call a
  remote provider.

Required security copy rules:

- loopback-only no-auth is valid only for `127.0.0.1`;
- LAN bind requires token auth;
- remote exposed local provider requires token auth plus explicit bind
  confirmation;
- remote-provider credentials must never appear in plaintext after save;
- debug bundles need privacy controls and redaction before export.

Credential copy must always name the direction when direction matters:

```text
Inbound API Credentials
Remote Provider Credentials
Credential Vault
```

Never use ambiguous labels such as `API keys/auth` when the direction matters.

## Visual System Requirements

The desktop implementation must follow these visual constraints:

- page and Chat workspace backgrounds are white or near-white;
- do not use large grey cards as page structure;
- do not nest cards inside cards;
- use dividers, table/list rows, quiet white panels, and spacing for hierarchy;
- use near-invisible strokes only for necessary interactive containment;
- use at most one accent primary CTA per screen;
- use Melix teal as the single primary accent;
- keep status chips text-based and not color-only;
- preserve readable text widths when Inspector is collapsed;
- keep titlebar height stable across navigation and drawer changes;
- avoid decorative backgrounds, gradient blobs, and marketing hero treatment.

Domain visual signatures:

| Domain | Visual treatment |
|---|---|
| Chat | conversational, blank-ready transcript, runtime-aware composer |
| Servers | provider list, compact overview, queue and recovery operations |
| Models | local inventory, Hugging Face discovery, adapter management |
| Workflows | local run overview, recipes, training, evidence links |
| Settings | global configuration, credential vault, advanced preferences |

## Production Implementation Rules

The prototype may use static HTML. Production must not depend on those
mechanics.

Required implementation rules:

- model route metadata with typed application data rather than scattered string
  literals;
- treat model names, file paths, logs, receipt IDs, artifact paths, and remote
  labels as untrusted runtime text;
- render dynamic runtime text through escaped/native component text, not raw
  HTML interpolation;
- bundle and pin icon dependencies;
- keep demo-only controls out of shipping UI;
- persist Inspector collapse as user preference, preferably per surface;
- persist Chat session provider/model/adapter metadata;
- use route `push` for navigation and `replace` for row selection to keep back
  navigation predictable;
- encode and decode selected-object route values through structured APIs, not
  string concatenation at call sites;
- test that legacy selected-object aliases are not emitted by refreshed desktop
  routes, command targets, support links, or screenshots;
- keep copied support links canonical.

## Implementation Readiness Criteria

Before production SwiftUI implementation begins:

- the implementation plan identifies this spec as its governing source;
- outdated plans that describe the older 10-domain IA are marked superseded or
  updated;
- screenshot capture expectations are updated for the five-domain titlebar
  shell;
- the first implementation slice names the route metadata type or equivalent
  state object it will introduce or update;
- the first implementation slice names the Chat readiness and setup wizard
  state it will implement;
- verification includes documentation validation for this spec and focused
  Swift tests for any later implementation slice.

Recommended implementation slice order:

1. Documentation alignment and screenshot walkthrough update.
2. Five-domain titlebar shell and removal of the 72px content gap.
3. Chat context strip, composer readiness states, and blank ready transcript.
4. Provider setup wizard with validation.
5. Thinking disclosure and compact runtime details.
6. Servers Providers/Overview/Queue/Recovery.
7. Models Library/Discover/Adapters.
8. Workflows Runs/Recipes/Training and local-provider-only constraints.
9. Settings global configuration and credential vault.
10. Inspector drawer and responsive behavior.

## Implementation Review Checklist

Use this checklist before opening or updating a pull request for any desktop
window implementation slice governed by this specification.

### IA And Chrome

- The visible titlebar navigation contains only Chat, Servers, Models,
  Workflows, and Settings.
- Provider, model, queue, runtime metrics, and page-local controls are not in
  the titlebar.
- The left side of Chat is a Sessions rail, not a global navigation sidebar.
- There is no 72px blank titlebar/content gap.
- Top-level navigation remains single-row and does not wrap at narrow widths.

### Chat

- Chat is the default first surface.
- Ready empty Chat has a blank transcript, no hero, and no suggestion cards.
- Chat no-provider and no-model states preserve drafts but disable Send.
- Disabled Send exposes visible, tooltip, and accessibility reasons.
- `Set Up Local Runtime` opens a sheet wizard, not a navigation jump.
- Setup validation makes a real minimal request before Ready.
- Each Chat session stores selected provider/model/adapter context.
- Each assistant message records provider/model/adapter metadata.
- Streaming Thinking auto-expands; completed Thinking auto-collapses; failed or
  stopped Thinking stays expanded.

### Servers

- Servers uses `Overview / Providers / Queue / Recovery`.
- `Default provider` copy is used instead of `Active provider`.
- Providers list local and remote providers in one list with type badges.
- `Add Provider` is one entry point and asks Local or Remote inside the flow.
- Queue defaults to current/default provider context.
- Recovery shows current actionable items before historical logs.

### Models

- Models uses `Library / Discover / Adapters`.
- Library contains local model assets only.
- Discover makes Hugging Face search primary.
- Download state is inline, not a permanent Downloads page.
- Model and adapter rows expose `Use in Provider`.

### Workflows

- Workflows uses `Overview / Runs / Recipes / Training`.
- Training is not the default Workflows page.
- Provider selectors in Workflows show local providers only.
- No-local-provider state exposes a setup banner.
- Training completion exposes Open Adapter, Use in Provider, and View Evidence
  without auto-navigation.

### Settings

- Settings contains global configuration only.
- Settings does not show runtime health, queue state, model download progress,
  or provider creation as primary content.
- Appearance follows macOS in the first slice.

### Accessibility And Visual System

- Icon-only controls have accessible names.
- Rows with nested actions avoid invalid accessibility semantics.
- Keyboard users can select rows and open detail routes without double-click.
- The screen has at most one accent primary CTA.
- Large grey card dashboards and nested cards are absent from the redesigned
  surfaces.

## Metrics And Verification

Documentation-only changes to this specification require:

```bash
git diff --check
```

The first SwiftUI implementation slice should define or preserve probes for:

- desktop titlebar navigation latency;
- Inspector toggle latency and layout stability;
- initial Chat hydration time;
- provider setup validation duration;
- Thinking disclosure layout stability while streaming;
- workflow form validation latency;
- screenshot capture and visual regression coverage.

Representative probe names:

```text
desktop.titlebar_navigation_ms
desktop.inspector_toggle_ms
desktop.chat_initial_hydration_ms
desktop.provider_setup_validation_ms
desktop.chat_thinking_layout_shift_px
desktop.workflow_validation_ms
```

For this spec-only baseline, coverage and metrics are `N/A` because no
executable code changes.
