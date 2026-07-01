# Startup Version Terminal Equal Return Performance Slice

## Scope

This Python-only performance slice is limited to
`worker.productization.startup_signals.compare_versions()` and its inlined
normalization comparator. It preserves version ordering semantics while avoiding
one extra empty-part loop when both normalized version streams reach the end
after an equal numeric segment.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for startup
signals and the version probe script.

## Expected Behavior

- Equal normalized versions still compare as equal, including `v` prefix and
  suffix cases.
- Versions with trailing zero parts such as `2.10` versus `2.10.0.0` still
  compare as equal.
- Differing numeric segments still short-circuit before later segments.

## Verification Plan

Run the registered focused startup-signals tests, changed-scope coverage, and
the registered `startup-signals-version-compare-single-pass` probe locally on
Linux before pushing. GitHub Actions PR-scoped performance remains the final
merge gate.
