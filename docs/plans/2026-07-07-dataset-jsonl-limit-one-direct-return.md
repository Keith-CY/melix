# Dataset JSONL limit-one direct return slice

## Scope

This Python-only performance slice is limited to `worker.dataset_registry.catalog._read_rows_from_file` for JSONL preview reads with `limit=1`.

The existing dataset preview path frequently asks for a single preview row. Before this slice, the JSONL reader still allocated the general result list and append binding used by multi-row reads. This slice keeps multi-row behavior unchanged and adds a direct `limit == 1` return path that stops once the first dictionary row is decoded.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset registry preview path, changed-scope coverage, and the JSON command probe. This slice adds the new limit-one regression test to those focused commands and gives the zero-limit elapsed metric a small `0.05ms` absolute tolerance because that edge is measured around one microsecond and percentage-only comparisons produce noise regressions unrelated to this JSONL reader change.

## Verification plan

Run the focused dataset registry tests, changed-scope coverage, and the registered probe locally on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_jsonl_limit_one_returns_first_dict_directly services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_respects_limit services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_jsonl_row_reader_stops_after_limited_dict_rows services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_limit_one_preview_avoids_full_supported_file_iterator services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_preview_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_preview_limit_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_jsonl_limit_one_returns_first_dict_directly services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_row_reader_respects_limit services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_jsonl_row_reader_stops_after_limited_dict_rows services/mlx-worker-python/tests/test_dataset_registry.py::test_dataset_catalog_limit_one_preview_avoids_full_supported_file_iterator services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_dataset_registry_preview_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_registry_preview_limit_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/dataset_registry/catalog.py services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_registry_preview_limit_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id dataset-registry-preview-limit-short-circuit --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/dataset_jsonl_limit_one_probe.json
```

GitHub Actions PR-scoped performance remains the final registered probe validation gate before merge.
