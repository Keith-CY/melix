# Melix Window UI Product Spec

Date: 2026-06-04

Status: Accepted product baseline for the desktop window IA refresh.

Audience: Melix product, design, SwiftUI implementation, QA, and agentic
implementation workflows.

## Purpose

This specification defines the product contract for the Melix desktop operator
window after the information-architecture refresh. It is the source of truth for
the first implementation slices that follow the approved walkthrough direction.
It supersedes walkthrough review notes for product behavior, terminology, and
route structure.

The goal is not to add more surfaces. The goal is to make Melix read as a
local-first AI runtime operator console where every action makes clear:

- which object the operator is acting on;
- what state that object is in;
- what runtime will answer or execute;
- what evidence proves the result.

The disposable walkthrough artifact under `.runtime/walkthrough/` is review
evidence only. Production implementation must follow this specification, not
copy prototype structure, fake data, CDN dependencies, or JavaScript rendering
patterns.

This document intentionally closes the IA expansion phase. Subsequent design
and engineering work should refine route behavior, object state, Inspector
behavior, security boundaries, and visual treatment without adding new
top-level domains.

## Normative Language

The words `must`, `must not`, `required`, `should`, `should not`, and `may` are
normative in this document:

- `must` and `required` define product behavior needed for conformance;
- `must not` defines behavior that is explicitly rejected;
- `should` defines the preferred behavior and requires a documented reason when
  not followed;
- `may` defines optional behavior that is allowed only when it does not weaken
  the required object, route, status, Inspector, or security contracts.

When this specification conflicts with a walkthrough artifact, review note, or
implementation plan, this specification wins. When it conflicts with a
canonical repository specification under `docs/`, resolve the conflict by
updating one of the documents before implementation continues.

## Scope

This specification governs:

- top-level desktop navigation;
- product object terminology;
- status, execution, and review-state vocabulary;
- route and selected-object behavior;
- header action behavior;
- Inspector behavior;
- server creation and chat runtime binding;
- Jobs and artifact lineage visibility;
- API, Diagnostics, Image, Workflows, Models, Servers, Settings, and Command
  Center roles;
- security boundary language for inbound and outbound credentials;
- first-run simplification rules for local server creation;
- accessibility and selection semantics for object-heavy rows;
- production safety rules for route metadata, dynamic runtime text, and icon
  loading.

This specification is implementation-facing. Each production slice that changes
desktop behavior should identify the sections it implements and should add
focused tests or inspection evidence for those sections.

This specification does not define:

- protobuf schema changes;
- worker execution behavior;
- final SwiftUI component names;
- exact visual token implementation;
- prototype HTML maintenance;
- PR sequencing beyond the first product-spec baseline.

## Conformance Summary

A desktop implementation conforms to this specification only when these
conditions are true:

- the top-level IA is exactly the 10 domains defined in this document;
- page labels, header actions, secondary tabs, selected-object state, and
  Inspector modules are driven from typed route metadata or an equivalent
  single source of truth;
- selected-object routes use canonical object-kind prefixes and support
  deep-link restoration;
- object rows select their object before acting or navigating;
- navigation clears selected-object state when the destination cannot display
  it meaningfully;
- health, execution, and review status channels are rendered separately;
- Chat cannot send until a concrete server profile is selected and usable;
- Servers owns runtime profiles and remote-provider credentials;
- API / Inbound Auth owns only inbound credentials for clients calling Melix;
- Jobs exposes durable operation state and artifact lineage across domains;
- Inspector selected-object mode never shows stale context from an unrelated
  route;
- primary actions are concrete, object-aware, and limited to one accent CTA per
  screen.

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
10. Route metadata is product source of truth for titles, secondary pages,
    primary actions, secondary actions, and Inspector modules.
11. Row actions always act on their row object and must not leave stale
    Inspector context.
12. Prototype walkthrough controls may demonstrate state but must not ship as
    user-facing controls.
13. The desktop shell should favor dense, clear operator tooling over decorative
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
be visible through Jobs, owner domains, Inspector evidence links, and command
palette or search results first.

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

