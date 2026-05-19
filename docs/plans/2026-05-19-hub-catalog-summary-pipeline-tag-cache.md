# Hub catalog summary pipeline tag cache

## Scope

This Python-only performance slice is limited to `HubCatalog._summary_record` in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The affected path is already covered by the registered PR-scoped performance
probe `hub-catalog-tag-normalization-single-pass` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for local Linux
verification and hosted PR-scoped CI validation.

## Change

`_summary_record` now normalizes the selected Hub `pipeline_tag` once and reuses
that value for both local-fit evidence and the returned summary record. This
preserves behavior while avoiding a repeated payload/card-data lookup and string
normalization on every summarized Hub record.

## Verification

Run, from the repository root:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_tag_normalization_probe.py
MELIX_HUB_CATALOG_TAG_PROBE_RECORDS=5000 MELIX_HUB_CATALOG_TAG_PROBE_SAMPLES=5 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_tag_normalization_probe.py
```

Hosted PR-scoped performance CI remains the merge gate for base-vs-head probe
validation.
