# Window UI Chat-First Refresh Plan

## Status

Accepted operator direction from the June 8, 2026 design grilling session.

This plan records the product direction revision for the Melix desktop Window
UI. The canonical product spec in `docs/window-ui-product-spec.md` has been
updated to match this chat-first five-domain direction.

The older 10-domain IA in
`docs/plans/window-ui-information-architecture-refresh.md` is now superseded.
Do not implement the older 10-domain shell if this plan and the updated product
spec are the active operator-approved direction.

## Goal

Redesign the Melix desktop Window UI into a quiet, chat-first local runtime
workbench with five top-level titlebar navigation pills, a white visual
surface, provider-aware Chat readiness, and compact runtime evidence.

The redesign should remove dashboard-like grey card surfaces, remove the
current artificial titlebar/content gap, and make each screen answer a clear
operator question:

- Can I chat with the selected provider and model?
- Which local or remote providers can Melix use?
- Which local model assets are available?
- Which local workflows can run?
- Which global preferences or credentials are configured?

## Non-Goals

- Do not change worker execution semantics.
- Do not add a web frontend to the production app.
- Do not preserve `Command Center`, `API`, `Jobs`, `Diagnostics`, or `Image` as
  permanent top-level navigation items in this redesign.
- Do not expose raw hidden chain-of-thought by default.
- Do not add a custom theme system in the first slice; the first version follows
  macOS appearance and focuses on a high-quality light workspace.

## Branch And Review Strategy

Implementation should use a stacked feature-branch flow instead of merging each
slice directly into `main`.

- Create a long-lived integration branch for the refresh, such as
  `feat/window-ui-provider-refresh`, from current `origin/main`.
- Land Provider Protocol Rename into the feature branch first.
- Land Provider Persistence, CLI, And App-Domain Rename into the same feature
  branch second.
- Land Shell And Titlebar into the same feature branch third.
- Continue later UI slices on the same feature branch unless the operator
  explicitly changes the review strategy.
- Review the feature branch in one shot after the stacked slices are merged
  into it.
- Keep the feature branch current with `origin/main` at natural boundaries, but
  do not merge the individual slices into `main` before the one-shot feature
  review.
- After each slice PR is merged into `feat/window-ui-provider-refresh`, update
  that feature branch from the latest `origin/main` before starting or merging
  the next slice PR. The feature branch must not drift behind `origin/main`
  across slice boundaries.

Required PR topology:

- Integration branch: `feat/window-ui-provider-refresh`.
- Slice PR A source: protocol-rename task branch.
- Slice PR A target: `feat/window-ui-provider-refresh`.
- Slice PR B source: persistence/CLI/app-domain task branch.
- Slice PR B target: `feat/window-ui-provider-refresh`.
- Slice PR C source: shell/titlebar task branch.
- Slice PR C target: `feat/window-ui-provider-refresh`.
- Slice PR D source: chat-readiness task branch.
- Slice PR D target: `feat/window-ui-provider-refresh`.
- Slice PR E source: provider-setup-wizard task branch.
- Slice PR E target: `feat/window-ui-provider-refresh`.
- Slice PR F source: thinking-runtime-details task branch.
- Slice PR F target: `feat/window-ui-provider-refresh`.
- Slice PR G source: domain-surfaces-completion task branch.
- Slice PR G target: `feat/window-ui-provider-refresh`.
- Final review PR source: `feat/window-ui-provider-refresh`.
- Final review PR target: `main`.
- Slice PRs are for slice-level review and CI evidence only. The final review
  PR is the product-level Provider migration and Window UI acceptance review.

Slice PR A acceptance boundary:

- Rename protocol-level `ServerSession` concepts to `Provider`.
- Update protobuf schemas, generated Swift/Python artifacts, control-plane
  request/response names, wire-facing runtime state names, and protocol-level
  tests.
- Do not change Window UI shell behavior.
- Do not change operator persistence file names or JSON field names.
- Do not change CLI command surface.
- Do not change visual screenshots.

Slice PR B acceptance boundary:

- Rename operator persistence from server-session naming to provider naming:
  `server-sessions.json` becomes `providers.json`,
  `server-session-api-keys.json` becomes `provider-api-keys.json`,
  `selected_server_session_id` becomes `selected_provider_id`, and
  `server_sessions` becomes `providers`.
- Rename AppMain, RuntimeViewModel projections, fixtures, screenshots support,
  and tests to provider-domain types and properties.
