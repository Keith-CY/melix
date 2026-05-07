# Hub Catalog Size Hint Text Normalization

## Goal

Reduce repeated Python-level text normalization work in Hub catalog size-hint parsing while preserving accepted model-size hint behavior.

## Scope

Touched files:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Optimization Slice

`_size_hint_bytes(...)` now normalizes each candidate payload text field once before joining the candidate fields for the existing explicit size-hint regex scan. The previous generator filtered with `_string(value)` and then yielded `_string(value)` again, doubling normalization calls for non-empty `description`, `readme`, and `cardData.description` fields. The slice also avoids a duplicate `payload.get("cardData")` lookup while preserving the existing joined-field fallback semantics.

## Registered Probe

Registered probe: `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

The existing registered probe has focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

The registered probe remains unchanged for apples-to-apples CI comparison and verifies that the shared Hub catalog size-hint path does not regress. The optimized `_size_hint_bytes(...)` payload path is measured locally with a paired base/head payload microprobe because changing the registered probe workload in the same optimization PR would compare different workloads between base and head.

## Success Metrics

- Focused pytest passes.
- Changed-scope coverage is at least 95% for touched executable lines.
- Local base-vs-head payload microprobe shows lower `elapsed_ms_mean` with unchanged guard-rail metrics (`checksum`, `matched_hint_count`, `sample_count`).
- `git diff --check` passes.
