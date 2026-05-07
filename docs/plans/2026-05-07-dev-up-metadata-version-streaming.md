# Dev-up MLX Metal metadata version streaming

## Goal

Reduce transient memory pressure in `scripts/dev_up.py` when resolving the local `mlx_metal` wheel version for `mlx.metallib` discovery.

## Touched files

- `scripts/dev_up.py`
- `services/mlx-worker-python/tests/test_dev_up_script.py`

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic metadata-reading probe.

## Optimization

`read_mlx_metal_dist_info_version(...)` previously materialized the entire `METADATA` file with `Path.read_text(...).splitlines()` even though it only needs the first `Version:` line. The change streams the file line-by-line and returns as soon as the version header is found.

## Performance probe

Run a synthetic comparison against detached `origin/main` and the head worktree. The workload creates an `mlx_metal-*.dist-info/METADATA` file with a large trailing payload after the `Version:` header and repeatedly calls `read_mlx_metal_dist_info_version(...)`.

Success metrics:

- Preserve the resolved version.
- Reduce traced peak allocation by avoiding full-file materialization.
- Avoid a meaningful elapsed-time regression.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_uses_scandir_without_path_glob \
  services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_falls_back_to_dist_info_directory_name \
  services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_skips_scandir_errors

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same test nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/dev_up.py services/mlx-worker-python/tests/test_dev_up_script.py

python /tmp/dev_up_metadata_probe.py <repo-root>

git diff --check
```

## PR-scoped performance CI

Existing registered probe: `dev-up-mlx-metal-dist-info-scandir`. The touched script and focused tests are already in its `watch_globs`, `test_command`, and `coverage_command`, so no new registry entry is needed for this narrow metadata-reader optimization.
