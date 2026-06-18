# Dataset Version Listing Local Bindings

## Scope

This Python-only performance slice is limited to `list_dataset_versions()` in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.
It keeps dataset version listing semantics unchanged while reducing repeated
attribute/global lookups in the per-version manifest loop.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe declares focused `test_command`, `coverage_command`, and `probe_command`
entries and reports listing elapsed time plus version count.

## Implementation plan

1. Keep the existing `os.scandir()` manifest discovery behavior unchanged.
2. Reuse local loop bindings for version append/read operations and avoid a
   redundant `str()` conversion for manifest paths that are already yielded as
   strings.
3. 2026-06-12 follow-up: bind each loaded manifest's `dict.get` method once
   before copying the summary fields into the listing row. This keeps the same
   missing-field defaults and ordering while removing repeated bound-method
   lookups across large version directories.
4. Run the registered focused tests, changed-scope coverage, and the registered
   probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate after opening the
   PR.

## Validation

Local Linux validation for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_is_deterministic_and_reports_latency services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_handles_missing_versions_root services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_version_listing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_version_listing_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_is_deterministic_and_reports_latency services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_handles_missing_versions_root services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_version_listing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_version_listing_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/tests/test_dataset_preparation_versioning.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_version_listing_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id dataset-version-listing-scandir --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/dataset_version_listing_probe.json
```
