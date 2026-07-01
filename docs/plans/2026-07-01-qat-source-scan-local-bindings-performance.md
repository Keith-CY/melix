# QAT Source Scan Local Bindings Performance Slice

## Scope

Optimize the Python QAT source artifact directory scan in
`services/mlx-worker-python/worker/model_ops/quantization_pipeline.py` by keeping
attribute/function lookups out of the inner scandir traversal loop.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`quantization-qat-source-scan-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the QAT source scan path.

## Behavior Contract

The slice preserves the current traversal semantics:

- a file source path is returned directly;
- directory sources are traversed with `os.scandir` and an explicit stack;
- bad entries and unreadable directories are skipped;
- an empty scan still raises `invalid_qat_source_artifact`;
- returned paths remain sorted before conversion to `Path` objects.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux. The probe compares elapsed scan time, `rglob` call count,
peak bytes, and QAT source stats scan metrics. CI PR-scoped performance remains
the merge gate.
