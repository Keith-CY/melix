# Maintenance Capability Empty Fast Path

## Scope

This Python-only performance slice is limited to `_split_capability_values()` in
`services/mlx-worker-python/worker/engine/maintenance_core.py` and the registered
maintenance capability split probe.

The runtime frequently calls capability parsing for model metadata fields that
are absent or already a single value. Those inputs do not need comma splitting or
list-comprehension iteration. The slice keeps comma-delimited capability
semantics unchanged while returning directly for empty, whitespace-only, and
single-value capability strings.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`maintenance-capability-split-single-strip` in `infra/perf/pr_scoped_probes.json`.
The registry entry has focused `test_command`, `coverage_command`, and
`probe_command` values. This slice extends the existing probe script output with
empty/singleton input timings while keeping the registered comparison metrics
stable for CI gating.

## Implementation plan

1. Add regression coverage for empty, whitespace-only, singleton, and existing
   comma-delimited capability strings.
2. Fast-path empty strings and strings without commas in `_split_capability_values()`.
3. Extend `scripts/maintenance_capability_split_probe.py` to report
   empty/singleton timing deltas alongside the existing registered metrics.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux; use PR-scoped performance CI as the merge gate.

## Validation

Local Linux validation for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_split_capability_values_strips_once_and_drops_empty_segments services/mlx-worker-python/tests/test_maintenance_service.py::test_get_model_info_appends_tool_parser_when_capability_parser_metadata_is_absent services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_capability_split_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_capability_split_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_split_capability_values_strips_once_and_drops_empty_segments services/mlx-worker-python/tests/test_maintenance_service.py::test_get_model_info_appends_tool_parser_when_capability_parser_metadata_is_absent services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_capability_split_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_capability_split_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/maintenance_capability_split_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id maintenance-capability-split-single-strip --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/maintenance_capability_empty_fastpath_probe.json
```
