# Melix Window UI Product Spec

Date: 2026-06-03

## Purpose

This specification defines the product contract for the Melix desktop operator
window after the information-architecture refresh. It is the source of truth for
the first implementation slices that follow the approved walkthrough direction.

The goal is not to add more surfaces. The goal is to make Melix read as a
local-first AI runtime operator console where every action makes clear:

- which object the operator is acting on;
- what state that object is in;
- what runtime will answer or execute;
- what evidence proves the result.

The disposable walkthrough artifact under `.runtime/walkthrough/` is review
evidence only. Production implementation must follow this specification, not
copy prototype structure or JavaScript.

## Scope

This specification governs:

- top-level desktop navigation;
- product object terminology;
- status, execution, and review-state vocabulary;
- route and selected-object behavior;
- Inspector behavior;
- server creation and chat runtime binding;
- Jobs and artifact lineage visibility;
- API, Diagnostics, Image, Workflows, Models, Servers, Settings, and Command
  Center roles;
- security boundary language for inbound and outbound credentials;
- first-run simplification rules for local server creation.

This specification does not define:

- protobuf schema changes;
- worker execution behavior;
- final SwiftUI component names;
- exact visual token implementation;
- PR sequencing beyond the first product-spec baseline.

## Product Principles

1. Chat stays the default first surface.
2. There is no hidden default provider. Chat sessions must bind to an explicit
   local or remote server before sending.
3. Command Center is the operator cockpit for what needs attention now, not the
   default home page and not the Diagnostics area.
4. Diagnostics is the canonical evidence and debugging domain.
5. Servers owns runtime profiles, lifecycle, credentials, active runtime
   switching, and capability receipts.
6. Models owns model and adapter assets, not running endpoints.
7. Jobs is top-level because durable operation state crosses product domains.
8. The Inspector must become selected-object driven whenever an object is
   selected.
9. Inbound Melix API auth and outbound remote-provider credentials must never be
   conflated.
10. The desktop shell should favor dense, clear operator tooling over decorative
    pages.

## Top-Level Information Architecture

The production desktop window uses these top-level domains:

```text
Chat
Command Center
Servers
Models
Workflows
Jobs
Diagnostics
API
Image
Settings
```

Do not add another top-level domain in the first implementation phase. In
particular, do not add a top-level Artifacts domain yet. Artifact lineage should
be visible through Jobs and owner domains first.

### Secondary Pages

Each top-level domain owns secondary pages inside the shared desktop shell:

| Domain | Secondary pages |
|---|---|
| Chat | Session; Inspector Collapsed |
| Command Center | Overview; Menu Bar Command Center |
| Servers | Overview; Local Servers; Remote Servers; Create Local Server; Add Remote Server; Capability Receipts |
| Models | Library; Downloads & Imports |
| Workflows | Training; Workflow Recipes; Dataset Generation; Batch Runs |
| Jobs | Overview; Queue; History |
| Diagnostics | Overview; Benchmark; Matrix; Evaluation; Logs |
| API | Overview; Inbound Auth; Playground; Endpoints |
| Image | Generate; Edit |
| Settings | Runtime & Storage; Reserved IA |

Breadcrumbs and headings should use the domain and page names. User-visible
labels should not expose implementation buckets such as `Tools / ...`.

## Object Model

| Object | Owner | Contract |
|---|---|---|
| Server Profile | Servers | Durable local or remote runtime configuration, endpoint or launch policy, auth policy, routing constraints, and capability receipts. |
| Model Asset | Models | Downloaded or remote model artifact/reference that can be imported, validated, quantized, or used to create a server. It is not a running endpoint. |
| Adapter Asset | Models / Workflows | Fine-tuned artifact that can be attached to a compatible model asset or server after validation. |
| Job | Jobs | Durable operation state for downloads, training, evaluation, benchmark, image, batch, capability refresh, and debug-bundle work. |
| Artifact | Owner domain plus Jobs lineage | Durable output or referenced input produced, imported, or consumed by a job or operation. Artifacts remain surfaced in owner domains in this phase. |
| Capability Receipt | Servers / Diagnostics | Evidence record that proves runtime capabilities, unsupported routes, probe timing, and routing eligibility. |
| Diagnostic Report Artifact | Diagnostics | Benchmark, matrix, evaluation, log bundle, or debug-bundle artifact with evidence and provenance. |
| API Token | API / Inbound Auth | Inbound credential for clients calling Melix. It is separate from outbound remote-provider credentials. |

