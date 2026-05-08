# Code Evaluation Runner Config Load Optimization Plan

## Goal

Reduce per-evaluation sandbox runner startup overhead by loading the small runner configuration JSON directly from bytes instead of opening a text wrapper and decoding through `json.load(...)`.

## Linux Verification Boundary

This slice touches Python worker code only and is fully verifiable on Linux through focused unit tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_runner_script_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Slice

- Add a `_load_config(...)` helper inside the generated runner script that parses `Path(config_path).read_bytes()` with `json.loads(...)`.
- Keep behavior unchanged for object JSON configs and preserve failure behavior for invalid or non-object config payloads.
- Extend the registered `code-eval-runner-script-cache` probe so it records `config_load_elapsed_ms_mean` for repeated generated-runner config loads.

## Success Metrics

- Focused code-evaluation runner tests pass.
- Changed-scope coverage remains at least 95% for the touched Python scope.
- The registered probe reports a lower `config_load_elapsed_ms_mean` than an `origin/main` baseline on the local Linux worktree.
