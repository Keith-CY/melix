# Training Config Target Module Cache Optimization

## Goal

Reduce repeated normalization work in LoRA training target-module resolution by reusing normalized family-profile target presets and default target tuples.

## Linux-only Constraint

This slice only touches Python worker code and repository CI probe metadata. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json performance probe.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_config.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/training_config_target_modules_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance Probe

Register `training-config-target-module-cache` in PR-scoped performance CI. The probe repeatedly resolves static family target presets across dense and MoE profiles and reports:

- `elapsed_ms_mean` — lower is better
- `peak_bytes_mean` — lower is better with a 1 KiB absolute noise floor, because
  the cached target-module path normally allocates below 1 KiB and percentage
  deltas at that size are not meaningful regression signals
- `checksum`, `iteration_count`, and `case_count` structural metrics

## Success Metrics

- Preserve exact resolved target-module lists and mutation isolation for returned default lists.
- Achieve at least 95% changed-scope automated coverage for touched Python files.
- Show a concrete local base-vs-head improvement for the registered probe before PR creation.

## Verification Commands

- Focused pytest for target-module behavior and PR-scoped probe registration.
- Changed-scope coverage via `scripts/changed_scope_coverage.py`.
- Local branch probe: `python scripts/training_config_target_modules_probe.py` through `uv run`.
- Base-vs-head registered probe through `scripts/pr_scoped_performance_run.py`.
- `git diff --check`.
