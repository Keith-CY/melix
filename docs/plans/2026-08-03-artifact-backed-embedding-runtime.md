# Artifact-Backed Embedding Runtime

**Date:** 2026-08-03
**Issue:** #3166
**Status:** Implementation in Review; Production Acceptance Blocked
**Owner:** Codex

## Goal

Replace model-family-shaped digest projection on product embedding routes with a
local, artifact-backed MLX encoder runtime for BERT and XLM-R checkpoints. Keep
the existing worker and `/v1/embeddings` response contracts, preserve a clearly
named deterministic fixture backend for tests and development, and expose
enough load and execution evidence to prove which artifact and vector contract
produced an embedding.

## Governing Boundaries

- The Swift control plane continues to own admission, route selection, and the
  immutable backend model identity.
- The Python worker owns tokenizer loading, encoder execution, pooling,
  normalization, output validation, and model-local receipts.
- Local model configuration and weights are the execution source of truth.
  Runtime code must not download artifacts or execute remote model code.
- `EmbedRequest`, `EmbedResponse`, and `/v1/embeddings` remain unchanged.
- Model kind and structured route declarations remain the routing source of
  truth. The runtime defensively validates artifact capabilities but does not
  invent a route from a directory name.
- Multi-vector and media-capable artifacts are refused until their output
  cardinality and modality contracts are typed.
- Workerless control-plane loads derive the effective route from catalog truth;
  Python-backed embeddings fail closed when that route has no live worker.

## Current-State Audit

`DeterministicEmbeddingRuntime` is the default worker embedding runtime. Its
`bert-v1` and `xlmr-v1` backends canonicalize text differently but both project
a SHA-256 digest into a family-shaped vector. The development catalog and Swift
bootstrap metadata advertise those identifiers as BERT and XLM-R execution,
even though no tokenizer, model configuration, or weight artifact is loaded.

The worker model registry already owns the model-handle lifecycle, memory
admission estimate, backend identity, and loaded-model summaries. The embedding
core already preserves request order and the public response shape. This change
therefore belongs behind the existing embedding runtime interface and should
reuse the loaded handle rather than adding another model cache.

## End-State Interface

The worker default is an embedding runtime router with explicit backend IDs:

- `deterministic-fixture-v1`: named fixture/development digest projection only;
- `mlx-bert-v1`: local BERT encoder artifact;
- `mlx-xlmr-v1`: local XLM-R encoder artifact.

The legacy `bert-v1` and `xlmr-v1` identifiers are rejected rather than treated
as fixture aliases. Development callers must migrate explicitly to
`deterministic-fixture-v1` and product callers must select an artifact backend.

The artifact runtime exposes the existing methods:

```python
load_model(model_spec) -> loaded_model
estimate_resident_bytes(model_spec) -> int
embed_inputs(loaded_model, inputs, *, request_id="") -> list[list[float]]
```

The loaded model owns the tokenizer, MLX encoder, immutable artifact descriptor,
and load receipt. `embed_inputs` tokenizes the whole request batch, validates
all rows, invokes the encoder exactly once, pools and normalizes on device, then
materializes ordered Python vectors once at the worker response boundary.
Artifact load, execution, and teardown run on the worker's shared single-owner
MLX executor.

## Artifact Contract

The runtime reads `config.json`, local tokenizer files, and one or more local
`.safetensors` weight files from `ModelSpec.model_path`. It accepts BERT and
XLM-R model types with single dense token embeddings. It resolves:

- backend and architecture from `config.json`;
- dimensions from `hidden_size`;
- maximum length from the smallest valid artifact/tokenizer/config limit;
- pooling from Sentence Transformers pooling metadata or an audited
  `embedding_pooling_mode` override;
- normalization from Sentence Transformers normalization metadata or an
  audited `embedding_normalization` override;
- vector kind and input modalities from explicit artifact metadata, defaulting
  only to single dense text for the supported encoder architectures;
- dtype from loaded weights.

