# Backend Model Identity Enforcement

## Goal

Fail closed at the worker boundary when a dispatched inference request does not
match the model and adapter identity that the selected backend actually loaded.
Stale handles, reused sockets, and unload/reload races must not let a healthy
but wrong backend emit model output.

This plan governs issue #2945 and its watch notes from 2026-07-21 and
2026-07-26. It extends the multi-model server router in
`docs/plans/2026-05-14-multi-model-server-router.md` without changing model
selection UX or introducing a distributed serving system.

## Current-State Audit

The current worker protocol selects loaded state with `model_handle` only.
`ExecutionMetadata`, `EmbedRequest`, `RerankRequest`, `TranscribeRequest`,
`SpeakRequest`, `ImageGenerateRequest`, and `ImageEditRequest` do not carry an
untranslated requested model identity, adapter identity, or route generation.

The Swift control plane owns model admission and route selection. It can check
whether a remembered handle is present through `ListLoadedModels`, but presence
does not prove that a restarted process or reused endpoint loaded the requested
model. `WorkerRegistry.admitInferenceRoute` also uses a constant selection
snapshot identifier and `ModelCatalog` stores handles without a generation.

The Python worker records the resolved `ModelSpec` in each `LoadedModel`, and
the Swift text worker records the resolved `ModelSpec` in each
`LoadedModelRecord`. Both therefore have backend-owned load-time model and
adapter evidence, but neither compares it with a separate request identity
before inference work begins.

The production-dispatched inference surface is:

| Task | Request modalities | Worker RPC | Runtime owner |
|---|---|---|---|
| Text generation and tool-adjacent generation | text | `Generate` | Swift text or Python compatibility |
| Multimodal generation and OCR | text plus image or video | `Generate`; VLM `Prefill`/`Decode` when selected | Swift vision or Python VLM/OCR |
| Embedding | text | `Embed` | Python embedding |
| Reranking | text | `Rerank` | Python rerank |
| Transcription | audio, optional text instruction | `Transcribe` | Python transcription |
| Speech | text | `Speak` and `SpeakStream` | Python speech |
| Image generation | text | `ImageGenerate` | Python image |
| Image editing | text plus image | `ImageEdit` | Python image |

There is no tokenizer inference RPC in the production protocol. Tokenization
that can produce request output is part of `Generate` or phase-aware
`Prefill`/`Decode`, so those seams carry and enforce the same identity. Tool
parsing is likewise part of the generation stream rather than a separately
scheduled backend RPC.

The control plane currently connects to fixed worker clients. It has no
request-path process supervisor that can spawn a replacement process. Recovery
in this issue therefore means invalidating a route binding, coalescing one
fresh model binding/load decision, and redispatching to a newly selected ready
worker. Process supervision remains outside this plan; tests must not label a
model rebind as a process respawn.

## Public Test Seams

The issue contract and implementation assignment confirm these observable
test seams:

1. Generated worker protobuf messages for load and inference identity.
2. Python and Swift worker RPC service boundaries, before runtime execution.
3. Control-plane route binding and invalidation APIs.
4. Control-plane inference dispatch for streaming and unary RPCs.
5. Worker runtime stats and control-plane metric snapshots.
6. HTTP and XPC production entrypoints that build worker requests.

Tests may script the external worker transport boundary. They must not mock
private parser, runtime, or registry collaborators merely to assert call order.

## End-State Architecture

### Protocol identity

Add one shared worker-protocol message with:

- `requested_model_id`: the public/catalog identity exactly as admitted by the
  control plane, never a rewritten local model path;
- `requested_adapter_id`: the active adapter identity, using the model's
  `melix.adapter_set_hash` when present and the empty string for no adapter;
- `route_generation`: a positive generation owned by the control plane for one
  model and worker route binding;
- `worker_instance_id`: the exact backend-owned identity returned by the
  selected route's health handshake.

`LoadModelRequest` carries the binding identity used to create backend-owned
loaded state. Every inference request carries the requested identity. Generate,
Prefill, and Decode use `ExecutionMetadata`; all unary and speech-stream
requests carry the same message directly. Generated Swift and Python artifacts
must come only from `make proto`.

### Backend-owned loaded identity

Python `LoadedModel` and Swift `LoadedModelRecord` retain a normalized immutable
loaded identity captured at load time. Model and adapter identifiers come from
the worker's resolved `ModelSpec`; only the positive route generation comes
from the control-plane binding, while the worker instance comes from the running
backend itself. The worker therefore cannot relabel a resolved model by copying
inconsistent identifiers from the load envelope. It compares
the inference request against this record at the RPC service boundary before
acquiring a runtime lease, preprocessing media, tokenizing, decoding, or
invoking any model code.

