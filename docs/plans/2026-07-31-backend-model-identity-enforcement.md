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

### Final review corrections

The independent Standards and Spec reviews found additional blockers after the
first correction pass. The implementation is not accepted until it also:

1. Separates the stable logical worker name from a process-lifetime backend
   instance UUID. Each Python and Swift worker boot must publish a new instance
   UUID, use that UUID in loaded identity, and prove a same-socket restart cannot
   recreate an identity accepted by a stale request.
2. Treats changes to backend identity inputs such as `melix.model_path`, model
   revision metadata, or `melix.adapter_set_hash` as model replacement. The
   catalog must invalidate every route binding and advance its generation before
   the new settings become dispatchable.
3. Allows recovery to reuse only the coalesced task that owns the failed
   generation. A caller that arrives after explicit unload or replacement must
   fail closed instead of adopting an arbitrary newer binding.
4. Requires a route binding whenever a production `ModelCatalog` is present.
   Compatibility dispatch without backend identity remains available only when
   the coordinator is explicitly constructed without a catalog.
5. Makes failed-residency retirement an atomic worker-side compare-and-unload
   operation carrying the expected backend identity. A list-then-unload sequence
   must not be able to unload a new process residency that reused a handle.
6. Treats a zero-event stream and a stream ending without a terminal event as
   failures. Before response open this is a recoverable transport-style failure;
   after response open it is `partial_stream_failure` and is never replayed.
7. Resolves preload routes from the canonical structured route declaration and
   rejects a missing declaration instead of inferring from free-form model kind.
8. Removes the unrelated local-job probe reporting change from this branch and
   replaces the superseded performance evidence with a final current-main report
   plus complete analysis for every direct alert.
9. Rebinds restored snapshot executions to the backend identity of the currently
   validated loaded residency. A persisted worker boot epoch must not create a
   decode handle that no request identity can consume after a worker restart.

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
- cached loaded-model summary listing retains its 5 percent relative threshold
  with a `0.005 ms` absolute budget for the required backend identity field;
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

## Final Independent Review Corrections

The final Standards and Spec reviews identified additional races and lifecycle
gaps. The branch is not ready for remote review until it also:

1. Atomically validates the worker epoch claimed by
   `LoadModelRequest.backend_identity` before runtime load work begins. A worker
   restart between health and load must reject the stale reservation, so every
   successful load is proven to belong to the same worker epoch captured by the
   control plane. Cleanup of a rejected or stale load completion can then
   compare-and-unload with that proven reservation identity.
2. Tracks Swift inference leases per model handle and records a pending unload
   when the target handle is busy. Activity on another model must not block
   retirement, and the target residency must be removed after its last lease is
   released without relying on a second control-plane unload request.
3. Moves text and speech replay-safe stream handling behind one typed state
   machine. The first completed, finish, or non-recoverable error event is
   terminal; trailing worker events are not exposed. Zero-event and
   unterminated streams retain the existing fail-closed recovery policy.
4. Resolves bootstrap preload only from structured request-route declarations.
   Deprecated `route_class` cannot select or invalidate an otherwise valid
   declaration. The bootstrap stage supplies its target worker route, while the
   model must declare at least one compatible structured task for that route;
   multiple tasks sharing one worker residency remain valid.
5. Retains the three delayed stale-load/same-handle regression tests for lazy,
   bootstrap, and explicit control-plane loads, proving cleanup uses the
   worker-validated reservation identity.

The performance evidence must continue to measure the registered identity
boundary probe and cached loaded-model listing. The final pass additionally
reports changed-line coverage for load-epoch validation, per-handle
lease release, and the shared stream state machine. Load-epoch comparison,
terminal classification, and per-handle lease accounting are constant-time
boundary operations and must stay within the existing control-plane `1.0 ms`
absolute budget; no new production debug mode is introduced.

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

Snapshot restore validates the persisted model identity against a current loaded
residency, then rebinds the restored execution to that residency's current
backend identity and the restore request owner before creating its decode
context. This keeps explicit recovery usable across worker boot epochs without
relaxing the decode guard.

## Metrics Report

Final changed-line coverage against current `origin/main`:

- Python backend identity scope: `96.98%` (`610/629`).
- Swift control-plane scope: `96.19%` (`1337/1390`).
- Swift text-worker scope: `99.16%` (`356/359`).

The control-plane coverage command runs affected suites and identity-recovery
tests as isolated shards, then merges their LLVM profiles before measuring the
changed lines. This avoids shared-state interference under instrumentation.
The normal full Swift gate remains the complete behavior gate and passed.

The first current-snapshot pre-commit report at
`.runtime/pre-commit-performance/20260731-212740-686de830/report` selected five
direct probes and found no performance regression. It correctly blocked the
commit because the structured-output probe's verification command did not
cover the new Python prefill-session binding line. The registered command now
includes the focused cross-residency decode-session test, which measures that
line at `100%` changed-line coverage.

Changing the versioned performance registry intentionally forces the final
pre-commit report to execute all `148` registered probes. The report for the
exact committed snapshot is published at the stable local artifact path
`.runtime/issue-2945-final-performance/report`; the pull request evidence also
records its timestamped source directory and aggregate result. Verification
failures are never eligible for an override. Any sampled regression must be
analyzed and reproduced before using the repository's documented intentional
regression override.

The review-correction snapshot report at
`.runtime/pre-commit-performance/20260801-103014-06c48008/report` completed all
`148` probes with status `ok`: all `3` direct/gated probes passed, with `0`
regressions and `0` verification failures. A prior isolated registry cold-load
alert did not reproduce in seven repeated base/head measurements and did not
recur in this exact staged-snapshot report.

The post-merge report at
`.runtime/pre-commit-performance/20260801-113349-bd849303/report` also completed
all `148` probes with `0` verification failures. The backend identity, registry
cache, and same-cohort probes were all `ok`. An upstream one-line change to the
shared performance test file forced `20` probes into the direct gate and two
unrelated timing samples crossed their `5%` thresholds. Neither probe watches
or executes a runtime path changed by this branch. Seven alternating
`origin/main`/merged-tree repetitions disproved both alerts: deterministic image
output byte accounting changed from `20.407 ms` to `20.457 ms` (`+0.24%`), and
deterministic OCR token counting changed from `793.868 ms` to `791.479 ms`
(`-0.30%`). The sampled alerts are therefore recorded as non-reproducing
measurement noise, not accepted regressions.

The final-base report at
`.runtime/pre-commit-performance/20260801-125020-a86f8a8c/report` completed all
`148` probes with `0` verification failures. Backend identity, worker registry,
performance registry, same-cohort batching, and both upstream token-counting
probes were `ok`; OCR measured `819.743 ms` versus `830.158 ms`, and VLM
completion counting measured `23.960 ms` versus `24.242 ms`. Because the shared
performance test file was part of the staged snapshot, four otherwise unrelated
probes were included in the direct gate and produced isolated alerts. Seven
alternating `29d6f332`/merged-tree repetitions disproved all four: image digest
was `-2.78%`, embedding duplicate-input reuse was `+0.79%`, rerank request
processing was `+2.20%`, and audio local-URI preprocessing was `-7.63%`. None
crossed its `5%` threshold on repeat. These alerts are recorded as
non-reproducing measurement noise rather than intentional regressions.

