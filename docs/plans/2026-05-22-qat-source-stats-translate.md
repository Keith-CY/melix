# QAT source stats byte-translation aggregation

## Scope

This Python-only performance slice is limited to QAT fake-quant source-stat aggregation in `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `quantization-qat-source-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and records both directory-scan metrics and QAT source-stat aggregation metrics:

- `elapsed_ms_mean`
- `scandir_calls_mean`
- `rglob_calls_mean`
- `source_stats_elapsed_ms_mean`
- `source_stats_peak_bytes_mean`

## Optimization

`_qat_fake_quant_source_stats()` previously iterated every source byte in Python to add the fake-quant error proxy and track the max error. This slice keeps the existing public float error table warm for behavior compatibility, then derives a cached 256-byte translation table that maps each source byte to its integer error unit. Each file chunk can then translate bytes and aggregate `sum()` / `max()` through C-backed bytes operations while preserving the same `error / 255.0` metric values.

## Verification plan

Run the focused quantization regression test, the registered probe command, changed-scope coverage, and the PR-scoped performance workflow. Local Linux probe evidence is valid for this Python path; GitHub Actions remains the merge gate for registered probe validation.

## Probe runner stabilization

The same `quantization_pipeline.py` change also selects the registered `model-ops-bundle-artifact-byte-accounting` probe. Its elapsed metric is intentionally tiny, so this slice stabilizes that supporting probe by timing multiple convert/quantize operations per sample and normalizes its registry command to `python3`. This does not change model-op behavior; it reduces false regression noise while preserving the zero bundle-rescan counter gate.
