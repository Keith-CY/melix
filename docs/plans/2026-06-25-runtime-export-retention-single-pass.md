# Runtime Export Retention Single-Pass Summary Slice

## Scope

This Python-only performance slice is limited to
`worker.productization.export_target_layout.build_export_retention_report()` and
its target-relative path helper. It preserves retention decisions and report
payloads while reusing the resolved target root and avoiding separate
post-processing passes for retained, cleanable, deleted, and missing file
summaries.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`runtime-export-layout-retention` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries and measures layout materialization plus retention-report aggregation.

## Implementation Plan

1. Resolve the export target root once per retention report and reuse it for
   target-relative path validation.
2. Keep `_decide_file()` behavior and decision order unchanged.
3. Replace the four derived list comprehensions in
   `build_export_retention_report()` with one summary loop that accumulates byte
   sizes, file counts, and decision payloads.
4. Run the registered focused tests, changed-scope coverage, and local Linux
   registered probe before opening the PR.
5. Use GitHub Actions PR-scoped performance as the final merge gate.

## Validation Boundary

This slice touches Python code only and is locally verifiable on Linux. It does
not claim Swift runtime effects.
