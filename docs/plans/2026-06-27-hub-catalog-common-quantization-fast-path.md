# Hub catalog common quantization fast path

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._quantization_summary()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-tag-normalization-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_tag_normalization_probe.py`

## Slice

The Hub catalog normalization probe repeatedly summarizes records with the common `4-BIT` plus `OptiQ` tag pair. Keep the existing general ordered-alias fallback, but short-circuit the common lowered tag set when no higher-priority or additional quantization aliases are present.

## Verification plan

1. Preserve quantization summary ordering for mixed aliases with focused unit coverage.
2. Run the registered focused test command for `hub-catalog-tag-normalization-single-pass` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally via `scripts/pr_scoped_performance_run.py` against `origin/main` and this branch.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage for touched files remains at or above the repository threshold.
- The registered probe shows a non-regressing direction for `elapsed_ms_mean`.
- CI PR-scoped performance completes successfully before merge.
