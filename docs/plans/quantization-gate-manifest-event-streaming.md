# Quantization Gate Manifest Event Streaming

## Goal

Reduce transient memory pressure in `collect_quantization_benchmark_evidence(...)` by avoiding full materialization of every `convert_model(...)` event when the gate only needs the first manifest payload for each quantization profile.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/quantization_gates.py`
- `services/mlx-worker-python/tests/test_release_gates.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/quantization-gate-manifest-event-streaming.md`

## Performance probe definition

Register `quantization-gate-manifest-event-streaming` in `infra/perf/pr_scoped_probes.json`.

The probe monkeypatches `_build_maintenance_core(...)` with a fake core that emits many non-manifest events after the manifest event. It measures `collect_quantization_benchmark_evidence(...)` over a synthetic profile set and reports:

- `elapsed_ms_mean` / `elapsed_ms_min` (lower is better)
- `events_consumed_mean` (lower is better; expected to drop from consuming all post-manifest events to only the started + manifest events per profile)

## Success metrics

- Focused release-gate tests pass.
- Changed executable coverage for touched Python scope is at least 95%.
- Local base-vs-head probe shows fewer consumed events and lower or acceptable elapsed time.
- `git diff --check` passes.
