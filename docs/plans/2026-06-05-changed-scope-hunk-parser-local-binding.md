# Changed-scope hunk parser local binding slice

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py`, specifically the unified-diff hunk-start parser used by changed-scope coverage.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization

`_parse_changed_lines()` calls the hunk-start digit parser once for each hunk header in the zero-context diff. This slice keeps the existing parsing semantics but binds `_parse_hunk_new_start_from_digit` into a local variable before the hot loop and switches the digit scan from a `range(...)` iterator to a direct index loop with a local `ord` binding.

The change avoids repeated global helper lookup and a small iterator allocation on every parsed hunk header while preserving malformed-header behavior and all changed-line outputs.

## Verification

Run the registered focused tests, registered changed-scope coverage command, `git diff --check`, and the registered `changed-scope-coverage-diff-parser` probe locally on Linux. PR-scoped performance CI remains the merge gate after the pull request opens.
