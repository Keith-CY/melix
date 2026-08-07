# Hub Catalog MLX Tag Exact Membership Performance Slice

## Status

Accepted for the 2026-07-17 performance slice.

## Scope

Optimize the Python hub catalog MLX compatibility check in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py` by short-circuiting
exact `"mlx"` and `"MLX"` tag payload membership before entering the mixed-case
atom scanner.

## Registered Probe

This slice is covered by the existing PR-scoped performance probe:

- `hub-catalog-size-hint-regex-precompile`
- watched path: `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- focused tests: `services/mlx-worker-python/tests/test_hub_catalog.py`
- coverage command: registered `coverage_command` in
  `infra/perf/pr_scoped_probes.json`
- probe command: registered `probe_command` in
  `infra/perf/pr_scoped_probes.json`

The registered probe reports both the size-hint path and
`payload_compatibility_elapsed_ms_mean`, which exercises the compatibility
payload path changed by this slice.

## Behavior

Exact lowercase and uppercase MLX tags now return before calling the per-item
case-insensitive atom helper. Mixed-case tags such as `"mLx"` still use the
existing helper, preserving compatibility semantics for list subclasses and
non-string payload entries.

## Verification Plan

1. Run the focused hub catalog tests and PR-scoped registry tests.
2. Run changed-scope coverage using the registered coverage command.
3. Run `scripts/hub_catalog_size_hint_probe.py` locally on Linux and compare the
   metrics against the pre-change baseline.
4. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.
