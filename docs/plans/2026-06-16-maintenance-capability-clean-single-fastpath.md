# Maintenance capability clean single-value fast path

## Scope

This Python-only performance slice narrows `_split_capability_values()` in
`services/mlx-worker-python/worker/engine/maintenance_core.py` to the common
single capability metadata value that is already clean (for example `qwen`).
The previous single-value path always called `str.strip()` before returning a
one-item list. This slice returns the original string directly when there is no
comma and neither boundary character is whitespace, preserving the existing
strip-and-drop behavior for padded or blank values.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `maintenance-capability-split-single-strip` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_capability_split_probe.py`

This slice extends that probe with clean single-value metrics so CI reports the
optimized path directly.

## Behavior parity

- Preserve comma-separated capability splitting.
- Preserve trimming for padded single values such as ` qwen `.
- Preserve blank single-value elision.
- Add a focused assertion for already-clean single capability values.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_split_capability_values_strips_once_and_drops_empty_segments services/mlx-worker-python/tests/test_maintenance_service.py::test_get_model_info_appends_tool_parser_when_capability_parser_metadata_is_absent services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_capability_split_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_capability_split_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_split_capability_values_strips_once_and_drops_empty_segments services/mlx-worker-python/tests/test_maintenance_service.py::test_get_model_info_appends_tool_parser_when_capability_parser_metadata_is_absent services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_capability_split_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_capability_split_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/maintenance_capability_split_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/maintenance_capability_split_probe.py
```

GitHub Actions remains the merge gate for the registered PR-scoped performance
report.
