# Evaluation Answer Strip-Match Fast Path

## Scope

This Python performance slice is limited to `EvaluationCore._answers_match()` in
`services/mlx-worker-python/worker/engine/evaluation_core.py`.

The common exact-answer path already returns before normalization. This slice
extends the same behavior to predictions that differ only by leading/trailing
whitespace, avoiding two answer-normalization calls while preserving existing
case-folding, numeric, option, punctuation, and empty-prediction behavior for
non-exact matches.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`evaluation-answer-normalization-fast-path` in
`infra/perf/pr_scoped_probes.json`. The registry entry watches the evaluation
core implementation, focused evaluation tests, the PR-scoped performance tests,
and `scripts/evaluation_answer_normalization_probe.py`; it includes focused
`test_command`, `coverage_command`, and `probe_command` entries.

Primary metrics:

- `answer_match_elapsed_ms_mean` should decrease on the registered workload.
- `elapsed_ms_mean`, `numeric_extract_calls_mean`, and
  `option_extract_calls_mean` should remain stable because the slice does not
  change `_normalized_answer()` itself.

## Verification Plan

Run the focused evaluation regression tests, changed-scope coverage, and the
registered probe locally on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe result in
CI.

Linux local validation covers the Python evaluation path only. No Swift runtime
performance effect is claimed for this slice.
