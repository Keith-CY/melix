# Code Eval Payload JSON Integer Accumulator

## Goal

Reduce temporary byte-slice allocation in the code-evaluation payload fast path by accumulating JSON integer fields while scanning the payload bytes.

## Scope

This slice is Python-only under `services/mlx-worker-python` and can be verified on Linux with focused tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`

## Performance probe

Use the existing `code-eval-payload-json-bytes` registered PR-scoped probe in `infra/perf/pr_scoped_probes.json`. The probe exercises repeated `_load_payload_file(...)` calls against a synthetic large runner payload and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `payload_bytes`
- `sample_count`
- `iteration_count`

## Success metrics

- Focused pytest passes for code-eval payload fast-path tests and probe-registry smoke tests.
- Changed-scope coverage for the touched Python code is at least 95%.
- Local registered probe reports lower mean elapsed time or an explainable neutral result.
- `git diff --check` passes.
