# Code Evaluation Payload Key Token Cache

## Goal

Avoid rebuilding JSON object key tokens for every code-evaluation payload fast-path field lookup. The payload fast path scans bytes for a fixed set of runner result fields; those key tokens are stable and can be prepared once at import time.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `infra/perf/pr_scoped_probes.json`

## Registered Probe

The affected path is already covered by the PR-scoped `code-eval-payload-json-bytes` command-json probe in `infra/perf/pr_scoped_probes.json`. This slice keeps the same registered probe and extends its focused `test_command` and `coverage_command` with the regression test that proves known payload keys use precomputed tokens.

## Verification Plan

- Run the registered focused pytest command for `code-eval-payload-json-bytes`.
- Run the registered changed-scope coverage command and require at least 95% coverage for touched executable scope.
- Run the registered probe command on Linux before and after the change and compare `elapsed_ms_mean` and `peak_bytes_mean`.

## Success Metrics

- Preserve payload fast-path behavior and fallback behavior for non-canonical or escaped JSON payloads.
- Reduce repeated `json.dumps(...).encode(...)` work for known runner result keys.
- Improve or hold steady the registered probe's local Linux elapsed time and allocation metrics.
