# Evaluation Answer Exact Nonempty Fast Path Slice

## Scope

This Python-only performance slice is limited to `worker.engine.evaluation_core.EvaluationCore._answers_match`. It preserves empty-prediction rejection and normalized fallback matching while moving the non-empty exact-match short circuit before the whitespace-only check.

## Registered probe

The affected path is covered by the registered PR-scoped probe `evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/evaluation_answer_normalization_probe.py`

## Plan

1. Keep the registered `evaluation-answer-normalization-fast-path` probe unchanged.
2. Check `expected == predicted and predicted` before calling `predicted.strip()` so the common non-empty exact-match path avoids an unnecessary allocation/scan.
3. Preserve the existing empty-string and whitespace-only false result by requiring `predicted` to be truthy in the exact-match branch and retaining the strip guard afterward.
4. Follow-up slice: reuse the stripped prediction for a second exact-match fast path (`expected == predicted.strip()`) before invoking normalized fallback matching. This covers prediction payloads that only add surrounding whitespace while keeping case-folded, numeric, option, and wrapped-answer behavior on the existing normalized path.
5. Verify with the registered focused test command, changed-scope coverage command, and local registered Linux probe before PR creation. Use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by `answer_match_elapsed_ms_mean` from `scripts/evaluation_answer_normalization_probe.py` with unchanged match checksum and exact-pair count. The follow-up stripped-exact slice should reduce normalization calls for whitespace-wrapped exact predictions without changing `answer_match_checksum`. Changed-scope coverage must stay at or above 95%.
