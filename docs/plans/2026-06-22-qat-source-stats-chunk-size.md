# QAT source stats 4 MiB chunk scan

## Scope

This Python-only performance slice is limited to `worker.model_ops.quantization_pipeline._qat_fake_quant_source_stats()`.

The hot path streams QAT source artifact bytes to compute a source digest and fake-quant error proxy.

## Registered probe

The affected path is covered by the registered PR-scoped probe `quantization-qat-source-scan-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantization_qat_source_scan_probe.py`

## Change

`_qat_fake_quant_source_stats()` now reads source artifacts in 4 MiB chunks instead of 1 MiB chunks. QAT source artifacts are typically large tensor/config files, so the larger chunk size reduces Python loop overhead while keeping transient memory bounded for the registered scan.

The digest, byte count, fake-quant mean, and fake-quant max semantics are unchanged because every byte is still streamed through the same hash and translation-table aggregation path.

## Verification plan

1. Run the focused QAT tests selected by the registered probe.
2. Run the registered changed-scope coverage command and require at least 95% measured coverage for the touched scope.
3. Run the registered local performance probe on Linux against `origin/main` and `HEAD` via `scripts/pr_scoped_performance_run.py`.
4. Use GitHub Actions PR-scoped performance as the merge gate after pushing.

## Success criteria

- Focused tests pass.
- Changed-scope coverage passes at or above the repository threshold.
- The registered probe reports improvement or non-regression for `source_stats_elapsed_ms_mean` while preserving `source_stats_byte_count`.
- CI PR-scoped performance report completes successfully before merge.
