# Hub catalog summary exact tag list fast path

## Scope

This Python-only performance slice is limited to tag normalization inside
`HubCatalog._summary_record(...)` in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

Hub API payloads normally provide `tags` as an exact `list`. This slice preserves
existing behavior while collecting exact-list string tags and their lowered set
in a single pass in the per-record summary hot path. List subclasses, string tag
payloads, missing tags, and other non-list payload shapes continue to route
through `_string_list(...)`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-tag-normalization-single-pass` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already exposes focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_tag_normalization_probe.py`

No probe registry change is required for this slice.

## Plan

1. Add focused regression tests proving exact-list tags are filtered inline and
   list subclasses still use the shared `_string_list(...)` helper.
2. In `_summary_record(...)`, read raw tags once and collect exact-list string
   tags plus their lowered set in a single pass before falling back to
   `_string_list(...)` for all other payload shapes.
3. Run the registered focused tests, changed-scope coverage, and registered Hub
   catalog tag-normalization probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_tag_normalization_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_tag_normalization_probe.py
```
