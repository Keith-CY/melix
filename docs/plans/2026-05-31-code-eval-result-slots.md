# Code Evaluation Result Slots

Date: 2026-05-31

## Scope

This Python-only performance slice is limited to `CodeEvaluationResult` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py` and the already
registered code-evaluation runner-script PR-scoped probe.

## Problem

`run_python_code_evaluation()` returns a `CodeEvaluationResult` object on every
success and failure path. The result type is immutable but previously used the
regular dataclass instance dictionary, leaving avoidable per-result allocation
and attribute-storage overhead in repeated code-evaluation workloads.

## Plan

- Convert `CodeEvaluationResult` to a frozen slotted dataclass.
- Add a focused regression test proving the result remains immutable-style field
  access without an instance `__dict__`.
- Extend the existing `code-eval-runner-script-cache` probe to report result
  allocation elapsed time, peak bytes, and instance-dict count.
- Keep the change Python-only; no protocol, dependency, or generated-output
  changes are involved.

## Registered Probe

Registered PR-scoped probe: `code-eval-runner-script-cache` in
`infra/perf/pr_scoped_probes.json`.

Focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_evaluation_result_uses_slots_without_instance_dict services/mlx-worker-python/tests/test_code_eval_runner.py::test_runner_script_reuses_dedented_static_payload services/mlx-worker-python/tests/test_code_eval_runner.py::test_runner_script_loads_config_from_bytes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_runner_script_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_evaluation_result_uses_slots_without_instance_dict services/mlx-worker-python/tests/test_code_eval_runner.py::test_runner_script_reuses_dedented_static_payload services/mlx-worker-python/tests/test_code_eval_runner.py::test_runner_script_loads_config_from_bytes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_runner_script_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_runner_script_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_runner_script_probe.py
```

## Acceptance Criteria

- Focused behavior and registry tests pass locally on Linux.
- Changed-scope coverage is at least 95% for the touched scope.
- The registered local probe reports `result_instance_dict_count_mean=0.0` and
  improved result allocation peak bytes versus `origin/main`.
- GitHub Actions PR-scoped performance completes successfully before merge.
