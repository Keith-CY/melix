# Melix Worker RPC Schema

Date: 2026-03-27

## Summary

This document defines the execution-plane protocol between the Melix control plane and Melix inference workers.

The protocol is:

- streaming-first
- phase-aware
- cache-aware
- model-family-neutral
- multimodal-ready
- quantization-aware

Workers are local execution engines. They are not public HTTP servers. The protocol is shared across worker implementations and is not tied to Python as an implementation language.

## Core Principles

In V1, the split is:

- the Swift control plane owns scheduling, session and branch state, EnginePool decisions, and cache metadata truth
- the default text hot path is expected to move toward a dedicated Swift text worker
- Python workers remain the broader execution layer for multimodal, retrieval, cache materialization, snapshot payloads, parser glue, and maintenance flows

Transport should use gRPC over Unix Domain Sockets with proto3 code generation shared across languages.

## Transport and Addressing

Recommended socket layout:

```text
/var/run/melix/
  controlplane.sock
  worker-text-001.sock
  worker-vision-001.sock
  worker-image-001.sock
```

The control plane should track at minimum:

- `worker_id`
- worker kind
- socket path
- capabilities
- worker state
- loaded model handles
- memory budget

Security rules:

- sockets are local-only
- workers do not listen on TCP
- large cache payloads are not sent inline through gRPC

## Schema Layout

Recommended proto split:

```text
packages/protocol/schema/worker/v1/
├─ common.proto
├─ runtime.proto
├─ inference.proto
├─ cache.proto
└─ maintenance.proto
```

Split by responsibility, not by frontend use case.

## Common Messages

Recommended base package:

```proto
syntax = "proto3";
package melix.worker.v1;
```

Core shared messages should include:

### ErrorStatus

- stable machine-readable `code`
- human-readable `message`
- retriable flag
- optional detail map

### ModelSpec

Should identify:

- model id
- model path
- model kind
- revision
- tokenizer hash
- quantization profile
- parser mode
- reasoning mode
- max context

### RuntimeCapabilities

`RuntimeCapabilities` should combine typed core capability groups with an extensible metadata layer.

Recommended direction:

```proto
message RuntimeCapabilities {
  CacheCapabilities cache = 1;
  ExecutionCapabilities execution = 2;
  ParserCapabilities parsing = 3;
  MultimodalCapabilities multimodal = 4;
  repeated Capability ext = 5;
}

message Capability {
  string name = 1;
  map<string, string> metadata = 2;
}
```

The typed core keeps policy decisions readable and type-safe. The `Capability` extension list covers future evolution without forcing every capability into booleans.

Core capability groups should express things such as:

- continuous batching support
- prefix, paged, and disk cache tiers
- KV quantization profiles
- boundary snapshot support
- speculative decoding support
- supported parser families
- supported multimodal surfaces

### CacheScope

Should isolate reusable cache by:

- model id
- revision
- tokenizer hash
- quantization profile
- prompt template hash
- parser mode
- reasoning mode
- multimodal adapter hash when relevant

`CacheScope` remains the descriptive scope boundary. It is not sufficient as the dedup key by itself.

### CacheKey

The worker schema should define a computable cache key layer on top of `CacheScope`.

Recommended direction:

```proto
message CacheKey {
  bytes prefix_hash = 1;
  bytes fingerprint_hash = 2;
  string scope_id = 3;
}
```

`prefix_hash` should identify the concrete reusable prefix. `fingerprint_hash` should identify the deterministic request fingerprint used for cache matching. `scope_id` should be the normalized identifier derived from `CacheScope`.

This is required for cross-session reuse and cache dedup without overloading `CacheScope` itself.

### SamplingConfig

Should carry:

- temperature
- top-p
- top-k
- frequency penalty
- presence penalty
- max output tokens
- stop sequences
- seed

### ReasoningConfig

Should carry:

- enabled flag
- parser choice
- separate-stream flag

### ToolConfig

Should carry:

- tool definitions
- schema format
- schema version
- toolset or registry version
- parser choice
- parser contract version
- tool choice policy