The exact staged-tree report after merging `origin/main` at `99c402a0` is
`.runtime/pre-commit-performance/20260801-135926-dcf1a567/report`. It completed
all `148` probes with `0` verification failures. All `20` direct probes passed
their targeted tests and coverage checks; the backend identity, worker
registry, dataset preview, OCR, same-cohort batching, and integration probes
were functionally `ok`. Three unrelated timing samples crossed their direct
thresholds because this branch changes the shared performance registry test:
VLM completion token counting, audio local-URI preprocessing, and the remove
tree submetric bundled with Swift binary resolution. Seven alternating
base/head repetitions in equivalent fresh worktrees using Python `3.14.4`
disproved the alerts. VLM changed by `+1.16%` against its `5%` threshold, audio
changed by `-1.80%` against its `10%` threshold, and Swift binary resolution
changed by `+1.35%` against its `5%` threshold. The remove-tree samples had one
base outlier at `-286 ms`; the medians were `-71.81 ms` for base and `-76.56 ms`
for head, so the head remained faster. These are non-reproducing measurement
noise, not intentional regressions.

After the next mainline synchronization at `dba0f70d`, the exact staged-tree
report at
`.runtime/pre-commit-performance/20260801-151056-e0c1557e/report` again ran all
`148` probes with `20` direct probes and `0` verification failures. The backend
identity and all newly synchronized runtime-weight paths were functionally
`ok`. Two unrelated direct timing samples crossed thresholds: deterministic
embedding duplicate-input reuse and audio local-URI preprocessing. Seven
alternating repetitions in equivalent fresh worktrees using the pre-commit
hook's Python `3.12.13` disproved both alerts. Embedding total time changed by
`-1.03%`, its single-cycle metric changed by `+1.11%` against a `5%` threshold,
and audio changed by `-6.33%` against a `10%` threshold. These are
non-reproducing measurement noise, not intentional regressions.

After synchronizing the changed-scope and model-registry optimizations from
`origin/main` at `4fb0226b`, the exact staged-tree report at
`.runtime/pre-commit-performance/20260801-162645-9f721311/report` completed all
`148` probes with `20` direct probes and `0` verification failures. The backend
identity probe remained `ok`: it rejected `140,000` mismatches with `0` output
events before mismatch, recorded retry counts `3/2/1`, coalesced one recovery
caller into two fresh bindings, and measured matched-worker p95 at
`0.000450 ms` and control-plane p95 at `0.001422 ms`.

Four unrelated direct timing samples crossed their thresholds in the single
full-registry pass: deterministic embedding duplicate-input reuse, rerank
request processing, audio local-URI preprocessing, and Swift binary
resolution. Seven alternating base/head repetitions in equivalent fresh
worktrees using Python `3.12.13` disproved all four alerts. Embedding total time
changed by `+1.36%` and its single-cycle metric by `+3.41%`, both below the
`5%` threshold; rerank request processing changed by `-1.82%`; audio changed by
`-0.72%` against its `10%` threshold; and Swift binary resolution changed by
`-2.00%`. The bundled remove-tree mean also improved from `-101.44 ms` to
`-107.82 ms`. The report's `32` context-only timing alerts had no verification
failures and do not gate this change. These sampled direct alerts are
non-reproducing measurement noise, not intentional regressions. Only this
evidence paragraph changed after the exact staged-tree report.

After synchronizing the usage-only remote-provider stream fix and model-registry
filename prefilter from `origin/main` at `cd99c4a4`, the exact staged-tree report
at `.runtime/pre-commit-performance/20260801-174846-24722764/report` again ran
all `148` probes with `20` direct probes and `0` verification failures. The
backend identity, model-registry, remote-provider, and all focused post-merge
tests passed. One direct timing sample crossed its threshold: Swift binary
resolution measured `13.769 ms` for the base and `14.761 ms` for the merged tree
in the single report (`+7.21%`). The probe was selected because this task adds
the worker-restart identity regression through the shared integration helper;
the timed Swift binary lookup implementation itself is unchanged.

Seven alternating `cd99c4a4`/merged-tree repetitions using the pre-commit
hook's Python `3.12.13` did not reproduce the alert. The aggregate means were
`14.521 ms` for the base and `14.640 ms` for the merged tree (`+0.82%`), below
the `5%` threshold; the medians were `14.448 ms` and `14.685 ms`. The report's
`21` context-only timing alerts had no verification failures and do not gate
this change. The direct alert is therefore non-reproducing measurement noise,
not an accepted regression, and no performance-regression override is used.

After synchronizing the event-actor spaced-alias fast path from `origin/main`
at `415eba04`, the exact staged-tree report at
`.runtime/pre-commit-performance/20260801-190032-7ed9469e/report` again ran all
`148` probes with `20` direct probes and `0` verification failures. The full
Swift, Python, and integration gates passed. The backend identity probe remained
`ok`: it rejected `140,000` mismatches with `0` output events before mismatch,
recorded retry counts `3/2/1`, coalesced one recovery caller into two fresh
bindings, and measured matched-worker p95 at `0.000515 ms` and control-plane p95
at `0.001534 ms`.

One unrelated direct timing sample crossed its threshold in that single report:
local-URI multimodal preprocessing measured `125.546 ms` for the base and
`133.563 ms` for the merged tree (`+6.38%` against a `5%` threshold). The probe
was selected because the shared performance registry test changed; the merge
does not change the measured multimodal preprocessing implementation. Seven
alternating base/merged-tree repetitions using Python `3.12.13` did not
reproduce the alert. Aggregate means were `131.521 ms` and `130.907 ms`
(`-0.47%`), while medians were `130.832 ms` and `130.041 ms`. Every repetition
preserved `0` URL parser calls and `5,000` byte reads. The report's `23`
context-only timing alerts had no verification failures. The direct alert is
therefore non-reproducing measurement noise, not an accepted regression, and
no performance-regression override is used.

After synchronizing the Swift Collections lock, closure-audit fast path, and
mixed-case Python fence branch from `origin/main` at `19a20821`, the first full
hook attempt stopped in the Swift control-plane core group with one failure
among `594` tests. The unchanged group passed immediately on an exact rerun,
and the subsequent full hook completed every functional gate: the Swift suites,
`5,495` Python tests with `14` skips, and `132` integration tests with one skip.
The exact staged-tree report at
`.runtime/pre-commit-performance/20260801-201542-9f9ed2ef/report` ran all `148`
probes with `20` direct probes and `0` verification failures. The backend
identity probe remained `ok`: it rejected `140,000` mismatches with `0` output
events before mismatch, recorded retry counts `3/2/1`, coalesced one recovery
caller into two fresh bindings, and measured matched-worker p95 at
`0.000443 ms` and control-plane p95 at `0.001358 ms`.

