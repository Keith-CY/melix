# Code eval assert prescan single find

## Scope

This Python-only performance slice is limited to the code-evaluation test-count
prescan in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.
It does not change sandbox execution, candidate extraction, payload parsing,
stdio handling, or generated protocol artifacts.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`. The
registry entry has focused `test_command`, `coverage_command`, and
`probe_command` entries covering:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

## Optimization

`_may_contain_assert_statement()` previously performed a full containment scan
for `"assert"` and then started a second `find()` scan from the beginning.
For no-assert code-evaluation payloads, this doubled the prescan work before the
nonblank-line fallback could run.

This slice makes the first `find()` call serve as both the absence check and the
initial cursor. Subsequent candidate tokens still use `find()` from the previous
token boundary, preserving the existing boundary and literal/comment behavior.

## Verification plan

1. Add a regression sentinel proving the absent-token path does not use a
   separate containment scan.
2. Run the registered focused pytest command for `code-eval-count-tests-line-scan`.
3. Run changed-scope coverage from the same registered entry.
4. Run the registered local probe on Linux and compare against the pre-change
   baseline from `origin/main`.
5. Use the PR-scoped performance workflow and registered probe report as the
   merge gate.
