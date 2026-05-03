# Model Registry Metadata Signal Sort Elision

## Goal

Reduce redundant work in the Python model-registry MLX-signal detection path by avoiding unnecessary sorted JSON serialization when scanning `config_payload` metadata.

## Linux Constraint

This slice is Python-only and will be verified locally on Linux. No macOS/Swift-only runtime behavior is changed.

## Touched Files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Performance Probe

Use the existing registered scoped probe `model-registry-plain-local-manifest-stat-elision` and extend it to measure metadata-signal scan serialization overhead.

Success signals:
- `elapsed_ms_mean` improves or stays clearly better than `origin/main`
- existing guard metrics (`generation_config_stat_calls_mean`, `manifest_is_file_calls_mean`, `config_load_calls_mean`, `manifest_parse_calls_mean`) do not regress
- probe behavior stays semantically identical for discovered model count

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <focused registry tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused registry tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --probe model-registry-plain-local-manifest-stat-elision --output <json>
git diff --check
```
