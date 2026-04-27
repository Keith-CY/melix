# Melix Control Plane Protocol

Date: 2026-03-27

## Summary

This document defines the protocol between the native macOS app surfaces and the Melix control plane daemon. It also defines the core command, reply, snapshot, and event model used internally by the control plane.

The protocol is:

- Swift-native in transport choice
- XPC-first for local app-to-daemon communication
- schema-driven and versioned
- event-oriented
- compatible with richer internal semantics than the public HTTP layer

This is not the worker execution protocol. Worker RPC is defined separately.

## Scope

The control plane protocol covers three interaction layers:

1. Menu bar app and dashboard to control plane daemon over XPC
2. CLI or other local frontends to control plane daemon through the same schema model
3. Internal domain messages for server state, model state, cache state, sessions, requests, and operations

The public HTTP API remains separate. The control plane must map those requests into this richer command model rather than mirror public request shapes one-to-one.

## Transport Choices

### App to Daemon

The native app should talk to the daemon through `NSXPCConnection`.

Reasons:

- the app is long-lived and local
- XPC supports bidirectional communication
- the daemon should remain distinct from the UI process
- macOS code-signing validation can be enforced on the connection

### Payload Encoding

XPC should transport opaque `Data` payloads containing protobuf bytes rather than large trees of custom Swift classes.

Reasons:

- versioning stays explicit
- one schema model can serve UI, CLI, tests, and code generation
- transport concerns stay separate from message contracts
- the protocol surface stays small

## Naming

Melix should standardize these identifiers:

```text
com.melix.app
com.melix.controlplane
com.melix.controlplane.xpc
```

The app initiates the XPC connection. The dashboard remains a window owned by the app rather than a separate process.

## Responsibilities

### Control Plane Daemon

The daemon owns:

- local HTTP gateway behavior and request translation
- request admission
- queue coordination
- session and branch truth
- model lifecycle and EnginePool
- cache metadata summaries and indices
- worker discovery and health
- metrics, logs, diagnostics, and benchmark orchestration

### macOS App

The app owns:

- state presentation
- user-triggered actions such as pin, warmup, unload, purge, and preset apply
- event subscription and UI state diffing
- local settings and operational affordances

The app must not directly reach workers or cache internals.

## Protocol Style

The protocol has two message classes:

### Command and Reply

Commands:

- carry `request_id`
- may carry `idempotency_key`
- may carry deadlines
- return typed success or failure

Replies:

- preserve the original request identifier
- include explicit error payloads
- return a typed payload family rather than raw ad hoc JSON

### Event Stream

Events:

- belong to a `subscription_id`
- carry monotonic `seq`
- support reconnect by `last_seen_seq`
- carry normalized routing and causality metadata
- represent state changes or progress, not full source-of-truth snapshots

## Envelope Model

The control plane should use normalized envelopes with typed protobuf bodies.

Melix should not replace the core protocol with an untyped `bytes payload` or `google.protobuf.Any` envelope for first-party commands. The app, daemon, CLI, and tests are all controlled by the same product, so typed bodies are more useful than a fully dynamic dispatch layer:

- schema evolution stays explicit
- generated client code stays valuable
- compatibility checks remain mechanical
- command discovery remains readable in the protocol itself

If Melix later needs plugin-style extensibility, it can add a dedicated extension branch. Core commands and events should remain typed.

Recommended schema family:

