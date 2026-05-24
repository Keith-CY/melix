# Embedding Core Request Inputs View Performance Slice

## Scope

This Python-only performance slice is limited to the worker embedding request path. `EmbeddingCore.embed()` previously materialized `list(request.inputs)` before calling the embedding runtime. For large embedding batches this adds an avoidable per-request allocation before the runtime can process or cache repeated inputs.

## Probe Registration

This slice registers `embedding-core-inputs-view` in `infra/perf/pr_scoped_probes.json` with focused `test_command`, `coverage_command`, and `probe_command` entries. The probe exercises `EmbeddingCore.embed()` with a large protobuf repeated input container and records:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `runtime_input_type`

The existing deterministic embedding probe remains registered for runtime duplicate-input cache coverage. The new probe covers the service boundary that hands request inputs into the runtime.

## Implementation

Pass the protobuf repeated input view directly from `EmbedRequest.inputs` into the embedding runtime instead of converting it to a list first. Widen the deterministic embedding runtime type hints to `Sequence[str]` because it only requires length, slicing, and iteration semantics.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. CI remains the merge gate for the registered PR-scoped performance report.

## Expected Result

Behavior stays unchanged for embedding responses while large request batches avoid one list materialization at the service boundary. The registered probe should show lower peak allocation and/or elapsed time for the embedding-core request path.
