# Hub catalog exact-list string normalization slice

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._string_list`.

## Scope

Hub catalog summary construction normalizes Hub payload tag arrays through `_string_list` for each record before deriving MLX compatibility and local fit evidence. The hot path receives exact `list` instances from decoded JSON payloads; list subclasses remain supported for compatibility but are not the common case.

## Registered probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-tag-normalization-single-pass` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_tag_normalization_probe.py`

## Implementation plan

1. Add focused regression coverage proving exact `list`, list subclass, and scalar string inputs preserve `_string_list` behavior.
2. Fast-path exact `list` inputs before the generic `isinstance(value, list)` fallback.
3. Verify with the registered focused tests, changed-scope coverage, and local registered probe on Linux.
4. Use PR-scoped performance CI as the merge gate.

## Metrics

Target metric: lower `elapsed_ms_mean` in `hub-catalog-tag-normalization-single-pass` with unchanged `tag_normalization_calls_mean` and record count.
