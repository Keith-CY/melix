# Trajectory Manifest JSON Load Local Bindings

## Scope

This Python-only performance slice is limited to the trajectory snapshot manifest
loader in `services/mlx-worker-python/worker/trajectory_provenance.py`.

The affected path is already covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries, so no probe registry change is required for this slice.

## Optimization

`load_trajectory_provenance_from_snapshot_manifest()` already reads manifest
JSON as bytes to avoid text decoding overhead. This slice keeps that behavior,
binds the hot `json.loads` and `Path.read_bytes` call targets at module import,
uses local bindings for the per-call read/parse/extract sequence, and skips
rebuilding `Path` objects when callers already pass a `Path`. Repeated manifest
provenance loads avoid per-call global attribute lookup and an unnecessary
constructor on the registered probe path.

The change does not alter accepted manifest shapes, provenance field names,
copy semantics for nested fields, or non-trajectory manifest handling.

## Verification

Run the registered focused local Linux commands before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_reads_bytes services/mlx-worker-python/tests/test_trajectory_provenance.py::test_trajectory_provenance_helpers_ignore_empty_or_unrelated_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_trajectory_provenance_copy_elision_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_trajectory_manifest_json_load_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.trajectory_provenance -m pytest -q services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_reads_bytes services/mlx-worker-python/tests/test_trajectory_provenance.py::test_trajectory_provenance_helpers_ignore_empty_or_unrelated_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_trajectory_provenance_copy_elision_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_trajectory_manifest_json_load_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/trajectory_provenance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/trajectory_manifest_json_load_probe.py"; if [ -f "$SCRIPT" ]; then python3 "$SCRIPT"; else for CANDIDATE in "../head/$SCRIPT" "${GITHUB_WORKSPACE:-}/head/$SCRIPT"; do if [ -f "$CANDIDATE" ]; then python3 "$CANDIDATE"; exit $?; fi; done; echo "missing probe script fallback for $SCRIPT" >&2; exit 2; fi'
```

CI PR-scoped performance remains the merge gate for the registered probe result.

## Success Criteria

- Focused trajectory provenance tests pass.
- Changed-scope coverage for `worker.trajectory_provenance` stays at or above the repository threshold.
- The registered local probe reports a directionally lower `new_mean_ms` versus the current byte-loading hot path and a positive base-vs-head `speedup`.
- PR-scoped performance CI selects and completes the registered probe before merge.
