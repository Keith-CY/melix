# Trajectory manifest get binding

## Scope

This Python-only performance slice is limited to
`worker.trajectory_provenance._trajectory_provenance_from_snapshot_manifest()`.
The manifest loader already avoids text decoding and nested copy work on the
registered hot path; this slice reduces repeated mapping method lookup overhead
while preserving the same field selection, defaults, and optional provenance
handling.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The
registry defines focused `test_command`, `coverage_command`, and `probe_command`
entries for the trajectory provenance loader path.

## Implementation Plan

1. Keep the existing JSON byte-loading and `copy_nested=False` behavior.
2. Bind `manifest.get` once in the manifest-to-provenance helper and reuse that
   binding for the initial agentic-manifest guard plus required and optional
   field extraction.
3. Preserve the public return shape and the existing behavior for non-agentic or
   empty manifests.
4. Run the registered focused tests, changed-scope coverage, and registered
   local probe on Linux. PR-scoped performance CI remains the merge gate.

## Expected Metrics Direction

The registered probe should keep `component_count` stable and reduce
`new_mean_ms` / improve `speedup` for `trajectory-manifest-json-load` without
increasing `new_peak_bytes_mean`.
