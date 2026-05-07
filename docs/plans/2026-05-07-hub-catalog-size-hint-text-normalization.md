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
## 2026-05-07 follow-up: unit multiplier branch

A follow-up micro-slice keeps the same registered probe and narrows `_size_hint_from_text(...)` by replacing the per-match unit multiplier dictionary literal with direct `kb`/`mb`/`gb` branches. This preserves the precompiled regex behavior and accepted units while avoiding repeated short-lived dictionary allocation on every successful size-hint match.

Success criteria for this follow-up:

- Focused Hub catalog and PR-scoped performance tests pass.
- Changed-scope coverage remains at least 95%.
- The local registered probe reports lower `elapsed_ms_mean` versus the pre-change branch baseline with unchanged `checksum`, `matched_hint_count`, `sample_count`, and `size_hint_calls_mean` guard rails.
- Hosted PR-scoped performance CI runs `hub-catalog-size-hint-regex-precompile` before merge.