When present, `modules.json` must describe exactly the supported ordered
`Transformer -> Pooling -> optional Normalize` pipeline. Any other active
module, duplicate stage, reordered stage, or nested Transformer artifact is
refused instead of being silently ignored. `sentence_bert_config.json`
contributes its `max_seq_length` limit. Stale module directories that are not
selected by `modules.json` do not affect execution. Decoder, encoder-decoder,
cross-attention, relative-position, and relative-key configurations are refused
with a typed unsupported-config error.

Sentence Transformers pooling metadata is interpreted by one shared catalog
and loader predicate. Exactly one of `cls`, `mean`, or `last_token` may be true;
every other true `pooling_mode_*` flag makes the artifact unsupported rather
than silently reducing a composite pooling pipeline. Catalog sidecar discovery
uses the same fallback glob as the loader and refuses symbolic links in every
selected path component. Catalog admission also refuses every media component
that the loader refuses.

An override is accepted only when it names a supported value and remains
consistent with the artifact's dimensions, modality, and output cardinality.
The load receipt records both requested and effective values.

Before inspection, the worker copies every supported config, tokenizer,
Sentence Transformers contract, and safetensors file through no-symlink file
descriptors into a private read-only snapshot. Inspection, hashes, tokenizer
construction, and weight loading consume only that snapshot; the admitted
source path remains provenance and is never reopened by the backend. Model and
tokenizer hashes are therefore computed from the exact immutable bytes used at
load, including tokenizer-added-token and vocabulary/merge files. Snapshot
device, inode, size, modification time, change time, and content hashes are
verified after backend load; any mutation of the bound snapshot fails the load.

## Numerical Contract

- Supported pooling modes are `cls`, `mean`, and `last_token`.
- Attention masks use the most-negative finite value representable by the
  execution dtype, never negative infinity.
- A row with no active tokens is refused before encoder execution.
- Tokenizer fields must contain integral rank-two rectangular rows;
  `input_ids`, `attention_mask`, and optional `token_type_ids` must have exactly
  the same batch and sequence shape before any MLX array is constructed.
- Mean pooling divides by a validated positive active-token count.
- L2 normalization is evaluated in float32 with a positive epsilon.
- Every returned value must be finite and every row must match the effective
  dimension. A violation fails the request without a partial vector response.

## Receipt Contract

The model-handle load receipt records:

- requested and effective backend ID;
- model and tokenizer hashes;
- requested and effective pooling and normalization;
- requested and effective dimensions and maximum length;
- vector kind and dtype;
- estimated and measured resident bytes.

The registry's pre-load estimate is only an early reservation. After the
runtime loads the private snapshot, the registry reads the snapshot-bound
estimate from the load receipt, replaces the early reservation, and reruns both
process and request memory admission. A failed second admission closes the
loaded runtime object and leaves neither a model handle nor reserved bytes.

The request-local receipt records request ID, batch size, input token count,
forward count, output row count, dimensions, vector kind, dtype, and
finite-output status. The worker retains the latest 64 receipts per loaded
model under a lock and projects the latest receipt into `ListLoadedModels`
diagnostics. This does not change the public embedding response.

## TDD Delivery Slices

### Slice 1: Artifact Contract And Fail-Closed Loading

Add one failing public-runtime test at a time for local-only path validation,
BERT/XLM-R config classification, weight/tokenizer identity, effective metadata,
and typed refusals for unsupported media or multi-vector artifacts. Implement
only enough artifact parsing and backend routing to make each test pass.

### Slice 2: Batched Encoder Execution

Use a CPU-safe injected tokenizer and encoder test seam. First prove that a
multi-row request performs one tokenizer call and one encoder forward while
preserving row order. Then implement the batch path without singleton loops or
duplicate-input substitution.

### Slice 3: Pooling And Numerical Safety

Add golden-vector tests for `cls`, `mean`, and `last_token`, followed by a
float16 heavily padded mask canary. Add a fully padded row test that proves the
encoder was not called, then implement pre-forward validation, finite mask
sentinels, float32 normalization, and final finite/shape validation.

