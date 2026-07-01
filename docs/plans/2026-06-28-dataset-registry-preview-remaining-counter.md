# Dataset Registry Preview Remaining Counter

## Scope

This Python-only performance slice keeps `read_hf_dataset_snapshot_rows()` behavior unchanged while avoiding repeated `len(rows)`/`max()` work inside the limited preview read loop. The loop now carries a decrementing remaining-row counter across selected dataset files.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_preview_limit_probe.py`

## Plan

1. Preserve the existing limited and unlimited row-reader semantics.
2. Replace per-file `max(limit - len(rows), 0)` recomputation with a local `remaining` counter that is decremented by the number of rows read from each file.
3. Verify with the registered focused tests, changed-scope coverage, and the registered PR-scoped performance probe on Linux.
4. Use GitHub Actions as the final PR-scoped performance validation before merge.

## Local Evidence Template

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <registered focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <registered focused tests> && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/dataset_registry/catalog.py services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_registry_preview_limit_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/dataset_registry_preview_limit_probe.py
```
