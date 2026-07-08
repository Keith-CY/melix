# Code eval payload startswith local bindings

## Scope

This Python-only performance slice is limited to the code-evaluation payload fast
path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The change keeps the existing byte-oriented JSON payload extraction behavior and
only binds `payload_bytes.startswith` once in the hot helper scopes that perform
multiple prefix checks.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries and
watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Validation plan

1. Run the focused payload fast-path regression tests.
2. Run the registered probe coverage command and changed-scope coverage gate.
3. Run the registered probe locally on Linux before and after the change.
4. Use the PR-scoped performance workflow as the CI validation source.

## Success metrics

Accept the slice only if behavior tests pass and the registered probe does not
show a regression. Local Linux probe evidence should show stable or improved
`elapsed_ms_mean` while preserving `peak_bytes_mean`.