```proto
syntax = "proto3";

package melix.controlplane.v1;

message HandshakeRequest {
  string protocol_version = 1;
  string app_version = 2;
  string bundle_id = 3;
  string client_instance_id = 4;
  string ui_capabilities = 5;
}

message HandshakeResponse {
  string protocol_version = 1;
  string server_version = 2;
  string daemon_instance_id = 3;
  repeated string features = 4;
  ServerSnapshot snapshot = 5;
}

message ControlPlaneRequest {
  string request_id = 1;
  string actor_id = 2;
  string command_type = 3;      // model.pin / cache.purge / ops.run_bench
  string idempotency_key = 4;
  int64 deadline_unix_ms = 5;
  string correlation_id = 6;
  string causation_id = 7;
  string target_id = 8;         // optional model_id / session_id / request_id

  oneof command {
    ServerCommand server = 20;
    ModelCommand model = 21;
    CacheCommand cache = 22;
    SessionCommand session = 23;
    OpsCommand ops = 24;
    PresetCommand preset = 25;
  }
}

message ControlPlaneResponse {
  string request_id = 1;
  string command_type = 2;
  bool ok = 3;
  ErrorStatus error = 4;
  string correlation_id = 5;
  string causation_id = 6;

  oneof payload {
    ServerReply server = 20;
    ModelReply model = 21;
    CacheReply cache = 22;
    SessionReply session = 23;
    OpsReply ops = 24;
    PresetReply preset = 25;
  }
}

message ControlPlaneEvent {
  string event_type = 1;        // model.state_changed / request.progress / cache.stats_changed
  string source = 2;            // scheduler / engine_pool / cache_index / worker_registry
  string correlation_id = 3;
  string causation_id = 4;
  string request_id = 5;
  string actor_id = 6;
  string subscription_id = 7;
  uint64 seq = 8;
  int64 emitted_at_unix_ms = 9;

  oneof payload {
    ServerStateChanged server_state = 20;
    WorkerStateChanged worker_state = 21;
    ModelStateChanged model_state = 22;
    RequestProgressEvent request_progress = 23;
    SessionStateChanged session_state = 24;
    CacheStatsEvent cache_stats = 25;
    BenchmarkProgressEvent bench_progress = 26;
    LogEvent log = 27;
    Heartbeat heartbeat = 28;
  }
}
```

`command_type` and `event_type` are normalized routing and observability fields. Typed bodies remain authoritative for schema shape.

## XPC Interface

The XPC layer should stay intentionally thin.

```swift
@objc public protocol MelixControlPlaneXPC {
    func handshake(
        _ requestData: Data,
        withReply reply: @escaping (Data?, NSError?) -> Void
    )

    func execute(
        _ requestData: Data,
        withReply reply: @escaping (Data?, NSError?) -> Void
    )

    func subscribe(
        _ requestData: Data,
        sink: MelixControlPlaneEventSinkXPC,
        withReply reply: @escaping (Data?, NSError?) -> Void
    )

    func unsubscribe(
        _ requestData: Data,
        withReply reply: @escaping (Data?, NSError?) -> Void
    )
}

@objc public protocol MelixControlPlaneEventSinkXPC {
    func onEvent(_ eventData: Data)
    func onClose(_ terminalData: Data)
}
```

This preserves transport simplicity while leaving schema evolution in protobuf.

## Command Families

### ServerCommand

Used for:

- start, stop, or restart
- fetching server snapshot
- setting global policy such as default model, port, budgets, or log level

### ModelCommand

Used for:

- listing models
- loading and unloading
- pinning and unpinning
- warmup
- model-scoped policy updates

### CacheCommand

Used for:

- fetching cache snapshot
- purging cache by scope or tier
- pinning and unpinning prefixes
- saving and restoring checkpoints

### SessionCommand

Used for:

- creating sessions
- creating branches
- closing sessions
- getting session and branch graph state
- registering tool results
- resuming after a tool boundary

### OpsCommand

Used for:

- tailing logs
- running diagnostics
- running benchmarks
- exporting diagnostics bundles
- canceling requests
- reading metrics snapshots

### PresetCommand

Used for:

- listing presets
- applying presets
- exporting presets
- importing presets

## State Models

The control plane should represent at least these states:

### ServerState

- booting
- ready
- degraded
- draining
- stopped
- failed

### WorkerState

- starting
- idle
- busy
- saturated
- draining
- exited
- crash loop

### ModelState

- discovered
- loading
- warm
- pinned
- evicting
- unloaded
- failed

