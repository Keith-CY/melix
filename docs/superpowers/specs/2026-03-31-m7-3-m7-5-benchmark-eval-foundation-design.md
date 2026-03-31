# M7.3-M7.5 Benchmark And Evaluation Foundation Design

## Context

Melix now has the first typed benchmark and evaluation schema foundation from `M7.1-M7.2`, but the runtime still lacks the executable platform behaviors required by the next M7 slices.

Current state:

- `ops.run_bench` can stream benchmark progress and metrics, but it still behaves like a thin bench wrapper over ad hoc worker logic.
- benchmark and evaluation results now have typed schema support, but there is no durable benchmark runner layer, no offline dataset packaging, and no evaluation execution path.
- release-gate and comparison work in later M7 slices depends on stable persisted job outputs, not only transient markdown.

This design covers the next bounded execution segment:

- `M7.3` Serving benchmark runners
- `M7.4` Offline dataset packaging and runners
- `M7.5` Evaluation-suite coverage

## Goal

Turn benchmark and evaluation execution into repository-owned, persistent, and reproducible product capabilities before queueing, export, VLM variants, community submission, or release-gate expansion.

## Non-Goals

This design does not cover:

- benchmark queueing, sample-size selection, and batch-factor scheduling from `M7.6`
- result export and comparison tables from `M7.7`
- VLM-specific benchmark variants from `M7.8`
- community submission and device identity from `M7.9`
- release-gate expansion for benchmark and evaluation evidence from `M7.10`

## Recommended Approach

Use one shared execution model with two typed job families:

- serving benchmark jobs
- evaluation-suite jobs

Both should persist through the same Python productization layer, while keeping execution semantics separate.

Why this approach:

- it reuses the newly landed schema foundation instead of inventing a second result path
- it gives later queueing and export slices one persistence model to build on
- it keeps serving throughput measurement and offline quality evaluation distinct enough to avoid semantic drift

## Alternatives Considered

### 1. Extend the existing bench markdown path only

Pros:

- minimal short-term code changes

Cons:

- blocks queueing, export, and release-gate evolution
- keeps result parsing fragile and UI-dependent
- does not help evaluation execution at all

### 2. Build queueing first, then attach runners later

Pros:

- queue semantics become available early

Cons:

- queues would carry under-specified job payloads
- later runner changes would rewrite queue persistence and result contracts
- increases risk of incompatible job-state migrations

### 3. Recommended: runner and persistence foundation first

Pros:

- durable benchmark and evaluation outputs exist before queueing and export
- later slices can reuse stable job and result documents
- lets deterministic and real-runtime evidence share one repository-owned shape

Cons:

- requires adding a new evaluation execution path now

## Architecture

### 1. Python Productization Persistence Layer

Add a benchmark and evaluation persistence module in the Python worker productization package.

Responsibilities:

- create durable job documents for serving benchmarks and evaluation suites
- persist typed result documents using the M7 schema helpers
- expose small helper functions that later queue, export, and release-gate flows can reuse

Persistence shape:

- benchmark jobs under a benchmark jobs root
- evaluation jobs under an evaluation jobs root
- each job owns:
  - a job manifest
  - one or more typed result documents
  - optional markdown or human-readable report artifacts

This layer should remain file-backed and deterministic first. No database should be introduced in this slice.

### 2. Serving Benchmark Runner

Refactor the current bench execution path so it produces:

- a typed benchmark job summary
- typed per-suite benchmark result documents
- the existing markdown report as a secondary artifact

Execution should remain worker-owned in Python. The control plane should orchestrate and surface results, not compute them.

The runner should support the currently implemented suites:

- `smoke`
- `latency`

It should also persist the parameters used to produce the job, even if the first slice only uses default parameters.

### 3. Evaluation Dataset Package Layer

Introduce a repository-owned offline dataset package format.

Each packaged dataset should declare:

- dataset ID
- schema version
- suite compatibility
- sample entries
- optional metadata such as split and source revision

The initial format should be simple JSON or JSONL plus a package manifest. It should avoid hidden network fetches and be fully runnable from local files.

### 4. Evaluation Runner

Add a dedicated evaluation execution path with a separate runner from serving benchmarks.

This runner should:

- accept an evaluation job definition
- load a packaged offline dataset
- execute the requested suite against the target model
- persist typed evaluation result documents

The first suite coverage should stay intentionally narrow and deterministic enough to validate the platform shape. The point of `M7.5` here is to land the execution interface and at least one reproducible suite, not to exhaust the full long-term suite catalog in one change.

### 5. Control-Plane Integration

Control-plane work should add explicit operator-facing execution paths for:

- `ops.run_bench`
- a new evaluation command family or operation path dedicated to evaluation execution

The control plane should:

- dispatch requests to the Python model-operations worker
- relay progress
- return typed benchmark or evaluation job and result payloads
- keep legacy markdown fields when useful for operator readability

The control plane should not own result persistence or scoring logic.

### 6. Desktop Integration

Desktop work in this slice should stay minimal.

Required behaviors:

- preserve the existing bench surface
- allow evaluation results to be surfaced once the control-plane path exists
- avoid building queue UIs, comparison tables, or community-submission views yet

This keeps the slice focused on platform truth rather than premature UI expansion.

## Data Flow

### Serving Benchmark

1. Desktop or client issues `ops.run_bench`.
2. Control plane translates the request into a worker benchmark request.
3. Python worker runner executes the requested suites.
4. Python productization layer persists:
   - benchmark job document
   - typed benchmark result documents
   - markdown report
5. Control plane returns typed benchmark payloads plus markdown compatibility fields.

### Evaluation Suite

1. Desktop or client issues a dedicated evaluation execution request.
2. Control plane dispatches to the Python worker evaluation runner.
3. Runner loads the requested local dataset package.
4. Runner computes suite metrics and persists:
   - evaluation job document
   - typed evaluation result document(s)
5. Control plane returns typed evaluation payloads to the caller.

## Error Handling

The system should fail explicitly on:

- missing packaged datasets
- unsupported suite IDs
- model capability mismatches
- malformed persisted job or result documents

Errors must remain typed and machine-readable. No error path should rely on parsing markdown.

## Testing Strategy

### Python

- unit tests for benchmark and evaluation persistence helpers
- runner tests for benchmark result generation
- runner tests for offline dataset loading and evaluation result generation
- release-gate compatibility tests proving the new benchmark result payload still feeds current benchmark evidence

### Swift

- control-plane tests for typed benchmark and evaluation replies
- command translation tests for any new evaluation command surface

### Integration

- serving benchmark smoke path with persisted result verification
- offline evaluation smoke path against a packaged dataset

## Acceptance

This segment is complete when:

- Melix can execute repository-owned serving benchmark jobs and persist typed results
- Melix can execute at least one offline packaged evaluation suite and persist typed results
- benchmark and evaluation jobs are durable, machine-readable, and control-plane visible
- later M7 queueing, export, and release-gate slices can build on these persisted job artifacts without rewriting the execution model
