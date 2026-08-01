# Changed-scope coverage two-line sparse fast path

## Goal

Optimize the changed-scope coverage source-line classifier for the common sparse
case where exactly two changed lines remain measurable after coverage filtering.
The behavior stays equivalent to the existing sparse streaming path while
avoiding the temporary `set(line_numbers)` allocation and membership updates used
by the generic sparse branch.

## Linux-only constraint

This slice changes a Python repository utility and is fully verifiable on Linux
with focused pytest, changed-scope coverage, and the registered PR-scoped
performance probe.

## Registered probe

The affected path is already covered by the registered
`changed-scope-coverage-measured-set-filter` entry in
`infra/perf/pr_scoped_probes.json`. That probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries watching:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

The probe reports the `sparse_elapsed_ms_mean` metric for this two-line sparse
path plus guard metrics for source reads and the existing dense/out-of-range
paths.

## Verification plan

- Run the registered focused pytest command for changed-scope coverage.
- Run the registered changed-scope coverage command and remove generated
  `coverage.json` afterward.
- Run `python3 scripts/changed_scope_coverage_measured_probe.py` locally before
  push and use the PR-scoped performance workflow as the merge gate after push.
- Run `git diff --check` before commit.
