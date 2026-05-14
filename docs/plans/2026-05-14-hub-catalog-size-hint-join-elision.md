# Hub Catalog Size Hint Join Elision

## Scope

This Python-only performance slice narrows `worker.model_ops.hub_catalog._size_hint_bytes` for payloads that provide multiple descriptive text fields but no model-size marker.

## Optimization

Before this slice, the multi-field fallback always built a newline-joined string before checking whether any field could contain a `model size` marker. The slice checks each source field for the marker first, and only builds the combined string when at least one field can require the explicit size parser.

The combined-string parser path remains intact when a marker is present so cross-field inputs such as `description="Model size:"` plus `readme="5 MB"` preserve existing behavior.

## Registered Probe

Affected paths are already covered by PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

The probe provides:

- focused tests through `test_command`
- changed-scope coverage through `coverage_command`
- repeated command JSON metrics through `probe_command`

## Verification Plan

Run locally on Linux before PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_size_hint_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id hub-catalog-size-hint-regex-precompile --base-repo <baseline-worktree> --head-repo "$PWD" --output <probe-output.json>
```

CI PR-scoped performance remains the final registered-probe merge gate.