### RequestPhase

- queued
- prefilling
- decoding
- tool-wait
- checkpointing
- completed
- aborted
- failed

## Scheduler Read Models

Scheduler behavior is core control-plane behavior and must be visible through protocol state, not left as an implementation-only concern.

### QueueSummary

Recommended fields:

```proto
message QueueSummary {
  repeated QueueLaneSummary lanes = 1;
  uint32 queued_requests = 2;
  uint32 active_requests = 3;
  double admission_latency_ms = 4;
  double backpressure = 5;
  uint32 admitted_requests = 6;
  uint32 rejected_requests = 7;
}

message QueueLaneSummary {
  string lane_id = 1;           // text.decode.interactive / text.prefill.hot / text.prefill.background
  uint32 queued_requests = 2;
  uint32 active_requests = 3;
  double queue_delay_ms_p50 = 4;
  double queue_delay_ms_p95 = 5;
  double admission_rate = 6;
  double backpressure = 7;
  string lane_class = 8;
  double priority_score = 9;
}
```

Default lane identities should already be meaningful before the full Phase 2 scheduler lands:

- `text.decode.interactive`
- `text.prefill.hot`
- `text.prefill.background`

### RequestProgressEvent

Recommended request-progress fields should include more than phase changes:

- request phase
- assigned lane
- queue delay
- priority score
- admission state
- queue position
- decode handle when one exists
- acceleration mode and acceleration profile
- backpressure at decision time
- active model handle or worker id when known

This gives the menu bar app and diagnostics tools a direct view into scheduler decisions without exposing the scheduler implementation itself.

## Session Read Models

Agent workloads require branch-aware state, not a flat session placeholder.

### SessionState

Recommended fields:

```proto
message SessionState {
  string session_id = 1;
  repeated BranchState branches = 2;
  string active_branch_id = 3;
  string latest_request_id = 4;
  string latest_checkpoint_id = 5;
  string latest_snapshot_id = 6;
}

message BranchState {
  string branch_id = 1;
  string parent_branch_id = 2;
  string head_request_id = 3;
  string head_checkpoint_id = 4;
  string resume_snapshot_id = 5;
  string last_tool_call_id = 6;
}
```

This is the minimum shape needed to represent branch graphs, tool boundaries, and replay or resume metadata.

## Cache Read Models

The control plane should expose cache keys and references, not only aggregate cache statistics.

### CacheKey and References

Recommended fields:

```proto
message CacheScopeKey {
  string model_id = 1;
  string revision = 2;
  string tokenizer_hash = 3;
  string quant_profile_id = 4;
  string prompt_template_hash = 5;
  string parser_mode = 6;
  string reasoning_mode = 7;
  string reasoning_effort = 8;
  string tool_parser_mode = 9;
  string structured_output_mode = 10;
  string chat_template_kwargs_hash = 11;
  bool reasoning_continuity_present = 12;
}

message CacheKey {
  bytes prefix_hash = 1;
  CacheScopeKey scope = 2;
}

message CacheBlockRef {
  string block_id = 1;
  uint32 token_length = 2;
  uint64 bytes = 3;
}

message SnapshotRef {
  string snapshot_id = 1;
  uint32 token_boundary = 2;
}
```

The control plane should expose logical cache identity and reference chains for inspection and scheduling. Payload data stays worker-side.

Reasoning mode, effort, parser mode, structured-output mode, effective template kwargs, and reasoning-continuity presence are cache compatibility inputs. Hash fields such as `chat_template_kwargs_hash` and the legacy `melix.cache.fingerprint.chat_template_kwargs` mirror store the lowercase SHA-256 hex digest of the canonical JSON input, or an empty string when the input is absent. A prefix generated under one of those settings must not be treated as equivalent to a prefix generated under a different setting unless an explicit downgrade policy says so.

## Structured Text Streaming

