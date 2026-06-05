# Changed Scope Coverage Allowlist Single-String Fast Path

## Scope

This Python-only performance slice narrows probe-specific coverage allowlist
parsing in `scripts/changed_scope_coverage.py`. Registered probes often target a
single coverage path; allowing `MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` to carry
a JSON string for that case avoids list iteration and repeated `str()` coercion
while preserving the existing JSON-list behavior.

Affected paths:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `docs/plans/2026-06-05-changed-scope-allowlist-single-string.md`

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The registry entry already provides focused
`test_command`, `coverage_command`, and `probe_command` entries for this path.
This slice extends `scripts/changed_scope_coverage_measured_probe.py` so the
registered probe script also emits `allowlist_parse_elapsed_ms_mean` and
`allowlist_parse_count` for the new single-string allowlist path.

## Implementation Plan

1. Add regression coverage for a single JSON string allowlist payload.
2. Add a minimal parser fast path that returns a one-entry `frozenset` for string
   payloads before falling back to the existing JSON-list parsing.
3. Extend the measured changed-scope probe script with a focused repeated
   single-string allowlist parse metric.
4. Run the registered focused tests, changed-scope coverage command, and the
   registered local probe on Linux.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage for touched Python lines remains at least 95%.
- The registered probe reports no regression in `elapsed_ms_mean` for the
  measured changed-scope coverage workload.
- The new `allowlist_parse_elapsed_ms_mean` metric is emitted for the
  single-string allowlist path.

## Verification Boundary

This is a Python tooling slice and is locally verifiable on Linux. It does not
change Swift runtime behavior.
