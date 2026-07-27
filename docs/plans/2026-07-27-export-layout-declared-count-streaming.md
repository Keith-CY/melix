# Runtime Export Layout Declared Count Streaming

This Python-only performance slice is limited to `worker.productization.export_target_layout._build_export_report()`.

## Probe coverage

The affected path is already covered by the registered PR-scoped performance probe `runtime-export-layout-retention` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the export target layout module, retention tests, PR-scoped performance registry tests, and `scripts/runtime_export_layout_retention_probe.py`.

## Optimization slice

`_build_export_report()` previously materialized a temporary flattened `file_rows` list only to compute `declared_file_count`, even though the immediately preceding retention pass had already counted the same declared file rows. This slice reuses the retention report's `retention_decision_count` for `declared_file_count` and avoids the extra flattening pass. Export report semantics are unchanged because both values are derived from the same `_file_sections()` rows.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered `runtime-export-layout-retention` probe locally on Linux. GitHub Actions PR-scoped performance remains the merge gate after push.

## Success criteria

- Focused export target layout retention tests pass.
- Changed-scope coverage for the touched Python/test/probe scope stays at or above the repository threshold.
- The registered probe reports directionally improved or neutral runtime export layout retention metrics.
- GitHub Actions and the registered PR-scoped performance report complete successfully before merge.
