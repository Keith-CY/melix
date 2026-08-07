# Report evidence probe phase clean-string fast path

## Scope

This Python-only performance slice is limited to `_probe_phases()` in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The function scans PR-scoped performance report probe phase buckets and builds a
set of normalized phase names for release matrix rules. Registered probe rows use
plain, already-trimmed string phase names on the hot path.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The registered entry watches the report
evidence gate module, focused tests, this probe script, and related plan files,
and includes focused `test_command`, `coverage_command`, and `probe_command`
entries.

## Optimization

Keep behavior equivalent while checking exact string phase values against the
accumulator before normalization. Registered probe summaries repeat the same
clean phase names across baseline/candidate buckets, so duplicate clean strings
can skip the `strip()` path after their first occurrence. Edge-whitespace strings
still trim, and non-string phase values still pass through the existing
`str(...).strip()` fallback.

## Verification Plan

Run, on Linux:

1. Focused report evidence gate regression tests for probe phase extraction and
   PR-scoped probe selection.
2. Changed-scope coverage command from the registered probe entry.
3. The registered `report-evidence-gate-run-kind-set-membership` probe locally.
4. GitHub Actions PR-scoped performance workflow after opening the PR.

## Acceptance

Accept only if the focused tests and changed-scope coverage pass, the local
registered probe shows an improved or neutral `probe_phases_elapsed_ms_mean` and
overall `elapsed_ms_mean`, and the PR-scoped performance workflow completes
green.
