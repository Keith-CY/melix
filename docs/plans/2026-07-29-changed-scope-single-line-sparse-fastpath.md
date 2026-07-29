# Changed-scope single-line sparse source fast path

## Scope

This Python tooling performance slice is limited to `scripts/changed_scope_coverage.py` and the sparse source-line filter used when changed-scope coverage classifies a single measured line. The behavior remains identical: blank and comment-only changed lines are excluded, non-comment changed lines are reported, and out-of-range changed lines return no measurable source lines.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-singleton-range-fastpath` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries watching:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_singleton_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Plan

1. Add a focused regression test proving singleton sparse source scans stream the target source line without building the generic `remaining` set.
2. Add a single-line fast path in `_measurable_non_comment_lines(...)` before the generic sparse branch.
3. Run the registered focused test command, changed-scope coverage command, and registered local probe on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Metrics

Primary metrics are `singleton_measured_elapsed_ms_mean` and `elapsed_ms_mean` from `changed-scope-coverage-singleton-range-fastpath`. `source_read_calls_mean` must remain `0.0` because the probe monkeypatches `Path.read_text` and expects sparse source scans to stream instead of materializing source text.
