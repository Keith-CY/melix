# Retrieval Context Admission Direct Dispatch Slice

This Python performance slice is limited to `worker.runtime.retrieval_context._admit_entry`.

## Scope

`project_retrieval_contexts` and `project_retrieval_store_records` call `_admit_entry` for every retrieval context item before prompt projection. The prior implementation dispatched valid document/image entries through the public wrapper helpers before returning to `_admit_context`. This slice preserves the wrapper APIs but lets `_admit_entry` call `_admit_context` directly for the two valid hot-path kinds.

Out of scope:

- changing public retrieval admission semantics
- changing refusal receipt schemas
- changing retrieval lookup payload copy behavior
- changing probe registry definitions

## Registered Probe

The affected path is already covered by the registered PR-scoped performance probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The registry includes focused commands for:

- `test_command`
- `coverage_command`
- `probe_command`

## Verification Plan

Run the registered focused commands locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_admits_multiple_entries_with_redacted_receipts services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_store_records_accepts_valid_records services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_builds_prompt_message_with_copied_payloads services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_retrieval_context_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_admits_multiple_entries_with_redacted_receipts services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_store_records_accepts_valid_records services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_lookup_result_builds_prompt_message_with_copied_payloads services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_retrieval_context_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/retrieval_context.py services/mlx-worker-python/tests/test_retrieval_context.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/retrieval_context_projection_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/retrieval_context_projection_probe.py"; if [ -f "$SCRIPT" ]; then python3 "$SCRIPT"; else python3 - <<"PYPROBE"
raise SystemExit("probe script missing")
PYPROBE
fi'
```

CI remains the merge gate for the registered PR-scoped performance report.
