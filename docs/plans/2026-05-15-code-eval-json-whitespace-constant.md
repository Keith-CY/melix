# Code Eval Payload JSON Whitespace Constant

## Goal

Reuse the module-level JSON payload whitespace byte constant inside the code-evaluation payload field scanner instead of rebuilding the same bytes literal checks for each separator skip loop.

## Scope

This slice is Python-only under `services/mlx-worker-python` and is locally verifiable on Linux with focused tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `docs/plans/2026-05-15-code-eval-json-whitespace-constant.md`

## Registered performance probe

Use the existing `code-eval-payload-json-bytes` registered PR-scoped probe in `infra/perf/pr_scoped_probes.json`. The registry entry already covers `services/mlx-worker-python/worker/engine/code_eval_runner.py` and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

The probe reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `payload_bytes`
- `sample_count`
- `iteration_count`

## Success metrics

- Focused pytest passes for the code-eval payload fast path and registered probe smoke tests.
- Changed-scope coverage for the touched Python path is at least 95%.
- The local registered probe reports lower mean elapsed time or neutral elapsed time with unchanged/lower peak bytes.
- `git diff --check` passes.