### Page Metadata Contract

Every route page must define these product-facing fields:

| Field | Contract |
|---|---|
| Domain label | Top-level product domain shown in primary navigation and breadcrumbs. |
| Page label | Secondary navigation or tab label. It may be concise. |
| Title | Main heading for the current workspace. It must be meaningful without reading the breadcrumb. |
| Subtitle | One-sentence page purpose, runtime boundary, or current operator contract. |
| Primary action | The single accent CTA for the page, when a concrete page-level action exists. |
| Secondary actions | Contextual navigation or low-risk commands that support the page primary action. |
| Inspector module | Page-level Inspector summary module used when no object is selected. |

Breadcrumb and title must not duplicate the same full route string. The
breadcrumb identifies the parent path; the title identifies the current
workspace or object context.

Default domain pages may title themselves with the domain name when the page
label is too generic. Chat uses this rule:

```text
breadcrumb: Chat
secondary page label: Session
title: Chat
```

Do not render the Chat page with `Session` as the only main heading. `Session`
is a tab label and route page label, not the product identity of the first
surface.

### Canonical Route IDs

User-visible routes use stable lowercase route slugs. Labels may change; route
IDs should not change without a migration.

| Domain label | Route domain | Page IDs |
|---|---|---|
| Chat | `chat` | `session`, `inspector-collapsed` |
| Command Center | `command` | `overview`, `menu-bar` |
| Servers | `servers` | `overview`, `local`, `remote`, `create-local`, `add-remote`, `receipts` |
| Models | `models` | `library`, `downloads-imports` |
| Workflows | `workflows` | `training`, `recipes`, `dataset-generation`, `batch-runs` |
| Jobs | `jobs` | `overview`, `queue`, `history` |
| Diagnostics | `diagnostics` | `overview`, `benchmark`, `matrix`, `evaluation`, `logs` |
| API | `api` | `overview`, `inbound-auth`, `playground`, `endpoints` |
| Image | `image` | `generate`, `edit` |
| Settings | `settings` | `runtime-storage`, `reserved-ia` |

Compatibility aliases may redirect legacy route names, but new UI state,
support links, command-palette targets, and tests should use the canonical route
IDs above.

### Sidebar Badge Contract

Sidebar badges are signals, not labels. They should be omitted unless they add
operator value.

| Badge type | Example | Meaning |
|---|---|---|
| Attention | `1 action` | There is a specific operator action waiting. |
| Warning | `1 warn` | The domain contains a non-blocking warning. |
| Activity | `3 active` | The domain has running or queued work. |
| Static default | `default` | Avoid in production unless it explains a real pinned state. |

Badge rendering must distinguish attention, warning, and activity using text
and a subtle visual treatment. Color alone is insufficient. Avoid mixing
category labels and counts unless the category label represents persistent state
that the operator can act on.

## Object Model

The first implementation phase distinguishes routable product objects from
supporting concepts. Routable product objects may appear in
`?selected=<kind>:<id>` route state. Supporting concepts have product meaning
and ownership, but are not selected-object route kinds until a later
specification expands the route schema.

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

Supporting concepts:

| Concept | Owner | Contract |
|---|---|---|
| Workflow Template | Workflows | Repeatable user-configured operation template that creates concrete Jobs and may reference input Artifacts. |
| Chat Session | Chat | User interaction context bound to one explicit Server Profile and its runtime state. |
| Remote Provider Credential | Servers | Outbound secret used by Melix to call a remote runtime or provider. It is managed through Servers, not API / Inbound Auth. |

Supporting concepts must not be encoded as selected-object route kinds in the
first implementation phase. Actions for supporting concepts should route to the
nearest owning routable object or owner page. For example, editing a remote
provider credential routes through Servers / Remote Servers or Servers / Add
Remote Server, not through an API token route.

### Object Relationships

These relationships are required across domains:

```text
Workflow Template -> creates Job
Job -> produces Artifact
Job -> may produce Capability Receipt or Diagnostic Report Artifact
Artifact -> belongs to an owner domain
Artifact -> keeps lineage to source Job and input Artifacts
Server Profile -> references Model Asset and optional Adapter Asset
Chat Session -> binds to Server Profile
API Token -> authorizes inbound clients calling Melix
Remote Provider Credential -> authorizes Melix calling a remote runtime
```

Object names in UI copy, route metadata, Inspector modules, and tests should use
these canonical terms. Avoid generic labels such as `item`, `resource`, `run`,
or `asset` when a more specific product object is known.

Selected-object route values use these object-kind prefixes:

| Kind | Route prefix | Example |
|---|---|---|
| Server Profile | `server` | `server:remote-lab` |
| Model Asset | `model` | `model:example-local-text-8b` |
| Adapter Asset | `adapter` | `adapter:support-v23` |
| Job | `job` | `job:adapter-train-119` |
| Artifact | `artifact` | `artifact:report/benchmark-matrix-042.json` |
| Capability Receipt | `receipt` | `receipt:remote-lab-expired` |
| Diagnostic Report Artifact | `diagnostic-report` | `diagnostic-report:support-dialogue-v23` |
| API Token | `api-token` | `api-token:lan-shared-client` |

Object IDs may contain path-like values and must be URL-encoded in routes.
Display labels are not stable identifiers.

Legacy selected-object alias behavior is defined by the Routing Model.

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

Status channels are independent. A status word has one meaning everywhere it is
used:

- `blocked` means a required precondition prevents progress until the blocker is
  cleared;
- `failed` means the object or execution reached a terminal failure;
- `recoverable` applies only when a failed or interrupted execution has a known
  resume or repair path;
- `pending_review` is never a health status.

Allowed status by object:

| Object | Health status | Execution status | Review status |
|---|---|---|---|
| Server Profile | ready, degraded, offline, blocked | N/A | N/A |
| Model Asset | valid, unsupported, failed | validating | N/A |
| Adapter Asset | valid, unsupported, failed | validating | N/A |
| Job | N/A | draft, queued, running, validating, blocked, completed, recoverable, failed | N/A |
| Capability Receipt | valid, expired, unsupported, failed | N/A | N/A |
| Artifact | valid, failed | N/A | N/A |
| Diagnostic Report Artifact | valid, failed | N/A | none, pending_review, reviewed, rejected |
| API Token | valid, expired, failed | N/A | N/A |

Artifact creation, import, export, and repair progress belongs to the Job that
produces or mutates the artifact. The Artifact itself should not carry
`queued`, `running`, or `validating`.

Server launch failures, failed capability probes, and failed start/stop actions
belong to the relevant Job, runtime event, or Capability Receipt. The Server
Profile health should describe the profile's current operability as `ready`,
`degraded`, `offline`, or `blocked`, not as a terminal `failed` object.

For example, an evaluation report may have `healthStatus: valid` and
`reviewStatus: pending_review`. Pending review is not a degraded health state by
itself.

Warnings are separate from blockers:

- blocked means the object cannot continue without operator intervention;
- blocking state prevents the primary action and must expose a disabled reason;
- non-blocking warning allows the primary action but must describe risk and
  repair path;
- capability receipts must distinguish unsupported routes from failed probes.

The same status word must not mean different things across object types. If a
concept is domain-specific, use a domain-specific field instead of overloading
health or execution status. For example, `pending_review` is a review status,
not a health or execution status.

### State Transition Rules

Implementations may add internal states, but user-visible transitions must
preserve these rules:

- Server Profile: `offline -> ready` only after a successful start or health
  probe; `ready -> degraded` when runtime risk is non-blocking; `ready` or
  `degraded -> blocked` when operator intervention is required before use.
- Model Asset and Adapter Asset: `validating -> valid` only after validation
  evidence exists; `validating -> unsupported` when a worker or route rejects
  the asset as incompatible; `validating -> failed` when validation cannot
  complete because of an execution or integrity error.
- Job: `draft -> queued -> running -> completed` is the normal path;
  `running -> validating` is allowed for jobs that produce evidence requiring
  post-run validation; `queued` or `running -> blocked` requires a disabled
  reason and recovery action; `blocked -> running` requires operator or system
  recovery; `running`, `validating`, or `blocked -> failed` requires evidence.