One direct timing sample crossed its threshold in that report: Swift binary
resolution measured `13.008 ms` for the base and `13.956 ms` for the merged tree
(`+7.29%` against a `5%` threshold). The probe was selected because the upstream
merge changes HTTP polling in the shared integration helper; the timed binary
resolution implementation is unchanged. Seven alternating base/merged-tree
repetitions using Python `3.12.13` did not reproduce the alert. Aggregate means
were `14.757 ms` and `14.608 ms` (`-1.01%`), while medians were `14.556 ms` and
`14.779 ms`. Every repetition preserved `1,501` candidates, `1,200` removed
directories, and the same memory invariants; the remove-tree mean improved from
`-103.852 ms` to `-110.453 ms`. The report's `14` context-only timing alerts had
no verification failures. The direct alert is therefore non-reproducing
measurement noise, not an accepted regression, and no performance-regression
override is used.

After synchronizing the changed-scope singleton coverage fast path from
`origin/main` at `ec2c915e`, the final exact staged-tree hook again completed
every functional gate: all Swift suites, `5,495` Python tests with `14` skips,
and `132` integration tests with one skip. The report at
`.runtime/pre-commit-performance/20260801-212623-59bc0a5c/report` ran all `148`
probes with `20` direct probes and `0` verification failures. The backend
identity probe remained `ok`: it rejected `140,000` mismatches with `0` output
events before mismatch, recorded retry counts `3/2/1`, coalesced one recovery
caller into two fresh bindings, and measured matched-worker p95 at
`0.000445 ms` and control-plane p95 at `0.001365 ms`.

One unrelated direct timing sample crossed its threshold in that single report:
rerank request processing measured `279.356 ms` for the base and `294.333 ms`
for the merged tree (`+5.36%` against a `5%` threshold), while the probe's total
elapsed time improved by `2.32%` and all memory and semantic counters matched.
Seven alternating `ec2c915e`/merged-tree repetitions using Python `3.12.13` did
not reproduce the alert. Request-processing means were `278.812 ms` and
`279.048 ms` (`+0.085%`), and medians were `279.164 ms` and `277.142 ms`
(`-0.724%`). Total elapsed means differed by `+0.378%`, also below the threshold.
The report's `14` context-only timing alerts had no verification failures. The
direct alert is non-reproducing measurement noise, not an accepted regression,
and no performance-regression override is used.

After synchronizing the sparse sequential changed-scope scan from
`origin/main` at `7ca8655a`, the exact staged-tree hook completed every
functional gate again: all Swift suites, `5,495` Python tests with `14` skips,
and `132` integration tests with one skip. The report at
`.runtime/pre-commit-performance/20260801-223738-a8f842ae/report` ran all `148`
probes with `20` direct probes, `0` direct regressions, and `0` gated
verification failures. The backend identity probe remained `ok`: it rejected
`140,000` mismatches with `0` output events before mismatch, recorded retry
counts `3/2/1`, coalesced one recovery caller into two fresh bindings, and
measured matched-worker p95 at `0.000436 ms` and control-plane p95 at
`0.001473 ms`.

The synchronized changed-scope measured-set probe preserved zero source reads
and measured its sparse workload at `7.236 ms`, while the singleton-range probe
also preserved zero source reads and measured its singleton workload at
`31.718 ms`; both were `ok`. The rerank direct probe was also `ok`, with request
processing improving from `277.420 ms` to `276.159 ms`. The report recorded
`13` context-only timing alerts. One unrelated context-only startup-signals
verification command failed inside the all-probe run, but its exact registered
test and coverage commands immediately passed on the staged tree (`61` tests,
`100%` coverage over zero changed lines). Because it was outside the direct
gate, reproduced cleanly, and did not affect any performance metric or scoped
file, no performance-regression override is used.

After synchronizing the startup-signal version-prefix and trajectory provenance
copy fast paths from `origin/main` at `02214a49`, the exact staged-tree hook
again completed every functional gate: all Swift suites, `5,496` Python tests
with `14` skips, and `132` integration tests with one skip. The report at
`.runtime/pre-commit-performance/20260801-234544-9b2d6a27/report` ran all `148`
probes with `20` direct probes and `0` verification failures. The backend
identity probe remained `ok`: it rejected `140,000` mismatches with `0` output
events before mismatch, recorded retry counts `3/2/1`, coalesced one recovery
caller into two fresh bindings, and measured matched-worker p95 at
`0.000447 ms` and control-plane p95 at `0.001402 ms`.

The synchronized startup-signals probes were both `ok`: the lazy-log control
crash path improved from `7.976 ms` to `7.920 ms`, report serialization improved
from `55.259 ms` to `54.282 ms`, the single-pass version comparison measured
`6.571 ms`, and product-version parsing improved from `108.152 ms` to
`105.885 ms`. The trajectory copy-elision probe passed `43` focused tests and
changed-line coverage, retained `17,547` peak bytes, and measured a `7.58x`
speedup. The changed-scope sparse and singleton probes remained `ok` at
`7.422 ms` and `31.057 ms`, both with zero source reads. Rerank total elapsed
improved from `1260.338 ms` to `1253.110 ms`; its request submetric changed by
`+4.40%`, remaining below the `5%` threshold.

One unrelated direct timing sample crossed its threshold: vision-family config
resolution measured `4.274 ms` for the base and `4.501 ms` for the merged tree
(`+5.31%` against a `5%` threshold). The probe was selected only because this
task updates `test_vision_runtime.py` to send backend identity. The measured
production modules and probe script are byte-identical to `origin/main`, with
matching SHA-256 hashes. Seven alternating same-interpreter measurements did
not reproduce the alert: aggregate means were `4.270 ms` and `4.309 ms`
(`+0.93%`), medians were `4.268 ms` and `4.273 ms`, and the nominal head sample
was faster in three of seven pairs. All structural metrics remained identical.
The report's `16` context-only timing alerts had no verification failures. This
direct alert is non-reproducing measurement noise, not an accepted regression,
and no performance-regression override is used.

After synchronizing the code-fence tail-trim change from `origin/main` at
`dd57f6b4`, the code-evaluation and performance-registry focused suites passed
`83` tests. The registered code-block coverage command passed its `4` tests and
measured `100%` coverage over zero changed lines, and the standalone extraction
probe preserved `2,500` blocks, a `198`-byte peak allocation, and bounded empty
fallback behavior. The exact staged-tree hook then completed every functional
gate again: all Swift suites, `5,496` Python tests with `14` skips, and `132`
integration tests with one skip. The report at
`.runtime/pre-commit-performance/20260802-005537-91796e64/report` ran all `148`
probes with `20` direct probes, `0` direct regressions, and `0` verification
failures.

The backend identity probe remained `ok`: matched-worker p95 was `0.000446 ms`,
control-plane stamping/recovery p95 was `0.001392 ms`, `140,000` mismatches
produced zero output events, retry counts remained `3/2/1`, one recovery caller
was coalesced into two fresh bindings, and duplicate completed-tool output
remained zero. The newly synchronized code-block probe was `ok` at `0.0591 ms`
mean extraction time and `0.1656 ms` empty-fallback mean, with the same `198`-byte
peak allocation. Startup-signal probes, trajectory provenance, changed-scope
coverage, rerank, and vision-family token counting were all `ok`; the vision
config-resolution delta was only `+0.26%`. The report recorded `14` context-only
timing alerts, none with verification failures, and no performance-regression
override was used.

