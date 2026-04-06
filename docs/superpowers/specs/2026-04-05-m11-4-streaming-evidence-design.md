# M11.4 Streaming Evidence Design

## Summary

`M11.4` should add reproducible operator evidence for the current disk-streaming surface without
inventing SSD-backed performance numbers that the repository runtime does not actually produce.

The repository today exposes disk-streaming configuration, memory-budget admission, and cache
compatibility policy, but both the Swift text worker and the Python worker still reject
`prefer_disk` and `require_disk` loads with typed `disk_streaming_unsupported` failures. That means
Melix can truthfully benchmark:

- the RAM-resident baseline path
- the operator-visible unsupported-path behavior for disk streaming
- the recovery and diagnostic evidence around those flows

Melix cannot truthfully benchmark real SSD-backed restore latency or throughput deltas until a
runtime actually implements disk-backed execution.

## Problem

The roadmap asks `M11.4` to add large-model streaming benchmarks, smoke paths, and runbooks. If
Melix simply emits deterministic or placeholder SSD metrics today, the milestone would appear
complete while the runtime still has no true disk-streaming execution path. That would conflict
with the repository rule that runtime-depth milestones must measure real behavior instead of
contract-only placeholders.

## Approaches

### 1. Emit deterministic SSD metrics

- Fastest path.
- Makes operator output look complete.
- Invalid because Melix would claim SSD-backed evidence it does not have.

Rejected.

### 2. Implement true disk-backed execution before any evidence work

- Semantically strongest outcome.
- Requires a new runtime capability rather than just evidence and runbooks.
- Too large to treat as an unplanned extension of `M11.4` without first decomposing the execution
  into explicit runtime slices.

Rejected for the current transaction.

### 3. Ship truthful evidence for the current surface and leave true SSD metrics explicitly pending

- Measure the RAM-resident baseline with the current benchmark pipeline.
- Exercise `prefer_disk` and `require_disk` as explicit smoke scenarios and record the typed
  unsupported failure, requested-versus-effective disk-streaming modes, and resolved cache policy.
- Document exactly what operators can verify today and what remains blocked on future runtime
  support.

Recommended.

## Recommended Design

### Operator Evidence Command

Add a repository-owned smoke command, `melix-disk-streaming-smoke`, that runs against the local
control plane and emits a machine-readable report. The command should:

1. Capture the current model settings and server snapshot for the selected model.
2. Force a RAM-resident baseline configuration by setting `disk_streaming_mode=disabled`.
3. Run a small benchmark on the same model through the existing `runBench` control-plane path and
   record the measured startup or request metrics Melix already owns truthfully.
4. Switch the model to `prefer_disk` and then `require_disk`, attempt the same load or benchmark
   path, and capture the typed `disk_streaming_unsupported` failure plus the resolved runtime or
   cache-policy state exposed by the control plane.
5. Restore the original model settings before exiting.

### Report Shape

The smoke report should contain these sections:

- `baseline`
  - benchmark task kind
  - measured request metrics Melix already owns today, such as TTFT, latency, and throughput
- `streaming_prefer_disk`
  - requested mode
  - effective mode
  - typed error code
  - transition reason
  - cache compatibility summary
- `streaming_require_disk`
  - same fields as above
- `capability`
  - whether the active runtime advertises disk-streaming support
  - cache-policy summary relevant to streaming compatibility
- `future_metrics`
  - explicit placeholders for `ssd_restore_latency_ms`, `disk_streaming_throughput_delta`, and
    `ssd_footprint_bytes`, marked unavailable until a runtime supports disk-backed execution

The command must never synthesize unavailable metrics as numeric zeroes.

### Integration Coverage

Add an integration test that starts the live local stack, runs the smoke command, and asserts:

- baseline benchmark metrics are present and numeric
- `prefer_disk` and `require_disk` both surface `disk_streaming_unsupported`
- the report includes requested-versus-effective disk-streaming state
- the report includes cache-compatibility detail and runtime support flags
- the emitted JSON is suitable for future release-gate ingestion

### Runbook

Add a runbook dedicated to disk-streaming evidence and diagnostics. It should cover:

- what Melix supports today
- how to run the smoke command
- how to interpret requested-versus-effective disk-streaming state
- how memory budget and cache compatibility interact with the unsupported-path result
- what evidence is still unavailable until true SSD-backed execution exists

## Architecture Notes

- The smoke command should reuse the existing control-plane client rather than shelling out to
  `melix bench run`.
- The command should call the control-plane settings surface directly so the evidence path stays
  repository-owned and type-safe.
- The smoke path should treat “unsupported” as a first-class diagnostic result, not as a test
  failure.
- Any future true disk-backed runtime can extend the report by filling the currently unavailable
  `future_metrics` fields without changing the top-level command shape.

## Testing Strategy

- CLI parser and runner tests for the new smoke command
- focused control-plane tests for settings restore and typed unsupported evidence capture
- live integration coverage through `tests/integration`
- repository-default verification before any completion claim

## Scope Guardrails

- No fake SSD-backed throughput or restore metrics
- No new general-purpose CLI for model policy editing in this transaction
- No attempt to implement true disk-backed execution as an implicit side quest of `M11.4`

