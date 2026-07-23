# Evaluation Answer Normalizer Local Bind

## Scope

This Python performance slice is limited to `EvaluationCore._answers_match()` in
`services/mlx-worker-python/worker/engine/evaluation_core.py`.

The non-exact answer path calls the same normalization helper twice after the
exact and stripped-exact fast paths have already failed. This slice stores that
helper in a function-local binding before the two calls, reducing repeated class
attribute lookup overhead while preserving the same inputs to normalization.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`evaluation-answer-normalization-fast-path` in
`infra/perf/pr_scoped_probes.json`. The registry entry watches the evaluation
core implementation, focused evaluation tests, PR-scoped performance tests, and
`scripts/evaluation_answer_normalization_probe.py`; it includes focused
`test_command`, `coverage_command`, and `probe_command` entries.

Primary metric:

- `answer_match_elapsed_ms_mean` should decrease on the registered answer-match
  workload.

Secondary metrics:

- `elapsed_ms_mean`, `numeric_extract_calls_mean`, and
  `option_extract_calls_mean` should remain stable because this slice does not
  change `_normalized_answer()` behavior.

## Verification Plan

Run the focused evaluation regression tests, changed-scope coverage, and the
registered probe locally on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe result in
CI.

Linux local validation covers the Python evaluation path only. No Swift runtime
performance effect is claimed for this slice.
