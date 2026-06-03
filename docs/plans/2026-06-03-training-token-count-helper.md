# Training Token Count Helper Fast Path

## Goal

Reduce allocation overhead in prompt/completion training dataset token summaries by
reusing the shared `whitespace_token_count(...)` helper instead of materializing
intermediate `split()` token lists for each prompt and completion string.

## Scope

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `docs/plans/2026-06-03-training-token-count-helper.md`

## Registered Probe

The affected path is covered by the registered PR-scoped
`training-dataset-token-percentiles-single-sort` probe in
`infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`,
`coverage_command`, and `probe_command` values for `training_dataset.py`, the
training dataset builder tests, and the PR-scoped performance selector tests.
No registry changes are required for this helper-only slice.

## Verification Plan

- Run the registered focused `test_command` locally on Linux.
- Run the registered changed-scope `coverage_command` locally on Linux and keep
  touched scope at or above 95% coverage.
- Run the registered `probe_command` before and after the implementation on
  Linux and compare `elapsed_ms_mean` and `peak_bytes_mean`.

## Success Metrics

- Preserve whitespace token summary semantics for prompt/completion samples.
- Improve or hold `elapsed_ms_mean` in the local registered training dataset
  token percentile probe.
- Keep `peak_bytes_mean` stable or lower in the registered probe.
