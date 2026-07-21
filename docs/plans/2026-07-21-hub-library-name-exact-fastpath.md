# Hub catalog library-name exact MLX fast path

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._payload_is_mlx_compatible()`.
It preserves Hub MLX compatibility detection while replacing a tiny exact-name frozenset lookup on
the payload library name with direct string comparisons before the mixed-case atom fallback.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

The probe records both size-hint parser metrics and the Hub payload compatibility workload;
this slice targets `payload_compatibility_elapsed_ms_mean` while keeping size-hint counters
unchanged.

## Implementation plan

1. Keep `_is_mlx_atom()` unchanged for mixed-case and scalar compatibility checks.
2. Replace exact `MLX`/`mlx` library-name set membership with direct equality checks in
   `_payload_is_mlx_compatible()`.
3. Reuse the focused Hub catalog tests that cover exact, mixed-case, malformed, and nested
   compatibility payloads.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused Hub catalog tests pass.
- Changed-scope coverage for touched Python paths remains at least 95%.
- The registered local probe reports directionally lower `payload_compatibility_elapsed_ms_mean`
  without changing `size_hint_calls_mean` or compatibility match counts.
- GitHub Actions and the registered PR-scoped performance report complete successfully before merge.
