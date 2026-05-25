# Startup Version Next-Part Binding Slice

## Scope

This Python-only performance slice is limited to `compare_versions()` in `services/mlx-worker-python/worker/productization/startup_signals.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`.

The registry entry already has focused `test_command`, `coverage_command`, and `probe_command` entries for the startup-signal source path, tests, PR-scoped probe tests, and `scripts/startup_signals_version_probe.py`.

## Implementation Plan

1. Keep version comparison semantics unchanged.
2. Bind `_next_normalized_version_part` once before the comparison loop so each component comparison avoids repeated module global lookup.
3. Bind the character-code helper on `_next_normalized_version_part()` as a default argument so per-character scanning avoids repeated global lookup.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.

## Acceptance Criteria

- Focused startup-signal tests and PR-scoped registry tests pass locally on Linux.
- Changed-scope coverage for touched Python/probe files remains at or above 95%.
- The registered probe shows lower `elapsed_ms_mean` than the pre-change baseline.
- PR-scoped performance CI completes successfully before merge.

## Non-Goals

- No update-channel schema or behavior changes.
- No change to normalized version parsing semantics.
- No generated protocol or lockfile changes.
