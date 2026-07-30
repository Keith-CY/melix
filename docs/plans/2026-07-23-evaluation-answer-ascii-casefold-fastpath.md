# Evaluation Answer ASCII Casefold Fast Path

## Scope

This Python performance slice is limited to `EvaluationCore._answers_match()` in
`services/mlx-worker-python/worker/engine/evaluation_core.py`.

The exact and stripped-exact answer paths already return before normalization.
This slice adds a narrow ASCII-only case-insensitive fast path after whitespace
trimming and before the generic normalization fallback. It preserves empty
prediction rejection, stripped exact matching, numeric/option/free-text
normalization fallback behavior, and non-ASCII `casefold()` semantics by only
short-circuiting when both compared strings are ASCII and their lowercase forms
match directly.

A rejected prefix-cache experiment was also measured during this cron slice:
replacing the prefix snapshot byte estimator pair-unpack path with a `len(state)
== 2` branch regressed the registered Linux probe (`elapsed_ms_mean` 376.013 ms
baseline -> 392.790 ms candidate), so it was reverted and is not part of this
change.

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
