# Dataset Version JSON Load Inline Slice

## Goal

Reduce per-version overhead in `list_dataset_versions(...)` by inlining the small manifest JSON read in the hot listing loop.

## Scope

- Change exactly one Python optimization point in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
- Preserve dataset version listing semantics, deterministic sorting, missing-root behavior, and manifest payload fields.
- Keep the existing `os.scandir` manifest-path discovery unchanged.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused:

- `test_command` for dataset version listing behavior, scandir usage, PR-scoped probe selection, and probe script emission.
- `coverage_command` for the same focused tests plus changed-scope coverage on the touched implementation, test, probe registry, and probe script paths.
- `probe_command` via `scripts/dataset_version_listing_probe.py`, which measures `elapsed_ms_mean`, `elapsed_ms_min`, and `elapsed_ms_p95` over a synthetic multi-version listing workload.

## Verification

Focused local Linux verification for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_is_deterministic_and_reports_latency \
  services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_uses_scandir_without_path_glob \
  services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_handles_missing_versions_root \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_version_listing_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_version_listing_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/dataset_preparation.py \
  services/mlx-worker-python/tests/test_dataset_preparation_versioning.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/dataset_version_listing_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id dataset-version-listing-scandir \
  --base-repo <baseline-worktree> \
  --head-repo "$PWD" \
  --output /tmp/dataset_version_listing_probe.json
```

## Metrics

Accept only if the registered local probe shows a clear non-regression or improvement for `elapsed_ms_mean`; GitHub Actions PR-scoped performance remains the merge gate.
