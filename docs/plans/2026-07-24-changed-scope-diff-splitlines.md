# Changed-scope coverage diff splitlines slice

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py` diff hunk parsing in `_parse_changed_lines(...)`.

The parser already accepts byte payloads from `git diff --unified=0`. This slice keeps the byte-oriented parser and switches line iteration from an explicit `split(b"\n")` delimiter to `splitlines()`, avoiding extra empty trailing entries and letting CRLF diff payloads normalize without decoding the entire diff.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.

The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

The primary metric for this slice is `elapsed_ms_mean` from `scripts/changed_scope_coverage_parse_probe.py`.

## Verification plan

1. Keep the existing parser behavior tests as guards.
2. Add a focused CRLF byte-diff regression test for the new line iteration behavior.
3. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused changed-scope coverage tests pass.
- Changed-scope coverage for this slice stays at or above 95%.
- The registered local probe reports directionally lower `elapsed_ms_mean` compared with the pre-change baseline.
- Hosted `changed-scope-coverage-diff-parser` PR-scoped CI completes successfully before merge.
