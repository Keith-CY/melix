# Trajectory manifest str binding

## Scope

This Python-only performance slice is limited to
`worker.trajectory_provenance._trajectory_provenance_from_snapshot_manifest()`.
The manifest loader already reads JSON as bytes, skips nested copy work on the
registered load path, and binds `manifest.get`; this slice reduces repeated
built-in lookup overhead for required string coercions while preserving field
selection and default behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The
registry entry already has focused `test_command`, `coverage_command`, and
`probe_command` entries for this trajectory provenance loader path, so no probe
registry change is required.

## Implementation Plan

1. Keep the existing JSON byte-loading and `copy_nested=False` hot-path behavior.
2. Bind `str` at module import and localize it inside the manifest-to-provenance
   helper before the repeated manifest string coercions.
3. Preserve all public return shapes, optional fields, default values, and
   non-agentic manifest handling.
4. Run the registered focused tests, changed-scope coverage, and registered
   local probe on Linux. PR-scoped performance CI remains the merge gate.

## Expected Metrics Direction

The registered probe should keep `component_count` stable and reduce
`new_mean_ms` for `trajectory-manifest-json-load` without increasing
`new_peak_bytes_mean`.
