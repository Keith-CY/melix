# Response-only Boundary No-limit Aggregate Min/Max Fast Path

## Scope

This performance slice only touches `worker.model_ops.response_only_boundary.aggregate_response_only_boundaries()` for the no-truncation path (`max_seq_length is None` or non-positive).

## Rationale

When there is no truncation limit, trainable response-token bounds and totals are exactly the response-token bounds and totals. The previous loop maintained separate `trainable_response_tokens_*` running values even though they could not diverge from `response_tokens_*` in this branch.

## Implementation

- Keep the existing truncation-limit branch unchanged.
- In the no-limit branch, seed running bounds from the first entry so the hot loop no longer checks `sample_count == 0` on every sample.
- Compute only response-token bounds/totals in the hot loop.
- After the loop, mirror those values into the trainable response-token aggregate fields.

## Validation

The registered PR-scoped probe `response-only-boundary-slotted-records` covers this path and includes focused tests, changed-scope coverage, and `scripts/response_only_boundary_slots_probe.py` metrics.

Local Linux validation for this slice must run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_summarizes_train_set_without_rereading_disk services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_returns_empty_when_response_only_is_disabled services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_handles_empty_and_full services/mlx-worker-python/tests/test_response_only_boundary.py::test_response_only_boundary_records_are_slotted services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_marks_truncated_labels services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_without_limit_updates_running_bounds services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_response_only_boundary_slots_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_response_only_boundary_slots_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_summarizes_train_set_without_rereading_disk services/mlx-worker-python/tests/test_response_only_boundary.py::test_probe_returns_empty_when_response_only_is_disabled services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_handles_empty_and_full services/mlx-worker-python/tests/test_response_only_boundary.py::test_response_only_boundary_records_are_slotted services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_marks_truncated_labels services/mlx-worker-python/tests/test_response_only_boundary.py::test_aggregate_response_only_boundaries_without_limit_updates_running_bounds services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_response_only_boundary_slots_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_response_only_boundary_slots_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/response_only_boundary.py services/mlx-worker-python/tests/test_response_only_boundary.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/response_only_boundary_slots_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/response_only_boundary_slots_probe.py
```
