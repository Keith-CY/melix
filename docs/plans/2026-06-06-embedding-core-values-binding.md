# Embedding Core Values Binding Slice

## Scope

This Python-only performance slice is limited to `worker.engine.embedding_core.EmbeddingCore.embed` response assembly. The runtime already receives the protobuf `request.inputs` repeated-field view without list materialization; this slice reduces repeated protobuf repeated-field lookup while copying generated vectors into the response.

## Registered probe

The affected path is covered by the registered PR-scoped probe `embedding-core-inputs-view` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/engine/embedding_core.py`
- `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/embedding_core_inputs_probe.py`

## Plan

1. Keep the registered `embedding-core-inputs-view` probe unchanged.
2. Bind each protobuf embedding's repeated `values` field once before extending it with the runtime vector.
3. Verify with the registered focused test command, changed-scope coverage command, and local registered Linux probe.
4. Use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by `elapsed_ms_mean` from `scripts/embedding_core_inputs_probe.py` with unchanged checksum, input count, dimensions, and runtime input view metrics. Changed-scope coverage must stay at or above 95%.
