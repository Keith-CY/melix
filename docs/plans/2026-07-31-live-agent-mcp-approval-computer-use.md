# Live Agent Runtime, MCP Execution, Approval, Cancellation, And Computer Use Plan

## Goal

Deliver one production-oriented Melix agent runtime that can:

- continue model turns after structured function calls;
- discover and call real MCP servers;
- require and record operator approval according to durable policy;
- cancel provider turns, queued approvals, active tools, MCP requests, and
  Computer Use sessions reliably;
- execute macOS Computer Use through an isolated native broker;
- expose the same run, approval, cancellation, and evidence truth to Chat,
  control-plane diagnostics, and future workflow callers.

This plan extends the deterministic tool runtime governed by
`docs/unified-agentic-tool-runtime-contract.md`. It does not replace that
runtime or relabel fixture-backed behavior as live execution.

## Current Delivery Boundary

The current delivery implements the live Agent loop, built-in and MCP tool
execution, durable approval policy and run journals, receipt-backed Stop, and a
native Computer Use semantic-press slice. `GetAgentOperations` is the single
operator read model for live source receipts, callable schemas, Computer Use
permissions, and configured session limits; the UI must not infer these values
from run history.

The live Agent catalog excludes deterministic-only `workspace_file`,
`skill_lookup`, and `memory_lookup`. The live execution RPC has neither an
operator-authorized workspace root nor a selected skill/memory fixture store;
those adapters remain opt-in only in deterministic fixture contexts and must
not be advertised as empty-result live capabilities.

`AgentRunSnapshot.computer_use_session` is the separate durable, per-run
operator projection for an admitted Computer Use session. It is derived only
from bound structured adapter receipts, excludes the private session
capability, and remains attached while the run moves from a completed Computer
Use call into the next model turn. The active-run card may show only its typed
target app/window, session state, frame/action limit and usage, idle/absolute
deadline, permission/restart state, and last operation/result. Missing or
untrusted values are explicitly `unavailable`; the UI must not recover them by
parsing tool arguments, observation copy, or arbitrary status prose.

The operator read model reports target discovery separately from the target
array. It records `not_requested`, `ready`, `empty`, or `failed`, a bounded
typed error when discovery fails, and the observation time for each attempted
refresh. An empty successful discovery is therefore not interchangeable with a
broker, transport, timeout, or response-validation failure.

Computer Use currently supports only `get_permissions`, operator-only trusted
window discovery, `open_session`, `capture_frame`, `press_element`, and
`close_session`. The broker enumerates live on-screen windows, the operator
selects one in Chat, and the control plane revalidates and freezes that exact
process-launch/window identity into the run context. The public model schema
does not expose discovery or accept an `allowed_targets` allowlist; the control
plane injects the frozen target before approval and signing, and rejects later
capture/action targets outside that context. Text entry, key press,
scroll, pointer, coordinate fallback, Pause, and Take Over are not advertised.
Pause and Take Over remain gated on a dedicated resumable session state
machine. The private UDS transport validates its path, owner, mode, and inode,
and each non-handshake request carries both the private caller-verification
capability and an exact Ed25519 authorization. Capability comparison is
stateless and constant-time per RPC because anonymous UDS `remotePeer` values
can collapse to the shared server socket path and cannot identify a connection.
Handshake remains protocol negotiation and never unlocks later requests for a
peer key. Permission requests require the same two admission proofs. The current gRPC
UDS API does not expose an audit token for peer code-sign identity. The runtime
must publish that boundary as
`private_uds_signed_authorization_peer_code_identity_unavailable` and must not
describe this slice as complete Computer Use.

Execution authorization remains limited to 60 seconds. The worker refreshes a
session's retained revocation authorization only after the broker accepts an
exact same-owner session call carrying a strictly newer issue and expiry tuple;
rejected refreshes and equal-freshness conflicts cannot replace the retained
grant, while the broker accepts an expired grant only on its
session-cancellation endpoint and only for a bounded 15-minute grace period.
That cleanup-only grace covers the longest desktop Agent run without extending
capture, action, or close authority.

Worker execution and cancellation identities are retained in bounded,
process-local tombstone caches for a fixed one-hour retry horizon. The caches
fail closed at their 4,096-record default capacity unless an expired,
non-active record can be evicted. Run and call identifiers are globally unique
and are never reusable after that horizon; durable cross-restart terminal truth
remains owned by the control plane.

Run history currently exposes typed terminal summaries, failure attribution,
cancellation receipts, and bounded evidence references. Deterministic run
replay and a user-invoked evidence-export command are follow-on Slice 6 work;
they are not present in the current `AgentCommand` protocol or advertised by
the current Agents UI.

## Best End-State Architecture

Melix should have one agent loop and multiple execution adapters.

The Swift control plane owns the long-lived `AgentRun` state machine, model-turn
orchestration, tool admission, approval decisions, budgets, cancellation,
operator read models, and persisted receipts. The menu bar app renders and
commands that state; it does not execute tools.

