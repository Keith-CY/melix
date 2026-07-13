# Changed Scope Diff Header Prefix Slice

## Scope

This Python performance slice is limited to `scripts/changed_scope_coverage.py` diff-header detection inside `_parse_changed_lines()`.

## Registered Probe

The affected path is already covered by the registered PR-scoped `changed-scope-coverage-diff-parser` probe in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the parser and synthetic diff workload.

## Plan

1. Keep diff parsing semantics unchanged for git diff headers, hunk lines, additions, deletions, and context lines.
2. Replace the byte-prefix helper call on candidate `diff --git` lines with a direct fixed-length bytes slice comparison.
3. Run the registered focused tests, changed-scope coverage command, and the registered parser probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance report as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from `scripts/changed_scope_coverage_parse_probe.py`; lower is better.

Secondary metrics: `elapsed_ms_min`, `line_count`, `file_count`, and `changed_line_count` ensure the synthetic parser workload and output cardinality remain stable.

## Boundary

This slice changes Python tooling only and is fully locally verifiable on Linux. Swift runtime effects are not in scope.
