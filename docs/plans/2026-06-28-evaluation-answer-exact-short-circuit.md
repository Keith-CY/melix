# Evaluation answer exact-match short circuit

This Python-only performance slice is limited to
`EvaluationCore._answers_match(...)` in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

## Registered probe

The affected path is covered by the existing PR-scoped probe
`evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` coverage for:

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Slice

Exact non-empty predicted answers are already semantically equal to the expected
answer. This slice returns early before running both normalization passes for
that hot path, while preserving the existing empty-prediction rejection and all
case/whitespace-insensitive fallbacks.

## Verification plan

1. Add a regression test proving exact non-empty matches skip normalization.
2. Run the registered probe's focused tests and changed-scope coverage locally on Linux.
3. Run the registered `evaluation-answer-normalization-fast-path` probe locally against `origin/main` and this branch.
4. Use the PR-scoped performance workflow as the CI merge gate.