Per-run event handling and the 100-millisecond coalesced snapshot flush share a
single serialization gate across persistence, terminal cleanup, and event
publication. A failed in-flight flush therefore wins before a queued terminal
event, makes later events inert, completes owner-bound cleanup, retries the
smaller failure snapshot once, and publishes only journal-failure terminal
truth. Cancellation drains that exact event stream before returning and embeds
the complete receipt into the terminal snapshot under the same gate. The
separately retained cancellation index is secondary and may be evicted without
changing get, list, restart, or repeated-cancel side-effect truth.

The Python worker owns tool execution truth. A deep `ToolExecutionRuntime`
interface hides built-in adapter execution, live MCP client lifecycle, result
normalization, timeout handling, and execution cancellation. The runtime
returns one normalized result and evidence envelope regardless of adapter.

An independent native `melix-computer-broker` process owns ScreenCaptureKit
and Accessibility access. The Python worker's Computer Use
adapter calls the broker through a typed local RPC. The broker never calls a
model, decides approval, or owns an agent run.

```text
macOS App
  | render run / approve / deny / stop
  | packaged XPC or private typed source-tree UDS
  v
Swift Control Plane
  single MELIX_HOME writer lease + daemon fencing generation
  AgentRunCoordinator
    | model turn
    | policy + approval
    | cancellation tree
    v
Python Worker ToolExecutionRuntime
    | deterministic adapters
    | live MCP adapters
    | Computer Use adapter
    v
Native Computer Use Broker
  ScreenCaptureKit + AXUIElement semantic press
```

The app-to-daemon transport never changes ownership: the final signed service
boundary uses XPC, while source-tree and packaged-preview launchers use the
generated private UDS service for handshake, commands, subscriptions, Chat
stream/cancel, and Agent start. The CLI selects that same daemon from an
explicit socket or the validated active-runtime descriptor; malformed explicit
configuration fails closed instead of creating another writer. Chat start
metadata has a bounded wait whose timeout cancels the transport and server
request. In every mode, the app and CLI have no worker or broker socket and no
Computer Use authorization key. MCP credential environment references are
resolved only by the Python tool worker; launchers construct the app, CLI,
probe, Swift worker, control-plane, and Computer Use broker environments from
a minimal reserved allowlist, backed by a bounded fail-closed active-config
resolver whose explicit path accepts only an absolute path or normalized
current-user `~` / `~/...` syntax. Each child role uses its own
declared environment contract. The Python worker receives only active-config
credential values present at worker startup; introducing a new source key is
restart-required and fails closed. The Python MCP runtime independently rejects
launcher-owned or other reserved process keys in typed stdio and HTTP source
definitions. Launcher, App, worker, and direct control-plane admission share a
bounded active-config contract: descriptor-bound regular file, at most 1 MiB,
no-follow/non-blocking final open with same-descriptor classification and bounded
read, FIFO/device/directory/final-symlink replacement refusal, duplicate-key,
non-standard-constant, and non-integer-number rejection, no explicit null for
known fields, depth at
most 128, at most 16,384 JSON value tokens and 8,192 object members, at most 256
sources, bounded unique worker-compatible source IDs, supported typed transport
shapes, and at most 1,024 credential references with 255-byte names and a
32,768-byte raw target-name list. Independently, static and referenced HTTP
header-name entries share a global 1,024-entry and 32,768-byte budget; an HTTP
reference counts against both budgets, and names within one transport are
unique case-insensitively. Credential-bearing HTTP headers are reference-only;
literal static values fail config admission before any child is forked.
The daemon holds one fail-fast
process-lifetime writer lease for `MELIX_HOME`; its fencing token is the daemon generation
exposed by handshake. The UDS mode is explicitly an interim local boundary
without XPC audit-token identity.

## Deep Module Interfaces

### Swift Agent Orchestration Seam

`AgentRunCoordinator` is the only public orchestration module for interactive
agent runs.

Its interface should remain small:

```swift
start(_ request: AgentRunRequest) async throws -> AgentRunExecution
decideApproval(_ decision: ApprovalDecision) async throws
cancel(runID: String, reason: AgentCancellationReason) async -> AgentCancellationReceipt
```

`AgentRunExecution` exposes a typed asynchronous event stream. Model adapters,
approval persistence, tool execution clients, clocks, and ID generation are
accepted dependencies and remain internal seams.

The run state machine is:

```text
created
  -> modelTurn
  -> waitingForApproval
  -> toolRunning
  -> modelTurn
  -> completed | failed | cancelled
```

A tool call is:

```text
requested
  -> waitingForApproval
  -> running
  -> completed | failed | cancelled
```

The coordinator must enforce:

- one stable `run_id`;
- one unique `call_id` per run;
- schema validation before approval or execution;
- request and tool budgets;
- no new provider turn or tool execution after cancellation becomes terminal;
- tool results correlated to the originating call and projected as untrusted
  prompt data;
- bounded retry nudges for recoverable malformed tool calls;
- sequential execution in the first live slice; parallel execution remains
  disabled until cancellation and approval semantics are proven.