### ChatMessage

Should support:

- system
- developer
- user
- assistant
- tool

Message parts should support text plus inline or referenced media as needed.

Multimodal message parts should carry typed media metadata so routing and preprocessing do not rely on URI-vs-bytes inference alone. The schema should include:

- media type such as text, image, or audio
- source kind such as URI-backed or inline bytes
- MIME type and format hints
- size or duration metadata when known
- preprocessing hints such as image detail mode

### CacheHints

Should include:

- allow L1
- allow L2
- persist to L2
- prefer hot prefix
- save boundary snapshot
- restore snapshot id
- pinned prefix ids
- cache policy
- preferred block size

### RequestIdentity

Should include:

- `request_id`
- `session_id`
- `branch_id`
- `parent_request_id`
- `workflow_run_id`
- `workflow_node_id`
- `latency_class`

These fields are required for scheduling, cache affinity, and tool-follow-up recovery.

### SchedulingHints

The worker should receive explicit scheduling intent from the control plane even though the worker is not the global scheduler.

Recommended direction:

```proto
message SchedulingHints {
  int32 priority = 1;
  string lane = 2;              // text.decode.interactive / text.prefill.hot / text.prefill.background
  bool latency_sensitive = 3;
  uint32 queue_delay_ms = 4;
  uint32 queue_position = 5;
  string admission_policy = 6;
}
```

This prevents worker execution from becoming blind to latency-sensitive work, lane placement, and admission context.

### Admission and Acceleration Vocabulary

Phase-aware execution should use explicit typed vocabulary for admission and acceleration state.

Recommended direction:

```proto
enum AdmissionState {
  ADMISSION_STATE_UNSPECIFIED = 0;
  ADMISSION_QUEUED = 1;
  ADMISSION_ADMITTED = 2;
  ADMISSION_REJECTED = 3;
  ADMISSION_DROPPED = 4;
}

enum ExecutionPhase {
  EXECUTION_PHASE_UNSPECIFIED = 0;
  EXECUTION_QUEUED = 1;
  EXECUTION_ADMITTED = 2;
  EXECUTION_PREFILLING = 3;
  EXECUTION_DECODING = 4;
  EXECUTION_COMPLETED = 5;
  EXECUTION_ABORTED = 6;
  EXECUTION_FAILED = 7;
}

enum AccelerationMode {
  ACCELERATION_MODE_UNSPECIFIED = 0;
  ACCELERATION_MODE_BASELINE = 1;
  ACCELERATION_MODE_SPECULATIVE_DECODE = 2;
  ACCELERATION_MODE_ACCELERATED_PREFILL = 3;
  ACCELERATION_MODE_ACTIVE_KV_QUANTIZED = 4;
}

message AccelerationPolicy {
  AccelerationMode mode = 1;
  string profile_id = 2;
  string draft_model_id = 3;
  string prefill_hint = 4;
  string active_kv_quant_profile = 5;
  bool allow_baseline_fallback = 6;
  map<string, string> ext = 7;
}
```

This lets later Phase 2 milestones add speculative decode, accelerated prefill, and active-path KV quantization without inventing one-off request flags.

## Runtime Service

The runtime service manages lifecycle and model state.

```proto
service RuntimeService {
  rpc Handshake(HandshakeRequest) returns (HandshakeResponse);
  rpc LoadModel(LoadModelRequest) returns (LoadModelResponse);
  rpc UnloadModel(UnloadModelRequest) returns (UnloadModelResponse);
  rpc WarmupModel(WarmupModelRequest) returns (WarmupModelResponse);
  rpc GetRuntimeStats(GetRuntimeStatsRequest) returns (GetRuntimeStatsResponse);
  rpc ListLoadedModels(ListLoadedModelsRequest) returns (ListLoadedModelsResponse);
  rpc Drain(DrainRequest) returns (DrainResponse);
  rpc Shutdown(ShutdownRequest) returns (ShutdownResponse);
}
```

Recommended semantics:

- `LoadModel` returns a stable `model_handle`
- `RuntimeCapabilities` reported by the worker are authoritative
- `Drain` stops new admissions without forcing immediate process exit
- `Shutdown` may optionally flush L2 state

Runtime stats should include:

- worker state
- resident bytes
- active requests
- active prefills
- active decodes
- L1 and L2 cache bytes
- L1 and L2 hit rates

## Inference Service

Melix should support both end-to-end generation and explicit phase separation.

```proto
service InferenceService {
  rpc Generate(GenerateRequest) returns (stream GenerateEvent);
  rpc Prefill(PrefillRequest) returns (PrefillResponse);
  rpc Decode(DecodeRequest) returns (stream GenerateEvent);
  rpc Abort(AbortRequest) returns (AbortResponse);

  rpc Embed(EmbedRequest) returns (EmbedResponse);
  rpc Rerank(RerankRequest) returns (RerankResponse);
  rpc Transcribe(TranscribeRequest) returns (TranscribeResponse);
  rpc Speak(SpeakRequest) returns (SpeakResponse);
  rpc ImageGenerate(ImageGenerateRequest) returns (ImageGenerateResponse);
  rpc ImageEdit(ImageEditRequest) returns (ImageEditResponse);
}
```

The three RPCs should remain in V1, but they should not drift into three unrelated schemas. Melix should define one shared execution model underneath them so tracing, scheduling, metrics, and future extensions stay coherent.

Recommended direction:

```proto
message ExecutionMetadata {
  RequestIdentity id = 1;
  string model_handle = 2;
  CacheScope scope = 3;
  CacheKey cache_key = 4;
  SchedulingHints scheduling = 5;
  ToolConfig tool_config = 6;
  ReasoningConfig reasoning = 7;
  CacheHints cache_hints = 8;
  map<string, string> ext = 9;
}

message ExecutionMode {
  oneof mode {
    GenerateMode generate = 1;
    PrefillMode prefill = 2;
    DecodeMode decode = 3;
  }
}

message ExecuteEvent {
  string request_id = 1;
  string execution_kind = 2;    // generate / prefill / decode
  uint64 seq = 3;
  oneof payload {
    PrefillStarted prefill_started = 10;
    PrefillProgress prefill_progress = 11;
    TokenDelta token_delta = 12;
    ReasoningDelta reasoning_delta = 13;
    ToolCallDelta tool_call_delta = 14;
    UsageDelta usage_delta = 15;
    CacheDecision cache_decision = 16;
    BoundarySnapshotCreated snapshot_created = 17;
    Completed completed = 18;
    ErrorEvent error = 19;
    Heartbeat heartbeat = 20;
  }
}
```

`GenerateRequest`, `PrefillRequest`, and `DecodeRequest` should be thin typed wrappers over this shared model rather than three divergent request families.

### GenerateRequest

Should include:

- shared execution metadata
- chat messages
- sampling config
- streaming flag
- usage-return flag

### Shared ExecuteEvent

The streaming event model should support:

- prefill started
- prefill progress
- token delta
- reasoning delta
- tool-call delta
- usage delta
- cache decision
- boundary snapshot created
- completed
- error
- heartbeat

This allows the control plane to bridge events cleanly into SSE while preserving internal semantics.

### Prefill and Decode Split

`Prefill` should return:

- success or error
- `decode_handle`
- `block_table_id`
- `BlockTable`
- restored snapshot id when applicable
- prompt token count

`Decode` should accept:

- shared execution metadata
- `decode_handle`
- sampling config
- output token budget
- usage-return flag

This split is required for:

- chunked prefill
- checkpoint and resume
- tool-loop recovery
- interactive sticky slots
- future decode-path upgrades

The important fix is unifying the execution schema, not collapsing the service surface to one RPC.

### Abort

`Abort(request_id)` should be best-effort, but the worker must still conclude the stream with an explicit terminal event rather than silently disappearing.

### Other Modalities

V1 should support dedicated RPCs for:

- embeddings
- rerank
- transcription
- image generation
- image editing

These should not be forced through the text-generation path.

## Cache Service

