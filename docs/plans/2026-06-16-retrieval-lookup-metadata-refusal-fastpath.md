# Retrieval lookup metadata refusal fast path

## Scope

This Python-only performance slice narrows `project_retrieval_lookup_result()` in
`services/mlx-worker-python/worker/runtime/retrieval_context.py` to one invalid
lookup-record path. When wrapper lookup metadata is present and the `records`
field is missing or not an accepted records container, the function already
returns a lookup-level refusal and ignores the intermediate store-record refusal.
This slice returns that final refusal directly instead of first invoking
`project_retrieval_store_records()` and copying its transient empty projection.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `retrieval-context-projection-fastpath` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

No probe registry change is required for this slice.

## Behavior parity

- Preserve valid list and tuple `records` projections.
- Preserve malformed wrapper metadata refusals before inspecting records.
- Preserve the existing lookup-level refusal emitted for missing or malformed
  records when lookup wrapper metadata is present.
- Add a regression test proving the metadata-refusal path does not call the
  store-record projector for invalid records.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_metadata_refusal_skips_store_projection services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_reads_records_once_for_metadata_refusal services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_uses_wrapper_metadata_for_malformed_records services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_preserves_valid_tuple_records_with_metadata services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_retrieval_context_projection_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_covers_lookup_wrapper_metadata services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_metadata_refusal_skips_store_projection services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_reads_records_once_for_metadata_refusal services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_uses_wrapper_metadata_for_malformed_records services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_preserves_valid_tuple_records_with_metadata services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_retrieval_context_projection_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_covers_lookup_wrapper_metadata services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/retrieval_context.py services/mlx-worker-python/tests/test_retrieval_context.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/retrieval_context_projection_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/retrieval_context_projection_probe.py
```

GitHub Actions remains the merge gate for the registered PR-scoped performance
report.