### Authoritative Run Inventory And Retention

Safety reconciliation is separate from bounded run-history presentation.
`ListAgentRuns` exposes an explicit nonterminal-only query and an explicit
completeness bit. App startup, daemon reconnect, and selected-Chat hydration
use that complete nonterminal inventory and fail closed when it is unavailable,
corrupt, or incomplete; a count at the request limit is not itself evidence of
truncation. Bounded terminal history may be loaded independently for Chat and
Agents presentation. Clear Chat and Delete Chat remain fail-closed and
unavailable while the durable session-close boundary below is unimplemented;
the App must not substitute a list-then-cancel approximation.

A nonterminal run whose `session_id` still belongs to a known in-process Chat
is background work for that Chat: it remains visible and its own destructive
actions require exact receipt-backed cancellation, but it does not block an
unrelated selected Chat. A nonterminal run whose `session_id` belongs to no
known Chat is an orphan recovery conflict and blocks new Agent admission until
the operator reviews or stops it. Multiple or unknown nonterminal states in the
target Chat fail closed without choosing an arbitrary run.

The following destructive-session boundary is planned but remains explicitly
unimplemented pending operator authorization for permanent session-ID closure.
Deleting a Chat or clearing its transcript is a session mutation, not a
client-side list-then-act check. The control plane atomically and durably closes
Agent admission for the exact session, drains or cancels every admission/live
run, and returns a typed idempotent close receipt. The tombstone is permanent,
is recovered before any later Start admission, and is not part of run-history
retention. Delete removes the local Chat only after the receipt is safe (or the
operator explicitly verifies an indeterminate/committed side effect). Clear
keeps the visible Chat shell but replaces the old execution session and branch
with fresh unpredictable identities before accepting new work. This closes
both the second-client race after an apparently empty list and the stale
terminal-snapshot rehydration of a cleared transcript.

Durable snapshot retention never evicts a nonterminal run. It removes only
terminal snapshots, and a new identity fails closed when the configured bound
cannot be maintained without deleting live truth. Nonterminal inventory reads
also fail closed on an unreadable, corrupt, or identity-mismatched entry rather
than claiming a complete safe inventory.

### Python Tool Execution Seam

`ToolExecutionRuntime` owns:

```python
list_tools(context) -> ToolCatalogReceipt
execute(call, context, cancellation) -> ToolExecutionResult
cancel(run_id, call_id) -> ToolCancellationReceipt
cancel_run(run_id, owner) -> RunToolCancellationReceipt
```

Adapters are internal. The first real adapters are:

- existing deterministic built-ins;
- MCP stdio and streamable HTTP;
- Computer Use through the native broker.

All adapters must return the existing normalized observation and
untrusted-context evidence shapes. Live adapters add source, transport,
approval, timeout, and cancellation receipts without copying credentials,
private prompt text, raw hidden reasoning, or unbounded tool payloads.
Normalization applies the existing UTF-8-safe per-string limit and a
1,048,576-byte cap to the complete canonical serialized observation. Crossing
either boundary produces a typed truncation receipt; the global case preserves
only a deterministic canonical preview, original byte count, and payload hash.

### MCP Client Seam

`MCPClientManager` owns connection lifecycle per configured source:

```python
initialize(source) -> MCPServerCapabilities
list_tools(source) -> tuple[MCPToolDefinition, ...]
call_tool(source, request, cancellation) -> MCPToolResult
close(source) -> None
```

The implementation must support MCP initialization, protocol-version
negotiation, notifications, `tools/list`, `tools/call`, cancellation, timeout,
process exit, reconnect, and deterministic schema-change receipts. Stdio
servers run with explicit command vectors and a scrubbed environment.
Their stderr is untrusted and must not inherit the persisted worker log; the
initial implementation discards it and exposes bounded typed failures instead.
Streamable HTTP servers use explicit configured URLs and credential references;
credentials never enter catalog or run receipts.

Every inbound MCP message is bounded at the raw transport layer before UTF-8,
JSON, SSE, or Pydantic parsing. The initial limit is 20 MiB per stdio JSON line,
non-SSE HTTP response body, and SSE event. Streamable HTTP rejects an oversized
or conflicting `Content-Length`, bounds chunked bodies incrementally, and
requires identity content encoding so decompression cannot bypass the bound.
Wire-limit violations fail the source with `mcp_wire_limit_exceeded`; SDK
exception handling must not downgrade them to a generic timeout or connection
close.

Existing namespace-only `MCPToolCatalog` configuration is a compatibility input.
Live sources require an explicit transport block. A source without live
transport remains catalog-only and must be labeled as such.

### Approval Policy Seam

`ApprovalPolicyStore` owns durable policy and decision receipts. Policy is
evaluated in the control plane before execution.

The first policy levels are:

- `allow`: execute without a prompt;
- `ask`: require an explicit decision for every matching call;
- `deny`: fail closed without execution.

