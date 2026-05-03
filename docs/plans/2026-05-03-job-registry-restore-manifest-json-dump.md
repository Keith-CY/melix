# Job registry restore manifest JSON dump fast path

## Scope

This Python-only performance slice targets the model-ops job registry restore path in
`services/mlx-worker-python/worker/model_ops/job_registry.py`.

When restoring thousands of persisted model-ops manifests, `_restore_manifest_jobs()`
keeps the decoded manifest dict cached on `ModelOpsJob`. The companion
`manifest_json` field only needs to preserve a JSON representation of the same
payload for compatibility; it does not need deterministic key ordering during
restore. Sorting every restored manifest's keys adds avoidable CPU work in the
registered restore probe.

## Registered probe

The affected path is covered by registered PR-scoped probe
`job-registry-restore-sort-elision` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and reports:

- `restore_elapsed_ms_mean`
- `per_manifest_ms_mean`
- `job_count`

## Implementation plan

1. Add a regression assertion that restored jobs still cache the decoded manifest
   and keep a JSON `manifest_json` payload equivalent to the manifest dict.
2. Remove deterministic key sorting from the restore-only `json.dumps()` call.
3. Keep all snapshot and active-derived-model behavior unchanged; the cached
   manifest dict remains the authoritative restore payload.
4. Run the registered focused tests, changed-scope coverage, and registered probe
   locally on Linux.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/job_registry_restore_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_restore_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
