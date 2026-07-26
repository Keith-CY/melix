# Changed-scope sparse source-line iterator performance slice

## Scope

This Python-only performance slice is limited to the sparse source-line filtering branch in `scripts/changed_scope_coverage.py`.

The behavior remains unchanged: sparse changed-line coverage still streams source files, filters blank/comment-only lines, preserves covered/missed partitioning, and leaves dense ASCII/non-ASCII handling untouched.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Slice plan

1. Keep the existing sparse branch threshold and streaming source read behavior.
2. Replace the temporary `set(line_numbers)` membership/removal state with a monotonic iterator over the already sorted sparse changed-line list, with a direct `readline()` path for leading consecutive sparse lines.
3. Add regression assertions that the sparse branch avoids `set` allocation while preserving measurable/covered/missed output and short-source handling.
4. Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.

## Metrics

Primary metric: `sparse_elapsed_ms_mean` from `scripts/changed_scope_coverage_measured_probe.py`; lower is better. The probe also reports aggregate empty-set, dense-set, allowlist, and source-read metrics to catch regressions outside this slice.
