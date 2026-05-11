# Hub Catalog Combined Size-Hint Marker Guard

## Scope

This performance slice narrows `worker.model_ops.hub_catalog._size_hint_bytes` when Hub payloads provide multiple free-text fields (`description`, `readme`, and `cardData.description`) that contain byte-like values but no explicit `model size` marker.

Affected registered probe:

- `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`

The probe already has focused `test_command`, `coverage_command`, and `probe_command` entries covering `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, `services/mlx-worker-python/tests/test_hub_catalog.py`, and `scripts/hub_catalog_size_hint_probe.py`.

## Plan

1. Add regression coverage proving combined free-text fields without a model-size marker do not call the regex parser.
2. Reuse `_may_contain_model_marker(...)` after joining multiple candidate fields and return `0` before `_size_hint_from_text(...)` when the marker is absent.
3. Extend `scripts/hub_catalog_size_hint_probe.py` with a deterministic multi-field no-marker payload so the registered probe reports the parser-call reduction against `origin/main`.

## Success Criteria

- Focused Hub catalog tests pass on Linux.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows fewer `size_hint_calls_mean` calls for the synthetic mixed payload workload while preserving matched hint counts/checksum semantics.