Matching inputs are tool source, canonical tool name, risk class, operation
kind, workspace scope, app bundle ID, and optional network host. The most
specific deny wins, then the most specific ask, then allow. Unknown tools,
schema changes, credential access, authentication actions, uploads, sends,
purchases, destructive mutations, process execution, and secure-field
interaction default to `ask` or `deny` according to their risk class.

An approval decision is bound to the exact run ID, call ID, tool schema digest,
argument digest, and policy revision. A changed argument or schema requires a
new decision.

The durable operator-decision journal is the approval command's commit
boundary. Deadlines are checked before that journal is written and before an
Always Allow policy CAS. After either durable mutation has committed, the
control plane must finish delivering that exact bound decision to the waiting
run instead of rechecking the RPC deadline and stranding a stale approval.

If the decision journal commits but the Always Allow policy CAS does not, the
receipt records `not_applied`, the current exact call continues through its
original binding, and the UI explicitly reports that the persistent rule was
not saved.

### Computer Use Broker Seam

The broker exposes typed RPCs:

```text
ListTargets
OpenSession
CaptureFrame
ExecuteAction
CancelSession
CloseSession
GetPermissions
```

Every session is bound to:

- an owner/run ID;
- an app bundle-ID allowlist;
- optional window IDs;
- an artifact root;
- a maximum frame/action budget;
- an idle and absolute deadline.

`ListTargets` is a signed, read-only operator path. It returns bounded live
identities composed of bundle ID, PID, process-launch identity, window ID, and
display title. A run may freeze zero or exactly one operator-selected window.
When a window is selected, the control plane re-lists and requires that exact
full identity to remain present in the current live inventory; the selected
singleton is not required to equal the entire multi-window inventory. An IPC
client or model cannot widen the run scope by supplying target fields or more
than one selected window.

Each signed `CaptureFrame` authorization binds the expected previous frame
generation. When that optional argument is absent, it means only the initial
generation `0`; it is never a wildcard. Reusing the same signed envelope with a
later protobuf generation must fail before frame capture and must not consume
the frame budget.

ScreenCaptureKit is the capture adapter. AXUIElement semantic press is the only
current action adapter. Coordinate-based CGEvent injection remains deferred;
adding it requires a new explicit policy, approval, freshness, focus, target,
and secure-field contract before it can be advertised.

The broker refuses:

- capture or action outside the allowlisted app/window scope;
- stale frame actions;
- semantic press when the commit-time AX locator is not exactly one, when the
  selected element is disabled or its `AXEnabled` state is unavailable, when
  it is a secure text field, or when it no longer supports `AXPress`;
- text containing credential or payment values supplied by the model;
- actions after cancellation or session expiry;
- unsupported Accessibility or Screen Recording permission states.

Once commit-time `AXPress` has been invoked, an adapter error is reported as a
failed action with a conservative committed side-effect projection. It must
never be downgraded to proof that no action occurred.

The broker writes bounded frame artifacts under its configured runtime
directory and returns artifact references plus hashes, never an unbounded image
history.

## Protocol Work

Authoritative protobuf schemas must add:

- agent run, tool call, tool result, approval request/decision, and cancellation
  receipt messages to the control-plane protocol;
- worker `ListAgentTools`, `ExecuteAgentTool`, and `CancelAgentTool` RPCs;
- a worker `CancelAgentRunTools` RPC that cancels every active call and revokes
  every adapter resource, including already-open Computer Use sessions, for the
  exact owner-bound run;
- Computer Use broker session, frame, action, permission, and cancellation RPCs.

Generated Swift and Python outputs must be regenerated with `make proto`.
First-party commands and events must remain typed; opaque JSON is permitted only
for schema-governed tool arguments and normalized result payloads.

Swift worker calls carry bounded gRPC timeouts: catalog and execution calls use
their typed absolute deadlines (30-second and 120-second fallbacks only when a
deadline is absent), while per-call cancellation and owner-bound run cleanup
use fixed 3-second and 5-second safety bounds. A stalled worker must therefore
return control to the cancellation tree rather than leaving Stop or terminal
cleanup suspended indefinitely.

## Product And UI Contract

Chat exposes user concepts, not protocol terminology:

- `Ask` means no tool execution;
- `Act` enables the agent runtime;
- capability chips show Tools, Computer, Local/Remote, and data-egress state;
- every tool call appears as a timeline card with source, risk, state, duration,
  bounded result summary, truncation state, typed failure stage, and inspectable
  redacted evidence;
- pending approvals show exact intended effect and independent Allow Once,
  Always Allow For This Tool, and Deny actions;
- generation exposes an independent Stop action only after end-to-end runtime
  cancellation is wired;
- Computer Use ships a receipt-backed Stop first. Pause and Take Over remain
  gated on a dedicated resumable session state machine and must not be aliases
  for generic run cancellation. Stop copy is bound to both cancellation
  disposition and side-effect state: only `accepted` plus `none` may say the
  session stopped before any side effect was reported; `already_terminal` and
  `too_late` remain distinct, while `committed` or `unknown` always require a
  warning and receipt review.
