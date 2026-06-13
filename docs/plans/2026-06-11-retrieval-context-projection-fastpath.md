# Retrieval context projection and store-record local binding fast paths

## Scope

This Python-only performance slice is limited to retrieval context projection and
store-record projection in `services/mlx-worker-python/worker/runtime/retrieval_context.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization plan

`project_retrieval_contexts()` projects already-admitted retrieval entries into a
single user payload. The common path has unique `source_field` values, but the
previous duplicate detection allocated a list for every admission and copied the
admission payload through `dict(...)` before updating the aggregate payload.

This slice keeps the duplicate-refusal semantics unchanged while reducing common
unique-field overhead:

1. Iterate admission payload keys directly and only allocate `duplicate_fields`
   after the first collision.
2. Reuse the admission payload mapping for `dict.update(...)` instead of making an
   intermediate shallow dict copy.
3. Preserve defensive receipt copying and duplicate receipt fallback behavior.

The 2026-06-13 follow-up keeps the same registered probe and narrows the next
change to `project_retrieval_store_records()`: bind `RetrievalContextEntry` and
each record's `.get` method once per valid record, then reuse those local
bindings while building the entry descriptor. This preserves all validation and
refusal behavior while trimming repeated attribute lookup overhead in the
registered store-record projection workload.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_admits_multiple_entries_with_redacted_receipts services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_refuses_duplicate_payload_fields_before_overwrite services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_refuses_duplicate_with_defensive_receipt_fallbacks services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_retrieval_context_projection_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_admits_multiple_entries_with_redacted_receipts services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_refuses_duplicate_payload_fields_before_overwrite services/mlx-worker-python/tests/test_retrieval_context.py::test_project_retrieval_contexts_refuses_duplicate_with_defensive_receipt_fallbacks services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_retrieval_context_projection_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/retrieval_context.py services/mlx-worker-python/tests/test_retrieval_context.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/retrieval_context_projection_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/retrieval_context_projection_probe.py"; if [ -f "$SCRIPT" ]; then python3 "$SCRIPT"; else for CANDIDATE in "../head/$SCRIPT" "${GITHUB_WORKSPACE:-}/head/$SCRIPT"; do if [ -f "$CANDIDATE" ]; then MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT="$PWD" python3 "$CANDIDATE"; exit $?; fi; done; echo "missing probe script fallback for $SCRIPT" >&2; exit 2; fi'
```

## Success criteria

- Focused retrieval context projection tests pass.
- Changed-scope coverage for the touched files stays at or above the repository
  threshold.
- The registered probe reports lower `optimized_elapsed_ms_mean` than
  `baseline_elapsed_ms_mean`, positive `speedup`, and negative `delta_ms` on the
  synthetic projection workload. For the store-record follow-up, the same probe
  must also keep `store_optimized_elapsed_ms_mean` below
  `store_baseline_elapsed_ms_mean` with negative `store_delta_ms`.
