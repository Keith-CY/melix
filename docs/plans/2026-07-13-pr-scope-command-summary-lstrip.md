# PR Scoped Command Summary Lstrip Fast Path

## Scope

This Python-only performance slice is limited to `_summarize_command(...)` in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`. The helper is used by PR-scoped performance command logging and is exercised by the scope matcher probe workload.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries, and the probe reports `command_summary_ms_mean` for repeated command summary rendering.

## Optimization

The previous helper trimmed leading and first-line trailing whitespace with Python-level character loops. This slice switches those trims to `str.lstrip()` and `str.rstrip()` while preserving the existing first-line/newline behavior, empty-command fallback, and max-length truncation rules.

## Verification Plan

Run locally on Linux before PR:

1. Focused `test_pr_scoped_performance.py` command-summary and registered-probe tests.
2. Changed-scope coverage using the registered coverage command for `pr-scoped-performance-scope-matcher`.
3. Registered probe locally with `pr-scoped-performance-scope-matcher` against `origin/main` and the candidate branch.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