- Replace CLI `server-session` commands with `provider` commands.
- Do not preserve legacy files, JSON fields, or CLI aliases.
- Do not change Shell or Titlebar visual structure.
- Do not change Chat interaction behavior.
- Do not change Thinking UI behavior.

Slice PR C acceptance boundary:

- Replace visible top-level navigation with exactly five titlebar/toolbar pills:
  `Chat`, `Servers`, `Models`, `Workflows`, and `Settings`.
- Keep top-level navigation out of the sidebar.
- Remove the artificial 72px titlebar/content gap.
- Keep provider, model, queue, and runtime metrics out of the titlebar.
- Use a near-white window workspace background rather than grey dashboard/card
  surfaces.
- Make Chat the default surface.
- Remove `Command Center`, `API`, `Jobs`, `Diagnostics`, and `Image` from
  visible top-level navigation. Existing capabilities may remain reachable only
  as secondary pages, contextual commands, or non-top-level implementation
  paths.
- Add screenshot coverage for Chat ready, Chat no-provider, Chat no-model,
  Servers, Models, Workflows, and Settings.
- Do not implement the full Chat composer redesign.
- Do not implement the setup wizard.
- Do not implement Thinking UI.

Slice PR D acceptance boundary:

- Add the Chat context strip inside the Chat surface, not in the titlebar.
- Make the ready empty transcript completely blank.
- Remove the `Ask Melix` hero and suggestion cards.
- Keep the bottom composer stable and avoid a grey floating card treatment.
- Preserve drafts in no-provider and no-model states while keeping Send
  disabled.
- Expose disabled Send tooltip text and accessibility reasons.
- Add screenshot coverage for Chat ready, no-provider, no-model, and streaming
  states.
- Allow drafting the next message while streaming, but do not allow concurrent
  sends in the same session.
- Keep Stop in the composer only.
- Do not implement the setup wizard.
- Do not implement Thinking disclosure details.

Slice PR E acceptance boundary:

- Implement the `Set Up Local Runtime` sheet.
- Use these steps: Provider Type, Provider Details, Model, Validate, and Review.
- Keep Workflows eligible providers local-only.
- Default the local provider name to `Local MLX`.
- Keep local provider port and runtime directory controls under Advanced.
- Make Hugging Face search the primary Model step path.
- Show at most three local model recommendations as supporting options.
- Keep Import Local Model as a secondary path.
- Validate with a real minimal request before declaring the provider ready.
- Keep validation failures on the Validate step with Retry Validation, Open
  Recovery, and Back actions.
- Show Provider, Model, Validated, and `Chat will use this provider` in Review.
- Do not auto-send any existing Chat draft after setup completion.
- Do not implement Thinking disclosure details.
- Do not implement the full Models page redesign.

Slice PR F acceptance boundary:

- Auto-expand Thinking while the assistant response is streaming.
- Auto-collapse completed Thinking to `Thought for Ns`.
- Keep failed and stopped Thinking disclosures expanded.
- Limit Thinking narrative to at most three visible lines with a max height of
  roughly 120-160px.
- Use first-person user-visible activity narrative, not raw hidden
  chain-of-thought.
- Keep runtime details compact: one line by default and two lines maximum.
- Do not show request IDs by default.
- Persist provider, model, and adapter metadata on assistant messages.
- Show Retry and Open Recovery actions for failed responses.
- Route Open Recovery to `Servers / Recovery` with provider and request context.
- Do not change the setup wizard.
- Do not redesign Models or Servers pages.

Slice PR G acceptance boundary:

- Complete Servers with `Overview`, `Providers`, `Queue`, and `Recovery`.
- Use `Default provider` copy and behavior. Do not reintroduce `Active
  provider` as the primary concept.
- Render Providers as a list, not a card wall.
- Complete Models with `Library`, `Discover`, and `Adapters`.
- Keep Hugging Face search as the primary Discover path.
- Keep Downloads as row state rather than a separate top-level or secondary
  page.
- Implement Adapter `Use in Provider`.
- Complete Workflows with `Overview`, `Runs`, `Recipes`, and `Training`.
- Restrict Workflows provider selectors to local providers.
- Keep Settings limited to global configuration.
- Add final screenshot coverage for all top-level and secondary domain
  surfaces touched by this slice.
- Run an accessibility sweep for the refreshed domain surfaces.

