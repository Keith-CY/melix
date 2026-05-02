# PR-Scoped Performance Report Single-Render Optimization Plan

## Goal

Remove redundant scoped-performance report rendering in the GitHub Actions report job while preserving the exact sticky-comment payload and uploaded report artifacts.

## Constraints

- Linux-only cron execution; no macOS-local validation is available.
- Keep the change small and limited to the PR-scoped performance reporting path.
- Preserve existing PR comment marker, markdown body format, and artifact filenames.

## Touched Files

- `.github/workflows/pr-scoped-performance.yml`
- `scripts/pr_scoped_performance_report.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization Hypothesis

The report workflow currently invokes `scripts/pr_scoped_performance_report.py` twice during the report step:
1. once to emit the terminal report and write `artifacts/report/report.{json,md}`
2. again to rebuild the markdown report only to add the sticky-comment marker

If the script can optionally write the sticky-comment body into the output directory during the first invocation, the workflow can avoid the second render pass and still reuse identical markdown content.

## Probe / Measurement

- Local explicit measurement: compare a double-render loop vs a single-render loop over the report script on synthetic scope/results fixtures and record elapsed milliseconds.
- CI validation path: existing `pr-scoped-performance` workflow remains the scoped CI probe for this path because the optimized code lives directly in that workflow/reporting surface.

## Success Metrics

- Sticky-comment output remains byte-for-byte identical to the previous script behavior.
- Focused tests for the reporting path pass.
- Changed-scope automated coverage is at least 95% for touched executable Python lines.
- Local measurement shows the single-render path performs less report-generation work than the double-render baseline.

## Verification Commands

- Focused pytest for `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- Changed-scope coverage measurement for `scripts/pr_scoped_performance_report.py`
- Local synthetic timing probe for report generation
- `git diff --check`