The implementation must not use `Run` as a model-library action. Use explicit
object-aware actions:

- `Open Details`
- `Download`
- `Validate`
- `Quantize`
- `Create Local Server From Model`
- `Add Remote Server From Reference`
- `Attach Adapter`

## Status Model

Melix desktop UI uses separate finite vocabularies for health, execution, and
human review state.

```text
HealthStatus =
  ready
  valid
  degraded
  offline
  blocked
  expired
  unsupported
  failed

ExecutionStatus =
  draft
  queued
  running
  validating
  completed
  recoverable
  failed

ReviewStatus =
  none
  pending_review
  reviewed
  rejected
```

Allowed status by object:

| Object | Health status | Execution status | Review status |
|---|---|---|---|
| Server Profile | ready, degraded, offline, blocked | N/A | N/A |
| Model Asset | valid, unsupported, failed | validating | N/A |
| Adapter Asset | valid, failed | validating | N/A |
| Job | blocked, failed | draft, queued, running, validating, completed, recoverable, failed | N/A |
| Capability Receipt | valid, expired, unsupported, failed | N/A | N/A |
| Artifact | valid, failed | completed | N/A |
| Diagnostic Report Artifact | valid, failed | completed | none, pending_review, reviewed, rejected |
| API Token | valid, expired, failed | N/A | N/A |

For example, an evaluation report may have `healthStatus: valid` and
`reviewStatus: pending_review`. Pending review is not a degraded health state by
itself.

Warnings are separate from blockers:

- blocking state prevents the primary action and must expose a disabled reason;
- non-blocking warning allows the primary action but must describe risk and
  repair path;
- capability receipts must distinguish unsupported routes from failed probes.

## Routing Model

Production should preserve the route concepts proven by the walkthrough:

```text
/<domain>/<page>
/<domain>/<page>?selected=<object-kind>:<object-id>
```

Examples:

```text
/servers/overview?selected=server:remote-lab
/jobs/queue?selected=job:adapter-train-119
/diagnostics/evaluation?selected=eval:support-dialogue-v23
```

Route metadata should drive:

- sidebar active state;
- secondary tabs;
- crumb, title, and subtitle;
- page primary and secondary actions;
- selected-object state;
- Inspector module;
- permission or security warnings;
- empty, loading, error, and blocked states.

History behavior should match operator intent:

| Operation | History behavior |
|---|---|
| Switch primary domain or secondary tab | push |
| Select object row | replace |
| Open detail route | push |
| Use page primary action | push |
| Use row action navigation | push |

Row action routing must be object-aware:

- Row actions always act on their row object.
- If an action navigates, carry the selected object into the destination route
  only when that destination can display it meaningfully.
- If the action produces or repairs a more specific object, select that object
  instead. For example, `remote-lab -> Test` routes to
  `/servers/receipts?selected=receipt:remote-lab-expired`, not
  `/servers/receipts?selected=server:remote-lab`.
- If the destination page cannot display the row object or a more specific
  action object, clear selection to avoid stale Inspector context.

## Selection Model

Selection is the UI focus on a concrete object. It is distinct from page routing
and from primary action execution.

Required behavior:

- click row: select the object and update the Inspector;
- double-click row: open the object's detail route when one exists;
- keyboard row selection: select the object and expose a visible `Open Detail`
  action when a detail route exists;
- row button: execute a contextual action for that row object;
- page primary CTA: execute the page-level draft or current next operator
  action.

Selectable rows should use table, list, card, or button semantics that tolerate
nested row actions. Avoid `listbox > option` semantics when rows contain nested
buttons.

## Inspector Contract

The Inspector has two modes:

- Page-level mode: no object is selected; show domain summary, current risk, and
  high-frequency domain actions.
