# Hub Catalog MLX-only Prefilter Optimization

## Goal

Avoid redundant hub summary/local-fit work for search results that are discarded by `HubCatalog.search_models(..., mlx_only=True)`.

## Touched files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Linux-only constraint

This is a Python worker slice and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local probe.

## Performance probe definition

Synthetic workload:

- construct a large in-memory Hub payload page with a small fraction of MLX-compatible records
- call `HubCatalog.search_models(..., mlx_only=True)` through a fake opener
- count `_local_fit_evidence(...)` calls and measure elapsed time / traced peak bytes

Success metrics:

- returned MLX records are identical
- local-fit calls drop from all payloads to only MLX-compatible payloads
- elapsed time improves materially on the synthetic mostly-non-MLX page

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py
python3 /tmp/hub_catalog_mlx_prefilter_probe.py
```
