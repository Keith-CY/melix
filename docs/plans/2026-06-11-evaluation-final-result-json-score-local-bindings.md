# Evaluation Final Result JSON Score Local Bindings

## Goal

Reduce per-node overhead in `services/mlx-worker-python/worker/productization/evaluation_final_result.py` JSON typed scoring by keeping the recursive scoring semantics unchanged while binding repeated lookups locally inside the recursive walker.

## Scope

Touched files:

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `docs/plans/2026-06-11-evaluation-final-result-json-score-local-bindings.md`

## Registered probe coverage

The affected production file is covered by the registered PR-scoped probe `evaluation-final-result-json-typed-score-aggregate` in `infra/perf/pr_scoped_probes.json`. The probe already has focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `score_checksum` (higher is better / parity guard)

## Planned change

1. Keep `_json_typed_score` output identical for dictionaries, lists, primitive values, ignored paths, and missing actual values.
2. Replace repeated global/function/member lookups in hot recursive branches with local bindings (`actual_get`, `ignored_contains`, and `score_child`).
3. Inline the small child-path join at the call site to avoid the helper call in the per-key loop.
4. Return immediately for equal list payloads, which preserves scoring semantics because every element would otherwise score `1.0` even when ignored paths are present.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_evaluation_json_typed_score_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_evaluation_json_typed_score_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/evaluation_final_result.py services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/evaluation_json_typed_score_probe.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/evaluation_json_typed_score_probe.py`
- `git diff --check`
