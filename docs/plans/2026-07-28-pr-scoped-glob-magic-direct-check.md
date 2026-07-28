# PR-Scoped Glob Magic Direct Check Slice

## Scope

This Python-only performance slice is limited to glob magic detection in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

The hot helper `_glob_has_magic()` is used while loading and matching the
PR-scoped performance probe registry. Registry watch globs are checked many
times during scope selection, and the helper only needs to detect the fnmatch
magic characters `*`, `?`, and `[`. This slice replaces the generator-based
`any()` scan with direct string membership checks while preserving the same
fnmatch magic semantics.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

The probe reports `build_scope_report_ms_mean` for large changed-file scope
matching plus unchanged guard metrics for selected probe count and command
summarization.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `pr-scoped-performance-scope-matcher` probe locally on Linux
before opening the PR. GitHub Actions PR-scoped performance remains the merge
gate for the registered probe report.