- Selected-object mode: an object is selected; show object details, cross-page
  context, actions, and evidence.

Selected-object Inspector panels keep this order:

1. Context
2. Health
3. Metrics
4. Actions
5. Evidence

Action priority:

- first action: the most likely safe next action for the selected object;
- detail action: always available when a detail route exists, either as the
  first action or a visible secondary action;
- destructive or credential-changing actions: never first unless the page exists
  specifically for that operation.

Evidence links should point to receipts, logs, diagnostic reports, job output,
or artifact lineage rather than generic pages when a specific evidence artifact
exists.

Inspector collapse must persist as a user preference. Production may remember it
per surface, for example:

```text
chat inspector collapsed
diagnostics inspector open
image inspector open
```

## Domain Contracts

### Chat

Chat is the default first screen and the default user interaction surface.

The composer must block send until an explicit local or remote server is
selected. Required composer states:

- no server selected;
- selected server degraded;
- selected server unavailable;
- ready.

Production composer state is driven by runtime state, not by a user-facing
manual segmented control.

Chat should expose runtime failure locally before forcing the operator into
Command Center:

```text
Select a server before sending.
[Choose Local Server] [Connect Remote Server]

Primary Server is running, but active model is cold.
[Warm Model] [Switch Server]

Primary Server is offline.
[Start Server] [Switch Server] [Open Logs]
```

### Command Center

Command Center answers `What should I do now?`

Its first viewport should prioritize:

1. current next action;
2. runtime health;
3. active blockers;
4. active jobs summary.

It may show recovery items and recent critical events, but it must not duplicate
full diagnostics, logs, benchmark tables, evaluation reports, or debug-bundle
details. Deeper evidence links to Diagnostics, Jobs, or Servers.

The primary action must be concrete, such as `Review Eval Drift`, not generic
recovery copy such as `Run Recovery`.

### Servers

Servers owns local and remote runtime profiles, health, lifecycle controls,
credentials, active runtime switching, and capability receipts.

Server creation is split:

- `Create Local Server`;
- `Add Remote Server`.

Create Local Server concerns:

- model asset;
- adapter asset;
- worker route;
- port;
- bind address;
- memory profile;
- runtime directory;
- `MELIX_HOME`;
- local inbound auth.

Add Remote Server concerns:

- base URL;
- provider compatibility;
- network policy;
- outbound remote-provider credentials;
- capability test;
- capability receipt.

Add Remote Server is a strict four-step flow:

1. Endpoint
2. Authentication
3. Capabilities Test
4. Review

Create Local Server uses first-run disclosure:

- Basic: Server name, Model Asset, Memory Profile, Create and Start.
- Advanced: Adapter Asset, Worker route, HTTP port, Bind address, Runtime
  directory, `MELIX_HOME`, and Inbound auth.

Advanced fields are collapsed by default for first-run setup unless the operator
entered through an explicit advanced setup affordance.

### Models

Models owns asset management:

- local model library;
- downloads and imports;
- compatibility metadata;
- quantization artifacts;
- LoRA and adapter assets.

Models must not become a runtime cockpit. Running or switching a model belongs
to Servers and Command Center.

Model rows should communicate whether the asset is downloaded, validated,
worker-compatible, used by a server, or linked to adapters and receipts.

### Workflows

Workflows are repeatable, user-configurable operation templates that produce
jobs and durable artifacts.

Workflows owns:

- Training;
- Workflow Recipes;
- Dataset Generation;
- Batch Runs.

Jobs are concrete executions. Artifacts are durable outputs. Diagnostic reports
are evidence and measurement artifacts.

### Jobs

Jobs is top-level because durable operation state crosses Workflows, Models,
Diagnostics, Image, Servers, and API.

Jobs must expose:

- current queue and active jobs;
- retry, cancel, archive, and inspect actions;
- source domain;
- output artifact links;
- evidence and logs;
- global visibility from Command Center and any domain that starts long-running
  work.

Artifact lineage must be visible here even though Artifacts is not top-level in
this phase.

### Diagnostics

Diagnostics answers `What exactly happened, and how do I prove or debug it?`

