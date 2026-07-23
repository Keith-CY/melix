# Model registry root identity fast path

This Python-only performance slice is limited to the registry-root tree scanner in `services/mlx-worker-python/worker/model_registry/catalog.py`.

## Registered probe

The affected path is already covered by the PR-scoped registered probe `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`. This slice extends that probe's evidence with a `root_identity_comparisons_mean` metric so the registered report captures the hot-path root-check elimination directly, in addition to elapsed time and child-path join counts.

## Optimization

`_scan_registry_root_tree_with_hf_repos()` only needs the Hugging Face cache repo-name check for immediate children of the resolved registry root. The traversal stack starts with the exact `resolved_root` object and pushes newly constructed child `Path` instances, so object identity preserves the current semantics for this root-only branch while avoiding repeated `Path.__eq__` dispatches for every directory child candidate.

The slice changes only the root check from value equality to identity and adds tests/probe metrics that count root equality comparisons during a synthetic plain-local scan.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after PR creation.

Expected local commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_uses_root_identity_check_for_hf_cache_detection services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_skips_hf_prune_relative_probe_for_plain_dirs services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_defers_plain_child_path_construction_until_stack_push services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_registry_plain_child_path_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/model_registry_plain_child_path_probe.py
```