- Act revalidates a selected Computer Use window immediately before submission;
  stale selections are cleared without discarding the draft or starting a run.
- completed tools with unavailable evidence use warning copy and never render as
  execution failures.
- terminal evidence references use a bounded two-line presentation with full
  selectable/help/accessibility truth; they never introduce a nested horizontal
  scroll container that can stall transcript layout or accessibility traversal.
- validated approval arguments use bounded collapsed and expanded line limits,
  preserve their complete value through selection, help, and accessibility,
  and never introduce a nested vertical scroll container inside the transcript.
- ordinary Ask transcript bottom-follow uses an unanimated placement update.
  Agent run markers preserve the current viewport and never enter the
  programmatic scroll path; subsequent approval, evidence, cancellation, and
  status changes therefore cannot feed card-height changes back into scrolling.
- the transcript content uses a non-lazy vertical stack so completed and active
  Agent cards with changing heights are not repeatedly mounted at the viewport
  boundary. Future virtualization requires frozen terminal-card geometry or
  compact historical rows plus the same two-consecutive-run native acceptance.

An `Agents` destination contains:

- Tool Sources;
- Tool Sets;
- Approval Policies;
- Computer Use permissions and session limits;
- Run History.

The operator walkthrough artifact is
`.runtime/walkthrough/agent-control.html`. Accepted visual and interaction
decisions must be recorded in
`.runtime/walkthrough/agent-control-decisions.md` before broad SwiftUI edits.

## Delivery Slices

### Slice 0: Contract, Walkthrough, And Test Fakes

- update canonical architecture, runtime, protocol, and UI contracts;
- add this plan and the interactive walkthrough;
- define typed test fakes for model turns, tool execution, approvals, clocks,
  and Computer Use;
- register performance probes before hot-path implementation.

### Slice 1: Worker Tool Execution RPC And Real MCP Client

- add worker tool RPC protocol;
- expose existing deterministic built-ins through `ToolExecutionRuntime`;
- implement MCP stdio initialize/list/call/cancel/reconnect;
- implement streamable HTTP only after stdio lifecycle and cancellation tests
  pass;
- add an in-repository deterministic MCP fixture server for integration tests;
- persist redacted transport and result receipts.

### Slice 2: Real-Time Swift Agent Loop

- add `AgentRunCoordinator`;
- adapt local worker and OpenAI-compatible remote provider turns;
- preserve complete structured tool call IDs and arguments;
- execute admitted tool calls through the worker RPC;
- append normalized tool output and continue the next model turn;
- treat MCP `CallToolResult.isError = true` as a completed application-level
  result whose normalized observation has `status = failed`; append that
  correlated untrusted result for model self-repair, while transport, protocol,
  timeout, cancellation, and worker-runtime failures remain terminal;
- enforce a default maximum of eight tool calls, two healing nudges, and one
  active tool at a time;
- validate every complete argument object against the selected catalog schema
  before tool-budget accounting, approval evaluation, or execution;
- return recoverable malformed calls to the provider with a fixed user-role
  guardrail nudge that contains no rejected arguments, tool output, paths,
  URLs, or provider error text; the third rejection after two nudges is a
  typed terminal failure;
- persist run timeline and correlation receipts.

### Slice 3: Approval Policies And Reliable Cancellation

- add revisioned approval-policy persistence;
- add typed approval request/decision commands and read models;
- bind decisions to call and schema/argument digests;
- propagate one cancellation tree to model turn, approval waiter, tool RPC, MCP
  request/process, and Computer Use session;
- invoke owner-bound run cleanup on Stop from every coordinator state and on
  every normal terminal path, even when no tool call is currently active;
- serialize concurrent model-stream cleanup and explicit Stop through one
  per-execution cancellation flight so one transport is never cancelled twice;
- make cancellation idempotent and terminal;
- expose cancellation receipts and latency metrics.

### Slice 4: Native Computer Use Broker

- add the separate Swift executable and typed broker RPC;
- launch the control-plane and broker UDS endpoints from distinct
  current-user `0700` parents, keep the broker verification capability in the
  broker parent with mode `0600`, and preserve cross-runtime canonical path
  spelling;
- initialize the broker's headless AppKit runtime before ScreenCaptureKit
  target inventory so a CLI-launched broker cannot abort at the SkyLight
  initialization boundary;
- implement permission inspection;
- implement bounded trusted on-screen-window discovery with process-launch
  identity and exact target revalidation;
- implement window-scoped capture and artifact references;
- implement AX semantic actions;
- add stale-frame, focus, allowlist, secure-field, timeout, and cancellation
  guards;
- keep coordinate fallback and unsupported action modes unavailable;
- wire the Python Computer Use adapter through the broker client.

### Slice 5: Operator UI

- implement the accepted Chat `Ask`/`Act` and tool timeline design;
- add an explicit Computer Use window picker sourced from the live operator
  read model; distinguish not-requested, empty, failed, and stale-target states
  without auto-selecting;