Workers need a dedicated cache service so the control plane can inspect and mutate cache state without directly touching worker storage.

```proto
service CacheService {
  rpc GetCacheStats(GetCacheStatsRequest) returns (GetCacheStatsResponse);
  rpc PinPrefix(PinPrefixRequest) returns (PinPrefixResponse);
  rpc UnpinPrefix(UnpinPrefixRequest) returns (UnpinPrefixResponse);
  rpc SaveBoundarySnapshot(SaveBoundarySnapshotRequest) returns (SaveBoundarySnapshotResponse);
  rpc RestoreBoundarySnapshot(RestoreBoundarySnapshotRequest) returns (RestoreBoundarySnapshotResponse);
  rpc PurgeCache(PurgeCacheRequest) returns (PurgeCacheResponse);
}
```

Recommended capabilities:

- fetch L1 and L2 stats
- pin and unpin logical prefixes
- save boundary snapshots from active decode state
- restore a snapshot into a new decode handle
- purge by scope and tier

Important message concepts:

- `PrefixRef` identifies a logical prefix by scope and content hash
- `CacheKey` identifies a computable cache match target
- `snapshot_id` is a persistent boundary object
- `decode_handle` is a runtime handle
- `BlockTable` is the block-chain structure used for reuse and resume
- purge must support `l1`, `l2`, or `both`

Recommended cache structures:

```proto
message BlockTable {
  repeated BlockRef blocks = 1;
  repeated PageRef pages = 2;
  bytes prefix_hash = 3;
  string scope_id = 4;
  uint32 total_token_count = 5;
}

message BlockRef {
  string block_id = 1;
  int32 token_start = 2;
  int32 token_end = 3;
  uint64 bytes = 4;
}

message PageRef {
  string page_id = 1;
  repeated string block_ids = 2;
  uint32 token_start = 3;
  uint32 token_end = 4;
  uint64 bytes = 5;
}

message RestoreBoundaryRef {
  SnapshotRef snapshot = 1;
  bytes prefix_hash = 2;
  string scope_id = 3;
  string boundary_kind = 4;
}

message CacheRestorePlan {
  string plan_id = 1;
  RestoreBoundaryRef boundary = 2;
  string block_table_id = 3;
  BlockTable block_table = 4;
  repeated PageRef pages = 5;
  uint32 restored_token_count = 6;
  bool partial = 7;
  string tier = 8;
}
```

`block_table_id` is not enough on its own. The worker schema should define the structure that the identifier refers to, and restore metadata should carry typed boundary and page information rather than only opaque snapshot identifiers.

## Maintenance Service

Maintenance flows are product features, not shell-script afterthoughts.

```proto
service MaintenanceService {
  rpc ConvertModel(ConvertModelRequest) returns (stream ConvertModelEvent);
  rpc GetModelInfo(GetModelInfoRequest) returns (GetModelInfoResponse);
  rpc RunDoctor(RunDoctorRequest) returns (RunDoctorResponse);
  rpc RunBench(RunBenchRequest) returns (stream RunBenchEvent);
}
```

`GetModelInfoResponse` should expose supported modalities and supported task families so the control plane can surface OCR, VLM, transcription, and speech capability without guessing from the model id.

### ConvertModel

Should support:

- source model identifier or local path
- output directory
- weight quantization mode
- KV quantization mode
- manifest generation
- smoke-test request

Streaming events should expose:

- started
- progress
- manifest
- completed
- failed

### GetModelInfo

Should return:

- model kind
- max context
- supported parser families
- supported modalities

### RunDoctor

Should support cache and memory diagnostics and return a report payload suitable for local display or export.

### RunBench

Should stream progress and metrics for suites such as:

- ttft
- decode
- cache-hit
- tool-calling
- long-context

## Large Payload Rule

Melix should never move large cache payloads through RPC messages.

Wrong:

- serializing full prefix caches into gRPC messages
- returning large checkpoint blobs inline
- using protobuf `bytes` for multi-megabyte cache blocks

Right:

