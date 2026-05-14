# Evaluation final-result text fallback tail scan

## Scope

This Python-only performance slice targets heuristic text extraction in
`services/mlx-worker-python/worker/productization/evaluation_final_result.py`.
When no answer prefix or fenced block is present, the fallback only needs the
last nonblank output line. The previous implementation materialized paragraph
and line lists before returning that value.

## Probe coverage

Register `evaluation-final-result-text-fallback-tail-scan` in
`infra/perf/pr_scoped_probes.json` for this slice. The registered probe includes:

- focused pytest coverage for text fallback behavior and probe selection,
- changed-scope coverage for the implementation, tests, registry, and probe
  script,
- `scripts/evaluation_text_fallback_probe.py`, which compares the legacy
  paragraph-list fallback with the optimized tail scan over a synthetic
  multi-paragraph response.

## Success criteria

- Behavior remains equivalent for answer-prefix, fenced-text, and fallback text
  extraction cases.
- Changed-scope coverage remains at or above the repository 95% requirement.
- The registered local Linux probe reports lower `elapsed_ms_mean` and lower
  `peak_bytes_mean` versus the legacy fallback, with matching checksum.
- PR-scoped performance CI selects and completes the registered probe before
  merge.

## Validation boundary

This slice is Python-only and fully locally verifiable on Linux. GitHub Actions
remains the merge gate for the PR-scoped registered probe report.
