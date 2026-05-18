# Hub catalog size-hint integer parser fast path

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._size_hint_from_text(...)` when the precompiled size-hint regex captures an integer value such as `MODEL SIZE | 512 kb`.

## Registered probe

Affected paths are covered by the existing PR-scoped performance probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

The probe workload includes integer explicit README hints and records `elapsed_ms_mean` plus `size_hint_calls_mean`.

## Implementation plan

1. Preserve the precompiled regex and accepted `kb`/`mb`/`gb` units.
2. After a successful regex match, use direct multiplier branches for common exact-case units instead of normalizing every unit string.
3. Multiply integer captures with `int(value_text)` directly.
4. Keep decimal captures on the existing `float(value_text)` fallback path.
5. Add focused regression tests proving integer hints skip float conversion and decimal/mixed-case hints still use the fallback behavior.

## Verification

Run the registered focused tests, changed-scope coverage, and the local registered probe on Linux before opening the PR. Use the hosted PR-scoped performance workflow as the merge gate.
