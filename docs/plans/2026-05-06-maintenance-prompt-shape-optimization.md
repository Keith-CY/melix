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

Build the repeated prompt as repeated text instead of materializing the entire repeated token vector:

1. Keep empty-prompt fallback as `benchmark`.
2. Keep truncation behavior when the prompt already contains at least `context_length` tokens.
3. For shorter prompts, compute full repeats and remainder once, join the base token phrase once, repeat the phrase string, and append only the remainder phrase when needed.
4. Keep the registered probe command on `python3` so local and CI evidence follows the repository operator constraint.

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
