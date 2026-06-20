# Evaluation Answer ASCII Check Reuse

## Scope

This Python-only performance slice is limited to `EvaluationCore._normalized_answer`
in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

The affected path is already covered by the registered PR-scoped performance probe
`evaluation-answer-normalization-fast-path`, which includes focused tests,
changed-scope coverage, and a command-json probe.

## Plan

1. Preserve existing answer normalization semantics for free-text, option,
   numeric, quoted, and non-ASCII answers.
2. Reuse the ASCII classification already needed for the whitespace fast path so
   ASCII free-text answers avoid a second full-string `isascii()` scan before
   lowercasing.
3. Keep the change local to the normalization helper and its regression test.
4. Verify on Linux with the registered focused tests, changed-scope coverage, and
   registered PR-scoped probe, then use GitHub Actions as the merge gate.

## Validation Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_core.py::test_evaluation_helpers_cover_numeric_option_and_normalization_paths services/mlx-worker-python/tests/test_evaluation_core.py::test_normalized_answer_skips_extractors_for_free_text services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_probes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_evaluation_answer_normalization_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_persists_agentic_tool_evidence services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_writes_agentic_judge_prompt_snapshot_and_audit services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_prompt_snapshot_rejects_hidden_gold_context services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_payload_no_leak_validator_rejects_forbidden_keys services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_payload_no_leak_validator_allows_explicit_answer_values services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_payload_no_leak_validator_rejects_extra_payload_fields services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_returns_agentic_judge_artifacts_without_jobs_root services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_injects_agentic_tool_trace_before_scoring
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_core.py::test_evaluation_helpers_cover_numeric_option_and_normalization_paths services/mlx-worker-python/tests/test_evaluation_core.py::test_normalized_answer_skips_extractors_for_free_text services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_probes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_evaluation_answer_normalization_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_persists_agentic_tool_evidence services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_writes_agentic_judge_prompt_snapshot_and_audit services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_prompt_snapshot_rejects_hidden_gold_context services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_payload_no_leak_validator_rejects_forbidden_keys services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_payload_no_leak_validator_allows_explicit_answer_values services/mlx-worker-python/tests/test_evaluation_core.py::test_agentic_judge_payload_no_leak_validator_rejects_extra_payload_fields services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_returns_agentic_judge_artifacts_without_jobs_root services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_injects_agentic_tool_trace_before_scoring && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_pr_scoped_performance.py infra/perf/pr_scoped_probes.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 - <<'PYPROBE'
# Run via the registered `evaluation-answer-normalization-fast-path` probe command.
PYPROBE
```
