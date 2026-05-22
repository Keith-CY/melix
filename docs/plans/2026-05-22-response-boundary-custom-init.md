# Response-only Boundary Custom Init Fast Path

## Scope

This Python-only performance slice touches only the `ResponseOnlyBoundary` record construction path in `services/mlx-worker-python/worker/model_ops/response_only_boundary.py`.

## Rationale

The registered `response-only-boundary-slotted-records` probe spends a measurable share of time constructing many frozen, slotted `ResponseOnlyBoundary` records before aggregation. The generated frozen dataclass initializer performs repeated generic frozen-assignment setup. A tiny hand-written initializer can keep the same frozen/slotted dataclass semantics while binding `object.__setattr__` once and assigning the two fields directly.

## Implementation

- Keep `ResponseOnlyBoundary` as a frozen, slotted dataclass.
- Disable the generated initializer with `init=False`.
- Add a minimal initializer that assigns `assistant_offset` and `total_tokens` through a module-level bound `object.__setattr__`.
- Do not change aggregate semantics, manifest field names, or truncation behavior.

## Validation

The registered PR-scoped probe `response-only-boundary-slotted-records` covers this path and includes focused tests, changed-scope coverage, and `scripts/response_only_boundary_slots_probe.py` metrics.

Local Linux validation for this slice must run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_summarizes_train_set_without_rereading_disk services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_returns_empty_when_response_only_is_disabled services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_handles_empty_and_full services/mlx-worker-python/tests/test_response_only_boundary.py::test_response_only_boundary_records_are_slotted services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_marks_truncated_labels services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_without_limit_updates_running_bounds services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_response_only_boundary_slots_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_response_only_boundary_slots_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_summarizes_train_set_without_rereading_disk services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_returns_empty_when_response_only_is_disabled services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_handles_empty_and_full services/mlx-worker-python/tests/test_response_only_boundary.py::test_response_only_boundary_records_are_slotted services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_marks_truncated_labels services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_without_limit_updates_running_bounds services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_response_only_boundary_slots_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_response_only_boundary_slots_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/response_only_boundary.py services/mlx-worker-python/tests/test_response_only_boundary.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/response_only_boundary_slots_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/response_only_boundary_slots_probe.py
```