All four components must match exactly. A missing or zero request identity is a
typed `model_identity_missing` contract failure. A different model, adapter,
generation, or worker instance is a typed `model_identity_mismatch` with no
token, audio, image, embedding, rank, transcription, tool, usage, or completed
payload.

### Route generations and invalidation

`ModelCatalog` owns a positive monotonically increasing generation for each
model/route binding. A load attempt reserves the current generation; successful
load records the handle and generation atomically. Explicit unload, failed
load, missing-handle validation, and identity mismatch invalidate the matching
binding and advance the generation. A stale completion may not publish a handle
after a newer invalidation or explicit unload. Recovery uses the invalidation
receipt generation as a compare-and-swap precondition for reload reservation,
so unload in that interval cannot reopen the route.

All inference request builders obtain one immutable binding receipt containing
model ID, adapter ID, route kind, handle, generation, and worker instance. They
stamp the worker request from that receipt instead of assigning `model_handle`
independently.

### Replay-safe recovery

A shared control-plane dispatch coordinator classifies both worker error
payloads and transport failures. It may perform at most one recovery attempt
when all of the following are true:

- no backend response event, header-equivalent stream acceptance, token,
  audio chunk, image artifact, embedding/rank/transcription response, usage
  payload, completed tool action, or completion has been exposed;
- the failure is an identity mismatch or a transport connect, read, write,
  protocol, or timeout failure before the response opens;
- the original binding is still the catalog's active generation;
- the model has not entered explicit unload, eviction, or replacement state.

Image generation and editing permit recovery only for a typed identity mismatch;
ambiguous transport failures are not replay safe for those artifact operations.

Recovery invalidates only the failed generation, performs a fresh route
admission and model-ready decision, and stamps a strictly newer generation.
Concurrent callers for the same model/route share one recovery task. Explicit
unload or replacement advances the generation and wins over any in-flight
recovery completion.

After a first backend event or completed tool action, failure produces a typed
`partial_stream_failure` and never replays. The HTTP gateway reads the first
event before opening response headers. Provisional downstream state closes
through the existing stream terminal error path. A completed tool action is
never emitted twice.

Unary requests have no partial response state: retry is allowed only before a
response object is returned. A typed backend response, including mismatch, is
not translated into success.

### Diagnostics and redaction

Worker runtime stats expose cumulative mismatch count plus the last requested
and loaded model IDs, requested and loaded adapter IDs, requested and loaded
route generations, requested and loaded worker instances, and mismatch reason.
The control plane projects mismatch and retry-decision counters into production
metrics and records the last mismatch receipt for diagnostics.

Diagnostic string fields pass through one bounded redactor. Absolute paths,
relative local paths, UNC paths, and case-insensitive local file URIs become
deterministic redacted identifiers. Raw model paths, adapter manifest paths,
socket paths, prompts, tool arguments, audio, images, and generated output are
never recorded.

## Acceptance Checklist

- [x] `LoadModelRequest` and every production inference RPC carry the shared identity message.
- [x] Control-plane stamping preserves the admitted model ID instead of any rewritten `model_path`.
- [x] Adapter-backed and adapter-free loads preserve distinct loaded identities.
- [x] Route generations are positive, monotonic per model/route, and atomically bound to handles.
- [x] Python and Swift workers reject missing identity before runtime work.
- [x] Python and Swift workers reject model, adapter, and generation mismatches with typed errors and no output.
- [x] Text, image-conditioned generation, video-conditioned generation, embedding, ranking, transcription, speech, image generation, and image editing mismatch fixtures fail closed.
- [x] Phase-aware Prefill and Decode enforce identity; tool-adjacent Generate output uses the same guard.
- [x] Port/socket reuse and unload/reload fixtures cannot return output from the wrong loaded identity.
- [x] Mismatch invalidates only the stale binding and a successful retry uses a newer generation plus matching loaded identity.
- [x] Connect, read, write, protocol, and timeout failures before response open receive at most one fresh dispatch retry.
- [x] Failure after first delta returns `partial_stream_failure` without replay.
- [x] Failure after a completed tool action returns `partial_stream_failure`; the tool completion appears exactly once.
- [x] Concurrent stale callers coalesce one recovery decision/load for a model/route.
- [x] Explicit unload or model replacement wins over in-flight recovery and stale recovery cannot republish a handle.
- [x] Exhausted recovery returns a typed unavailable error, never silent model fallback.
- [x] Runtime and control-plane diagnostics expose bounded mismatch/retry evidence with sensitive paths redacted.
- [x] Changed-scope automated coverage is at least 95 percent.
- [x] The scoped performance probe reports no unexplained request-boundary regression.

