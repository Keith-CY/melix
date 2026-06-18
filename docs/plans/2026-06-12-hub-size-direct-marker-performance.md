# Hub Catalog Size Hint Direct Marker Performance Slice

## Status

Accepted for the 2026-06-12 performance slice.

## Scope

Optimize the Python hub catalog size-hint path in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py` by adding a direct
common-case parser for explicit `Model size` README/card lines before falling
back to the registered regex path.

## Registered Probe

This slice is covered by the existing PR-scoped performance probe:

- `hub-catalog-size-hint-regex-precompile`
- watched path: `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- focused tests: `services/mlx-worker-python/tests/test_hub_catalog.py`
- coverage command: registered `coverage_command` in
  `infra/perf/pr_scoped_probes.json`
- probe command: registered `probe_command` in
  `infra/perf/pr_scoped_probes.json`

## Behavior

The direct parser handles high-frequency explicit marker forms such as:

- `Model size: 12 GB`
- `MODEL SIZE | 7 kb`
- `model size 1.5 MB`

Mixed-case marker variants that are not covered by the direct fast path still
fall back to the existing case-insensitive regex parser, preserving behavior.

## Verification Plan

1. Run the focused hub catalog tests and PR-scoped registry tests.
2. Run changed-scope coverage using the registered coverage command.
3. Run `scripts/hub_catalog_size_hint_probe.py` locally on Linux and compare the
   metrics against the pre-change baseline.
4. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.
