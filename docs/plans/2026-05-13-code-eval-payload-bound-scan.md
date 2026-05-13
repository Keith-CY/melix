# Code Eval Payload Boundary Scan

## Goal

Avoid allocating a stripped copy of code-evaluation runner payload bytes before the JSON fast-path field extraction. The fast path only needs to confirm that the payload is an object with optional leading/trailing JSON whitespace, so it can scan the original byte buffer boundaries directly.

## Scope

This slice is Python-only under `services/mlx-worker-python` and can be verified on Linux with focused tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`

## Registered performance probe

Use the existing `code-eval-payload-json-bytes` registered PR-scoped probe in `infra/perf/pr_scoped_probes.json`. The probe covers `services/mlx-worker-python/worker/engine/code_eval_runner.py`, has focused `test_command`, `coverage_command`, and `probe_command` entries, and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `payload_bytes`
- `sample_count`
- `iteration_count`

## Success metrics

- Focused pytest passes for the code-eval payload fast path and probe registry smoke tests.
- Changed-scope coverage for touched Python code is at least 95%.
- Local registered probe reports a lower mean elapsed time or a neutral result with lower/unchanged peak bytes.
- `git diff --check` passes.
