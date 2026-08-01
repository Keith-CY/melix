# Closure audit no-match probe-source fast path

This Python-only performance slice is limited to `worker.productization.closure_audit._scan_probe_source_file(...)`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `closure-audit-probe-source-short-circuit` in `infra/perf/pr_scoped_probes.json`. The probe watches the closure-audit implementation, focused tests, PR-scoped performance dispatch, and PR-scoped performance tests, and defines focused `test_command`, `coverage_command`, and `probe_command` entries.

## Slice

Synthetic closure-audit repositories can contain many text files that do not mention any required probe metric names. For those no-match files, `_scan_probe_source_file(...)` should record the file as scanned and then return without rebuilding the pending-probe list or looking up every pending probe bucket.

This keeps behavior identical for matching files, duplicate-file suppression, and pending probe saturation while removing per-file list/dict work from the no-match path.

## Verification

Run the registered focused test command, changed-scope coverage command, and registered closure-audit probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe result.
