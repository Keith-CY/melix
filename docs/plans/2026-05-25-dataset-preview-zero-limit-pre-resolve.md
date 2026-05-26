# Dataset Preview Zero-Limit Pre-Resolve Fast Path

## Slice

This Python-only performance slice is limited to `read_hf_dataset_snapshot_rows()` in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`.

The registered PR-scoped performance probe is
`dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`.
That probe already covers the affected path with focused `test_command`,
`coverage_command`, and `probe_command` entries, including zero-limit latency and
peak-memory metrics.

## Optimization

Return `[]` for `limit <= 0` before resolving the snapshot path, normalizing split
state, or allocating the row accumulator. This preserves the existing zero-limit
contract while avoiding all path setup work in the no-row preview path.

## Verification Plan

Run locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_respects_limit \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_json_row_reader_limit_uses_incremental_decode \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_zero_limit_returns_empty \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_snapshot_row_reader_zero_limit_skips_file_scan \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_limit_one_preview_avoids_full_supported_file_iterator \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_preview_limit_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_respects_limit \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_json_row_reader_limit_uses_incremental_decode \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_zero_limit_returns_empty \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_snapshot_row_reader_zero_limit_skips_file_scan \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_limit_one_preview_avoids_full_supported_file_iterator \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_preview_limit_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/dataset_registry/catalog.py \
  services/mlx-worker-python/tests/test_dataset_registry.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/dataset_registry_preview_limit_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/dataset_registry_preview_limit_probe.py
```

GitHub Actions PR-scoped performance remains the merge gate for the registered
probe report.

## Success Criteria

- Focused dataset preview tests pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe shows lower `zero_limit_elapsed_ms_mean` and
  `zero_limit_peak_bytes_mean` without regressing normal `limit=1` preview beyond
  probe tolerance.
