# Evaluation Empty Prediction Fast Path

This Python-only performance slice is limited to `EvaluationCore._answers_match()` in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/evaluation_answer_normalization_probe.py`

## Slice

Add an explicit empty-prediction branch before the whitespace-only `strip()` check in `_answers_match()`. Exact non-empty matches already bypass normalization; this slice gives true empty predictions the same low-overhead early return while preserving the whitespace-only rejection path.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for final registered probe validation.

Expected metric direction: lower `answer_match_elapsed_ms_mean` for the registered answer-normalization probe, with no change to answer-match semantics.
