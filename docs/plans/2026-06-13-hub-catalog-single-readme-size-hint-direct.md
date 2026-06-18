# Hub catalog single-readme size hint direct parse

## Scope

This Python performance slice is limited to the Hub catalog model-size hint parser in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The change preserves model-size hint semantics while reusing the existing direct explicit-marker parser for payloads that only provide one marked text field, such as a README containing `MODEL SIZE | <value> <unit>`. Before this slice, those single-field branches skipped the direct parser and immediately used the regex fallback.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for `hub_catalog.py`, `test_hub_catalog.py`, `test_pr_scoped_performance.py`, and `scripts/hub_catalog_size_hint_probe.py`. This slice relies on the probe's `size_hint_calls_mean` and `elapsed_ms_mean` metrics to validate reduced regex fallback work.

## Plan

1. Add a regression test proving a single README `MODEL SIZE | ...` payload is parsed without calling the regex fallback helper.
2. Route single marked text fields through a small direct-then-regex helper.
3. Run focused Hub catalog tests, changed-scope coverage, and the registered Hub catalog probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance report as the merge gate.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_size_hint_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_HUB_CATALOG_SIZE_HINT_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_size_hint_probe.py
```
