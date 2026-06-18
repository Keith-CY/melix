# PR-scoped command summary trim pass

## Slice

Optimize `_summarize_command()` in the PR-scoped performance runner without changing its public output. The hot path is the CI heartbeat command summary and the registered scope matcher probe measures it with `command_summary_ms_mean`.

## Registered probe

The affected path is already covered by the registered `pr-scoped-performance-scope-matcher` probe in `infra/perf/pr_scoped_probes.json`. That probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/pr_scoped_performance.py` and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`.

## Implementation plan

- Preserve the existing compact single-line summary semantics.
- Keep the existing single whole-command `strip()` before first-line selection so trailing blank heredoc lines are eliminated.
- Replace tuple-producing `partition("\n")` with a direct newline index lookup so the summary path does not allocate the unused remaining payload.
- Keep the behavior tests under `test_command_summary_keeps_ci_heartbeats_compact` as the regression guard.

## Verification plan

- Run the focused scope matcher tests.
- Run changed-scope coverage for `pr_scoped_performance.py` and `test_pr_scoped_performance.py` via the registered coverage command.
- Run the registered scope matcher probe locally on Linux and compare `command_summary_ms_mean` against the pre-change baseline.