The shipped text HTTP surfaces are stream-first: Chat Completions, Completions, Responses, and Messages normalize into one worker `GenerateRequest` shape. Native Ollama `/api/*` routes and new non-stream behavior are outside this contract.

Reasoning policy is resolved once in the Swift request layer. Precedence is:

1. Top-level request flags: `enable_thinking` and `reasoning_effort`
2. Effective `chat_template_kwargs`
3. Messages `thinking`
4. Preset, model, or operator defaults
5. Model-family auto-detect
6. Tool or structured-output suppressions

The resolved execution metadata includes:

- `melix.reasoning.mode`
- `melix.reasoning.mode_source`
- `melix.reasoning.source` as a compatibility alias for `melix.reasoning.mode_source`
- `melix.reasoning.effort`
- `melix.reasoning.auto_detect_model_family`
- `melix.reasoning.continuity_rehydrated`
- typed `ReasoningConfig.mode`, `mode_source`, `effort`, `auto_detect_model_family`, and `continuity_rehydrated`

Workers preserve raw generation text separately from public content. Stream assembly is request-local and reads `raw_text` when available, otherwise `text`. It emits only unseen tails and separates three channels:

- `TokenDelta` for public assistant content
- `ReasoningDelta` for hidden reasoning stream material
- `ToolCallDelta` for parsed tool-call fragments

Malformed or truncated tool fragments are recoverable parser observations. They should increment parser metrics and be skipped rather than fail the request. Display cleanup is not structural parsing; cleanup must not collapse meaningful leading or trailing content whitespace and must not re-emit generation-prefix control tokens.

JSON-only structured-output requests without explicit tools suppress generic model-default tool parsing. The worker must not validate or output reasoning preambles as JSON content; any reasoning prefix is stripped before structured-output validation.

Session reasoning continuity is stored inside control-plane runtime state keyed by session, branch, and request. Follow-up turns receive continuity markers through execution metadata and effective template kwargs, not raw hidden text. Public session state, SSE content output, and operator-visible metadata must not contain raw hidden reasoning.

## Resource Read Models

Resource state should be observable in the control-plane protocol because model lifecycle, scheduler admission, and UI affordances all depend on it.

### ResourceSnapshot

Recommended fields:

```proto
message ResourceSnapshot {
  double cpu_util_pct = 1;
  double gpu_util_pct = 2;
  uint64 memory_used_bytes = 3;
  uint64 memory_total_bytes = 4;
  uint64 memory_budget_bytes = 5;
  uint64 metal_active_bytes = 6;
}
```

`WorkerSummary` and `ServerSnapshot` should include resource snapshots so the UI can surface resource pressure without inferring it indirectly from errors.

## Snapshots and Summaries

### ServerSnapshot

The first UI render should be driven by a full server snapshot, not by waiting for incremental events.

Recommended fields:

- overall server state
- worker summaries
- model summaries
- queue summary
- cache summary
- active sessions summary
- resource snapshot
- metrics summary
- recent errors

### WorkerSummary

Should include:

- worker identifier
- worker kind
- worker state
- loaded model handles
- inflight request count
- active prefill and decode counts
- resource snapshot
- recent health or crash-loop signals

### ModelSummary

Should include:

- model identifier
- model kind
- current state
- pin status
- inflight request count
- estimated resident memory
- quantization profile
- maximum context
- supported features

### CacheSummary

Should include:

- L1 bytes
- L2 bytes
- L1 hit rate
- L2 hit rate
- dedup ratio
- pinned-prefix hit rate
- checkpoint count
- hot cache keys or prefix references for inspection views

## Subscription Model

Recommended subscription request shape:

```proto
message SubscribeRequest {
  string client_instance_id = 1;
  string last_subscription_id = 2;
  uint64 last_seen_seq = 3;
  repeated EventTopic topics = 4;
}
```

Recommended topics:

- server
- worker
- model
- request
- session
- cache
- resource
- benchmark
- log

Design rules:

