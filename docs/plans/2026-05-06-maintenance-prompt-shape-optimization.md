# Maintenance Benchmark Prompt Shape Optimization

## Goal

Reduce Python loop overhead in `MaintenanceCore._shape_benchmark_prompt()` when benchmark suites synthesize large prompt contexts by repeating a short prompt to a requested token length.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a local prompt-shaping performance probe. It does not change Swift or macOS-only surfaces.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-06-maintenance-prompt-shape-optimization.md`

## Proposed change

Replace the repeated `list.extend(...)` loop used for prompt repetition with a `divmod(...)`-based list multiplication path:

1. Keep empty-prompt fallback as `benchmark`.
2. Keep truncation behavior when the prompt already contains at least `context_length` tokens.
3. For shorter prompts, compute full repeats and remainder once, build the repeated token list directly, and join once.

## Performance probe

Register `maintenance-prompt-shape-vector-repeat` in the PR-scoped performance registry. The probe runs `_shape_benchmark_prompt()` over synthetic contexts of 2,048, 8,192, and 32,768 tokens and reports:

- `elapsed_ms_mean` — lower is better
- `token_count_mean` — structural guard that the shaped prompt still reaches the requested token counts
- `iteration_count` / `sample_count` — workload description

## Success metrics

- Focused pytest passes for prompt-shaping behavior and PR-scoped probe selection.
- Changed executable coverage is at least 95% for the touched Python code/tests.
- Local base-vs-head probe shows lower mean elapsed time while preserving token counts.
- `git diff --check` passes.