After synchronizing the ASCII code-fence prefix fast path from `origin/main` at
`ebbf7f85`, the code-evaluation and performance-registry focused suites passed
`84` tests. The registered code-block coverage command passed its `4` tests and
measured `100%` coverage over zero changed lines. The standalone extraction
probe preserved `2,500` blocks and a `198`-byte peak allocation while measuring
`0.0562 ms` mean extraction and `0.1641 ms` mean empty-fallback latency. The
exact staged-tree hook again completed every functional gate: all Swift suites,
`5,496` Python tests with `14` skips, and `132` integration tests with one skip.
The report at
`.runtime/pre-commit-performance/20260802-020233-13fb927d/report` ran all `148`
probes with `20` direct probes and `0` verification failures.

The backend identity probe remained `ok`: matched-worker p95 was `0.000492 ms`,
control-plane stamping/recovery p95 was `0.001466 ms`, `140,000` mismatches
produced zero output events, retry counts remained `3/2/1`, one recovery caller
was coalesced into two fresh bindings, and duplicate completed-tool output
remained zero. One unrelated direct rerank request sample crossed its threshold,
from `281.953 ms` to `298.356 ms` (`+5.82%`), even though total probe elapsed
improved by `1.43%` and the rerank implementation and probe are byte-identical
to `origin/main`. Seven alternating Python 3.12 measurements did not reproduce
the alert: request means were `287.883 ms` and `287.707 ms` (`-0.06%`), medians
were `288.146 ms` and `287.790 ms`, and total elapsed means changed by `-0.04%`.
All structural and memory invariants matched. The report's `6` context-only
timing alerts had no verification failures. The rerank alert is non-reproducing
measurement noise, not an accepted regression, and no performance-regression
override is used.

After synchronizing the Swift compatibility verification changes from
`origin/main` at `6a64e7f7`, the shared protocol package built successfully with
`swift-collections` resolved at `1.3.0`. The focused OpenAI idle-unload
regression and the Python long-enum structured-output regression each passed.
The exact staged-tree hook completed every functional gate: all Swift suites,
`5,496` Python tests with `14` skips, and `132` integration tests with one skip.
The report at
`.runtime/pre-commit-performance/20260802-031951-872d4285/report` ran all `148`
probes with `20` direct probes and `0` verification failures.

The backend identity probe remained `ok`: matched-worker p95 was `0.000448 ms`,
control-plane stamping/recovery p95 was `0.001464 ms`, `140,000` mismatches
produced zero output events, retry counts remained `3/2/1`, one recovery caller
was coalesced into two fresh bindings, and duplicate completed-tool output
remained zero. Two unrelated deterministic-image direct samples crossed their
timing thresholds even though the measured runtime and both probe scripts are
byte-identical to `origin/main`; the probes were selected because the image
handler tests now stamp backend identity. Equal-environment Python 3.12.13
alternating measurements did not reproduce either alert. Ten edit repetitions
measured `11.316 ms` for the base and `11.182 ms` for the merged tree
(`-1.18%`). After an initial ten-repetition output sample remained noisy, an
expanded thirty-repetition output run measured `21.436036 ms` for the base and
`21.436463 ms` for the merged tree (`+0.002%`), with medians differing by only
`0.83%`. Digest calls, output-byte scan calls, payload checksums, and generated
and edited byte counts matched exactly. The report's `20` context-only timing
alerts also had no verification failures. The image alerts are non-reproducing
measurement noise, not accepted regressions, and no performance-regression
override is used.

After synchronizing the single-token maintenance prompt-shape fast path from
`origin/main` at `d0c09938`, its registered focused command passed `23` tests
and measured `100%` changed-line coverage over zero task-owned lines. The
standalone probe preserved three prompt contexts, `5,160,960` aggregate tokens,
`16,384,000` plain tokens, and `2,000` single-context iterations. The exact
staged-tree hook completed every functional gate: all Swift suites, `5,496`
Python tests with `14` skips, and `132` integration tests with one skip. The
report at
`.runtime/pre-commit-performance/20260802-043705-2541f90d/report` ran all `148`
probes with `20` direct probes and `0` verification failures. The synchronized
maintenance probe was `ok`, with base/head means of `40.716 ms` and `40.965 ms`
and unchanged token counts.

The backend identity probe remained `ok`: matched-worker p95 was `0.000444 ms`,
control-plane stamping/recovery p95 was `0.001387 ms`, `140,000` mismatches
produced zero output events, retry counts remained `3/2/1`, one recovery caller
was coalesced into two fresh bindings, and duplicate completed-tool output
remained zero. Two unrelated direct timing samples crossed their thresholds.
The deterministic embedding runtime and probe are byte-identical to
`origin/main`; ten alternating Python 3.12.13 repetitions measured base/head
means of `8.3958 ms` and `8.4161 ms` (`+0.24%`, threshold `5%`) with identical
call counts and checksums. The integration probe scripts are also identical;
the task's helper change only extracts Python worker restart control and does
not change the measured tree-removal implementation. Ten alternating
repetitions measured base/head removal savings of `-109.89 ms` and
`-109.13 ms`, a `0.76 ms` difference against the `5 ms` threshold, with
identical directory and memory invariants. Both alerts are non-reproducing
measurement noise, not accepted regressions, and no performance-regression
override is used.

After synchronizing the bound-method kwarg-cache fast path from `origin/main`
at `115e2c02`, the registered focused command passed `28` tests and measured
`100%` changed-line coverage over zero task-owned lines. Its standalone probe
measured `4.096 ms` across `40,000` calls per sample with one
`inspect.signature` call. The exact staged-tree hook completed every functional
gate: all Swift suites, `5,497` Python tests with `14` skips, and `132`
integration tests with one skip. The report at
`.runtime/pre-commit-performance/20260802-055011-8d17d99c/report` ran all `148`
probes with `20` direct probes and `0` verification failures. The synchronized
runtime-utils probe was `ok` and improved from `4.630 ms` to `3.838 ms`
(`-17.12%`) while retaining one signature inspection.

The backend identity probe remained `ok`: matched-worker p95 was `0.000492 ms`,
control-plane stamping/recovery p95 was `0.001419 ms`, `140,000` mismatches
produced zero output events, retry counts remained `3/2/1`, one recovery caller
was coalesced into two fresh bindings, and duplicate completed-tool output
remained zero. One unrelated deterministic image output-byte timing sample
crossed its threshold even though the measured production runtime and probe
script are byte-identical to `origin/main`. An expanded `100`-repetition,
alternating Python 3.12.13 comparison disproved the alert: the head mean improved
from `27.040 ms` to `25.615 ms`, the 10% trimmed means were `22.249 ms` and
`22.344 ms` (`+0.43%`), the medians differed by about `2.2%`, and head p95
improved. Output-byte scan calls, payload checksums, and generated/edit byte
counts matched exactly. This is non-reproducing measurement noise, not an
accepted regression, and no performance-regression override is used.

After synchronizing `origin/main` at `bb934729`, the task branch includes the
prefix snapshot state-length fast path and signed GitHub release app updates.
The packaging verification exposed a macOS LibreSSL output variant that renders
RFC2253 subjects as `subject= CN=...` rather than `subject=CN=...`. The shared
self-signed identity parser now accepts equivalent whitespace after the
`subject=` prefix while preserving the self-signed issuer/subject equality,
common-name, fingerprint, and EKU checks. The focused packaging feature group
passed `282` tests, the full self-signed identity suite passed `31` tests, and
the real PKCS#12 regression passed on the host LibreSSL implementation. The
menu-bar software-update controller suite passed `23` tests.

