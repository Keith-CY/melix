# Hub catalog MLX repo-id substring fast path

## Scope

This Python-only performance slice is limited to MLX compatibility checks in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The optimization preserves existing Hub catalog semantics while deferring
`cardData` normalization until the top-level library, tags, and repo-id checks
have failed in `_payload_is_mlx_compatible()`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`Hub catalog size hint regex precompile` in `infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for `hub_catalog.py`, its focused tests, and the
Hub catalog probe script. This slice keeps the registered probe definition
stable and relies on its `payload_compatibility_elapsed_ms_mean` metric for the
MLX compatibility hot path.

## Plan

1. Add a regression test that exercises every ASCII case variant of the `mlx`
   substring in repo ids across both compatibility entry points.
2. Defer `cardData` dict extraction in `_payload_is_mlx_compatible()` until
   earlier top-level compatibility checks miss.
3. Run the focused Hub catalog tests, changed-scope coverage, and the registered
   Hub catalog probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_size_hint_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_HUB_CATALOG_SIZE_HINT_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_size_hint_probe.py
```
