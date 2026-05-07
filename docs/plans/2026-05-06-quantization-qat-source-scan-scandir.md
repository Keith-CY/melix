# Quantization QAT Source Scan Scandir

## Goal

Reduce Python QAT fake-quant source artifact scan overhead by replacing the directory `Path.rglob("*")` materialization with an explicit `os.scandir()` stack while preserving deterministic file ordering and existing invalid-source behavior.

## Scope

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantization_qat_source_scan_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe Registration

Registered probe: `quantization-qat-source-scan-scandir`.

The probe includes:

- `test_command` for focused quantization and PR-scoped registry tests.
- `coverage_command` for changed-scope coverage across the touched Python source, tests, and probe script.
- `probe_command` using `command_json` to measure the QAT source scan against a synthetic nested merged-adapter artifact tree.

## Optimization

`_source_artifact_files_for_qat(...)` keeps the single-file fast path unchanged. For directory inputs it walks entries with `os.scandir()`, appends directory entries to an explicit stack, collects file paths, and sorts the final list before returning so downstream QAT hashing remains deterministic.

Directory symlinks are not followed during stack expansion. Per-entry `OSError` and root scan failures continue to be ignored until the existing empty-source validation raises `invalid_qat_source_artifact`.

## Linux-only Verification Path

This is a Python-only worker optimization and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Registered probe reports `rglob_calls_mean == 0.0` and a successful deterministic file count.
- `elapsed_ms_mean` should not regress beyond the registered 5% warning threshold in PR-scoped CI.
