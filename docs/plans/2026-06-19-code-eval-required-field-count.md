# Code Eval Required Field Count Fast Path

## Scope

This Python-only performance slice is limited to the code-evaluation payload JSON
fast path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.
The behavior stays equivalent: the fast path still accepts only payloads with
all required string fields and falls back to full JSON decoding for malformed or
unexpected payloads.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`.
That probe declares focused `test_command`, `coverage_command`, and
`probe_command` entries and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Implementation Plan

1. Keep the existing tokenized JSON field extraction order and fallback rules.
2. Track required string fields while extracting values so the hot path avoids a
   separate post-loop dictionary membership pass.
3. Re-run the registered focused tests, changed-scope coverage command, and
   registered probe locally on Linux.
4. Use GitHub Actions and the PR-scoped performance report as the final merge
   gate.

## Metrics

Primary metric: `elapsed_ms_mean` from `scripts/code_eval_payload_json_probe.py`
(lower is better). Secondary metrics: `peak_bytes_mean`, `iteration_count`, and
`payload_bytes`.
