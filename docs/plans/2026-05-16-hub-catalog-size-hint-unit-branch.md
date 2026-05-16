# Hub Catalog Size Hint Unit Branch Slice

## Scope

This Python-only performance slice keeps Hub catalog size-hint parsing behavior
unchanged while replacing the per-match `_SIZE_HINT_MULTIPLIERS` dictionary
lookup with direct unit branches. The hot path parses synthetic and real Hub
catalog metadata where model-size hints commonly resolve to `kb`, `mb`, or
`gb`.

## Probe Coverage

The affected path is already covered by the registered PR-scoped performance
probe `hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Implementation Plan

1. Reuse the focused Hub catalog tests for direct `cardData.model_size`,
   explicit text hints, missing metadata, and PR-scoped probe dispatch.
2. Replace the shared size-hint unit dictionary lookup with a tiny branch helper
   for the three supported units.
3. Run the registered focused tests, changed-scope coverage, and registered
   size-hint probe locally on Linux.
4. Accept only if behavior is stable and the registered probe shows a clear
   non-regressing or improved direction.

## Validation Boundary

This slice changes Python worker/model-ops code only and is locally verifiable
on Linux. No Swift runtime performance effect is claimed.
