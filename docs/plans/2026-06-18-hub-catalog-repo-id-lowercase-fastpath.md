# Hub catalog lowercase repo-id MLX fast path

## Scope

This Python performance slice is limited to Hub catalog MLX compatibility checks in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The change preserves existing case-insensitive repo-id matching semantics while
adding a lower-case `mlx` substring fast path before allocating a lower-cased
repo id. This targets common Hub repo ids that already contain lower-case `mlx`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for `hub_catalog.py`, its focused tests, and
`scripts/hub_catalog_size_hint_probe.py`. The relevant metric for this slice is
`payload_compatibility_elapsed_ms_mean`; the probe also records
`elapsed_ms_mean` for the adjacent size-hint path sharing the same file.

## Plan

1. Keep the existing repo-id case-insensitivity regression tests as the behavior
   guard for `_payload_is_mlx_compatible()` and `_is_mlx_compatible()`.
2. Add one helper that checks for a lower-case `mlx` substring before falling
   back to the existing lower-case comparison.
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