## TDD Delivery Slices

## Review Corrections

The implementation review adds four required correction slices before this
plan can be accepted:

1. Bind each route receipt to the backend-owned worker instance identity from
   `HandshakeResponse`, reject missing instance identity, and make Python
   handshakes publish their worker family and instance ID.
2. Treat the first backend response event as the streaming response-open
   boundary. The HTTP gateway must not return streaming headers before that
   boundary, and image artifact RPCs may recover from typed identity mismatch
   only, not ambiguous transport failures.
3. Keep healthy route residencies available while another route loads, retire
   a failed residency only when worker introspection proves the handle still
   belongs to the failed identity, and unload stale preload completions.
4. Remove inference-service test helpers that silently add identity, extend
   local-path redaction, and register both Python and Swift changed-line
   coverage for this scope.

These corrections are part of issue #2945 rather than deferred cleanup because
they protect the same fail-closed and replay-safety guarantees.

### Slice 1: Protocol and worker guards

Start with fail-first protocol contract tests and worker service tests for one
streaming and one unary request. Add the schema, regenerate artifacts, record
loaded identities, and centralize worker guards. Extend the same guard through
the remaining RPCs one vertical slice at a time.

### Slice 2: Versioned route bindings

Add fail-first `ModelCatalog` tests for generation allocation, compare-and-
invalidate, stale load completion, and explicit unload precedence. Replace
independent handle reads with an immutable route-binding receipt.

### Slice 3: Replay-safe dispatch

Add a scripted external-worker harness at the `WorkerClient` seam. Cover
identity mismatch, connect/read/write/protocol/timeout failures, single retry,
concurrent recovery coalescing, first-delta cutoff, completed-tool cutoff, and
unload during recovery. Wire the coordinator through production streaming and
unary dispatch paths.

### Slice 4: Diagnostics and performance evidence

Add bounded worker mismatch receipts, control-plane counters, redaction tests,
the PR-scoped performance probe, canonical spec updates, and final integration
fixtures.

## Performance Probes

Add a synthetic repeated PR-scoped probe registered in
`infra/perf/pr_scoped_probes.json`. It exercises matched and mismatched request
boundary guards without model execution and reports:

- `matched_boundary_latency_ms_mean` and p95;
- `mismatched_boundary_latency_ms_mean` and p95;
- `mismatch_count`;
- `retry_allowed_count`, `retry_suppressed_count`, and
  `retry_exhausted_count`;
- `recovery_coalesced_caller_count` and `fresh_binding_count`;
- `output_before_mismatch_count` and `duplicate_completed_tool_count`.

Success metrics:

- matched request-boundary p95 regression uses an absolute `0.05 ms` threshold
  in the synthetic
  worker guard and at most `1.0 ms` for control-plane identity stamping plus
  retry classification;
- mismatch fixtures produce exactly one mismatch count and zero output;
- every request has at most one retry decision;
- concurrent stale callers produce exactly one fresh binding;
- duplicate completed tool count remains zero;
- mismatch-path latency is informational because a base checkout without the
  identity guard uses a compatibility fallback rather than the same operation;
- no direct scoped probe regression is unexplained.

The production observability mode is `minimal`: execution reuses counters and a
single bounded last-mismatch receipt. The synthetic PR probe is evidence-only
and is not imported into production packages.

## Verification

Focused verification will include:

```text
make proto
swift test --package-path services/control-plane-swift --filter BackendIdentity
swift test --package-path services/mlx-text-worker-swift --filter BackendIdentity
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q <backend identity tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run -m pytest -q <changed-scope tests>
python3 scripts/python_changed_line_coverage.py --coverage-json <artifact> --diff-from origin/main <changed files>
python3 scripts/pr_scoped_performance_run.py <registered backend identity probe arguments>
git diff --check
```

Before handoff, install the versioned hook and run its commit gate on the final
branch so `make swift-test`, `make py-test`, `make integration-test`, changed-
scope coverage, and the scoped performance report are captured under
`.runtime/pre-commit-performance/`.

## Implementation Evidence

