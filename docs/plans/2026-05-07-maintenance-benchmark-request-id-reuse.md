# Maintenance Benchmark Request ID Reuse

## Goal

Reduce redundant request-id hashing in the text benchmark sample path. Warm and partial-prefix cache profiles currently compute the same benchmark request id for the warmup request and again for the measured request.

## Linux-only constraint

This is a Python worker slice and can be verified on Linux with focused pytest, changed-scope coverage, and the PR-scoped performance runner.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-07-maintenance-benchmark-request-id-reuse.md`

## Implementation plan

1. Add a focused regression test proving warm and partial-prefix text benchmark samples compute the base benchmark request id once per sample while preserving the warmup suffixes.
2. Compute the base request id once before cache-profile warmup dispatch in `_measure_text_bench_sample`.
3. Reuse that id for warmup suffixes and the measured `start_request` call.
4. Update the registered maintenance benchmark probe command/test selection to include the regression test and emit a structural `request_id_calls_mean` metric.

## Performance probe

Registered scoped CI probe: `maintenance-bench-report-readback`.

Success metrics:

- `request_id_calls_mean` drops from the legacy two calls per warm sample to one call per warm sample in the synthetic probe.
- `elapsed_ms_mean` should not regress materially.
- Changed executable coverage for the touched Python scope is at least 95%.

## Verification commands

- Focused pytest for the new request-id reuse test and related bench tests.
- `coverage run` + `scripts/changed_scope_coverage.py` for changed-scope coverage.
- `scripts/pr_scoped_performance_run.py --probe-id maintenance-bench-report-readback` for local base-vs-head performance evidence.
- `git diff --check`.
