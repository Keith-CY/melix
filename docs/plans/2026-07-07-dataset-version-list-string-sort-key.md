# Dataset Version Listing String Sort Key Slice

## Scope

This Python-only performance slice is limited to `list_dataset_versions()` in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The common dataset-version listing path reads generated `dataset-version.json`
files whose `created_at` and `version_id` fields are strings. The existing sort
key preserved malformed/non-string compatibility by calling a Python helper for
every row, even on this common string-only path.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
fields, and watches the production module, focused tests, and
`scripts/dataset_version_listing_probe.py`.

## Plan

1. Add a regression test proving non-string sort keys still use the historical
   string-coercion fallback ordering.
2. Keep the existing fallback helper for malformed manifests, but detect the
   common string-key path while building the listing.
3. Use a bound `operator.itemgetter("created_at", "version_id")` sort key for
   the common string-key path to avoid per-row Python helper calls.
4. Run focused pytest, changed-scope coverage, and the registered local probe on
   Linux before opening the PR. GitHub Actions PR-scoped performance remains the
   merge gate.

## Verification targets

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_skips_missing_or_directory_manifests services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_handles_missing_versions_root services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_preserves_non_string_sort_key_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_version_listing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_version_listing_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_skips_missing_or_directory_manifests services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_handles_missing_versions_root services/mlx-worker-python/tests/test_dataset_preparation_versioning.py::test_dataset_version_listing_preserves_non_string_sort_key_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_version_listing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_version_listing_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/tests/test_dataset_preparation_versioning.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_version_listing_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id dataset-version-listing-scandir --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/dataset_version_listing_probe.json
```
