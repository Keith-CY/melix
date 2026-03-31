# M7.6 Benchmark Queue, Sample Size, And Batch Factors Design

## Context

Melix now has:

- typed benchmark and evaluation schemas
- persisted serving benchmark artifacts
- persisted evaluation job and result artifacts
- a minimal control-plane execution path for evaluation

What is still missing for `M7.6` is the ability to queue benchmark and evaluation jobs with explicit reproducibility parameters and expose their queue state through product-owned surfaces.

Current gaps:

- benchmark execution starts immediately and has no queue identity beyond the transient worker stream
- evaluation execution also runs inline with no durable queue state
- benchmark parameters such as sample size and batch factor are not first-class on the worker request path
- operators cannot inspect benchmark or evaluation queue state from the control plane or desktop shell

## Goal

Add a repository-owned queue layer for benchmark and evaluation jobs, together with explicit parameterization for `sample_size` and `batch_factor`, so queued comparison workloads are reproducible and operator-visible.

## Non-Goals

This design does not cover:

- export and comparison tables from `M7.7`
- VLM-specific benchmark modes from `M7.8`
- community submission and device identity from `M7.9`
- benchmark/eval release-gate expansion from `M7.10`

## Recommended Approach

Introduce one small benchmark-or-evaluation queue store in the Python productization layer and surface queue snapshots through the control plane.

The queue should be:

- file-backed
- deterministic
- single-process
- explicit about state transitions

Why this approach:

- it builds directly on the persisted job artifacts from `M7.3-M7.5`
- it keeps queue semantics product-owned and inspectable
- it avoids prematurely adding a database or distributed scheduler

## Architecture

### 1. Queue Record Model

Each queued item should carry:

- queue item ID
- job kind (`benchmark` or `evaluation`)
- target model ID
- suite or suites
- reproducibility parameters:
  - `sample_size`
  - `batch_factor`
  - additional keyed parameters
- queue state:
  - `queued`
  - `running`
  - `completed`
  - `failed`
- timestamps for enqueue, start, and completion

This record should be serializable to one repository-owned JSON document.

### 2. Python Queue Store

Add a queue store under the Python productization package.

Responsibilities:

- enqueue benchmark and evaluation jobs
- list queue state in stable order
- transition queued items to running and terminal states
- preserve parameter choices with the queued job

The store should write queue artifacts under a predictable jobs root and should not depend on in-memory state for correctness.

### 3. Worker Execution Semantics

The first `M7.6` implementation can remain single-consumer and deterministic:

- enqueue the job
- mark it `running` when execution begins
- persist final state when execution completes or fails

The queue is therefore durable even if execution remains effectively serial in the first pass.

### 4. Control-Plane Surface

The control plane should expose:

- enqueue-oriented benchmark and evaluation command handling
- typed queue snapshot payloads
- queue progress visibility through machine-readable replies

It should not move execution ownership away from the Python worker.

### 5. Desktop Surface

The desktop shell should remain thin.

Required behaviors for the first pass:

- show queued benchmark and evaluation entries
- show `queued/running/completed/failed` state
- show `sample_size` and `batch_factor`

No comparison tables or export UI belong in this slice.

## Data Flow

1. Client submits benchmark or evaluation request with explicit parameters.
2. Control plane forwards the request to the Python model-operations worker.
3. Python queue store persists a `queued` record.
4. Worker transitions that record to `running`.
5. Worker writes benchmark or evaluation result artifacts.
6. Worker transitions queue state to terminal status.
7. Control plane and desktop can inspect queue state from durable product-owned records.

## Error Handling

The queue layer should fail explicitly on:

- missing required parameters
- invalid `sample_size` or `batch_factor`
- queue record corruption
- attempts to transition unknown queue items

Errors must remain typed and machine-readable.

## Testing Strategy

### Python

- queue store unit tests
- benchmark enqueue and dequeue tests
- evaluation enqueue and dequeue tests
- parameter persistence tests

### Swift

- control-plane tests for typed queue replies
- desktop view-model tests for queued item visibility

### Integration

- benchmark-queue smoke command
- evaluation-queue smoke command

## Acceptance

This slice is complete when:

- benchmark and evaluation jobs can be queued with explicit `sample_size` and `batch_factor`
- queued state is persisted and replayable
- control plane and desktop can inspect queued job state
- parameter choices remain visible in queued and completed records
