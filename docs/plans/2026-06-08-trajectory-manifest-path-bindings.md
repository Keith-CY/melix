# Trajectory Manifest Path Bindings Performance Slice

## Scope

This Python-only performance slice narrows the trajectory snapshot manifest JSON
loader in `services/mlx-worker-python/worker/trajectory_provenance.py`.

The slice keeps behavior unchanged while avoiding repeated `str(...)` calls for
manifest fields that are already exact strings in the hot manifest extraction
path. Non-string values continue to be coerced through `str(value).strip()`.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`.

Required local commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_reads_bytes \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_accepts_dict_subclass \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_trajectory_provenance_helpers_ignore_empty_or_unrelated_inputs \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_trajectory_provenance_copy_elision_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_trajectory_manifest_json_load_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=worker.trajectory_provenance -m pytest -q \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_reads_bytes \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_load_trajectory_provenance_from_snapshot_manifest_accepts_dict_subclass \
  services/mlx-worker-python/tests/test_trajectory_provenance.py::test_trajectory_provenance_helpers_ignore_empty_or_unrelated_inputs \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_trajectory_provenance_copy_elision_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_trajectory_manifest_json_load_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/trajectory_provenance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT="$PWD" \
  uv run --project services/mlx-worker-python python3 scripts/trajectory_manifest_json_load_probe.py
```

## Decision Rule

Accept only if focused tests and changed-scope coverage pass and the registered
probe shows a stable improvement or a clearly non-regressing result on Linux.
PR-scoped performance CI remains the merge gate for the registered probe.
