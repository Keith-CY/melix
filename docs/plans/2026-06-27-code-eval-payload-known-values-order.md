# Code Evaluation Payload Known Status Fast Path

This Python-only performance slice is limited to the byte-level code evaluation payload loader in `worker.engine.code_eval_runner._extract_json_string_field_at()` and its known status value mapping.

## Scope

The common runner payload contains repeated short status strings such as `compiled`, `ok`, `passed`, and an empty `failure_detail`. The current known-value helper checks the full known-value tuple before matching many common hot-path status values.

This slice keeps the existing JSON fast-path behavior and fallback semantics unchanged while dispatching known status tokens by byte length before the exact prefix check. It does not change field extraction, malformed-payload handling, or subprocess execution behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Verification Plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and remove generated `coverage.json` afterwards.
3. Run the registered PR-scoped probe locally against `origin/main` and this branch.
4. Use GitHub Actions PR-scoped performance and normal PR checks as the final merge gate.

## Metrics

Primary local metric: `elapsed_ms_mean` from `scripts/code_eval_payload_json_probe.py` via `scripts/pr_scoped_performance_run.py`.

Secondary metric: `peak_bytes_mean` from the same probe, expected to remain stable because the change only reorders existing token checks.