The synchronized prefix snapshot probe passed its registered `14` tests and
reported `100%` changed-line coverage over zero task-owned lines. Its report
status was `ok`: base/head means were `554.630 ms` and `559.466 ms` (`+0.87%`),
with `80` iterations, `4,096` layers, a `68071200` checksum, and `702` peak
bytes. The standalone staged-tree probe measured `560.065 ms` mean and
`559.175 ms` p95 with the same structural metrics.

The exact staged-tree hook completed every functional gate: all Swift suites
including `907` menu-bar tests, `5,652` Python tests with `14` skips, and `132`
integration tests with one skip. The report at
`.runtime/pre-commit-performance/20260802-071205-971706ac/report` ran all `148`
probes with `20` direct probes and `0` verification failures. The backend
identity probe remained `ok`: matched-worker p95 was `0.000479 ms`,
control-plane stamping/recovery p95 was `0.001539 ms`, all `140,000` mismatches
produced zero output events, retry counts remained `3/2/1`, one recovery caller
was coalesced into two fresh bindings, and duplicate completed-tool output
remained zero.

One unrelated deterministic image output-byte timing sample crossed its direct
threshold (`20.924 ms` to `25.496 ms`, `+21.85%`). The production runtime and
probe script are byte-identical between `origin/main` and the staged tree. An
expanded `100`-repetition alternating Python 3.12.13 comparison disproved the
alert: head mean improved by `10.12%`, the medians differed by `+0.90%`, the 10%
trimmed mean improved by `0.65%`, and head p95 improved by `6.08%`. Every
repetition retained zero output-byte scans, `96` generated and `96` edited
outputs, `9,302` generated bytes, `15,062` edited bytes, and checksum `26,304`.
This is sampled noise rather than an accepted regression, so no performance-
regression override is used.

After synchronizing the inline state-type prefix snapshot fast path from
`origin/main` at `1b10925c`, the registered focused command again passed `14`
tests and reported `100%` changed-line coverage over zero task-owned lines. The
standalone probe retained checksum `68071200`, `80` iterations, `4,096` layers,
and `702` peak bytes while measuring `554.121 ms` mean and `558.518 ms` p95.

After synchronizing the pipe channel header parsing simplification from
`origin/main` at `03cf747a`, the registered stream-assembler parser-mode command
passed `109` tests and reported `100%` changed-line coverage over zero task-owned
lines. The standalone probe retained `13` channel-name parses, checksum `86`,
and `10` tool calls while measuring `1.567 ms` across `512` samples.

The exact staged-tree pre-commit report after that merge is
`.runtime/pre-commit-performance/20260802-094319-a4b68f56/report`. The full
Swift gate, `5652` Python tests with `14` skips, and `132` integration tests
with one skip passed. All `148` performance probes completed with zero
verification failures. The backend identity probe remained `ok`: matched
worker-boundary p95 was `0.000451 ms`, control-plane stamping and recovery p95
was `0.001381 ms`, all `140000` mismatches produced zero output, retry counts
remained `3/2/1`, and coalesced/fresh/duplicate-tool counts remained `1/2/0`.
The synchronized parser-mode and structural-prefix probes were also `ok` at
`1.613 ms` and `449.201 ms`, respectively, with their structural counters
unchanged.

Four direct timing samples crossed their `5%` thresholds in that report. Ten
alternating equivalent-worktree repetitions using Python `3.12.13` returned
the deterministic VLM mean to `+2.00%`, vision-family config resolution to
`+3.30%`, and integration binary resolution to `+1.64%`. The image probe had
one large outlier on each side; its minimum/maximum-trimmed means were
`21.588 ms` and `22.549 ms` (`+4.45%`). All production runtime modules and
probe scripts watched by the three inference probes are byte-identical to
`origin/main`; they were selected because identity-aware tests changed. The
integration helper changed only worker-start orchestration, while the measured
binary-resolution and remove-tree implementations are unchanged. Every
repetition retained the same output counts, byte totals, token counts,
checksums, candidate count, directory count, and memory invariants. These are
non-reproducing sampled alerts rather than accepted regressions, so no
performance-regression override is used.

After synchronizing the prefix cold-index suffix checks and direct close-marker
prefix tuples from `origin/main` at `f5c05870`, the registered structural-prefix
slice passed `9` focused tests and `110` coverage tests, while the cold-index
slice passed `17` focused and `17` coverage tests. Both changed-line coverage
commands reported `100%` over zero task-owned lines. The standalone structural
probe retained `1,750,000` close-marker, held-suffix, and prefix-identity hits;
the cold-index probe retained `600` loaded entries, `600` filename-pruned
orphans, zero path-glob calls, and one scandir call.

## Verification Results

The latest post-merge repository gates completed successfully against
`origin/main` at `6457b21b` on 2026-08-02:

- `make swift-test` (`301` text-worker and `907` menu-bar tests passed,
  together with the control-plane and remaining Swift package suites)
- `make py-test` (`5652` passed, `14` skipped)
- `make integration-test` (`132` passed, `1` skipped)

The synchronized packaging suites passed `282` tests, including `31` self-signed
identity tests, and the menu-bar software-update controller suite passed `23`
tests. The registered prefix snapshot probe command passed `14` tests and its
changed-line coverage command reported `100%` over zero task-owned lines. The
preceding runtime-utils probe command passed `28` tests with the same coverage
result, and the maintenance probe command passed `23` tests. The backend
identity coverage command measured `96.98%` for Python, `96.19%` for the Swift
control plane, and `99.16%` for the Swift text worker. The preceding
compatibility merge also passed the shared protocol package build, focused
OpenAI idle-unload test, and focused Python long-enum structured-output test.
The earlier `ebbf7f85` base passed `make bootstrap`, `make proto`, and
`make proto-check`, proving the locked dependencies and generated protobuf
artifacts were current and idempotent before the compatibility-only increment.

The final mainline merge also passed the code-evaluation and relevant
performance-registry focused suites (`84` tests), the registered coverage
command (`4` tests), and the code-block extraction probe. The preceding merge
passed the combined startup-signals, trajectory, and relevant
performance-registry focused suites (`144` tests), plus both new probe scripts.
The merge before that passed the changed-scope coverage and
registered coverage/probe focused suites (`69` tests). The merge before that passed the
changed-scope coverage, backend identity, and identity-probe focused suites
(`73` tests). The merge before that
passed the integration-helper, closure-audit, code-evaluation, backend-identity,
and shared performance-registry focused suites (`129` tests), while the merge
before that passed the event-extraction, event-performance, and backend-identity
focused suites (`96` tests). The focused same-endpoint worker-restart integration
test also passed. Earlier
final-base verification passed the atomic stale-cleanup and remote-provider
routing tests together, and the registered performance and binary-resolution
tests (`15` tests). The remote-review corrections additionally passed all `14`
backend identity tests, all `254` OpenAI handler tests, the stale-generation
snapshot restore regression, the stream-consumption and phase-aware replay
regressions, and the in-process worker handler performance tests. The three
changed-line coverage totals are `96.98%`, `96.19%`, and `99.16%`.