- Capability Receipt: `valid -> expired` when its freshness window is exceeded;
  receipt creation and probe progress are represented by a Job, usually with
  `executionStatus: validating`; a Receipt appears in selected-object UI only
  after it resolves to `valid`, `expired`, `unsupported`, or `failed`;
  unsupported routes produce `unsupported`, not `failed`, when the runtime
  responds correctly with an unsupported capability.
- Artifact: `valid` only after owner-domain validation succeeds; `failed` when
  the artifact cannot be read, trusted, or attached to its owner domain.
  Artifact production progress remains on the producing Job.
- Diagnostic Report Artifact: `valid + none -> valid + pending_review` when a
  human review gate is required; `pending_review -> reviewed` only after
  explicit operator review; `pending_review -> rejected` when the report cannot
  be accepted as evidence.

Every transition that blocks a primary action must expose a user-facing reason,
a recovery path, and a supporting evidence link when evidence exists.

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
/diagnostics/evaluation?selected=diagnostic-report:support-dialogue-v23
```

Canonical selected-object kinds are:

```text
server
model
adapter
job
artifact
receipt
diagnostic-report
api-token
```

Legacy aliases may be accepted only as compatibility inputs. They must normalize
to canonical route state before display, persistence, Inspector rendering, or
new link generation:

| Legacy input | Canonical selected-object kind |
|---|---|
| `eval` | `diagnostic-report` |
| `token` | `api-token` |

New routes and copied support links must always use canonical kinds.

Route metadata should drive:

- sidebar active state;
- secondary tabs;
- crumb, title, and subtitle;
- page primary and secondary actions;
- selected-object state;
- Inspector module;
- permission or security warnings;
- empty, loading, error, and blocked states.

Header metadata must render consistently. Each page may define:

- zero or more secondary actions;
- at most one primary action;
- an Inspector toggle.

The Inspector toggle is shell chrome, not the page primary action. Page primary
actions must be concrete and object-aware. Use labels such as
`Review Eval Drift`, `Create Local Server`, `Add Remote Server`, or
`Send Request`; avoid generic labels such as `Run Recovery`.

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

Canonical detail routes:

| Object kind | Preferred detail route |
|---|---|
| server | `/servers/overview?selected=server:<id>` |
| model | `/models/library?selected=model:<id>` |
| adapter | `/models/library?selected=adapter:<id>` |
| job | `/jobs/queue?selected=job:<id>` |
| artifact | `/jobs/history?selected=artifact:<id>` |
| receipt | `/servers/receipts?selected=receipt:<id>` |
| diagnostic-report | `/diagnostics/evaluation?selected=diagnostic-report:<id>` |
| api-token | `/api/inbound-auth?selected=api-token:<id>` |

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

Rows with nested action buttons should use one of these patterns:

- table, list, or card row with `aria-current` or selected styling plus
  ordinary nested buttons;
- row button for selection/opening plus a separate contextual action menu.

Double-click must never be the only way to open details. Keyboard users need a
visible `Open Detail` action when a detail route exists.

Row actions must not leave stale Inspector context behind. The production rule
is:

- when a row action acts in place, select that row object before executing;
- when a row action navigates to a page that can display that row object, carry
  the selected object through the route;
- when a row action navigates to a more specific generated object, select the
  generated object instead;
- when no meaningful selected-object context exists on the destination, clear
  selection.

## Inspector Contract

The Inspector has two modes:

- Page-level mode: no object is selected; show domain summary, current risk, and
  high-frequency domain actions.
- Selected-object mode: an object is selected; show object details, cross-page
  context, actions, and evidence.

The Inspector should not repeat the page. Page-level mode may summarize the
domain, but selected-object mode must shift to the selected object. If a route
contains a selected object the page cannot display, the implementation must
clear selection rather than showing stale context.

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

Inspector action rules:

- row actions that navigate should select the acted-on object or the more
  specific object created by the action;
- if a server capability test produces a receipt, the destination should select
  the receipt, not the source server profile;
- page-level primary actions should preserve selection only when the selected
  object remains meaningful on the destination page;
- destructive, credential-changing, or privacy-sensitive actions require an
  explicit confirmation path outside the Inspector first action.

Inspector collapse must persist as a user preference. Production should remember
it per surface, for example:

```text
chat inspector collapsed
diagnostics inspector open
image inspector open
```

Collapsed Inspector preference is presentation state. It must not change the
selected object, route, evidence links, or page primary action.

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

Metrics are supporting context. Do not place generic metric cards above the
current next action when there is an unresolved operator decision.

Command Center header actions must come from route metadata. Examples:

```text
[Jobs] [Review Eval Drift] [Hide Inspector]
```

The page should link to Jobs and Diagnostics instead of embedding full job
history or full diagnostic reports.

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
- Review: profile summary, bind policy, auth policy, runtime directories,
  selected model compatibility, and disabled-action reasons.

Advanced fields are collapsed by default for first-run setup unless the operator
entered through an explicit advanced setup affordance.

Basic, Advanced, and Review are sections inside `Create Local Server`, not new
top-level pages. The first-run path should land on Basic. Operators entering
through advanced setup may open Advanced by default, but Review must always be
available before creating or starting the server.

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

Melix may later need an Artifact Browser when artifact volume makes owner-domain
surfacing insufficient. Until then, artifact search and command-palette results
may expose artifacts without adding another top-level sidebar item.

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
- Inbound auth context;
- Latency;
- Receipt;
- Copy as curl;
- Save as example;
- Open logs.

The default Playground layout should make request and response equally visible.
Authentication mode, selected endpoint, latency, and receipt identity must stay
visible while the operator edits the request. The page should support copying a
request as `curl` without requiring logs or debug-bundle export.

API / Inbound Auth protects clients calling Melix. Remote Provider Credentials
belong under Servers.

API pages must not imply outbound provider credential ownership. Any remote
provider token warning or edit action routes to Servers / Remote Servers or
Servers / Add Remote Server.

Production must not depend on `lucide@latest`, remote icon injection, or any
other unpinned runtime CDN dependency. Icons should be bundled or pinned through
the application build.

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

Settings category tiles should read as configuration areas, not metrics. Use a
two-column layout on wide desktop surfaces unless the shell width cannot support
it. Do not compress all reserved settings categories into a dense four-column
metric grid.

Reserved IA categories are placeholders for future settings contracts, not
permission to add under-specified forms. A category may appear before its form
exists, but any actionable setting must define owner, persistence, validation,
security effect, disabled reason, and recovery path.

## Accessibility Contract

Production implementation must include:

- stable keyboard navigation for primary sidebar, secondary tabs, rows, row
  actions, Inspector actions, and dialogs;
- `aria-current` or platform-equivalent current-page semantics for the active
  route;
- tabs with platform-equivalent selected state and controlled panels;
- visible focus rings that follow Melix design-system tokens;
- non-color status text for every health, execution, warning, and review state;
- disabled-action explanations for primary actions and row actions;
- screen-reader-visible names for icon-only controls;
- no interactive controls nested inside invalid ARIA composite roles.

SwiftUI implementation should use native accessibility modifiers rather than
copying HTML prototype roles directly.

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

Credential copy must always name the direction:

```text
Inbound API Auth
Remote Provider Credentials
```

Never use ambiguous labels such as `API keys/auth` when the direction matters.

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

Sidebar badge styling must follow the Sidebar Badge Contract above. Do not use a
static `default` badge for Chat. Chat's default role is expressed by its
position, route, and active state.

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

## Production Implementation Rules

The prototype may use static HTML and inline JavaScript. Production must not
depend on those mechanics.

Required implementation rules:

- model route metadata with typed application data rather than scattered string
  literals;
- treat model names, file paths, logs, receipt IDs, artifact paths, and remote
  labels as untrusted runtime text;
- render dynamic runtime text through escaped text or native component text, not
  raw HTML interpolation;
- bundle and pin icon dependencies; do not use `lucide@latest` or any runtime
  CDN injection in production;
- keep demo-only controls, such as manual composer-state switches, out of
  shipping UI;
- persist Inspector collapse as a user preference, preferably per surface;
- use route `push` for navigation and `replace` for row selection to keep back
  navigation predictable;
- encode and decode selected-object route values through structured APIs, not
  string concatenation at call sites;
- test legacy selected-object aliases as parse-only compatibility paths;
- keep copied support links canonical even when a legacy alias was accepted as
  input.

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

Recommended implementation slice order:

1. Route metadata and top-level IA.
2. Header primary and secondary actions from route metadata.
3. Selected-object route state and Inspector switching.
4. Server creation split and Chat runtime binding states.
5. Jobs, artifact lineage, and row action routing.
6. Status-channel rendering and disabled-action explanations.
7. Accessibility pass for selection-heavy rows and keyboard detail opening.
8. Domain-specific visual tuning.

Do not start by expanding page count. The first implementation risk is
discipline around object identity, route state, status channels, Inspector
context, and security copy.

## Implementation Review Checklist

Use this checklist before opening or updating a pull request for any desktop
window implementation slice governed by this specification.

### IA And Route Metadata

- The visible primary sidebar contains only Chat, Command Center, Servers,
  Models, Workflows, Jobs, Diagnostics, API, Image, and Settings.
- Secondary pages use canonical route IDs from this document.
- Legacy route aliases, when supported, are parse-only compatibility paths and
  are not emitted in new copied links.
- Header title, subtitle, primary action, secondary actions, and Inspector
  module are derived from route metadata.
- Breadcrumb and title are not duplicates; the breadcrumb identifies the parent
  route and the title identifies the current page or object context.

### Selected Object And Inspector

- Selecting a row updates selected-object route state with replace history.
- Opening a detail route uses push history.
- Row actions first bind to the acted-on row object.
- Row action navigation carries a selected object only when the destination can
  display it meaningfully.
- Generated objects are selected instead of source objects when an action
  produces a more specific object, such as a capability receipt.
- Inspector selected-object mode shows object context, health, metrics, actions,
  and evidence in that order.
- Inspector page-level mode is restored when selection is cleared.
- Inspector collapse persists without changing route, selected object, or page
  primary action.

### Status And Copy

- Health, execution, and review status are rendered as separate channels.
- `pending_review` appears only as review state.
- Blocked primary actions and row actions expose a disabled reason.
- Warning copy distinguishes recoverable risk from blocking failure.
- Status chips include text and do not rely on color alone.
- No page uses generic recovery copy such as `Run Recovery` when a concrete
  next action is known.

### Security And Credentials

- API / Inbound Auth copy describes clients calling Melix.
- Remote Provider Credentials copy describes Melix calling remote runtimes.
- Loopback-only no-auth, LAN token requirements, remote bind confirmation, and
  debug-bundle privacy controls are represented where relevant.
- Saved credentials are not displayed in plaintext.
- Credential-changing actions are never the first Inspector action unless the
  page is specifically about credential management.

### First-Run And Forms

- Create Local Server starts in Basic mode unless the operator explicitly enters
  advanced setup.
- Advanced local-server fields are disclosed, not forced into the first-run
  path.
- Create Local Server review exposes bind policy, auth policy, runtime
  directory, `MELIX_HOME`, model compatibility, and disabled-action reasons.
- Add Remote Server remains a strict Endpoint, Authentication, Capabilities
  Test, Review flow.
- Form warnings distinguish field-level errors, form-level blockers,
  non-blocking warnings, capability receipts, and disabled save reasons.

### Accessibility And Visual System

- Rows with nested actions avoid invalid `listbox > option` semantics.
- Keyboard users can select rows and open detail routes without double-click.
- Icon-only controls have accessible names.
- The active route has platform-equivalent current-page semantics.
- The screen has at most one accent primary CTA.
- Chat does not use a static `default` sidebar badge.
- Settings reserved categories use configuration-area treatment, preferably two
  columns on wide desktop layouts, not dense metric-card treatment.

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
