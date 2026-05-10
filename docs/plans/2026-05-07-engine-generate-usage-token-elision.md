# Engine Generate Usage Token Elision Plan

## Goal

Avoid redundant prompt-token accounting work for `EngineCore.generate(...)` requests that do not ask for usage accounting, while preserving existing usage totals when callers do request usage.

## Current Slice

The original prompt-token-count elision is already present on current `origin/main` (`prompt_token_count_calls_per_request=0.0`). This scheduled follow-up keeps that behavior and replaces the fallback `len(prompt.split())` usage-token calculation with a single-pass whitespace scanner for runtimes that do not expose `prompt_token_count(...)`. That preserves `str.split(None)` token semantics while avoiding temporary token-list materialization for large rendered prompts.

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
- `fallback_elapsed_ms_mean` — lower is better for return-usage fallback requests on runtimes without a prompt-token helper.
- `fallback_peak_bytes_mean` — lower is better and should drop when fallback token counting no longer materializes a split list.

## Success metrics

- Focused generate tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- Local probe reports `prompt_token_count_calls_per_request=0` on the optimized branch and lower fallback peak bytes than the detached `origin/main` baseline.
- Detached `origin/main` vs head PR-scoped probe comparison shows lower `fallback_peak_bytes_mean` with identical structural guard rails.
