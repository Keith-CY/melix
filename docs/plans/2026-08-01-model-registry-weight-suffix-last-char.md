# Model Registry Weight Suffix Last-Character Guard

## Context

This Python performance slice is limited to the plain-local model registry tree scan in `worker.model_registry.catalog.WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(...)`.

The affected path is covered by the registered PR-scoped probe `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_registry_plain_child_path_probe.py`

## Slice

Add a sentinel filename prelookup before the hot tree scan handles the small set of exact metadata/weight-index filenames, and keep a last-character guard before `str.endswith(_MODEL_WEIGHT_FILE_SUFFIXES)` for ordinary directory and metadata entry names. The behavior stays equivalent because only exact sentinel files set scan flags, non-file sentinel names still continue to the directory traversal path, and every supported weight suffix (`.safetensors`, `.npz`) ends with either `s` or `z`; names ending with any other character cannot match the supported tuple.

This keeps the existing exact handling for `manifest.json`, `config.json`, `generation_config.json`, `tokenizer_config.json`, and `model.safetensors.index.json` unchanged.

## Validation

Run locally on Linux before PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_defers_plain_child_path_construction_until_stack_push services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py docs/plans/2026-08-01-model-registry-weight-suffix-last-char.md
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/model_registry_plain_child_path_probe.py
```

The registered PR-scoped performance CI probe is the merge gate for this slice.
