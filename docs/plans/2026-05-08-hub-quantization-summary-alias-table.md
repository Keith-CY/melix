# Hub quantization summary alias table

## Goal

Reduce per-record allocation overhead in Hub catalog summary construction by
hoisting quantization-summary alias definitions to a module-level immutable table
instead of rebuilding the alias list and sets for every record.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Registered Probe

The affected path is covered by `hub-catalog-tag-normalization-single-pass` in
`infra/perf/pr_scoped_probes.json`, including focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Verification Plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_tag_normalization_probe.py
```

## Decision Gate

Accept only if the focused tests pass, changed-scope coverage remains above 95%,
and the registered local probe shows a clear elapsed-time improvement versus the
same-worktree baseline.
