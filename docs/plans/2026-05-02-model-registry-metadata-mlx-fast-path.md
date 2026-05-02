# Model Registry Metadata MLX Fast-Path Plan

## Goal

Reduce repeated JSON serialization in the plain-local model registry scan by short-circuiting the common `config.json` MLX-signal cases before falling back to the legacy `json.dumps(...).lower()` compatibility path.

## Linux-Only Constraint

This slice is limited to the Python model registry implementation, focused tests, and the registered PR-scoped performance probe so it can be fully verified on Linux.

## Touched Files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Slice

- Add a direct fast path in `_metadata_payload_has_mlx_signal(...)` for the common serializable `library_name == "mlx"` and `tags` sequence cases.
- Preserve the legacy JSON-string fallback for compatibility when the direct checks do not match.
- Add focused regression coverage proving the fast path avoids `json.dumps(...)` for direct MLX metadata while preserving the legacy false result for unserializable payloads.
- Update the registered `model-registry-plain-local-manifest-stat-elision` probe commands so PR-scoped CI measures and covers the new changed scope.

## Performance Probe

Use the existing PR-scoped performance probe `model-registry-plain-local-manifest-stat-elision`, which builds an 800-model synthetic plain-local registry and reports:

- `elapsed_ms_mean`
- `manifest_is_file_calls_mean`

## Success Metrics

- Registry discovery semantics remain unchanged for focused tests.
- Changed executable scope coverage is at least 95%.
- The registered local base-vs-head probe shows lower `elapsed_ms_mean` than `origin/main` while keeping `manifest_is_file_calls_mean` unchanged.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_stops_after_first_matching_metadata_file services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_fast_paths_without_json_roundtrip services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_returns_false_for_unserializable_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_stops_after_first_matching_metadata_file services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_fast_paths_without_json_roundtrip services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_returns_false_for_unserializable_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-registry-plain-local-manifest-stat-elision --base-repo /tmp/melix-baseline-20260502-212321 --head-repo "$PWD" --output /tmp/model-registry-probe-20260502-212321.json`
- `python -m json.tool infra/perf/pr_scoped_probes.json >/dev/null`
- `git diff --check`
