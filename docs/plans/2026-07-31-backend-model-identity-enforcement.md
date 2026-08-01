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

- Python backend identity scope: `96.79%` (`603/623`).
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

## Verification Results

The final 2026-08-01 repository gates completed successfully against
`origin/main` at `a501bbb6`:

- `make bootstrap`
- `make proto`
- `make proto-check`
- `make swift-test` (`301` text-worker and `882` menu-bar tests passed,
  together with the control-plane and remaining Swift package suites)
- `make py-test` (`5494` passed, `14` skipped)
- `make integration-test` (`125` passed, `1` skipped)

The focused same-endpoint worker-restart integration test also passed. After
the final mainline merge, the atomic stale-cleanup and remote-provider routing
tests passed together, the registered performance and binary-resolution tests
passed (`15` tests). The remote-review corrections additionally passed all `14`
backend identity tests, all `254` OpenAI handler tests, the stale-generation
snapshot restore regression, the stream-consumption and phase-aware replay
regressions, and the in-process worker handler performance tests. The three
changed-line coverage totals are `96.79%`, `96.19%`, and `99.16%`.

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