- implement approval prompts and policy management;
- implement receipt-backed Stop and Computer Use permission repair; add Pause
  and Take Over only with a dedicated resumable session state machine;
- add Agents navigation and run history;
- keep pointer, keyboard, VoiceOver, and reduced-motion paths equivalent.

### Slice 6: Reliability, Evidence, And Release Gate

- add prompt-injection, tool-output poisoning, cross-owner replay, stale-schema,
  cancellation-race, reconnect, and broker permission suites;
- harden the packaged-preview launcher so every Unix-domain socket and broker
  trust file lives under one launcher-owned, unpredictable, current-user
  `0700` directory in `/tmp`, while metrics, bytecode caches, the active
  runtime descriptor, and other durable runtime artifacts remain under the
  configured `MELIX_RUNTIME_DIR`; validate every socket pathname against the
  macOS 103-byte limit before forking a service and remove only the exact
  launcher-owned socket directory during shutdown;
- add deterministic end-to-end fixtures and a live local MCP smoke;
- add a pinned Computer Use task suite with isolated test apps/windows;
- add deterministic run replay and user-invoked evidence export as a follow-on
  protocol and UI slice; this is not part of the current delivery boundary;
- complete full repository verification and native walkthrough evidence.

## Performance Probes And Success Metrics

### Agent Loop

- `agent.run.first_tool_call_ms`
- `agent.run.turn_transition_ms`
- `agent.run.tool_call_count`
- `agent.run.tool_admission_ms`
- `agent.run.healing_nudge_count`
- `agent.run.call_id_correlation_rate`
- `agent.run.terminal_duplicate_event_count`

Targets:

- 100 percent call-ID correlation;
- zero provider turns or tool starts after terminal cancellation;
- deterministic fake-adapter turn-transition p95 at or below 10 ms;
- deterministic JSON-schema admission p95 at or below 10 ms;
- no approval evaluation or tool execution for rejected calls;
- at most two healing nudges per run and no rejected arguments copied into a
  nudge;
- one terminal run event exactly.

The Swift control-plane observer measures `agent.run.tool_admission_ms` from a
completed model-turn projection to the first requested-tool, healing-nudge, or
typed terminal-admission projection. It measures
`agent.run.turn_transition_ms` from the final completed-tool or healing-nudge
projection to the next model-turn-start projection. These boundaries exclude
approval wait and tool execution time. `agent.run.healing_nudge_count` is the
exact per-run count observed from typed healing-nudge transitions.

### MCP

- `agent.mcp.initialize_ms`
- `agent.mcp.list_tools_ms`
- `agent.mcp.call_tool_ms`
- `agent.mcp.reconnect_count`
- `agent.mcp.cancel_propagation_ms`
- `agent.mcp.schema_change_count`

Targets:

- stdio transport overhead, excluding server work, p95 at or below 10 ms;
- cancellation reaches the MCP request/process within 250 ms in deterministic
  integration tests;
- zero silent schema changes;
- credentials absent from logs, receipts, and snapshots.

The Python worker owns these MCP measurements at typed manager boundaries.
`agent.mcp.initialize_ms`, `agent.mcp.list_tools_ms`, and
`agent.mcp.call_tool_ms` run from manager API admission through the typed result
or typed error. They therefore include server and response time and must not be
presented as transport-only overhead. `agent.mcp.reconnect_count` increments
only when a leased source has a non-live actor and the manager creates and
initializes its replacement. `agent.mcp.schema_change_count` increments only
for an observed catalog-digest transition or a typed schema-mismatch failure.

`agent.mcp.cancel_propagation_ms` is narrower than the general cancel API: it is
recorded only for an active call, from manager cancellation admission until the
local MCP SDK request task reaches its cancelled terminal. Queued cancellation,
not-found, scope-mismatch, and already-terminal receipts do not create a sample.
The worker bounds this acknowledgement wait at 250 ms and leaves the receipt
unacknowledged if a cancellation-resistant SDK task remains live.
This acknowledgement does not prove remote handler termination, process
termination, or reversal of server-side effects. The worker metrics export
stores the latest completed sample under each canonical `*_ms` key and also
publishes `.sample_count`, `.failure_count`, `.total_ms`, and `.max_ms`; a zero
sample count means that no qualifying lifecycle has completed.
Run-level cleanup cancels a local execution task only when that call's adapter
returns `accepted`; a `too_late` task remains live until its final observation
and execution receipt have been persisted.

The scoped `mcp-client-typed-lifecycle-dispatch` probe uses an in-process,
deterministic fake actor so it is fast, offline, and reproducible. It measures
manager dispatch and metrics-bookkeeping overhead only. The real stdio target
still requires the deterministic stdio fixture because the scoped probe is not
evidence for transport or server latency.

### Approval

- `agent.approval.wait_ms`
- `agent.approval.decision_propagation_ms`
- `agent.approval.required_count`
- `agent.approval.bypass_count`

Targets:

- 100 percent high-risk calls evaluated by policy;
- zero execution before a required approval;
- decision propagation p95 at or below 50 ms with the in-memory test store;
- zero approval reuse after argument, schema, or policy revision changes.

### Cancellation

- `agent.cancel.ui_to_control_plane_ms`
- `agent.cancel.control_plane_to_worker_ms`
- `agent.cancel.worker_to_adapter_ms`
- `agent.cancel.total_ms`
- `agent.cancel.late_event_count`

Targets:

- UI reflects Stop within 1 second;
- backend model/tool/broker cancellation completes or returns a typed
  best-effort failure within 2 seconds;
- one model-transport cancellation invocation per active model execution even
  when explicit Stop races stream-task cleanup;
- zero semantic stream events after the terminal cancellation event;
- repeated cancellation returns the same terminal receipt.

The Swift control plane owns `agent.cancel.late_event_count`: it increments only
when a non-terminal semantic transition arrives after that run's typed
`cancelled` terminal projection. It cannot accurately produce
`agent.cancel.ui_to_control_plane_ms` without a UI-origin timestamp and a
control-plane admission acknowledgement. The Python `ToolExecutionRuntime`
owns `agent.cancel.worker_to_adapter_ms`: it starts immediately before awaiting
an MCP or Computer Use cancellation adapter and stops on its typed receipt or
typed error. It counts only calls actually dispatched to those adapters and
excludes local not-found, scope-mismatch, already-terminal, and deterministic
built-in decisions. The Swift layer must not synthesize this value from the
broader control-plane cancellation round trip.

Interactive clients pre-bind an unpredictable run ID before `StartAgentRun`.
The control plane reserves it throughout catalog and target admission and keeps
the coordinator suspended until the initial durable snapshot is addressable.
Stop during this window returns a typed idempotent receipt immediately, closes
admission, and prevents any provider or tool execution without waiting for the
start reply.

### Computer Use

- `computer.capture_ms`
- `computer.action_ack_ms`
- `computer.stale_frame_refusal_count`
- `computer.scope_refusal_count`
- `computer.secure_field_refusal_count`
- `computer.cancel_propagation_ms`

Targets:

- window capture p95 at or below 250 ms on the local acceptance machine;
- semantic action acknowledgement p95 at or below 100 ms;
- 100 percent refusal for stale frame, out-of-scope window, and secure-field
  fixtures;
- zero actions after session cancellation.

### Packaged Preview Launch

The rendered-launcher and named-bundle acceptance probes record the maximum
socket pathname byte count, wall time to the existing worker/control-plane
readiness gates, and whether the exact socket root was removed. These are
release-evidence measurements rather than new resident product metrics.

Targets:

- every UDS pathname is at most 103 UTF-8 bytes even when the configured
  `MELIX_RUNTIME_DIR` is longer than that limit;
- the per-launch socket root is unpredictable, owned by the current user, mode
  `0700`, and never shared between launches;
- the control plane, both workers, and the Computer Use broker reach their
  existing readiness gates without moving metrics or operator state out of the
  configured runtime and home roots;
- normal exit and launcher failure remove the exact per-launch socket root and
  never remove a sibling launch directory.
- the outer bundle identifier resolves to exactly one regular AppKit process,
  the desktop UI; the AppKit-linked Computer Use broker resolves through its own
  nested background-only helper bundle and never shadows the UI during
  Accessibility lookup.

### Registered PR-Scoped Probes

`agent-worker-cancellation-computer-use` measures deterministic worker run
cancellation, idempotent retry, and the worker-to-Computer-adapter dispatch
boundary. Its focused gate also covers cancellation evidence, tombstone
horizons, authorization monotonicity, and the untrusted-schema validator cache.
The worker and MCP probes execute through the locked Python environment in both
base and head checkouts. Before the feature exists in the merge base, the base
probe emits only `feature_available_count = 0`; feature-specific base metrics
remain explicitly missing instead of being fabricated as zero-latency results.

`agent-runtime-control-surface` runs focused control-plane, native broker, and
desktop suites on macOS and reports each component's test wall time. That wall
time is a release-cost signal rather than a substitute for the runtime latency
measurements above. Its coverage command separately runs the full root,
control-plane, native-broker, and desktop suites, then binds Agent orchestration,
approval, Stop, target discovery, cleanup-only authorization, and desktop
presentation to one changed-file scope. Its changed-line gate compares the
separate CI base checkout with head, enforces at least 95 percent for every
selected measurable Swift package and for the aggregate, and reports any
non-measurable target explicitly. Because the real stdio MCP fixture and native
focus acceptance use isolated SwiftPM scratch trees, the versioned gate runs
both with Swift coverage enabled and merges their profiles into the owning
package profiles before measuring changed lines.
This keeps the guarded E2E test body measurable instead of treating its
environment-gated early return as coverage. A selected changed Swift file with
no coverage linkage now fails closed instead of silently contributing zero
lines. The two explicit `N/A` boundaries are the daemon and broker executable
entry files, `Bootstrap/main.swift` and `ComputerUseBrokerCLI/main.swift`:
SwiftPM test bundles do not link executable targets' `@main` boundaries. The
gate therefore requires named-runtime readiness, trust-root, writer-lease, and
shutdown acceptance for the daemon plus the broker `--version` and named
process acceptance, while all linked libraries remain subject to the 95
percent changed-line threshold. The Python implementation of this coverage
gate is itself held above 95 percent statement coverage.