## Walkthrough Evidence

The current low-fidelity walkthrough artifact is intentionally kept under the
ignored runtime tree for review and future high-fidelity previews:

```text
.runtime/walkthrough/window-ui-wireframe.html
```

In the current audit worktree this resolves to:

```text
/Users/chenyu/Documents/github/melix/.runtime/worktrees/window-ui-audit-20260608/.runtime/walkthrough/window-ui-wireframe.html
```

The local preview URL used during review was:

```text
http://127.0.0.1:4177/window-ui-wireframe.html
```

The walkthrough is evidence and design scaffolding only. Production SwiftUI
should reuse the decisions, not copy the static HTML structure.

## Top-Level IA

The top-level Window UI navigation is reduced to five titlebar pills:

```text
Chat
Servers
Models
Workflows
Settings
```

These pills live in the compact titlebar/toolbar. They must not move into a
left global sidebar. The left rail is reserved for page-local context, such as
Chat sessions.

Responsive labels:

- `Workflows` may shorten to `Flows` in narrow windows.
- `Settings` may shorten to `Prefs` only if needed.
- Top-level navigation remains text-based; do not collapse only one item into
  an icon.

Removed top-level labels:

- `Command Center` becomes `Servers / Overview`.
- `API` becomes provider detail material under `Servers / Providers`.
- `Jobs` becomes `Workflows / Runs`.
- `Diagnostics` becomes contextual detail, recovery, trace, and evidence
  drilldown.
- `Image` is handled through Chat capability, Workflows, and Models rather than
  a first-phase top-level workspace.

## Titlebar And Visual System

The titlebar should contain only:

- the five top-level navigation pills;
- an Inspector toggle;
- a Command Menu button;
- other window-level actions that are not page-local controls.

Provider, model, and queue state must not live in the titlebar. Runtime context
belongs inside the page surface where it matters.

The existing 72px artificial content inset should be removed or replaced with a
real compact toolbar. The target structure is:

- titlebar height around 40-48px;
- hairline divider below titlebar;
- content begins immediately below the divider;
- no large blank band between the titlebar and primary work area.

Visual direction:

- page and Chat workspace backgrounds are white or near-white;
- avoid large grey cards and nested card surfaces;
- use dividers, table/list rows, quiet white panels, and precise spacing for
  hierarchy;
- keep Melix teal as the single primary accent;
- use grey only for text hierarchy, borders, and very light row states.

## Chat

Chat is the default first surface.

The Chat screen is not a landing page and should not render a large `Ask Melix`
hero or prompt suggestion cards. The ready empty transcript is blank. The
composer and Chat context strip provide readiness and runtime context.

### Chat Layout

Desktop layout:

- titlebar with top-level navigation pills;
- optional left Sessions rail, default open at desktop sizes;
- center transcript with a constrained reading width of roughly 760-860px;
- bottom stable composer with the same width as the transcript;
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

- no provider: thin context strip says `No provider configured`;
- no model: thin context strip says the selected provider has no model;
- provider error or busy state: context strip may show the current provider and
  degraded state, but the composer remains the readiness truth source.

The context strip should stay thin, roughly 32-38px, and must not become a
dashboard banner.

### Composer

The composer is the send-readiness truth source.

Rules:

- ready: input enabled and Send enabled;
- no provider: input can accept a draft, Send disabled, inline note near the
  composer says `Set up a provider to send this message` and exposes
  `Set Up Local Runtime`;
- no model: input can accept a draft, Send disabled, inline note says
  `Choose a model for <provider> to send this message` and exposes
  `Choose Model`;
- streaming: the user may type the next draft, but Send becomes Stop and cannot
  submit a concurrent request in the same session;
- disabled Send must expose an accessibility reason and tooltip.

Placeholders:

- ready: `Ask the active model...`;
- no provider or no model: `Draft a message...`;
- streaming: `Draft the next message...`.

The composer is a stable bottom input bar with a white background, fine border,
and Send/Stop on the right. It should not float inside a large grey card.

### Chat Provider Binding

Each Chat session stores its own selected provider and model context. New Chat
sessions default to the current `Default provider` from Servers, when one
exists. Switching a Chat session's provider does not automatically update the
global default provider. A provider menu may expose an explicit
`Set as Default Provider` action.

Every assistant message must persist the provider, model, and adapter metadata
used to generate it. This metadata should be visible in trace/detail surfaces,
not as a heavy permanent label on every message.

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

