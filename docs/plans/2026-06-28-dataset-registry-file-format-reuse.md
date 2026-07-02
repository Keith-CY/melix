# Dataset Registry File Format Reuse

## Scope

This Python-only performance slice is limited to dataset registry snapshot file discovery in `worker.dataset_registry.catalog`. It preserves snapshot payload semantics while reusing the supported file format computed during the directory scan instead of recomputing it from each `Path` when building `DatasetFile` records.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-registry-snapshot-inference-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_snapshot_probe.py`

## Plan

1. Keep `_iter_supported_dataset_file_entries(...)` behavior stable for existing callers.
2. Add an internal scan record iterator that carries `(path, relative_path, file_format)`.
3. Use the scan-time `file_format` in `_dataset_files(...)` so snapshot construction avoids a second suffix/name parse per supported file.
4. Verify with the registered focused tests, changed-scope coverage, and the registered local probe on Linux.
5. Use GitHub Actions PR-scoped performance as the final merge gate.

## Local Evidence Template

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_snapshot_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_snapshot_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_snapshot_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_snapshot_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/dataset_registry/catalog.py services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_registry_snapshot_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/dataset_registry_snapshot_probe.py
```