The final-base pre-commit run also exposed an unrelated pre-existing flaky
assertion in the shared performance test: independently rounded six-decimal
scalar-copy metrics could differ by slightly more than `1e-6`. The assertion
now uses a `2e-6` absolute tolerance, matching the metric serialization
precision without weakening any measured performance threshold.

After synchronizing the prefix snapshot state type fast path from
`origin/main` at `1b10925c`, the exact staged-tree pre-commit report at
`.runtime/pre-commit-performance/20260802-082729-82285fd3/report` completed the
full Swift gate, `5652` Python tests with `14` skips, and `132` integration
tests with one skip. All `148` performance probes completed with `0`
verification failures. The backend identity probe remained `ok`: matched
worker-boundary p95 was `0.000441 ms`, control-plane stamping and recovery p95
was `0.001520 ms`, all `140000` mismatches produced zero output, retry counts
remained `3/2/1`, and coalesced/fresh/duplicate-tool counts remained `1/2/0`.
The synchronized prefix snapshot probe was also `ok`; its base/head means were
`556.402 ms` and `557.928 ms`, while head p95 improved to `557.161 ms`.

Two direct timing samples crossed their thresholds in that report. Generate
fallback accounting measured `63.469 ms` for the base and `67.919 ms` for the
staged tree (`+7.01%` against a `5%` threshold). Ten alternating equivalent-
worktree repetitions using Python `3.12.13` measured `63.889 ms` and
`65.261 ms` (`+2.15%`); every repetition retained zero prompt-counter,
request-state append, and native-parser calls. The integration cleanup
submetric changed from `-108.435 ms` to `-73.437 ms` in the single report even
though the measured `_remove_tree` implementation and probe script are
byte-identical. Ten standalone alternating repetitions measured `-106.380 ms`
for the base and `-111.652 ms` for the staged tree, a `5.272 ms` improvement,
with `1200` directories and identical memory invariants throughout. Both
alerts are non-reproducing measurement noise, not accepted regressions; no
performance-regression override was used. The report's `17` context-only
timing alerts had no verification failures.

After synchronizing the prefix cold-index and stream close-marker tuple
optimizations from `origin/main` at `f5c05870`, the exact staged-tree report at
`.runtime/pre-commit-performance/20260802-105538-4ee86133/report` completed the
full Swift gate, `5652` Python tests with `14` skips, and `132` integration
tests with one skip. All `148` performance probes ran, all `20` direct probes
passed their targeted tests and coverage commands, and there were `0`
verification failures. The newly synchronized prefix cold-index probe improved
from `36.090 ms` to `35.593 ms` (`-1.38%`) with `600` entries, `600` orphans,
zero glob calls, and one scandir call. The stream structural-prefix probe
improved from `468.160 ms` to `464.371 ms` (`-0.81%`) with `1,750,000` identity
hits. Its close-marker submetric remained within threshold at `+3.09%`.

Three direct timing samples crossed their `5%` thresholds in the single report:
deterministic VLM completion scanning (`+6.21%`), Generate fallback accounting
(`+7.57%`), and integration Swift binary resolution (`+11.59%`). Ten
base/head-alternating repetitions in equivalent fresh worktrees using Python
`3.12.13` disproved all three alerts. VLM means changed from `24.911 ms` to
`24.589 ms` (`-1.29%`), Generate fallback means changed from `64.178 ms` to
`64.817 ms` (`+1.00%`), and integration means changed from `14.537 ms` to
`14.405 ms` (`-0.91%`). Minimum/maximum-trimmed means produced the same
conclusion: `-1.53%`, `+1.04%`, and `-0.78%`, respectively. Every repetition
retained `6000` VLM completion tokens with zero split calls, zero Generate
fallback native-parser calls, and `1501` integration candidates with `1200`
removed directories. These alerts are non-reproducing measurement noise, not
accepted regressions; no performance-regression override was used. The report's
`29` context-only timing alerts had no verification failures. The backend
identity probe remained `ok`: matched worker-boundary p95 was `0.000523 ms`,
control-plane stamping and recovery p95 was `0.001566 ms`, all `140000`
mismatches produced zero output, retry counts remained `3/2/1`, and
coalesced/fresh/duplicate-tool counts remained `1/2/0`. Only these evidence
paragraphs changed after the exact staged-tree report.

After synchronizing the macOS SwiftPM resource-bundle tuple sort from
`origin/main` at `0545580e`, its registered slice passed `5` focused tests and
`94` coverage tests. Changed-line coverage was `100%` over zero task-owned lines,
and the standalone probe copied all `900` bundles with a `106.406 ms` mean and
`98.234 ms` minimum. The exact staged-tree report at
`.runtime/pre-commit-performance/20260802-120702-8f83ecc1/report` completed the
full Swift gate, `5652` Python tests with `14` skips, and `132` integration tests
with one skip. All `148` performance probes ran, all `20` direct probes passed
their targeted tests and coverage commands, and there were `0` verification
failures. The resource-bundle probe retained all `900` copied bundles and its
mean stayed within threshold at `+1.25%`; its context-only minimum sample was
`+7.56%`.

The report's only direct timing alert was deterministic VLM completion scanning,
which sampled `22.727 ms` and `25.782 ms` (`+13.44%`) while retaining `6000`
completion tokens, zero split calls, and `400` prompt-count calls. Ten alternating
equivalent-worktree repetitions against `origin/main@0545580e` disproved the
alert: means were `24.566 ms` and `24.672 ms` (`+0.43%`), while minimum/maximum-
trimmed means were `24.665 ms` and `24.393 ms` (`-1.10%`). Every repetition
retained the same token and call-count invariants. This is non-reproducing
measurement noise, not an accepted regression; no performance-regression
override was used. The report's `32` context-only timing alerts had no
verification failures. The backend identity probe remained `ok`: matched
worker-boundary p95 was `0.000479 ms`, control-plane stamping and recovery p95
was `0.001642 ms`, all `140000` mismatches produced zero output, retry counts
remained `3/2/1`, and coalesced/fresh/duplicate-tool counts remained `1/2/0`.
Only these evidence paragraphs changed after the exact staged-tree report.

After synchronizing the code-evaluation read-only flag binding from
`origin/main` at `6457b21b`, the registered stdio slice passed `19` focused tests
and `19` coverage tests. Its PR-scope allowlist reported `100%` over zero
task-owned lines. The standalone probe retained one static sandbox-profile build,
`6000` stdio stat calls, `5119` tail characters, and a `76.033 ms` stdio mean.

The exact staged-tree report at
`.runtime/pre-commit-performance/20260802-133627-bad9a417/report` completed the
full Swift gate, `5653` Python tests with `14` skips, and `132` integration tests
with one skip. All `148` performance probes ran, all `20` direct probes passed
their targeted tests and coverage commands, and there were `0` verification
failures. The backend identity probe remained `ok`: matched worker-boundary p95
was `0.000517 ms`, control-plane stamping and recovery p95 was `0.001660 ms`, all
`140000` mismatches produced zero output, retry counts remained `3/2/1`, and
coalesced/fresh/duplicate-tool counts remained `1/2/0`.