For remote providers, collect endpoint and credentials through the remote
provider path. Remote provider API keys belong primarily to provider detail and
creation flows, with Settings offering only global credential-vault management.

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

Melix should use an Atomic-style Thinking disclosure, adapted to Melix runtime
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

`Stop` belongs in the composer, not in the Thinking block. Failed Thinking
blocks may show `Retry` and `Open Recovery`.

Raw model-provided reasoning may be considered later as an advanced setting,
but the first implementation should show safe user-visible Thinking narrative
plus Melix runtime details.

## Servers

Servers owns providers, queue state, recovery, provider API examples, and
default provider selection.

Secondary pages:

```text
Overview
Providers
Queue
Recovery
```

### Terminology

Use `Provider` as the user-facing term for a local or remote model server that
Chat, API clients, or eligible workflows can use.

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
- lightweight provider switch or default-setting control;
- health summary;
- queue summary;
- recent activity;
- recovery banner only when action is needed.

`Default provider` means the provider preselected for new Chat sessions and
default workflows where eligible. Existing Chat sessions may use their own
provider.

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

- local/remote configuration;
- remote credentials;
- provider API examples;
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

Remote provider models should appear in `Servers / Providers / <provider
detail>`, not in the local model Library.

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
- producing workflow/run;
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

## Inspector

Inspector is closed by default.

It opens as a right-side drawer:

- 320-380px on desktop widths;
- overlay sheet below 1100px;
- shared by Chat trace/details, provider detail, model detail, workflow
  evidence, and other selected-object details.

The titlebar keeps a fixed height when Inspector opens or closes.

## Implementation Slices

1. Documentation Alignment
   - Keep `docs/window-ui-product-spec.md` and this plan aligned before
     production code changes.
   - Keep the walkthrough artifact for future high-fidelity previews.

2. Provider Protocol Rename
   - Complete this slice before desktop persistence, CLI, app-domain, Shell, or
     Titlebar implementation.
   - Rename control-plane protobuf schema definitions, generated Swift/Python
     artifacts, request/response names, and wire-facing runtime state from
     `ServerSession` to `Provider`.
   - Regenerate protocol artifacts and update protocol tests in the same slice.
   - Do not preserve legacy `ServerSession` protocol aliases.

3. Provider Persistence, CLI, And App-Domain Rename
   - Complete this slice before Shell And Titlebar implementation. New shell
     code must be built on provider-domain projections, not legacy
     server-session desktop state.
   - Treat `Provider` as the canonical desktop app-domain term, not only UI
     copy.
   - Move SwiftUI state projections, route metadata, fixtures, tests, support
     links, and accessibility labels to provider naming.
   - Replace operator-session fields and provider configuration files with
     provider-named storage. Do not preserve legacy `server_session` read
     compatibility.
   - Replace CLI `server-session` commands with provider commands. Do not keep
     deprecated command aliases.

4. Shell And Titlebar
   - Replace the old top-level shell with five titlebar nav pills.
   - Remove the artificial 72px content inset.
   - Keep titlebar free of runtime provider/model/queue data.
   - Keep only Inspector and Command Menu as fixed right titlebar actions.

5. Chat Composer And Runtime Readiness
   - Add Chat context strip inside the Chat surface.
   - Move readiness status to the composer area.
   - Remove `Ask Melix` hero and suggestion cards.
   - Make ready empty transcript blank.
   - Keep the bottom composer stable across ready, no-provider, no-model, and
     streaming states.
   - Preserve drafts while Send is disabled, with tooltip and accessibility
     reasons.

6. Provider Setup Wizard
   - Implement `Set Up Local Runtime` sheet.
   - Use Provider Type, Provider Details, Model, Validate, and Review steps.
   - Make Hugging Face search the primary local model selection path.
   - Reuse the same wizard from Chat and `Use in Provider`.
   - Add real validation before Ready and keep failures on the Validate step.
   - Do not auto-send Chat drafts after setup completion.

7. Thinking And Runtime Details
   - Add streaming auto-expanded Thinking disclosure.
   - Add completed auto-collapse and failed/stopped expanded behavior.
   - Add compact runtime detail line.
   - Persist provider/model/adapter metadata per assistant message.
   - Keep raw hidden chain-of-thought out of the default UI.

