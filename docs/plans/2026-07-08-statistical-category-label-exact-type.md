# Statistical evidence category label exact-type slice

## Scope

This Python-only performance slice is limited to category-label aggregation in
`services/mlx-worker-python/worker/productization/statistical_evidence.py`.
The hot path receives plain `str` category labels from benchmark/evaluation rows;
this slice keeps fallback coercion for non-string values but uses an exact-type
check for the common plain-string path.

## Registered probe

The affected path is covered by the PR-scoped registered probe
`statistical-evidence-category-breakdown-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries and measures elapsed time and peak
bytes for a large category breakdown workload.

## Implementation plan

1. Preserve existing aggregation behavior, ordering, and rounded accuracy fields.
2. Replace the common category-label `isinstance(..., str)` check with
   `type(...) is str`, keeping the existing `str(value).strip()` fallback for
   subclasses or non-string labels.
3. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux; rely on PR-scoped performance CI as the merge gate.

## Success metrics

The local registered probe must preserve checksum, row count, and category count,
and should improve or hold steady `elapsed_ms_mean` without increasing
`peak_bytes_mean` beyond the registered threshold.