### Slice 4: Runtime Lifecycle And Receipts

Load the artifact runtime through `WorkerRegistry`, prove the model handle owns
the loaded tokenizer and weights, and expose immutable load evidence through
loaded-model metadata. Add request receipt assertions for backend identity,
batch shape, dtype, one-forward execution, and residency.

### Slice 5: Catalog And Product Defaults

Rename the current digest route to `deterministic-fixture-v1`. Ensure only
fixture/dev entries advertise it. Admit artifact-backed BERT/XLM-R embedding
models only from explicit structured model metadata and supported artifact
evidence. Remove any production catalog claim that maps `bert-v1` or `xlmr-v1`
to digest execution.

### Slice 6: Endpoint And Evidence Gates

Exercise the unchanged worker and HTTP embedding contracts for ordering,
dimensions, usage, typed failures, and model identity. Register the scoped
performance probe and capture real Apple Silicon parity/residency evidence when
the checkpoint prerequisites are present.

## Performance Probes

### PR-Scoped CPU-Safe Batch Probe

Register an evidence-only probe in `infra/perf/pr_scoped_probes.json`. Its
injected tokenizer and encoder use the public artifact runtime interface and
report:

- `batch_32_forward_count`;
- `batch_32_tokenizer_count`;
- `batch_32_samples_per_second`;
- `singleton_32_forward_count`;
- `singleton_32_tokenizer_count`;
- `singleton_32_samples_per_second`;
- `batch_speedup_ratio`;
- `nonfinite_output_count`;
- `output_dimension_mismatch_count`.

Success requires exactly one batch tokenizer call and forward, exactly 32
singleton tokenizer calls and forwards,
zero non-finite values, zero shape mismatches, and at least `2.0x` batch
throughput. Runtime latency is evidence-only on CI; correctness counters are
hard gates.

### Apple Silicon Artifact Acceptance

The real-model acceptance harness runs against one pinned BERT checkpoint and
one pinned XLM-R checkpoint and records:

- artifact and tokenizer hashes;
- cosine similarity for a fixed golden corpus against a trusted reference;
- float16 padded-row finite counts;
- batch and singleton throughput;
- post-load estimated and measured resident bytes;
- request receipts and output dimensions.

Success requires cosine similarity `>= 0.999` for every golden row, zero
NaN/Inf values, typed pre-forward refusal for fully padded rows, exactly one
forward for batch 32, batch throughput `>= 2.0x` singleton throughput, and warm
measured resident bytes within `20%` of the post-load estimate.

## Measurement Points

- Artifact discovery: before runtime load, to prove routing and refusal reasons.
- Load start/end: file identities, MLX active memory delta, dtype, and effective
  vector contract.
- After tokenization and before forward: batch size, token count, row validity,
  and padded-mask dtype.
- Around encoder invocation: forward count and elapsed time.
- After pooling/normalization: output shape and finite-value validation.
- Worker response boundary: ordered row count and request receipt completion.

Production observability mode is `minimal`: immutable load facts plus bounded
last-request counters. Golden, throughput, and residency comparisons are
`evidence` mode and must produce machine-readable artifacts.

## Verification

