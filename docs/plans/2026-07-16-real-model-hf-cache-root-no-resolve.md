# Real model HF cache root resolve elision

## Scope

This Python-only performance slice keeps the real-model support HF cache fallback behavior unchanged while avoiding an unnecessary `Path.resolve()` call when `HOME` is already absolute. The affected code path is `scripts/real_model_support.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `real-model-support-hf-cache-latest-snapshot` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `hf_cache_elapsed_ms_mean`
- `hf_cache_peak_bytes_mean`
- `weight_scan_elapsed_ms_mean`

## Implementation plan

1. Add a regression test proving absolute `HOME` cache-root construction does not need `Path.resolve()`.
2. Keep relative `HOME` behavior conservative by resolving only relative expanded paths.
3. Run the registered focused tests, changed-scope coverage, and registered local probe on Linux.
4. Use the PR-scoped performance workflow as the merge gate.

## Verification notes

Local Linux verification is sufficient for this Python slice. GitHub Actions remains the source of truth for the registered PR-scoped performance comparison before merge.
