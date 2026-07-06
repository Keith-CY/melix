# Runtime export diagnostic common-phrase fast path

## Scope

This Python-only performance slice is limited to common runtime export diagnostic
failure classification in
`services/mlx-worker-python/worker/productization/export_target_diagnostics.py`.

The affected path is covered by the registered PR-scoped performance probe
`runtime-export-diagnostic-parser` in `infra/perf/pr_scoped_probes.json`. That
probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and reports both aggregate diagnostic report latency and
`diagnosis_matching_elapsed_ms_mean` for parser classification.

## Optimization

`_diagnoses_from_excerpt()` already lowercases each candidate log line and gates
unrelated text with diagnosis markers. This slice adds a narrow fast phrase table
for the most common literal runtime failure phrases emitted by fixtures and
runtime smoke checks. When a phrase maps directly to a known diagnosis pattern,
the parser emits the same diagnosis payload without walking the regex expression
table for that line. Lines that do not hit the phrase table keep the existing
marker and regex behavior unchanged.

## Verification

Local Linux validation for this slice must include:

1. Focused export diagnostic tests from the registered probe.
2. Changed-scope coverage from the registered probe.
3. The registered `runtime-export-diagnostic-parser` probe command with local
   metrics compared against the pre-change baseline.

GitHub Actions PR-scoped performance remains the final registered probe
validation and merge gate.

## Success Criteria

- Focused tests pass locally on Linux.
- Changed-scope coverage for touched files is at least 95%.
- The registered probe reports lower `diagnosis_matching_elapsed_ms_mean` with no
  behavior regressions in diagnostic parser coverage.
