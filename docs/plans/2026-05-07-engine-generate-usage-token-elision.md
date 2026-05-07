# Engine Generate Usage Token Elision Plan

## Goal

Avoid redundant prompt token counting for `EngineCore.generate(...)` requests that do not ask for usage accounting, while preserving existing usage totals when callers do request usage.

## Linux-only constraint

This slice touches Python worker code only and is verifiable on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/engine_generate_usage_token_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Registered probe: `engine-generate-usage-token-elision`.

The probe runs many `return_usage=false` generate requests through a counting runtime and reports:

- `prompt_token_count_calls_per_request` — should drop from one fallback count per request on `origin/main` to zero on the branch.
- `elapsed_ms_mean` — informational wall-clock timing for the same synthetic workload.

## Success metrics

- Focused generate tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- Local probe reports `prompt_token_count_calls_per_request=0` on the optimized branch.
- Detached `origin/main` vs head PR-scoped probe comparison shows the structural prompt-count call metric improves from `1.0` to `0.0` calls/request.
