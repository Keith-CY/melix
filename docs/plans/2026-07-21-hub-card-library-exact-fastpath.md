# Hub catalog card library-name exact MLX fast path

## Scope

This Python-only performance slice is limited to the Hub catalog MLX compatibility helpers in
`worker.model_ops.hub_catalog`. It preserves exact and mixed-case MLX library-name detection while
replacing the remaining exact-name frozenset membership checks with direct string comparisons.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The probe has focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

This slice extends that probe's compatibility workload with an exact `cardData.library_name == "mlx"`
case so the registered metrics cover the changed card-data branch.

## Implementation plan

1. Remove the exact MLX library-name frozenset constant from the Hub catalog hot path.
2. Use direct `"mlx"`/`"MLX"` equality checks before the existing mixed-case `_is_mlx_atom()` fallback.
3. Add focused regression coverage proving exact card-data library names bypass `_is_mlx_atom()` while
   mixed-case names still fall back to the atom check.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused Hub catalog tests pass.
- Changed-scope coverage for touched Python paths remains at least 95%.
- The registered local probe reports directionally lower `payload_compatibility_elapsed_ms_mean` with
  unchanged compatibility call count and expected match count for the updated workload.
- GitHub Actions and the registered PR-scoped performance report complete successfully before merge.
