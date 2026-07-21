# Engine generate empty media usage elision

## Scope

This Python-only performance slice is limited to `worker.engine.engine_core` generate/decode usage accounting for requests that do not have media-feature probe counters.

## Registered probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The probe already has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/engine_generate_usage_token_probe.py`

## Plan

1. Preserve protobuf usage defaults and media counter behavior for non-zero probe snapshots.
2. Return `None` for absent or all-zero media-feature probe snapshots so text-only usage accounting can use the compact `UsageDelta` and `TextFinalizationUsage` paths.
3. Add regression coverage for the all-zero probe snapshot elision.
4. Run the registered focused tests, changed-scope coverage, and local registered probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate.

## Acceptance

- Focused generate-stream and registered-probe tests pass locally.
- Changed-scope coverage for touched Python files remains at least 95%.
- The local registered probe reports directionally lower `fallback_elapsed_ms_mean` for text-only usage requests.
- The PR-scoped performance workflow completes successfully before merge.