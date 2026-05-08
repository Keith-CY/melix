# PR-scoped force-all context gate

## Problem

Melix PR-scoped performance reports intentionally run every registered probe when shared performance infrastructure changes. That keeps broad visibility, but it also lets unrelated context-probe noise block small optimization PRs that touched shared registry or scoped-performance tests only to add their own probe coverage.

Recent sibling optimization PRs selected roughly eighty probes after touching `infra/perf/pr_scoped_probes.json` or `services/mlx-worker-python/tests/test_pr_scoped_performance.py`. Their direct probes were healthy, while unrelated probes produced small or stale regressions. The report summary still marked the whole pull request as `regression`, which made the merge gate too broad.

## Approach

Keep force-all visibility, but separate direct gate probes from context probes:

1. `build_scope_report(...)` still selects every probe when force-all paths are touched.
2. The scope also records `matched_probe_ids`, computed from non-context-only changed files.
3. `build_performance_report(...)` uses direct matches for the blocking gate when force-all is true.
4. Regression or verification failures from non-direct probes remain visible as context counts and row metadata, but do not set the top-level status to `regression`.
5. If no direct match exists in a force-all report, preserve the conservative legacy behavior by gating all selected probes.

## Context-only trigger paths

The broad fan-out paths below should not make every probe direct by themselves:

- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

Other PR-scoped performance implementation paths can still match the probes that explicitly watch them, so real infrastructure regressions remain gated.

## Verification

- Add failing tests that prove force-all reports track direct matches separately from context probes.
- Add a regression-report test proving context-only regressions are visible but do not fail the top-level gate.
- Run focused `test_pr_scoped_performance.py` coverage for the changed report/scope behavior.