## Verification

Focused verification grows by slice and culminates in:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

Every implementation commit must also include:

- focused red/green tests for the touched module interface;
- changed-scope coverage at or above 95 percent;
- a scoped metrics report;
- `git diff --check`;
- updated canonical docs when behavior changes.

The final acceptance additionally requires:

- a real stdio MCP fixture interaction through the worker RPC and Agent loop;
- approval allow, deny, changed-arguments, and policy-revision evidence;
- cancellation races at model, approval, MCP, and Computer Use stages;
- native UI pointer and keyboard walkthrough evidence;
- Computer Use permission-denied, capture, semantic action, stale-frame,
  session-cancellation, and Stop evidence on macOS.

## Release Evidence Matrix

| Requirement | Required evidence before release |
| --- | --- |
| Structured Function Calling continues the same run across model and tool turns | Control-plane coordinator and remote-provider suites covering complete call IDs, schema admission, correlated tool results, healing bounds, and one terminal event; `agent-runtime-control-surface` probe |
| Real MCP discovery and execution | Worker stdio and streamable-HTTP lifecycle suites; deterministic real stdio fixture through the worker RPC and Swift Agent loop; `mcp-client-typed-lifecycle-dispatch` probe |
| Durable approval policy and operator decisions | Approval policy store, exact binding, CAS, deadline, allow, deny, changed-arguments, and policy-revision suites; native approval prompt and policy-management walkthrough |
| Reliable cancellation | Concurrent explicit-call, run-wide, RPC-disconnect, provider, approval-waiter, MCP, and Computer Use cancellation races; idempotent terminal receipts; `agent-worker-cancellation-computer-use` and `agent-runtime-control-surface` probes |
| Signed Computer Use authorization | Authorized, forged, stale, replayed, wrong-owner, and cleanup-only-grace requests over the real private UDS; startup trust-root wiring; broker process and socket ownership/mode evidence |
| Computer Use execution boundary | Permission-denied, target discovery, exact target revalidation, capture, semantic press, stale-frame refusal, out-of-scope refusal, secure-field refusal, and session cancellation evidence on macOS |
| Approval and Computer Use UI | Current-run screenshots for Ask/Act, source and policy management, pending approval, active tool, Computer Use permission/target/session, Stop receipt, terminal history, keyboard focus, and reduced-motion states; every unavailable state must remain explicit |
| Generated contracts | `make proto` with no generated diff after regeneration |
| Changed-scope quality | At least 95 percent changed-line coverage for every measurable Swift package and at least 95 percent Python coverage for the touched worker and probe scope; explicit N/A evidence only for the daemon and broker executable `@main` boundaries, each backed by process-level acceptance |
| Repository release gate | `make bootstrap`, `make swift-test`, `make py-test`, `make integration-test`, `git diff --check`, scoped performance report, and a named-instance native stack walkthrough |

## Commit And Review Strategy

Use focused commits for:

1. contracts, plan, and walkthrough;
2. worker tool RPC and MCP;
3. Swift Agent loop;
4. approval and cancellation;
5. Computer Use broker;
6. UI;
7. reliability and release evidence.

Before the pull request is considered ready, review the complete
`origin/main...HEAD` diff on two independent axes:

- repository standards and architectural boundary conformance;
- this plan's requirement coverage and behavioral correctness.

The primary agent performs an integration review. A separate review-only agent
must perform the independent two-axis review and must not be one of the agents
that implemented the reviewed slice.

## Known Risks

- Screen Recording and Accessibility are user-granted macOS permissions.
  Permission absence must remain a repairable typed state, not be treated as a
  test failure or silently bypassed.
- The broker persists exclusive, fully synced preflight and commit-intent
  records before AX invocation, but it does not yet scan and reconcile those
  records automatically at startup. An orphaned commit intent must be treated
  as possibly executed.
- A Mac sleep or process suspension that outlives the 60-second execution grant
  plus the 15-minute cleanup-only grace can leave an expired broker session
  record until restart. The session's five-minute absolute deadline already
  prevents further capture or action, but an automatic broker expiry sweeper is
  still future hardening.
- Worker cancellation and execution tombstones remain process-local. A worker
  restart relies on the durable control-plane terminal journal and the
  never-reuse run/call identity contract; durable worker-side tombstones remain
  future hardening.
- The source-tree private UDS transport cannot attest peer code-sign identity.
  Packaged distribution still requires the final XPC or equivalent attested
  local boundary described by the architecture specification.
- Coordinate actions, typing, scrolling, Pause, and Take Over remain outside
  this delivery and must not be advertised as available.
