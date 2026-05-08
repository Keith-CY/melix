# Engine Generate Usage Token Elision Plan

## Goal

Avoid redundant prompt-token accounting work for `EngineCore.generate(...)` requests that do not ask for usage accounting, while preserving existing usage totals when callers do request usage.

## Current Slice

The original prompt-token-count elision is already present on current `origin/main` (`prompt_token_count_calls_per_request=0.0`). This scheduled follow-up keeps that behavior and moves the lazy fallback calculation inline so `return_usage=false` requests do not allocate the unused fallback closure.

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

- `prompt_token_count_calls_per_request` — should remain zero for no-usage requests.
- `elapsed_ms_mean` — lower is better for the same synthetic no-usage workload.

## Success metrics

- Focused generate tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- Local probe reports `prompt_token_count_calls_per_request=0` on the optimized branch.
- Detached `origin/main` vs head PR-scoped probe comparison shows lower `elapsed_ms_mean` with identical structural guard rails.
