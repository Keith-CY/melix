# Code evaluation payload required-field fast path

## Scope

This Python-only performance slice targets the code-evaluation payload fast parser in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The behavior stays identical: the fast path returns only when the runner payload includes the required status fields, and malformed or unexpected payloads still fall back to the full JSON loader.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches the runner, tests, probe script, and changed-scope coverage helper.

## Implementation plan

1. Keep the existing byte-oriented payload parser and field token order.
2. Replace the required-field generator check with an explicit membership helper to avoid generator allocation and repeated tuple iteration on every successful fast-path parse.
3. Add a focused unit test for the helper so the fast-path gate remains documented and covered.

## Verification

Run the registered focused tests, changed-scope coverage, and `code-eval-payload-json-bytes` probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.
