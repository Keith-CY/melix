# Hub Catalog MLX Atom Exact Fast Path

## Goal

Reduce repeated compatibility-check overhead in the Hub catalog path when the common MLX marker is exactly `mlx` or `MLX`.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`
- `infra/perf/pr_scoped_probes.json` (existing registered probe only)

## Linux Constraint

This slice is Python-only and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped probe.

## Optimization Hypothesis

`_is_mlx_atom()` is called from hot Hub compatibility paths for library names, repo/card tags, and card metadata. The most common exact atoms are `mlx` and `MLX`; returning immediately for those exact values avoids the ordinal character checks while preserving the existing mixed-case fallback for less common variants such as `Mlx`.

## Registered Probe

- Probe ID: `hub-catalog-size-hint-regex-precompile`
- Workload: repeatedly exercises Hub size-hint extraction and MLX compatibility classification through `scripts/hub_catalog_size_hint_probe.py`.
- Metrics:
  - `elapsed_ms_mean` lower is better
  - `payload_compatibility_elapsed_ms_mean` lower is better
  - `size_hint_calls_mean`, compatibility call counts, checksum, and matched counts preserve behavior.

## 2026-07-11 marker prefilter substring slice

This follow-up Python-only slice stays within `services/mlx-worker-python/worker/model_ops/hub_catalog.py` and the registered `hub-catalog-size-hint-regex-precompile` probe. `_may_contain_model_marker(...)` now checks the four case combinations for the adjacent `mo` marker directly instead of first scanning separately for `m`/`M` and `o`/`O`. Behavior remains conservative for every marker spelling the downstream size-hint parser can match, while avoiding redundant full-string membership scans in Hub readme/description size-hint prefiltering.

Local Linux validation uses the same focused Hub catalog tests, changed-scope coverage command, and registered PR-scoped performance probe. GitHub Actions PR-scoped performance remains the merge gate.

## Success Metrics

- Focused Hub catalog tests preserve exact and mixed-case MLX marker behavior.
- Changed-scope coverage for touched lines remains at or above 95%.
- Local registered probe improves compatibility elapsed time versus the pre-change baseline.
- PR-scoped performance CI selects and completes the registered probe for this path.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_size_hint_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_size_hint_probe.py
git diff --check
```
