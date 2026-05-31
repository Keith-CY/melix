# Trajectory Manifest Fast Return Performance Slice

## Scope

This Python-only performance slice is limited to trajectory provenance manifest loading in `services/mlx-worker-python/worker/trajectory_provenance.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The probe defines focused `test_command`, `coverage_command`, and `probe_command` entries and emits:

- `old_mean_ms`
- `new_mean_ms`
- `delta_ms`
- `speedup`
- `old_peak_bytes_mean`
- `new_peak_bytes_mean`

## Linux verification boundary

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered command-json performance probe.

## Optimization hypothesis

`load_trajectory_provenance_from_snapshot_manifest()` reads fresh JSON payloads and uses `copy_nested=False`, so the manifest-load path does not need the final dictionary-comprehension pass that re-filters empty values after provenance fields are already assembled. Building the provenance mapping with non-empty scalar fields up front preserves empty-field omission while avoiding the extra pass on every manifest load.

## Validation plan

1. Run the registered focused tests for `trajectory-manifest-json-load`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered probe locally on Linux before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Acceptance criteria

- Behavior remains unchanged for empty/unrelated manifest inputs and fresh JSON nested fields.
- Changed-scope coverage remains at or above 95% for `trajectory_provenance.py`.
- Local registered probe shows lower `new_mean_ms` versus the synced `origin/main` baseline sample.
- PR-scoped performance CI selects and completes `trajectory-manifest-json-load` successfully.
