# Benchmark evaluation matrix label cache optimization

## Goal

Reduce repeated label construction in `benchmark_evaluation_report` while preserving the benchmark/evaluation report schema and metric names.

## Scope

- Cache matrix-style benchmark probe labels within `_collect_benchmark_probe_metrics()` for repeated request rows that share `suite_id`, `context_length`, `generation_length`, `batch_size`, and `concurrency_level`.
- Keep non-matrix benchmark context labels uncached because those rows are commonly unique in the PR-scoped probe workload.
- Do not change exported report rows, warning semantics, metric direction handling, or sticky comment formatting.

## Probe

The affected path is covered by the registered PR-scoped probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`, including focused pytest, changed-scope coverage, and the local Linux probe command.

## Success Criteria

- Focused benchmark-evaluation report tests pass.
- Changed-scope coverage remains at least 95%.
- Registered probe reports a non-regressing `elapsed_ms_mean` and unchanged `row_count`.
