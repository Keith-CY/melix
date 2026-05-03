# Model Registry Plain-Local Generation Config Stat Elision

## Scope

This slice optimizes the Python model registry plain-local directory discovery path in `services/mlx-worker-python/worker/model_registry/catalog.py`.

The root tree scan already performs a single `os.scandir()` pass through each candidate model directory. This change records whether `generation_config.json` was present during that pass and reuses that fact when constructing plain-local `ModelSpec` entries.

## Performance Probe

Registered PR-scoped probe: `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`.

The registered probe covers:

- `test_command` for focused model-registry and PR-scoped performance tests.
- `coverage_command` for changed-scope coverage across the registry, probe support, and tests.
- `probe_command` for a synthetic 800-model registry snapshot workload.

This is a Python-only slice and is locally verifiable on Linux. CI remains the merge gate for the registered PR-scoped performance report.

## Implementation Plan

1. Extend the plain-local tree scan metadata to include generation-config sidecar presence.
2. Skip the later `generation_config.json` stat/read path when the single tree scan already proved the sidecar is absent.
3. Preserve generation-config import behavior when the sidecar is present.
4. Add focused regression tests for both the stat-elision and present-sidecar paths.

## Validation Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-registry-plain-local-manifest-stat-elision --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/model_registry_generation_config_stat_elision_probe.json
```

## Success Criteria

- Plain-local models without `generation_config.json` avoid the redundant sidecar stat after the root tree scan.
- Plain-local models with `generation_config.json` still import generation metadata.
- Focused tests, changed-scope coverage, and the registered PR-scoped probe pass.