Two direct timing samples crossed their thresholds in the single report. Vision-
family config resolution sampled `4.147 ms` and `4.795 ms` (`+15.64%`), but ten
alternating equivalent-worktree repetitions measured `4.388 ms` and `4.190 ms`
(`-4.51%`); minimum/maximum-trimmed means improved by `4.05%`. Every repetition
retained `1309` tokens, zero prompt splits, zero metadata iterations, and a
`312`-byte configuration footprint. This alert is non-reproducing measurement
noise.

Worker registry load/unload sampled `0.004516 ms` and `0.006002 ms` in the full
report. Ten alternating repetitions measured `0.004499 ms` and `0.005589 ms`,
with minimum/maximum-trimmed means of `0.004465 ms` and `0.005562 ms`. The
approximately `0.0011 ms` cost per model load is the required construction and
binding of one `BackendModelIdentity` value on each `LoadedModel`; it is outside
the inference request path and is accepted as the explicit correctness tradeoff
for stale-residency enforcement. All repetitions retained `8196096` resident
bytes, one loaded-model listing sort, and the same `250/2000/3000` loop, preload,
and request counts. The commit records the required performance-regression
override reason for this model-load-only cost. The report's `26` context-only
timing alerts had no verification failures. Only these evidence paragraphs
changed after the exact staged-tree report.

After synchronizing the dev-up metadata-version prefix slice from
`origin/main` at `21621613`, its registered slice passed `6` focused tests and
`64` coverage tests. Changed-line coverage was `100%` over zero task-owned
lines, and the standalone probe retained `2000` dist-info records with a
`0.180548 ms` mean and `0.141375 ms` minimum.

The exact staged-tree report at
`.runtime/pre-commit-performance/20260802-144656-96fb94f2/report` completed the
full Swift gate, `5653` Python tests with `14` skips, and `132` integration tests
with one skip. All `148` performance probes ran, all `20` direct probes passed
their targeted tests and coverage commands, and there were `0` verification
failures. The backend identity probe remained `ok`: matched worker-boundary p95
was `0.000512 ms`, control-plane stamping and recovery p95 was `0.001491 ms`, all
`140000` mismatches produced zero output, retry counts remained `3/2/1`, and
coalesced/fresh/duplicate-tool counts remained `1/2/0`.

Five direct timing samples crossed their thresholds in the single report:
deterministic image output-byte accounting (`+13.38%`), rerank request selection
(`+5.16%`), performance-registry cold loading (`+8.94%`), vision-family config
resolution (`+14.50%`), and integration binary resolution (`+7.87%`). Ten
base/head-alternating repetitions in equivalent worktrees disproved every
alert. Minimum/maximum-trimmed means changed by `-10.40%` for image output,
`+1.39%` for rerank request selection, `+0.58%` for registry cold loading,
`+4.65%` for vision-family config resolution, and `+0.90%` for integration
binary resolution. Rerank total elapsed improved by `0.66%`. Every repetition
retained the same output counts and byte totals, rerank document/result counts
and checksum, vision token/split/metadata/footprint counters, and integration
candidate, directory, and memory counters. These alerts are non-reproducing
measurement noise, not accepted regressions. The report's `25` context-only
timing alerts had no verification failures. The previously measured and
accepted approximately `0.0011 ms` identity-construction cost per model load
remains documented above; it is outside inference dispatch and is the only
intentional performance tradeoff. Only these evidence paragraphs changed after
the exact staged-tree report.

After synchronizing the four-state prefix snapshot fast path from `origin/main`
at `968c508a`, its registered slice passed `14` focused tests and `14` coverage
tests at `100%` over zero task-owned lines. The standalone probe retained
checksum `68071200`, `80` iterations, `4096` layers, and `685` peak bytes while
measuring a `356.562 ms` mean and `361.334 ms` p95. In the final full report the
same probe improved from `373.344 ms` to `359.971 ms`, with p95 improving from
`380.700 ms` to `360.593 ms` and all structural counters unchanged.

The exact staged-tree report at
`.runtime/pre-commit-performance/20260802-160426-4299f27d/report` completed the
full Swift gate including `907` menu-bar tests, `5653` Python tests with `14`
skips, and `132` integration tests with one skip. All `148` performance probes
ran, all `20` direct probes passed their targeted tests and coverage commands,
and there were `0` verification failures. The backend identity probe remained
`ok`: matched worker-boundary p95 was `0.000423 ms`, control-plane stamping and
recovery p95 was `0.001458 ms`, all `140000` mismatches produced zero output,
retry counts remained `3/2/1`, and coalesced/fresh/duplicate-tool counts remained
`1/2/0`.

Two direct timing samples crossed thresholds in the single report. Deterministic
image output-byte accounting measured `21.067 ms` and `22.264 ms` (`+5.68%`),
while the immediately preceding ten alternating equivalent-worktree repetitions
measured a `-10.40%` minimum/maximum-trimmed change with identical output counts,
byte totals, checksum, and zero byte-scan calls. Integration binary resolution
improved from `14.623 ms` to `13.439 ms`; only its derived removal-savings metric
varied by `8.561 ms` against a `5 ms` absolute threshold. Repeated measurements
on this unchanged helper have independently returned that metric to a `0.76 ms`
difference and to a `5.272 ms` improvement, always with `1200` directories and
identical memory invariants. The only new mainline production change is the
prefix snapshot fast path measured above, so neither alert has a causal path to
that merge. They are sampled noise, not accepted regressions. The report's `31`
context-only timing alerts had no verification failures. The approximately
`0.0011 ms` identity-construction cost per model load remains the only accepted
performance tradeoff and is outside inference dispatch. Only these evidence
paragraphs changed after the exact staged-tree report.

After synchronizing the Swift binary debug-suffix fast path from `origin/main`
at `894df9e3`, its registered slice passed `30` focused tests and `30` coverage
tests at `100%` over zero task-owned lines. The standalone merged-tree probe
retained `1501` candidates, `1200` removal directories, and the expected memory
invariants while measuring binary resolution at `12.294 ms`. The exact staged
tree report at
`.runtime/pre-commit-performance/20260802-170956-d15f6d9f/report` completed the
full Swift gate including `907` menu-bar tests, `5653` Python tests with `14`
skips, and `132` integration tests with one skip. All `148` probes ran, all `20`
direct targeted test and coverage commands passed, and there were `0`
verification failures. The backend identity probe remained `ok`: matched
worker-boundary p95 was `0.000443 ms`, control-plane stamping and recovery p95
was `0.001408 ms`, all `140000` mismatches produced zero output, retry counts
remained `3/2/1`, and coalesced/fresh/duplicate-tool counts remained `1/2/0`.

Five direct timing samples crossed thresholds in that single report:
multimodal local URI preprocessing (`+8.78%`), deterministic embedding's
single-cycle submetric (`+5.26%`), performance-registry cold loading (`+10.42%`),
deterministic VLM completion scanning (`+17.35%`), and integration binary
resolution (`+16.76%`). Immediate reverse-order and forward-order measurements
returned the multimodal, embedding, and registry aggregate changes to `+2.54%`,
`+0.21%`, and `+0.50%`, respectively, with unchanged call, checksum, and memory
counters. Ten alternating VLM repetitions measured `24.220 ms` and `25.094 ms`
(`+3.61%`); minimum/maximum-trimmed means changed by `+4.48%`, and every run
retained `6000` completion tokens, zero split calls, and `400` prompt-count calls.
Five alternating equal-length-worktree comparisons of the synchronized
integration change measured `14.231 ms` before and `11.864 ms` after
(`-16.63%`), while the removal-savings metric improved by `3.534 ms`; all runs
retained `1501` candidates, `1200` directories, and identical memory invariants.
These alerts are sampled noise, not accepted regressions. The report's `25`
context-only timing alerts had no verification failures. The approximately
`0.0011 ms` identity-construction cost per model load remains the only accepted
performance tradeoff and is outside inference dispatch. Only these evidence
paragraphs changed after the exact staged-tree report.

