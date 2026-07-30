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
  model and worker route binding.

`LoadModelRequest` carries the binding identity used to create backend-owned
loaded state. Every inference request carries the requested identity. Generate,
Prefill, and Decode use `ExecutionMetadata`; all unary and speech-stream
requests carry the same message directly. Generated Swift and Python artifacts
must come only from `make proto`.

### Backend-owned loaded identity

Python `LoadedModel` and Swift `LoadedModelRecord` retain a normalized immutable
loaded identity captured at load time. The worker compares the request envelope
against this record at the RPC service boundary before acquiring a runtime
lease, preprocessing media, tokenizing, decoding, or invoking any model code.

All three components must match exactly. A missing or zero request identity is
a typed `model_identity_missing` contract failure. A different model, adapter,
or generation is a typed `model_identity_mismatch` with no token, audio, image,
embedding, rank, transcription, tool, usage, or completed payload.

### Route generations and invalidation

`ModelCatalog` owns a positive monotonically increasing generation for each
model/route binding. A load attempt reserves the current generation; successful
load records the handle and generation atomically. Explicit unload, failed
load, missing-handle validation, and identity mismatch invalidate the matching
binding and advance the generation. A stale completion may not publish a handle
after a newer invalidation or explicit unload.

All inference request builders obtain one immutable binding receipt containing
model ID, adapter ID, route kind, handle, and generation. They stamp the worker
request from that receipt instead of assigning `model_handle` independently.

### Replay-safe recovery

A shared control-plane dispatch coordinator classifies both worker error
payloads and transport failures. It may perform at most one recovery attempt
when all of the following are true:

- no semantic response event, header-equivalent stream acceptance, token,
  audio chunk, image artifact, embedding/rank/transcription response, usage
  payload, completed tool action, or completion has been exposed;
- the failure is an identity mismatch or a transport connect, read, write,
  protocol, or timeout failure before the response opens;
- the original binding is still the catalog's active generation;
- the model has not entered explicit unload, eviction, or replacement state.

Recovery invalidates only the failed generation, performs a fresh route
admission and model-ready decision, and stamps a strictly newer generation.
Concurrent callers for the same model/route share one recovery task. Explicit
unload or replacement advances the generation and wins over any in-flight
recovery completion.

After a first semantic delta or completed tool action, failure produces a typed
`partial_stream_failure` and never replays. Provisional downstream state closes
through the existing stream terminal error path. A completed tool action is
never emitted twice.

Unary requests have no partial response state: retry is allowed only before a
response object is returned. A typed backend response, including mismatch, is
not translated into success.

### Diagnostics and redaction

Worker runtime stats expose cumulative mismatch count plus the last requested
and loaded model IDs, requested and loaded adapter IDs, requested and loaded
route generations, and mismatch reason. The control plane projects mismatch and
retry-decision counters into production metrics and records the last mismatch
receipt for diagnostics.

Diagnostic string fields pass through one bounded redactor. Absolute paths,
home-relative paths, and URI-like local paths become deterministic redacted
identifiers. Raw model paths, adapter manifest paths, socket paths, prompts,
tool arguments, audio, images, and generated output are never recorded.

## Acceptance Checklist

- [ ] `LoadModelRequest` and every production inference RPC carry the shared identity message.
- [ ] Control-plane stamping preserves the admitted model ID instead of any rewritten `model_path`.
- [ ] Adapter-backed and adapter-free loads preserve distinct loaded identities.
- [ ] Route generations are positive, monotonic per model/route, and atomically bound to handles.
- [ ] Python and Swift workers reject missing identity before runtime work.
- [ ] Python and Swift workers reject model, adapter, and generation mismatches with typed errors and no output.
- [ ] Text, image-conditioned generation, video-conditioned generation, embedding, ranking, transcription, speech, image generation, and image editing mismatch fixtures fail closed.
- [ ] Phase-aware Prefill and Decode enforce identity; tool-adjacent Generate output uses the same guard.
- [ ] Port/socket reuse and unload/reload fixtures cannot return output from the wrong loaded identity.
- [ ] Mismatch invalidates only the stale binding and a successful retry uses a newer generation plus matching loaded identity.
- [ ] Connect, read, write, protocol, and timeout failures before response open receive at most one fresh dispatch retry.
- [ ] Failure after first delta returns `partial_stream_failure` without replay.
- [ ] Failure after a completed tool action returns `partial_stream_failure`; the tool completion appears exactly once.
- [ ] Concurrent stale callers coalesce one recovery decision/load for a model/route.
- [ ] Explicit unload or model replacement wins over in-flight recovery and stale recovery cannot republish a handle.
- [ ] Exhausted recovery returns a typed unavailable error, never silent model fallback.
- [ ] Runtime and control-plane diagnostics expose bounded mismatch/retry evidence with sensitive paths redacted.
- [ ] Changed-scope automated coverage is at least 95 percent.
- [ ] The scoped performance probe reports no unexplained request-boundary regression.

## TDD Delivery Slices

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

- matched request-boundary p95 overhead is at most `0.05 ms` in the synthetic
  worker guard and at most `1.0 ms` for control-plane identity stamping plus
  retry classification;
- mismatch fixtures produce exactly one mismatch count and zero output;
- every request has at most one retry decision;
- concurrent stale callers produce exactly one fresh binding;
- duplicate completed tool count remains zero;
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
