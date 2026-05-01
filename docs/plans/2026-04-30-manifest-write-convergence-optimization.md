# 2026-04-30 Manifest Write Convergence Optimization

## Context

This cron run is restricted to Linux-verifiable changes in `services/mlx-worker-python`.
The slice must stay small, locally testable with Python-only tooling, and include
focused coverage plus an explicit performance probe before commit.

## Scout Result Summary

The single scouting pass proposed these safe candidates:
1. Converge `manifest_bytes` in memory before a single manifest write across
   conversion, quantization, and upload receipt pipelines.
2. Eliminate redundant post-write artifact directory scans in conversion and
   quantization pipelines.
3. Avoid building full registry snapshots when only active derived-model
   manifests are needed.

## Chosen Slice

Optimize manifest serialization in:
- `services/mlx-worker-python/worker/model_ops/conversion_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`

The change will compute the fixed-point `manifest_bytes` value in memory first
and then write the converged manifest payload to disk once, instead of rewriting
`manifest.json` or the upload receipt multiple times until the embedded byte count
stabilizes.

## Why This Slice

- It reduces redundant JSON serialization and file writes without changing the
  manifest schema or payload semantics.
- It is pure Python and locally verifiable on Linux.
- The affected paths already have focused tests in
  `tests/test_quantization_pipeline.py`, `tests/test_maintenance_service.py`, and
  related model-ops coverage.
- The optimization effect can be measured with a synthetic repeated manifest
  write probe using temporary directories.

## Task

1. Add or update focused tests first to lock the converged single-write behavior
   and the persisted `manifest_bytes` value.
2. Refactor the three pipeline helpers so fixed-point byte convergence happens in
   memory and only the final payload is written.
3. Run focused pytest for the touched scope.
4. Measure changed-scope coverage for the touched executable files and require at
   least 95% automated coverage before commit.
5. Run an explicit performance probe comparing the legacy multi-write loop with
   the new single-write flow and record concrete numbers.
6. Run `git diff --check`, then commit, push, and open a PR.

## Success Metrics

- Persisted manifest payloads remain unchanged except for implementation detail
  improvements behind the same schema.
- Focused tests pass for conversion, quantization, and upload receipt flows.
- Changed-scope coverage for touched executable lines is at least 95%.
- The performance probe shows fewer manifest writes and improved wall-clock time.
- `git diff --check` reports no whitespace or merge-marker issues.
