# Hub Catalog Hot String Guard Inline

## Scope

This Python-only performance slice is limited to hot Hub catalog string-field guards in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, specifically `_size_hint_bytes(...)` and `_payload_is_mlx_compatible(...)`.

The affected path is covered by the registered PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries covering the Hub catalog implementation, focused tests, PR-scoped performance tests, and `scripts/hub_catalog_size_hint_probe.py`.

## Behavior

The Hub catalog path reads the same payload and card-data fields as before. This slice inlines the existing string-type guard for the hot size-hint and MLX-compatibility text fields, avoiding repeated helper calls while preserving the same `str`-only acceptance rule. It does not change accepted model-size syntax, regex fallback behavior, compatibility semantics, or local-fit calculations.

## Verification

Run the registered focused Hub catalog test command, changed-scope coverage command, and the registered `hub-catalog-size-hint-regex-precompile` probe locally on Linux before pushing. Use the GitHub Actions PR-scoped performance report as the merge gate.

Success criteria:

- focused Hub catalog tests pass;
- changed-scope coverage for touched files remains at least 95%;
- the registered size-hint probe shows non-regression or improvement for `elapsed_ms_mean` with unchanged `size_hint_calls_mean` and matched-count guard rails.
