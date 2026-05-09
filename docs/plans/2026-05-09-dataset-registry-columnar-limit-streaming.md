# Dataset Registry Columnar Limit Streaming

## Goal

Avoid loading full Parquet and Arrow dataset preview files when callers request a small row limit. JSONL and CSV readers already stop once the limit is satisfied; columnar readers should follow the same contract.

## Scope

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- Existing registered PR-scoped probe: `dataset-registry-preview-limit-short-circuit`

## Linux constraint

This is a Python-only slice. The local Linux environment does not include real `pyarrow`, so focused tests and the probe use lightweight fake `pyarrow` modules to validate the reader dispatch/limit behavior without adding dependencies.

## Probe definition

Reuse `scripts/dataset_registry_preview_limit_probe.py` for the registered `dataset-registry-preview-limit-short-circuit` probe. The current probe already measures preview limit behavior for large JSONL snapshots. Local focused tests add deterministic structural coverage for the columnar hot path: limited Parquet reads must avoid `read_table(...)`, and limited Arrow reads must avoid `read_all()`.

Success metrics:

- Focused pytest passes.
- Changed-scope coverage is at least 95%.
- Local probe emits concrete `elapsed_ms_mean` and `peak_bytes_mean` for preview reads.
- `git diff --check` passes.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_respects_limit \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_parquet_limit_uses_batched_reader \
  services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_arrow_limit_uses_first_batch \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_preview_limit_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused test nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/dataset_registry/catalog.py \
  services/mlx-worker-python/tests/test_dataset_registry.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/dataset_registry_preview_limit_probe.py

git diff --check
```