Focused verification during implementation:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_artifact_embedding_runtime.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_embedding_runtime.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python --extra mlx coverage run -m pytest -q <changed-scope tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json <changed Python files>
python3 scripts/pr_scoped_performance_run.py --probe artifact-embedding-batch
git diff --check
```

Before commit or PR handoff, the repository-wide gate remains mandatory:

```bash
make swift-test
make py-test
make integration-test
```

## Acceptance Criteria

- Product BERT and XLM-R embedding routes load only local artifact-backed MLX
  encoders; digest projection is visibly fixture-only.
- A request batch performs one tokenizer operation and one encoder forward and
  preserves input order.
- Pooling, normalization, dimensions, maximum length, vector kind, and dtype
  come from supported artifact evidence plus audited overrides.
- Invalid, fully padded, media-capable, or multi-vector artifacts fail closed
  with typed reasons before returning vectors.
- Load and request receipts bind outputs to artifact hashes and effective vector
  shape without changing the public response schema.
- Golden parity, finite-output, throughput, and residency gates meet the issue
  targets.
- Changed-scope automated coverage is at least 95 percent.

## Safe Exit

If pinned production-checkpoint acceptance is unavailable, keep the development
default on the explicitly named deterministic fixture backend and require
structured artifact evidence before catalog admission. Record the missing
acceptance evidence rather than treating tiny local checkpoints as proof of
production-model parity or residency.

## Implementation Evidence

Implemented and independently reviewed through 2026-08-04:

- the default worker router now separates `deterministic-fixture-v1` from
  `mlx-bert-v1` and `mlx-xlmr-v1`;
- local artifact inspection binds config, tokenizer, safetensors, pooling,
  normalization, dimensions, maximum length, vector kind, dtype, and hashes;
- the MLX encoder performs one forward per request batch with finite masking,
  supported pooling, float32 L2 normalization, and typed contract failures;
- generated tiny local BERT and XLM-R checkpoints exercise real tokenizer and
  safetensors loading, including a float16 padded attention canary;
- registry load receipts expose requested and effective contract values without
  changing `EmbedRequest`, `EmbedResponse`, or the HTTP response schema;
- request receipts are bounded, request-ID-keyed, concurrency-safe, and exposed
  through loaded-model diagnostics;
- artifact mutation after hashing is detected before the handle is admitted;
- tokenizer construction and weight loading consume a private read-only
  snapshot, so repeated source-path A-to-B-to-A swaps cannot change loaded bytes
  while preserving an A receipt;
- active Sentence Transformers modules are restricted to the ordered
  `Transformer -> Pooling -> optional Normalize` pipeline, and tokenizer rows
  are validated as integral, rectangular, and shape-equal before MLX conversion;
- unsupported BERT decoder, cross-attention, and relative-position variants
  fail closed instead of silently dropping tensors;
- catalog admission and runtime loading share the same unsupported-encoder
  predicate, so projected artifact capability never exceeds the loader contract;
- the RPC boundary converts protobuf repeated scalar containers to one concrete
  input batch before tokenization, while direct callers retain the same ordering;
- registry-discovered embedding summaries produce generic Swift worker specs,
  while missing specs and unavailable Python routes fail instead of recording a
  synthetic local load success;
- workerless Python embedding loads derive their route from catalog metadata and
  fail with `worker_unavailable`, while workerless Swift text remains local;
- catalog and loader share the complete Sentence Transformers pooling contract,
  reject every recognized media-component alias consistently, validate the
  loader's complete positive-integer and activation contract, and refuse any
  symlinked config, tokenizer, weight, or sidecar input under the same fallback
  discovery rule;
- model loads route from the control-plane service's resolved catalog summary,
  so a stale or differently seeded worker-registry catalog cannot downgrade an
  embedding load to the default text route;
- memory admission is repeated against the private-snapshot load receipt, with
  exact ledger replacement and loaded-runtime cleanup on rejection;
- artifact-backend teardown is idempotent, releases tokenizer and encoder
  ownership on the shared MLX executor thread, and rejects post-close reuse;
- Swift and Python development catalogs advertise digest projection only as a
  fixture with an explicit backend ID and preserve detected XLM-R family
  identity; missing fixture backend IDs and legacy `bert-v1`/`xlmr-v1`
  execution are rejected.

Focused evidence:

- artifact runtime tests: `166` collected; the macOS artifact probe executes the
  complete file with six dependency deprecation warnings, while Linux worker
  and catalog probes execute the split platform-neutral contract suites;
- performance registry contract: commands that replay the complete artifact
  runtime use the explicit MLX dependency extra; Linux context probes retain
  only platform-neutral contract nodes and do not collect the MLX runtime file;
- isolated-environment command validation: the maintenance representative
  passed `34` tests and the worker-registry representative passed `187` tests
  after each installed its own 79-package MLX environment;
- coverage-helper suite: `73 passed` in each final targeted runner replay;
- focused control-plane Swift coverage run: `353 tests` across the control-plane
  service, model catalog, and Python bridge suites;
- changed-line Swift coverage: `75/75 = 100%` across `ModelCatalog.swift`,
  `PythonBridgeWorkerClient.swift`, `WorkerRoute.swift`, and
  `ControlPlaneService.swift`;
- full-hook tokenizer/encoder probe: one batch tokenizer call and forward versus
  32 singleton tokenizer calls and forwards, `20,325.85` versus `794.98`
  samples per second (`25.57x`), zero non-finite outputs, and zero dimension
  mismatches;
- #3166 aggregate Python changed-scope coverage: `1,136/1,185` measurable
  changed lines, `95.86%`; the catalog scope is `97.62%` and the artifact
  runtime is `93.90%`;
- coverage-helper changed-scope coverage: `63/63` measurable changed lines,
  `100%`, with staged, unstaged, and untracked paths included and zero
  measurable lines treated as failure.

The first complete pre-commit execution on 2026-08-04 completed every functional
gate:

- `make swift-test` passed;
- `make py-test` passed with `5,988 passed`, `14 skipped`, and six warnings;
- `make integration-test` passed with `132 passed` and one skipped;
- all `150` selected performance probes completed.

That execution correctly stopped before commit with
`status=verification_failed`: 12 existing probes selected newly changed files
without replaying the corresponding changed tests, while the artifact embedding
probe itself passed at `96%` changed-scope coverage. The registry remediation
then produced `100%` coverage for all nine affected maintenance/model-ops probes,
`97%` for the worker-registry probe, and `98%` for both model-registry probes.
The changed-scope parser's one noisy `1.62 ms` to `1.79 ms` sample did not
reproduce: 24 interleaved runs differed by `0.26%`, and a formal targeted runner
replay passed `48/48` changed lines with base `1.6480 ms` and head `1.6095 ms`.

The second complete pre-commit execution also passed the full Swift, Python, and
integration gates and completed all 150 probes, but stopped on three direct
performance samples. Investigation separated a real dependency-boundary cost
from two undersampled measurements:

- catalog admission and execution now share pure artifact predicates through
  `artifact_embedding_contract.py`; ordinary model-registry scans no longer
  import the 1,300-line artifact execution runtime or `MLXRuntimeExecutor`;
- the extracted contract passed all 166 artifact runtime tests and covered
  `45/46 = 97.83%` changed lines;
- with both base and head pinned to Python 3.12 and the registry probe strengthened
  from five to 20 samples without changing its 5% threshold, three formal runs
  measured `+2.89%`, `-0.71%`, and `+4.41%`, each with 98% changed-line coverage;
- the maintenance readback probe now records nine samples instead of three,
  again without changing its threshold; three formal runs measured `+0.85%`,
  `-0.51%`, and `+0.53%`, each with 100% changed-line coverage;
- the unchanged changed-scope singleton hot path measured improvements in all
  three formal reruns, with 100% changed-line coverage.

Pinned production BERT/XLM-R parity and the `20%` measured-residency gate remain
an explicit acceptance evidence gap. A read-only cache audit found a 4.3 GiB
BAAI BGE-M3 snapshot, but it contains `pytorch_model.bin` rather than supported
safetensors and lacks the referenced `2_Normalize/config.json`; it is not a
usable acceptance checkpoint for this runtime. No production default was
switched to an artifact model, and the tiny local checkpoints are not
represented as production evidence.

PR CI exposed two portability defects in the performance evidence. First, the
probe-only fake encoder entered production MLX tensor operations, so Linux
coverage jobs failed while loading `libmlx.so` even though the workload was
synthetic. `MLXArtifactEmbeddingBackend` now owns an injected tensor-operations
boundary: production uses the same lazy MLX conversion, pooling, and evaluation
implementation, while the probe supplies platform-neutral tensor operations and
still exercises the real production batching method. The encoder call counter
therefore remains independent evidence of one forward for a batch of 32 rather
than a value synthesized by a probe-only backend. A focused regression guard is
installed before the probe script loads and rejects any `mlx` import throughout
script loading and measurement.

Second, Linux context probes no longer collect the complete macOS-only artifact
runtime test file; they retain the platform-neutral artifact probe contract
nodes. Clean CI checkouts receive the exact pull-request base SHA through
`MELIX_CHANGED_SCOPE_COVERAGE_DIFF_FROM`, so the strict zero-measurable-lines
failure now evaluates the committed PR diff. Local pre-commit use still defaults
to `HEAD` and includes staged, unstaged, and untracked paths.

The repaired registry entries were then replayed through the exact PR-scoped
runner against the committed base and the candidate worktree. Every replay
completed its focused tests, changed-scope coverage gate, base probe, and head
probe:

- worker registry: `78 passed`, `67/69 = 97.10%` changed-line coverage;
- plain model-registry scan: `185 passed`, `278/282 = 98.58%`;
- README model-registry scan: `186 passed`, `278/282 = 98.58%`;
- artifact embedding: `248 passed` with six dependency warnings,
  `1,417/1,463 = 96.86%`;
- maintenance and VLM context probes: `36 passed` and `54 passed`, each at
  `1/1 = 100%` for its selected changed line;
- all four changed-scope helper probes: `73 passed` and `63/63 = 100%` in each
  replay.

## Pull Request Review Remediation

The final review pass tightens the artifact admission boundary without changing
the public embedding response schema:

- catalog admission and runtime inspection require a vocabulary-bearing
  tokenizer artifact; auxiliary token metadata alone is not executable;
- the shared encoder contract requires a positive `num_hidden_layers`, so an
  empty encoder stack or fractional layer count cannot be admitted as a model;
- MLX active-memory lookup selects the top-level API lazily, falls back to the
  legacy `metal` API only when present, and otherwise fails with a typed runtime
  error;
- load receipts preserve `0` for unrequested numeric limits and record the
  artifact-declared pooling and normalization alongside requested and effective
  values, keeping the audited override contract visible; an explicit invalid
  dimension override fails typed rather than being collapsed into that `0`;
- the production router surfaces the same migration guidance as the fixture
  backend resolver for retired digest backend IDs.

Focused tests must cover each refusal and receipt branch with at least 95%
changed-scope coverage, including changed runtime and registry test code rather
than production files alone. The artifact batch probe remains the direct performance
measurement point: it must preserve one tokenizer call, one encoder forward for
the 32-row batch, finite vectors, exact dimensions, and no direct regression.
The full versioned pre-commit gate remains mandatory before the remediation
commit.

## 2026-08-11 Vector Validation Single-Pass Slice

This Python-only performance slice is limited to artifact embedding output
validation in `MLXEmbeddingRuntime._embed_inputs(...)`. The affected path is
covered by the registered PR-scoped performance probe `artifact-embedding-batch`
in `infra/perf/pr_scoped_probes.json`, including focused `test_command`,
`coverage_command`, and `probe_command` entries.

The slice preserves the backend contract checks and receipt shape while merging
per-value `float(...)` coercion and finite-value validation into one loop. This
removes the previous second pass over every output vector (`all(math.isfinite(...))`)
on successful batches. The registered probe remains the evidence source for the
32-row artifact batch path: one tokenizer call, one encoder forward, finite
outputs, exact output dimensions, and batch throughput versus singleton calls.

Acceptance requires focused artifact runtime tests, changed-scope coverage for
the touched runtime/test/probe scope, a local Linux replay of the registered
probe, and green GitHub Actions PR-scoped performance before merge.
