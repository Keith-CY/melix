# Runtime Export Manifest Probe Scandir Slice

## Scope

This Python-only performance slice is limited to fixture discovery in the runtime
export target manifest validation/reporting path:

- `scripts/runtime_export_manifest_validation_probe.py`
- `scripts/export_target_manifest_metrics_report.py`

The behavior stays the same: discover direct child fixture directories containing
`export-target-manifest.json`, sort the resulting manifest paths, and validate the
same checked-in fixture set.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`runtime-export-manifest-validation` in `infra/perf/pr_scoped_probes.json`. The
entry already includes focused `test_command`, `coverage_command`, and
`probe_command` values for the manifest contract tests, PR-scoped selector tests,
report script, and JSON-emitting probe script. No registry change is required for
this slice.

## Optimization

Replace `Path.glob("*/export-target-manifest.json")` fixture discovery with a
single `os.scandir()` pass over the fixture root, and hoist stable loop values in
the validation probe. The implementation keeps `follow_symlinks=False` for
directory filtering, only materializes candidate manifest paths that exist as
files, sorts the final path list to preserve the previous deterministic order,
and reuses the fixture count plus validator local binding inside the measured
validation loop.

## Verification plan

Run the registered commands locally on Linux:

1. Focused regression tests from the registered `test_command`.
2. Changed-scope coverage from the registered `coverage_command`.
3. Registered `probe_command` for local base/head metrics.

GitHub Actions PR-scoped performance remains the merge gate for the registered
probe report.

## Acceptance criteria

- Regression tests prove the scripts no longer use `Path.glob()` for default
  fixture discovery.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe reports neutral-to-improved manifest validation probe
  latency and no schema errors.
