# Window UI Information Architecture Refresh

## Goal

Refresh the Melix desktop window UI around a single product promise: make the local-first AI runtime feel immediately controllable while preserving Chat as the default first surface.

The first screen remains Chat, but Chat must carry lightweight runtime awareness through the inspector so the operator can see the current server, model, health, and recent activity without leaving the conversation flow. Command Center becomes a first-class cockpit entry point, not the default home page.

## Background

The current screenshot matrix shows a visually functional app, but the information architecture still reads as separate products in places:

- Workspace surfaces such as Chat, Image, Server, and API use a different navigation treatment than the Tools suite.
- Command Center exists, but is visually and structurally secondary despite being the best runtime cockpit.
- Tools contains too many unrelated operator domains under one bucket.
- Diagnostics, API, Server create, and Image edit/generate states need clearer workflow boundaries.
- Inspector collapse and main-only states can cause large layout reflows.

The design direction below is based on the current 38-screen capture set and Gemini review feedback, then resolved through operator decisions in the planning conversation.

## Scope

- Chat default empty state and runtime-aware inspector direction
- Command Center placement and role
- global navigation and domain information architecture
- Inspector contract and split-pane layout behavior
- Server creation flow shape
- Diagnostics navigation model
- long-form workflow ergonomics
- API and Image workspace role clarity
- screenshot and walkthrough acceptance matrix for the first implementation phase

## Non-Goals

- making Command Center the default first screen
- redesigning every visual detail in a single implementation pass
- backend runtime protocol changes unless a later implementation slice proves they are required
- replacing existing benchmark, evaluation, or model-operation behavior
- committing disposable `.runtime/walkthrough` artifacts
- treating Gemini feedback as the source of truth over Melix product decisions

## Product Principles

1. Chat stays the default first surface.
2. Chat is a runtime-aware conversation entry, not a generic chat shell.
3. Command Center is a first-class cockpit and global navigation entry, but not the home page.
4. The desktop shell uses one global navigation model across all primary surfaces.
5. Runtime operation, model assets, workflows, diagnostics, and developer API affordances should be separate domains.
6. Inspectors expose context, health, metrics, actions, and evidence consistently.
7. Long operator forms should feel like dense professional tools, not decorative card stacks.

## Information Architecture

The first-phase navigation model should move away from a single `Tools` bucket and toward domain entries:

- Chat
- Command Center
- Server
- Models
- Workflows
- Diagnostics
- Image
- API
- Settings

`Tools / ...` labels should be removed from user-facing breadcrumbs and titles. Use domain breadcrumbs instead:

- `Models / Library`
- `Models / Downloads`
- `Workflows / Training`
- `Workflows / Workflow Recipes`
- `Workflows / Synthetic Datasets`
- `Workflows / Batch Runs`
- `Workflows / Jobs`
- `Diagnostics / Overview`
- `Diagnostics / Benchmark`
- `Diagnostics / Matrix`
- `Diagnostics / Evaluation`
- `Diagnostics / Logs`
- `Settings`

The shell may still group entries visually, but primary surfaces should not swap into a separate navigation system when the operator moves between Chat, Models, Diagnostics, API, and Command Center.

## Chat Default Surface

Chat remains the default first screen.

The Chat empty state should include:

- starter prompts as the primary affordance;
- recent chats as a secondary affordance;
- a runtime setup banner or inline card only when runtime setup is incomplete or degraded;
- a right inspector that is open by default for first-time users and remembers the operator preference after manual collapse.

The Chat inspector should show the current runtime context:

- current server and connection state;
- active model identity;
- health or degraded status;
- memory or pressure summary when available;
- recent jobs or diagnostics;
- quick actions such as opening Command Center, starting local server, or connecting remote server.

The main Chat content should preserve comfortable reading width when the inspector is collapsed instead of stretching indefinitely.

## Command Center

Command Center becomes a primary navigation entry.

Its first viewport should prioritize runtime state:

- current server availability;
- active model;
- resource pressure;
- recent error state;
- next likely operator action.

Recent jobs, diagnostics, and logs should appear as secondary strips below the runtime summary. Command Center should feel like a cockpit, not an activity feed.

## Inspector Contract

Every primary surface with an inspector should use the same conceptual slots:

- Context: the selected object, target runtime, or workflow state.
- Health: status, warnings, and errors.
- Metrics: key measures relevant to the current surface.
- Actions: no more than three high-frequency contextual actions.
- Evidence: links to logs, reports, traces, recent events, or generated artifacts.

Surfaces may extend the contract, but should not reorder or reinvent the basic structure. The inspector can be collapsible, but collapse should not create disruptive layout reflows.

## Split-Pane Layout Rules

Use page-type constraints when the inspector is hidden:

- Chat, API, and documentation-like content use a max readable width.
- Table and diagnostic views may expand, but preserve stable column constraints.
- Image workspaces prioritize canvas and preview space.
- Forms preserve section width and sticky action placement.

The implementation should expose explicit inspector toggle affordances and avoid making the expanded main-only state look like a different screen.

## Domain-Specific Direction

### Models

Models owns asset management:

- local model library;
- downloads;
- compatibility metadata;
- quantization artifacts;
- LoRA and adapter assets.

Running or switching the active model belongs to Server and Command Center. Models may offer a `Run this model` affordance, but execution should transition into runtime context rather than turning Models into a cockpit.

### Workflows

Workflows owns long-running operator flows:

- Training;
- Workflow Recipes;
- Synthetic Datasets;
- Batch Runs;
- Jobs.

