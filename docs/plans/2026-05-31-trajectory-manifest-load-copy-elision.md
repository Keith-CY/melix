# Trajectory manifest load nested-copy elision

## Scope

This Python-only performance slice is limited to trajectory snapshot manifest
loading in `services/mlx-worker-python/worker/trajectory_provenance.py`.

The affected path is already covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the touched trajectory provenance path. This slice
keeps the optimized `new_*` metrics gated and marks the reference-only `old_*`
probe metrics informational so base-loader noise does not mask the optimized
loader result.

## Optimization

`load_trajectory_provenance_from_snapshot_manifest()` reads a fresh JSON payload
from disk and immediately extracts provenance fields. The public
`trajectory_provenance_from_snapshot_manifest()` API must still defensively copy
nested JSON containers because callers may retain and mutate the source mapping.
For the file-loader path, the parsed JSON object is private to the call, so this
slice routes through an internal helper that reuses nested containers from that
fresh payload instead of recursively copying them once more.

The optimization preserves the public API's defensive-copy semantics and only
elides redundant nested copies for the private manifest-load path.

## Validation Plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_reads_bytes services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_snapshot_manifest_reuses_fresh_json_nested_fields services/mlx-worker-python/tests/test_trajectory_provenance.py::test_snapshot_manifest_copies_nested_fields_once_via_normalization services/mlx-worker-python/tests/test_trajectory_provenance.py::test_trajectory_provenance_helpers_ignore_empty_or_unrelated_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_trajectory_provenance_copy_elision_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_trajectory_manifest_json_load_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.trajectory_provenance -m pytest -q services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_reads_bytes services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_snapshot_manifest_reuses_fresh_json_nested_fields services/mlx-worker-python/tests/test_trajectory_provenance.py::test_snapshot_manifest_copies_nested_fields_once_via_normalization services/mlx-worker-python/tests/test_trajectory_provenance.py::test_trajectory_provenance_helpers_ignore_empty_or_unrelated_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_trajectory_provenance_copy_elision_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_trajectory_manifest_json_load_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/trajectory_provenance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/trajectory_manifest_json_load_probe.py
```

## Success Criteria

- Focused trajectory provenance and registered-probe tests pass locally on Linux.
- Changed-scope coverage for `worker.trajectory_provenance` remains at or above
  95%.
- The registered local probe reports a lower `new_mean_ms` than the pre-change
  local baseline for this branch.
- PR-scoped performance CI selects and completes the registered
  `trajectory-manifest-json-load` probe before merge.