- send handles, descriptors, stats, and errors
- keep active payloads in worker memory
- keep durable payloads in SSD block and snapshot stores
- let the control plane reason about `block_table_id`, `snapshot_id`, scope, bytes, and last access time
- let the worker and control plane reason about `CacheKey` and `BlockTable` as typed structures, not only opaque ids

## Agent-Aware Request Identity

`RequestIdentity` is required because it determines:

- whether follow-up work belongs in a high-priority lane
- whether cache affinity should favor recent active blocks
- whether tool results resume against the correct boundary
- whether checkpoints belong to a session or a branch

Recommended intent:

- `session_id` identifies one conversation or agent run
- `branch_id` identifies a branch within that session
- `workflow_run_id` identifies a multi-request workflow run
- `workflow_node_id` identifies a step within that workflow

## Recommended Error Codes

### Runtime and Model

- `MODEL_NOT_FOUND`
- `MODEL_LOAD_FAILED`
- `MODEL_KIND_UNSUPPORTED`
- `MEMORY_BUDGET_EXCEEDED`
- `WORKER_DRAINING`

### Generation and Cache

- `DEADLINE_EXCEEDED`
- `DECODE_HANDLE_NOT_FOUND`
- `SNAPSHOT_NOT_FOUND`
- `CACHE_SCOPE_MISMATCH`
- `CACHE_CORRUPTED`
- `PREFIX_PIN_MISMATCH`

### Tool, Reasoning, and Format

- `TOOL_PARSE_FAILED`
- `REASONING_PARSE_FAILED`
- `UNSUPPORTED_RESPONSE_FORMAT`

### Multimodal

- `IMAGE_INPUT_INVALID`
- `AUDIO_INPUT_INVALID`
- `MODE_NOT_SUPPORTED`

## Streaming and Cancellation Semantics

### Streaming

`Generate` and `Decode` should use server streaming because:

- token and reasoning deltas must be ordered
- tool-call deltas fit naturally
- SSE bridging is straightforward
- cancellation maps cleanly to a single request

### Heartbeats

Long prefill, image, or other slow jobs must emit heartbeat events so the control plane can distinguish slow progress from a stuck worker.

### Abort

Abort is best-effort. Even when successful, the worker should emit either:

- a completed event with `finish_reason = "aborted"`
- or an explicit error event

Silent stream termination is not acceptable.

## Canonical Execution Flows

### Cold Text Request

1. Control plane loads model if needed.
2. Control plane dispatches generate.
3. Worker misses L1 and L2.
4. Worker performs prefill then decode.
5. Worker writes reusable state back to cache tiers.
6. Stream completes.

### Hot Follow-Up

1. Control plane dispatches a new request with scope and pin hints.
2. Worker restores from L1 or L2.
3. Worker prefills only new tokens.
4. Worker decodes and streams output.

### Tool Follow-Up Recovery

1. Worker emits tool-call deltas.
2. Control plane forwards tool semantics outward.
3. Boundary snapshot is saved around the tool handoff.
4. Tool result returns.
5. Control plane resumes by restoring boundary state and continuing execution.

## Why CacheService and Prefill/Decode Must Exist in V1

Melix should not wait for a future phase to model these explicitly.

Without `CacheService`:

- the control plane has no clean way to inspect or purge worker cache state
- or it is forced to touch worker storage directly

Without `Prefill` and `Decode`:

- chunked prefill becomes awkward
- tool recovery becomes fragile
- queueing policies cannot distinguish phase types cleanly
- future scheduler evolution gets boxed in by an overly thin API

Without a shared execution model underneath them:

- tracing splits across unrelated request shapes
- metrics schemas drift by RPC
- scheduler intent cannot be expressed consistently
- future expansion becomes additive duplication instead of extension

## Anti-Patterns

Melix should avoid:

- exposing a separate public HTTP server inside each worker
- letting workers own global session truth
- letting workers choose global model eviction policy
- collapsing all modality, parse, and cache behavior into one untyped payload
- supporting only end-to-end `Generate` with no phase-aware path
- leaving quantization and maintenance flows as shell-only scripts
