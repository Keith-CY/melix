# Local Job Follow-Up Claim Input Fast Path

## Goal

Reduce per-candidate overhead in the local-job follow-up batch claim path while preserving the existing store scan, reconciliation, prompt-admission, and receipt semantics.

## Scope

This Python-only performance slice is limited to `LocalJobContinuationStore.claim_scanned_followup_prompt_contexts(...)` and the registered local-job follow-up scan probe. It keeps the existing `os.scandir()` store scan, guarded record writes, prompt-context admission, projection copying, and receipt shapes unchanged.

The affected path is covered by the registered PR-scoped probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. This slice extends that registered probe with batch projection metrics so CI and local runs measure the newly added multi-candidate follow-up path, not only the file scan.

## Optimization

The prior claim loop rebuilt a three-entry tuple and a list comprehension for every scanned candidate just to discover missing claim-input maps. This slice replaces that per-candidate tuple/list-comprehension setup with direct membership checks against the normalized mappings, appending missing field names only when a field is absent.

This keeps exception mapping behavior unchanged: mapping membership errors still become `followup_claim_input_invalid`, and missing fields still emit `followup_claim_input_missing` with the same ordered field names.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_local_job_continuation.py::test_project_local_job_session_followup_returns_user_message_projection services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_local_job_followup_scan_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_local_job_continuation.py::test_project_local_job_session_followup_returns_user_message_projection services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_local_job_followup_scan_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/local_job_continuation.py services/mlx-worker-python/tests/test_local_job_continuation.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/local_job_followup_scan_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_LOCAL_JOB_SCAN_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/local_job_followup_scan_probe.py
```

## Success Criteria

- Focused local-job follow-up tests and registry validation tests pass.
- Changed-scope coverage remains at or above 95 percent for the touched scope.
- The registered probe emits `projection_elapsed_ms_mean` and related projection count metrics.
- `projection_elapsed_ms_mean` improves against the base implementation in the local probe and registered CI report without changing candidate, receipt, or follow-up message counts.
