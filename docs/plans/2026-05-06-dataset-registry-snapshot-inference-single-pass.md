# Dataset Registry Snapshot Inference Single-Pass Optimization

## Goal

Reduce redundant work in Hugging Face dataset snapshot discovery by deriving the file list, total byte count, split names, and config names in one pass over supported dataset files.

## Scope

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_snapshot_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Constraint

This is a Python worker slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and an explicit performance probe.

## Performance Probe

Registered scoped CI probe: `dataset-registry-snapshot-inference-single-pass`.

The probe builds a synthetic Hugging Face dataset cache with many supported files, wraps the legacy split/config inference helpers to count calls, and runs `DatasetCatalog.registry_snapshot_payload()` while measuring:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `legacy_inference_helper_calls_mean`
- `file_count_mean`

## Success Metrics

- Preserve dataset snapshot payload shape, ordering, split/config inference, and total byte reporting.
- Drive `legacy_inference_helper_calls_mean` to `0.0` on the optimized branch for snapshot builds.
- Keep changed-scope automated coverage at or above 95%.
- Keep the registered scoped CI probe selected for dataset registry changes.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_snapshot_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_snapshot_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/dataset_registry/catalog.py services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_registry_snapshot_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/dataset_registry_snapshot_probe.py
git diff --check
```
