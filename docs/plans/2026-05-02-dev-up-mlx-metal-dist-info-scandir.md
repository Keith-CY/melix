# Dev-up MLX Metal Dist-info Scandir Slice

## Goal

Reduce filesystem overhead in `scripts/dev_up.py` when resolving the installed `mlx_metal` wheel version for a discovered `mlx.metallib` candidate.

## Scope

- `scripts/dev_up.py`
- `services/mlx-worker-python/tests/test_dev_up_script.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Constraint

This slice is Python-only and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped probe. It does not validate Swift runtime effects locally.

## Optimization Hypothesis

`read_mlx_metal_dist_info_version()` currently calls `Path.glob()` twice for every ancestor of a discovered `mlx.metallib`: once for `mlx_metal-*.dist-info/METADATA` and once for `mlx_metal-*.dist-info`. Replacing those glob calls with one `os.scandir()` pass per ancestor preserves the metadata-first behavior while avoiding pathlib glob allocation and duplicate directory scans.

## Registered Probe

- Probe ID: `dev-up-mlx-metal-dist-info-scandir`
- Workload: create a synthetic site-packages ancestor containing 2,000 non-matching dist-info directories, one matching `mlx_metal` dist-info directory with `METADATA`, and then resolve the version seven times.
- Metrics:
  - `elapsed_ms_mean` lower is better
  - `elapsed_ms_min` lower is better
  - `dist_info_count` and `sample_count` informational

## Success Metrics

- Focused tests prove the version resolver no longer relies on `Path.glob()` and still prefers the `METADATA` version over the directory-name fallback.
- Changed-scope coverage for the touched script, tests, and registry remains at or above 95%.
- Local registered probe improves versus the pre-change baseline.
- PR-scoped performance CI selects and completes the registered probe for this path.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_falls_back_to_dist_info_directory_name services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_skips_scandir_errors services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dev_up_mlx_metal_dist_info_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_falls_back_to_dist_info_directory_name services/mlx-worker-python/tests/test_dev_up_script.py::test_read_mlx_metal_dist_info_version_skips_scandir_errors services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dev_up_mlx_metal_dist_info_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/dev_up.py services/mlx-worker-python/tests/test_dev_up_script.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 - <<'PY'
# Registered probe command from infra/perf/pr_scoped_probes.json.
PY
git diff --check
```
