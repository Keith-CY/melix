# Hub Catalog MLX Library Atom Fast Path

## Scope

This performance slice keeps the Hub catalog compatibility path behaviorally identical while removing a per-record lowercase allocation from the exact `library_name == MLX` check in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Probe Coverage

The affected path is already covered by the registered PR-scoped probe `Hub catalog size hint regex precompile` in `infra/perf/pr_scoped_probes.json`.

Registered commands include:

- focused test command for `services/mlx-worker-python/tests/test_hub_catalog.py` and PR-scoped probe selection tests;
- changed-scope coverage command over `hub_catalog.py`, `test_hub_catalog.py`, PR-scoped performance tests, and `scripts/hub_catalog_size_hint_probe.py`;
- local probe command through `scripts/hub_catalog_size_hint_probe.py`, which reports both size-hint and MLX compatibility metrics.

## Implementation Plan

1. Add a regression assertion for mixed-case `library_name` atom detection.
2. Replace `library_name.lower() == "mlx"` in `_is_mlx_compatible` with the existing allocation-free `_is_mlx_atom` helper.
3. Run focused tests, changed-scope coverage, and the registered probe locally on Linux.
4. Compare the registered probe against an `origin/main` baseline worktree before PR creation.

## Success Criteria

- Behavior remains unchanged for mixed-case `MLX` library metadata.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows a positive direction for `payload_compatibility_elapsed_ms_mean`.