After synchronizing the package build-triple sort and changed-scope singleton
ASCII-line fast paths from `origin/main` at `20f4dcd4`, the package slice passed
`107` focused tests and `107` coverage tests at `100%` over zero task-owned
lines. Its standalone probe retained `1500` build triples while measuring a
`0.712806 ms` mean, `0.629792 ms` minimum, `0.682505 ms` CLI mean, and
`7.451065 ms` tail-debug mean. The changed-scope slice passed `69` focused tests
and `69` coverage tests at `100%` over zero task-owned lines; its standalone
probe preserved zero source reads and measured the singleton workload at
`28.614 ms`.

The exact staged-tree report at
`.runtime/pre-commit-performance/20260802-182231-0805e426/report` completed the
full Swift gate including `907` menu-bar tests, `5653` Python tests with `14`
skips, and `132` integration tests with one skip. All `148` probes ran, all `20`
direct targeted test and coverage commands passed, and there were `0`
verification failures. The synchronized changed-scope singleton probe was `ok`,
improving from `23.100 ms` to `22.805 ms`; the package context probe's
byte-identical base/head code produced one non-gating `+13.01%` mean sample.
The backend identity probe remained `ok`: matched worker-boundary p95 was
`0.000447 ms`, control-plane stamping and recovery p95 was `0.001399 ms`, all
`140000` mismatches produced zero output, retry counts remained `3/2/1`, and
coalesced/fresh/duplicate-tool counts remained `1/2/0`.

Three direct timing samples crossed thresholds in that single report:
deterministic image edit digest reuse (`+35.15%`), deterministic image output
byte accounting (`+8.47%`), and integration cleanup removal savings (a
`7.181 ms` difference against a `5 ms` absolute threshold). The image runtime
and probes are unchanged; prior alternating evidence measured edit means at
`11.316 ms` and `11.182 ms` (`-1.18%`) and output minimum/maximum-trimmed means
at `-10.40%`, with identical digest calls, output counts, byte totals, checksum,
and zero byte-scan calls. Five equal-length-worktree integration comparisons
measured binary resolution improving from `14.231 ms` to `11.864 ms`
(`-16.63%`) and removal savings improving by `3.534 ms`, with `1501` candidates,
`1200` directories, and identical memory invariants. The only newly synchronized
production changes are the package and changed-scope fast paths measured above,
so none has a causal path to these direct samples. They are sampled noise, not
accepted regressions. The report's `27` context-only timing alerts had no
verification failures. The approximately `0.0011 ms` identity-construction cost
per model load remains the only accepted performance tradeoff and is outside
inference dispatch. Only these evidence paragraphs changed after the exact
staged-tree report.

## Known Boundaries

- Process respawn is not implemented by current request-path production code.
  The integration harness does restart a worker on the same endpoint and proves
  stale identity rejection, while production recovery performs one coalesced
  route/model rebind through the existing worker supervisor boundary.
- Maintenance RPCs are not inference dispatch and remain outside the identity
  envelope. Any maintenance operation that internally evaluates a model must
  continue to resolve a backend-owned loaded handle through its existing job
  contract; it cannot be used as a public inference fallback.
- Abort is request-scoped and carries no model output, so it remains keyed by
  request ID rather than backend model identity.

## Independent Review Corrections

The final independent specification review identified a phase-aware decode
confusion case in both worker implementations: a decode handle created by
residency A could be combined with a valid execution identity for residency B.
The corrected design binds each decode context to its prefill request, model
handle, and backend identity. Swift validates and acquires the decode lease in
one registry actor operation. Python records the binding beside the request
lease and validates it under the registry lock. Both paths reject cross-handle
or cross-identity decode before consuming the context or emitting output, and
their regression tests prove the original owner can still decode afterward.
The phase-aware control-plane path copies one `ExecutionMetadata` value into
both `Prefill` and `Decode`, so those RPCs retain one execution request ID.
`parent_request_id` remains request-lineage metadata and cannot substitute for
decode-handle ownership. Worker tests that exercised both phases were corrected
to preserve this production contract.

A later independent specification review found that snapshot restore preserved
the previous process's worker instance ID even after validating the snapshot
against a current residency. Restore now rebinds the complete execution backend
identity to the selected loaded residency before runtime prefill and context
creation. The restart regression uses distinct worker instance IDs and proves
the new owner and current residency can consume the restored handle.

## Remote Review Corrections

The pull request review found four additional implementation and evidence gaps.
Snapshot restore now derives the expected identity from the snapshot's own
execution metadata before comparing residency keys, so a snapshot from another
route generation is rejected before runtime prefill. Replay-safe streaming now
uses a labeled loop exit so a recoverable mismatch cannot leak trailing events
from the failed stream before the one allowed retry.

The worker performance probe retains the matched direct-guard microbenchmark but
measures mismatch output ordering through the in-process inference handler. Its
zero-output metric is therefore an observed handler result rather than a fixed
counter. The PR performance workflow imports the exact pull request base commit
into the head checkout and passes that SHA to changed-line coverage. The local
pre-commit gate instead passes the temporary repository's synthetic `HEAD`,
whose tree is the exact staged-comparison base, while the index snapshot remains
in its worktree. Only an interactive direct script invocation uses `origin/main`
as its default; a clean CI checkout never compares coverage to itself.

The final Linux performance matrix exposed a test-isolation error in the probe
contract test: it assigned the temporary repository root and fake subprocess to
the dictionary returned by `runpy.run_path()`, while the loaded functions read
their actual `__globals__` mapping. macOS masked the error by successfully
running the real Swift probe; Linux correctly failed when the control-plane
package imported `OSLog`. The test now injects both dependencies through the
function globals and asserts that the fake subprocess runs exactly once from the
temporary repository, so the contract test is platform-independent and cannot
fall through to a real Swift build.

A route-agnostic load completion cannot safely associate a changed handle with
an unknown worker instance. If such a completion changes an existing handle, the
catalog advances the route generation atomically with the handle and replaces
the old worker identity with the `legacy-unbound-worker` sentinel. This preserves
legacy handle routing without copying a real worker UUID across generations;
identity-enforcing workers fail closed until a route-aware load binds the actual
worker instance.

Two review suggestions were intentionally not applied because they contradict
the approved replay and replacement rules above. A caller arriving after a
failed-generation recovery task has completed cannot adopt an arbitrary newer
binding because that binding may belong to an explicit unload or replacement.
Likewise, phase-aware prefill events remain response-opening backend events:
once prefill has been exposed, a decode mismatch returns
`partial_stream_failure` and does not replay. Focused tests preserve both
contracts.
