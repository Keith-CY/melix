# Hub Catalog Size Label Prefix Fast Path

## Scope

This Python-only performance slice keeps hub catalog behavior unchanged while reducing allocation on the direct `cardData.model_size` parsing path in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

Focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_size_hint_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_HUB_CATALOG_SIZE_HINT_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_size_hint_probe.py
```

## Implementation Plan

- Replace the `text[:10].lower() == "model size"` label check with a no-allocation ASCII prefix predicate.
- Preserve the existing case-insensitive `Model size` / `MODEL SIZE` / `model size` behavior and existing `:` / `|` / whitespace separator handling.
- Keep the change limited to direct `cardData.model_size` label parsing; regex-based README/description parsing remains unchanged.

## 2026-06-01 Follow-up: Separator Branch Allocation Elision

This follow-up keeps the same registered probe and narrows the remaining hot
separator branch in `_strip_model_size_label(...)`: after the no-allocation
ASCII label match, test `:` and `|` with direct character comparisons instead
of constructing a two-element set for every labeled `cardData.model_size` value.
The behavior remains unchanged for `Model size: 12 MB`, `MODEL SIZE | 7 kb`,
and compact separator forms such as `MODEL SIZE:7 kb`. The registered
`hub-catalog-size-hint-regex-precompile` script now exercises that compact
separator branch directly so PR-scoped performance validation covers the changed
path instead of relying only on the exact `Model size: ` shortcut.

## Success Metrics

- Focused hub catalog tests pass.
- Changed-scope coverage is at least 95%.
- The local registered probe reports a lower `elapsed_ms_mean` for the synthetic size-hint workload, with `size_hint_calls_mean` unchanged.
