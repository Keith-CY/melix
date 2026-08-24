# Evaluation answer ASCII boundary gate

## Scope

This Python performance slice is limited to `EvaluationCore._normalized_answer(...)` in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

The hot path already fast-paths plain ASCII free-text answers before invoking wrapping, numeric, or option extractors. This slice keeps that behavior but checks the first and last character boundary predicates before the full-string `isascii()` scan, so numeric literals and wrapped/boundary-disqualified answers can skip an avoidable ASCII pass.

## Registered probe

The affected path is covered by the registered PR-scoped probe `evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/evaluation_answer_normalization_probe.py`

Because `evaluation_core.py` is shared by multiple evaluation probes, this slice also extends the neighboring evaluation probe registry commands to include the plain-ASCII normalizer regression test so PR-scoped coverage remains valid when those probes are selected by the shared file watch glob.

## Verification plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally on Linux and compare against the `origin/main` baseline.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

## Success criteria

- Answer normalization behavior is unchanged for options, numeric values, wrapped values, plain ASCII, and Unicode fallback values.
- `normalization_checksum` and `answer_match_checksum` remain unchanged.
- `elapsed_ms_mean` is lower or directionally neutral on the registered probe.

## Local Linux result

Three local registered-probe samples before and after the slice produced:

- `elapsed_ms_mean`: baseline mean `103.724741 ms`, head mean `97.012428 ms`, delta `-6.712313 ms`, speedup `1.069190x`.
- `answer_match_elapsed_ms_mean`: baseline mean `48.200893 ms`, head mean `47.229759 ms`, delta `-0.971134 ms`, speedup `1.020562x`.
- Checksums unchanged: `normalization_checksum=7724000`, `answer_match_checksum=324000`.
