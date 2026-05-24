# Runtime weight stat size fast path

## Scope

This Python-only performance slice is limited to model weight resident-byte estimation in `services/mlx-worker-python/worker/runtime/runtime_utils.py`.

The affected path is already covered by the registered PR-scoped performance probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the runtime utility, focused tests, PR-scoped performance selection tests, and `scripts/runtime_utils_top_level_weights_probe.py`.

## Optimization

For top-level weight files and direct weight-file paths, use the integer `st_size` returned by `stat()` directly after file checks. Local filesystem `stat().st_size` is already a non-negative integer for regular files, so this removes redundant `int()` and `max()` work inside the hot weight-size scan while preserving existing file/suffix/error handling.

## Verification Plan

Run the registered focused pytest command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the final base-vs-head validation source before merge.

## Acceptance Criteria

- Existing runtime utility behavior tests pass.
- Changed-scope coverage for the touched runtime utility/test/probe scope remains at least 95%.
- Local registered probe shows lower `elapsed_ms_mean` without changing checksum or expected bytes.
- PR-scoped performance CI selects and completes `runtime-utils-top-level-weight-streaming` successfully before merge.