Long forms should use fieldsets, section headings, inline validation, and a sticky action bar. Avoid turning dense engineering workflows into decorative card stacks.

The sticky action bar should expose:

- primary action, such as `Run`, `Generate`, or `Save`;
- dirty or validation state;
- blocking errors;
- a concise target/output summary when useful.

### Diagnostics

Diagnostics should move from subtle tabs to clear secondary navigation:

- Overview;
- Benchmark;
- Matrix;
- Evaluation;
- Logs.

These pages should share a Diagnostics shell for target model, time range, export, and evidence controls. Benchmark, Matrix, and Evaluation should have distinct visual markers or layout signatures so the operator can immediately tell which diagnostic context they are auditing.

### Server

Server create should become a stepper.

Local creation can remain short:

1. Runtime
2. Review

Remote creation should separate concerns:

1. Endpoint
2. Authentication
3. Capabilities Test
4. Review

Credentials, network connection details, local paths, and model identity should not be packed into one flat form because error attribution becomes too difficult.

### API

API should be a local endpoint console first and documentation second.

Proposed secondary structure:

- `API / Overview`: live endpoint, health, and quick-copy examples.
- `API / Keys/Auth`: token state and copy/revoke/create affordances.
- `API / Playground`: send a test request against the active runtime.
- `API / Endpoints`: reference docs.

API secondary navigation should be nested inside the global shell instead of replacing it.

### Image

Image remains a primary entry but is not a core IA spine.

Generate and Edit should diverge visibly:

- Generate emphasizes prompt, model, seed, size, and new artifact creation.
- Edit emphasizes source asset context, mask or selection state, revision history, and localized changes.

Primary action styling should help operators distinguish generating a new artifact from modifying an existing one.

## First Implementation Phase

The first implementation phase should be broad enough to prove the IA, but narrow enough to verify:

1. Add runtime-aware Chat inspector and improved Chat empty state.
2. Promote Command Center to a primary navigation entry while keeping Chat as default.
3. Replace the `Tools` bucket with Models, Workflows, Diagnostics, and Settings domain navigation.
4. Define and apply the shared Inspector contract to core surfaces.
5. Move long forms toward fieldsets plus sticky action bars.
6. Convert Server create, especially Remote, into a stepper.
7. Promote Diagnostics tabs into secondary pages.

## Walkthrough Plan

Before production SwiftUI implementation, create a disposable walkthrough under `.runtime/walkthrough/` following `docs/runbooks/agent-ui-walkthrough.md`.

The walkthrough should include:

- default Chat with inspector open;
- Chat inspector collapsed;
- Command Center as a primary entry;
- Models / Library and Models / Downloads;
- Workflows / Training and Workflows / Synthetic Datasets with sticky action bar;
- Diagnostics / Benchmark, Matrix, Evaluation, and Logs;
- Server create Local and Remote stepper;
- API Overview and Playground;
- Image Generate and Edit.

Record accepted walkthrough decisions in a paired `.runtime/walkthrough/` note, then copy durable decisions back into this plan or a successor implementation plan before code changes.

## Performance and UX Probes

The implementation phase should define or preserve probes for:

- inspector toggle latency and layout stability;
- initial Chat surface hydration time;
- navigation transition time between primary domains;
- Server create validation and capability-test duration;
- workflow form validation latency;
- Diagnostics page switch latency;
- screenshot capture and visual regression coverage.

Representative probe names:

- `desktop.shell_navigation_ms`
- `desktop.inspector_toggle_ms`
- `desktop.chat_initial_hydration_ms`
- `desktop.server_create_capability_test_ms`
- `desktop.workflow_validation_ms`
- `desktop.diagnostics_page_switch_ms`

## Acceptance Matrix

The first implementation phase is acceptable when:

- Chat remains the default first screen.
- Chat default state shows starter prompts, recent chats, and the runtime inspector.
- The Chat inspector is open by default for first-time users and can remember collapse preference.
- Command Center appears as a primary navigation entry.
- Command Center presents runtime state before activity history.
- No primary screen requires `Tools / ...` as the user-visible breadcrumb.
- Models, Workflows, Diagnostics, API, Image, Server, Settings, and Command Center share one global shell.
- Inspectors expose context, health, metrics, actions, and evidence in a predictable order.
- Server create Local and Remote can be walked through as steppers.
- Diagnostics Benchmark, Matrix, Evaluation, and Logs are visible secondary pages.
- Long workflow forms keep a sticky action bar visible during scroll.
- API default view behaves like an endpoint console.
- Image Generate and Edit have distinct visual and interaction priorities.
- The screenshot matrix is refreshed and includes at least the default 16 screens plus the extended pane and workflow states.
- The in-app browser walkthrough is reviewed before broad production UI edits.

## Verification Plan

Documentation-only changes:

- `git diff --check`

Implementation phase:

- update focused macOS menu bar tests for navigation state, inspector defaults, and route mapping;
- update screenshot capture tests or runners to include Command Center and extended pane states;
- run `swift test --package-path apps/macos-menubar`;
- run the relevant screenshot capture workflow and inspect the generated contact sheets;
- run `git diff --check`;
- include touched-scope coverage evidence or an explicit `N/A` metrics report when a slice is documentation-only.

## Known Gaps

- This plan does not choose exact visual styling, spacing tokens, or component names.
- The final route names and persisted state keys must be resolved during implementation against existing `DesktopShellState` and `RuntimeViewModel` code.
- Some runtime inspector data may need backend or view-model support that should be handled in separate focused slices.
- Gemini feedback was useful review input, but final authority is the operator-approved Melix IA captured in this plan.
