# Changed-scope coverage splitlines parser slice

## Linux-only constraint

This is a Python CI-tooling slice. It is locally verifiable on Linux with the focused changed-scope coverage tests, changed-scope coverage report, and the registered PR-scoped performance probe.

## Optimization

`changed_scope_coverage._parse_changed_lines()` parses the zero-context `git diff` text used by changed-scope coverage gates. The previous loop used `diff_text.split("\n")`, which materialized an extra empty trailing entry for newline-terminated diffs and routed that entry through the blank-line context handler even though it cannot affect reported changed lines.

This slice keeps parser behavior unchanged while iterating with `diff_text.splitlines()`. Blank context lines inside hunks are still preserved, while the synthetic trailing empty entry is avoided.

## Registered probe

Existing registered probe: `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.

The registry already defines focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

No new probe registration is required for this narrow parser optimization.

## Verification plan

- Focused changed-scope tests and PR-scoped registry tests.
- Changed-scope coverage command from the registered probe.
- Registered `changed-scope-coverage-diff-parser` probe locally on Linux.
- Direct old/new comparison against `HEAD:scripts/changed_scope_coverage.py` on the same synthetic diff workload.
- `git diff --check`.

## Acceptance criteria

- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Registered probe reports stable parser metrics.
- Direct old/new comparison shows lower mean elapsed time for the parser on the same workload.