8. Domain Surfaces Completion
   - Complete Servers with `Overview / Providers / Queue / Recovery`.
   - Replace `active provider` copy with `Default provider`.
   - Complete Models with `Library / Discover / Adapters`.
   - Make Hugging Face search the main Discover path.
   - Fold downloads into row state.
   - Implement `Use in Provider`.
   - Move Jobs into `Workflows / Runs`.
   - Restrict workflow providers to local providers.
   - Keep Settings focused on global configuration.

## Verification Plan

Documentation-only verification:

```bash
git diff --check
```

Walkthrough verification:

- open `.runtime/walkthrough/window-ui-wireframe.html`;
- confirm every top-level surface is represented;
- confirm titlebar contains only nav pills and window actions;
- confirm provider/model/queue context is inside page content, not titlebar.

SwiftUI implementation verification must add or update focused tests for:

- five top-level titlebar navigation pills;
- no 72px blank titlebar/content gap;
- Chat no-provider, no-model, ready, streaming, completed, failed, and stopped
  states;
- composer disabled reasons and accessibility labels;
- setup wizard provider/model/validate/review steps;
- Thinking disclosure auto-open/auto-collapse behavior;
- provider/model/adapter metadata persistence on assistant messages;
- Servers `Default provider`, Providers list, Queue, and Recovery pages;
- Models Library, Discover Hugging Face search, and Adapters pages;
- Workflows local-provider-only behavior;
- responsive Sessions and Inspector drawer behavior.

Slice verification gates:

- PR A: run `make proto` plus focused protocol Swift/Python tests.
- PR B: run focused CLI, AppMain persistence, RuntimeViewModel, and provider
  app-domain tests.
- PR C: run SwiftUI shell tests and screenshot capture for the five-domain
  titlebar shell.
- PR D: run Chat readiness/composer tests and Chat ready/no-provider/no-model/
  streaming screenshot capture.
- PR E: run setup wizard validation tests and local provider/Hugging Face
  success, failure, gated-model, and error-state tests.
- PR F: run Thinking behavior tests and assistant message metadata persistence
  tests.
- PR G: run the full refreshed Window UI screenshot suite and an accessibility
  sweep for the refreshed domain surfaces.

The final feature review PR from `feat/window-ui-provider-refresh` to `main`
must run the repository's full relevant gate:

```bash
make swift-test
make py-test
make integration-test
```

The final feature review PR must also include the coverage and metrics report
required by repository policy. Slice PRs should include focused coverage and
metrics evidence for their changed scope where measurable.

## Acceptance Criteria

- The Window UI uses exactly five top-level titlebar nav pills:
  `Chat / Servers / Models / Workflows / Settings`.
- Runtime provider/model/queue state is not shown in the titlebar.
- New desktop app-domain code, route metadata, fixtures, screenshots, tests,
  support links, and accessibility labels use `Provider` naming rather than
  `Server Session`, `Server Profile`, or `Endpoint`.
- Chat opens first and shows a white, blank ready transcript with a stable
  bottom composer.
- Chat has no `Ask Melix` hero and no prompt suggestion cards.
- Chat no-provider and no-model states preserve drafts but block Send with
  inline reasons and accessible disabled explanations.
- `Set Up Local Runtime` is a sheet wizard with real validation.
- Thinking behavior matches the accepted streaming/completed/failed rules and
  uses first-person user-visible process language plus compact runtime details.
- `Servers / Overview` replaces Command Center and uses `Default provider`.
- `Servers / Providers` shows local and remote providers in one list.
- `Models / Discover` makes Hugging Face search primary.
- `Models / Library` shows local model assets only.
- Workflows only allows local providers.
- Settings contains global configuration only.

## Known Risks

- Historical plans and existing SwiftUI code may still reflect the older
  10-domain IA. Implementation should treat the updated product spec and this
  plan as the governing direction.
- Provider migration is broader than UI copy. It includes protocol schemas and
  generated artifacts, operator persistence, CLI commands, desktop app-domain
  state, tests, fixtures, screenshots, routes, support links, and accessibility
  labels. The migration does not preserve legacy `ServerSession`,
  `server_session`, or `server-session` aliases.
- Thinking narrative must not accidentally leak raw hidden chain-of-thought or
  private prompts. The first implementation should generate safe activity text
  from app/runtime state and sanitized model events.
- Hugging Face search may require network/error/gated-model states that are not
  present in the existing screenshot fixtures.
