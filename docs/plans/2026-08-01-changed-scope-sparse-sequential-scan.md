# Changed-scope Sparse Sequential Scan

## Summary

This performance slice keeps `scripts/changed_scope_coverage.py` focused on the changed-line coverage hot path. The measured path already has PR-scoped probe coverage through `changed-scope-coverage-measured-set-filter`; this slice narrows the probe's sparse case to a multi-line sparse changed set and avoids constructing a temporary `set` when the changed line list is already sorted.

## Scope

- Optimize only `_measurable_non_comment_lines()` for sorted sparse line-number lists with three to eight entries.
- Preserve the existing set-based fallback for unsorted sparse inputs.
- Keep dense source scanning, diff parsing, allowlist parsing, and coverage aggregation behavior unchanged.

## Probe

Registered probe: `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries. This slice updates `scripts/changed_scope_coverage_measured_probe.py` so `sparse_elapsed_ms_mean` measures a five-line sparse target list rather than the already-special-cased two-line path.

## Success Criteria

- Focused changed-scope coverage tests pass.
- Changed-scope coverage for the touched files remains at least 95%.
- The registered measured probe shows the sparse path improving or remaining within a clearly explained boundary while preserving behavior.