The delivered request identity is the four-part tuple of admitted model ID,
adapter ID, positive route generation, and backend-owned worker instance ID.
The control plane obtains the worker instance from the health handshake, binds
the tuple atomically to the catalog route, and stamps every production
inference RPC. Python and Swift workers compare the request tuple with immutable
load-time state before runtime work or output.

Recovery is centralized around one versioned route invalidation and one fresh
dispatch. Streaming responses do not open until the first backend event is
available. Identity mismatch and eligible pre-open transport failures can
recover once, while image artifact transport failures, post-delta failures, and
post-tool-completion failures never replay. Concurrent callers share the same
recovery task, and explicit unload remains authoritative.

The implementation also records bounded mismatch and retry diagnostics. The
redactor covers absolute and relative paths, case-insensitive local file URIs,
and UNC paths without retaining prompts, media, tool arguments, or generated
content.

## Metrics Report

Changed-line coverage measured on 2026-07-31:

- Python backend identity scope: `100.00%` (`38/38`).
- Swift control-plane scope: `95.12%` (`1326/1394`).
- Swift text-worker scope: `98.55%` (`204/207`).

The control-plane coverage command excludes `SiblingFileAdvisoryLockTests`, an
unrelated timing-sensitive suite under instrumentation. The normal full Swift
gate includes that suite and passed.

The registered `backend-model-identity-boundary` performance probe passed with
no regression or verification failure. Matched worker-boundary p95 was
`0.0003817125 ms` against the `0.05 ms` absolute threshold, and control-plane
stamping plus recovery classification p95 was `0.0016627085 ms` against the
`1.0 ms` threshold. The probe observed `140000` mismatch checks, zero output
before mismatch, three allowed retries, two suppressed retries, one exhausted
retry, one coalesced caller, two fresh bindings across the scripted scenarios,
and zero duplicate completed tools.

The existing direct probes whose shared test modules gained explicit backend
identity fixtures also passed their snapshot coverage replay. Worker registry
coverage was `99.38%` (`159/160`), vision-family coverage was `98.06%`
(`101/103`), integration helper coverage was `100.00%` (`21/21`), and the
affected image, audio, rerank, and embedding probes reported `100.00%`.

The full 148-probe pre-commit run at
`.runtime/pre-commit-performance/20260731-092846-4c0c3d2f/report` had zero
verification failures. Three direct microbenchmark alerts were analyzed before
the final rerun:

- The deterministic image-edit runtime and probe were unchanged. Five paired
  reruns measured `12.242545 ms` for base and `12.172520 ms` for head, so the
  one-run `11.16%` alert was not reproducible.
- Swift binary resolution itself improved from `14.442075 ms` to `13.974417
  ms`, with identical candidate and allocation counts. Its alert came from
  variance in the separate legacy comparator that made the relative speedup
  less negative.
- The worker-registry alert exposed an avoidable second lock and empty receipt
  copy in `runtime_stats()`. Folding the mismatch receipt into the existing
  snapshot reduced request-stats latency from the alerted `0.002335 ms` to
  `0.001840 ms`, below the `0.001934 ms` base measurement. The combined
  load/stats/unload delta also fell below the probe's `0.001 ms` absolute
  threshold. The remaining loaded-summary cost is the required identity field
  and remained below its percentage threshold.

If the final full-matrix rerun needs the analyzed-regression override because
of another threshold-edge sample, the override applies only to these measured
microbenchmark effects. It does not waive tests, changed-line coverage, probe
execution, identity correctness counters, or any verification failure.

## Verification Results

The final 2026-07-31 repository gates completed successfully:

- `make bootstrap`
- `make proto`
- `make proto-check`
- `make swift-test` (`295` text-worker, `589` control-plane core, and `878`
  menu-bar tests passed, together with the remaining Swift package suites)
- `make py-test` (`5411` passed, `14` skipped)
- `make integration-test` (`124` passed, `1` skipped)

The focused backend identity integration selection also passed all seven tests.

## Known Boundaries

- Process respawn is not implemented by current request-path production code.
  This plan proves one coalesced route/model rebind and makes the coordinator
  injectable for a future process supervisor; it does not claim a worker
  process was spawned.
- Maintenance RPCs are not inference dispatch and remain outside the identity
  envelope. Any maintenance operation that internally evaluates a model must
  continue to resolve a backend-owned loaded handle through its existing job
  contract; it cannot be used as a public inference fallback.
- Abort is request-scoped and carries no model output, so it remains keyed by
  request ID rather than backend model identity.
