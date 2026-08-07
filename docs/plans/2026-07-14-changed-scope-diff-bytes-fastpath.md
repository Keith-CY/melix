# Changed-Scope Coverage Diff Bytes Fast Path

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py` diff parsing. The changed-scope coverage command already asks Git for a zero-context diff and then parses added line numbers. Before this slice, the subprocess path decoded Git output to text and the parser immediately encoded it back to bytes for byte-prefix dispatch.

## Optimization

The slice keeps existing diff semantics while capturing Git diff stdout as bytes and allowing `_parse_changed_lines()` to accept either `str` or `bytes`. Existing string callers remain supported, while the command hot path avoids one decode/encode round trip.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`. The entry already provides focused `test_command`, `coverage_command`, and `probe_command` values covering:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

This slice updates the probe script to feed bytes when the target module advertises byte-parser support, while remaining compatible with the previous string-only implementation for base comparisons.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered local probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