- the daemon issues the authoritative `subscription_id`
- `seq` must be monotonic within a subscription stream
- reconnect must support `last_seen_seq`
- the UI should treat snapshots as source of truth and events as incremental hints

## Deadlines, Idempotency, and Cancellation

### Idempotency

All state-changing commands should support:

- `request_id`
- `idempotency_key`

This protects against retries, reconnects, and repeated clicks from the UI.

### Deadlines

Commands may carry `deadline_unix_ms`.

The control plane should:

- reject work that has not started by the deadline
- attempt cancellation for expired work in flight
- emit terminal request progress when expiration leads to abort or failure

### Cancellation

Cancellation should be expressed as a normal command, not as a special XPC side channel.

The control plane then maps that request to worker abort semantics.

## Security Model

Recommended controls:

- app validates daemon signing requirements
- daemon validates caller bundle or team identity
- development builds may allow a narrow local whitelist
- permissions remain split by process role

The app should not inherit worker-level file access unnecessarily.

## Mapping from Public HTTP APIs

The control plane protocol is richer than the public HTTP surface, but it must map cleanly from it.

| Public API | Control plane intent |
|---|---|
| `POST /v1/chat/completions` | parse request, bind session context, dispatch to scheduler |
| `POST /v1/responses` | translate response semantics into internal request plus event stream |
| `POST /v1/messages` | normalize messages, reasoning, and tool semantics |
| `POST /v1/embeddings` | dispatch directly to embed-capable workers |
| `POST /v1/rerank` | dispatch directly to rerank workers |
| `POST /v1/images/generations` | route to image workers outside text queues |
| `GET /v1/models` | aggregate from model catalog and EnginePool |
| `/admin/*` | expose local operational state from the same control plane truth |

## Minimal UI Interaction Flows

### Startup

1. App launches.
2. App validates helper state.
3. App opens XPC connection.
4. App sends `HandshakeRequest`.
5. App receives `ServerSnapshot`.
6. App creates event subscription.

### Pin Model

1. User selects pin.
2. UI sends `ModelCommand.PinModel`.
3. Control plane updates EnginePool.
4. Control plane loads the model if needed.
5. Control plane emits `ModelStateChanged`.

### Purge Cache

1. UI sends `CacheCommand.PurgeCache`.
2. Control plane locks affected scopes.
3. Control plane instructs workers to purge payloads.
4. Control plane updates metadata state.
5. Control plane emits cache stats change.

## Recommended Swift Client Surface

```swift
public protocol ControlPlaneClient {
    func handshake() async throws -> HandshakeResponse

    func execute(_ request: ControlPlaneRequest) async throws -> ControlPlaneResponse

    func subscribe(
        _ request: SubscribeRequest
    ) async throws -> AsyncThrowingStream<ControlPlaneEvent, Error>
}
```

Suggested state holders:

- `ServerSnapshotStore`
- `ModelListViewModel`
- `SessionGraphViewModel`
- `CacheInspectorViewModel`
- `LogsViewModel`
- `PresetViewModel`

Each view model should depend only on the client facade, not on worker or storage details.

## V1 Required Commands and Events

Required commands:

- `GetServerSnapshot`
- `GetSessionState`
- `ListModels`
- `LoadModel`
- `UnloadModel`
- `PinModel`
- `UnpinModel`
- `WarmupModel`
- `GetCacheSnapshot`
- `PurgeCache`
- `TailLogs`
- `GetMetricsSnapshot`
- `RunDoctor`
- `RunBench`

Required events:

- `ServerStateChanged`
- `WorkerStateChanged`
- `ModelStateChanged`
- `RequestProgressEvent`
- `SessionStateChanged`
- `CacheStatsEvent`
- `ResourcePressureEvent`
- `LogEvent`

## Anti-Patterns

Melix should avoid:

- direct app reads from cache databases
- direct app-to-worker communication
- large trees of custom Swift classes over XPC
- one XPC method per feature
- duplicated truth between UI and daemon
- workflow orchestration logic embedded into the control plane protocol itself
