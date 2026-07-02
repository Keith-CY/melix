# Hub Catalog Repo-ID Compatibility Fast Path

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._payload_is_mlx_compatible(...)`.

The compatibility helper already treats repository IDs containing an MLX marker as compatible. The slice reorders that positive check before scanning tag payloads so repo-ID hits avoid walking tag lists or inspecting non-string tag values.

## Registered Probe

The affected path is covered by the existing PR-scoped registered probe:

- `hub-catalog-size-hint-regex-precompile`

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and local Linux registered probe before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe report.

## Expected Metrics

The probe reports both size-hint parsing and MLX compatibility metrics. This slice targets `payload_compatibility_elapsed_ms_mean` without increasing compatibility calls or changing matched compatibility counts.