It owns:

- Overview;
- Benchmark;
- Matrix;
- Evaluation;
- Logs.

Benchmark, Matrix, Evaluation, and Logs should have distinct visual and
interaction signatures so operators can tell which evidence context they are
auditing.

Evaluation report review state is separate from health. A report may be valid
and still pending review.

### API

API is a local endpoint console first and documentation second.

API owns:

- Overview;
- Inbound Auth;
- Playground;
- Endpoints.

API Playground should read as a developer console and expose:

- Request;
- Response;
- Headers;
- Auth;
- Latency;
- Receipt;
- Copy as curl;
- Save as example;
- Open logs.

API / Inbound Auth protects clients calling Melix. Remote Provider Credentials
belong under Servers.

### Image

Image remains a primary entry, with two modes:

- Generate: prompt, model, seed, size, and new artifact creation.
- Edit: source artifact, mask or selection, lineage, and revision.

Image should make generated-artifact lineage visible through Jobs and the
Inspector.

### Settings

Settings reserves IA for:

- Runtime & Storage;
- Discovery;
- Security;
- Appearance;
- Keyboard Shortcuts;
- Developer Mode;
- Logs & Privacy;
- Update Channel;
- Retention.

The first implementation does not need full forms for every category. It must
reserve space for the highest-risk policies:

- default bind policy;
- credential storage policy;
- model storage roots;
- job and artifact retention policy;
- debug-bundle privacy controls;
- developer-mode gates.

## Security Boundary

Labels, settings, and Inspector copy must distinguish:

- Inbound API Auth: protects clients calling Melix.
- Remote Provider Credentials: outbound credentials used by Melix to call
  external or remote runtimes.

Required security copy rules:

- loopback-only no-auth is valid only for `127.0.0.1`;
- LAN bind requires token auth;
- remote exposed server requires token auth plus explicit bind confirmation;
- remote-provider credentials must never appear in plaintext after save;
- debug bundles need privacy controls and redaction before export.

## Visual System Requirements

The desktop implementation must follow the Melix design-system constraints:

- no structural borders as the primary separator;
- whitespace and typographic hierarchy should separate sections;
- use near-invisible strokes only for necessary interactive containment;
- one accent primary CTA per screen;
- use the real Melix logo asset;
- avoid repeated generic panel/table treatment across every page;
- preserve readable text widths when the Inspector is collapsed;
- keep status chips text-based and not color-only.

Domain visual signatures:

| Domain | Visual treatment |
|---|---|
| Command Center | status dashboard, next-action first, recovery-first |
| Chat | conversational, minimal chrome, runtime-aware composer |
| Models | inventory/table/detail-drawer behavior |
| Workflows | form plus pipeline or job-output context |
| Jobs | queue, history, timeline, lineage |
| Diagnostics | reports, matrices, charts, evidence trail |
| API | console, code, request/response |
| Image | canvas/artifact-centric |

## Implementation Readiness Criteria

Before production SwiftUI implementation begins:

- this specification is linked from `docs/README.md`;
- the implementation plan identifies this spec as its governing source;
- the first implementation slice names the route metadata type or equivalent
  state object it will introduce;
- the first implementation slice names the Inspector contract it will implement;
- screenshot capture expectations are updated for the changed shell;
- verification includes at least documentation validation for this spec and
  focused Swift tests for any later implementation slice.

## Metrics And Verification

Documentation-only changes to this specification require:

```bash
git diff --check
```

The first SwiftUI implementation slice should define or preserve probes for:

- desktop shell navigation latency;
- Inspector toggle latency and layout stability;
- initial Chat hydration time;
- server creation validation latency;
- capability-test duration;
- workflow form validation latency;
- Diagnostics page switch latency;
- screenshot capture and visual regression coverage.

Representative probe names:

```text
desktop.shell_navigation_ms
desktop.inspector_toggle_ms
desktop.chat_initial_hydration_ms
desktop.servers_create_capability_test_ms
desktop.workflow_validation_ms
desktop.diagnostics_page_switch_ms
```

For this spec-only baseline, coverage and metrics are `N/A` because no
executable code changes.
