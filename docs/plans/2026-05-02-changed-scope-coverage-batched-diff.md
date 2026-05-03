# Changed-Scope Coverage Batched Diff Optimization Plan

## Goal

Reduce redundant subprocess work in `scripts/changed_scope_coverage.py` by parsing one batched `git diff --unified=0` output for the requested files instead of spawning a separate `git diff` process for each path.

## Linux-Only Constraint

This change is limited to a repository Python helper script plus focused tests, so it can be fully verified on Linux without relying on macOS or Swift-only execution paths.

## Touched Files

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`

## Optimization Slice

- Replace the per-path `_changed_lines(...)` subprocess pattern with one batched diff collection step for the requested paths.
- Parse the combined unified diff into a `{rel_path -> changed_line_set}` mapping while preserving current changed-line semantics for additions, deletions, and context lines.
- Keep output format and pass/fail behavior unchanged.
- Add focused regression tests that lock the combined-diff parser behavior and prove the implementation only invokes `git diff` once for multiple paths.

## Performance Probe

Run a local synthetic probe that:

- creates a temporary git repository with many changed Python files,
- executes the current baseline implementation and the branch implementation on the same workload,
- reports mean elapsed milliseconds and subprocess call count.

The success signal is identical coverage semantics with one `git diff` subprocess instead of one per file and lower elapsed time on the synthetic workload.

## Success Metrics

- Script output remains behaviorally identical for the covered test cases.
- Changed executable scope coverage is at least 95%.
- The local synthetic probe shows materially lower elapsed time and reduces diff subprocess count from `N` to `1` for an `N`-file workload.

## Verification Commands

- `pytest -q tests/test_changed_scope_coverage.py`
- `coverage run -m pytest -q tests/test_changed_scope_coverage.py && coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py tests/test_changed_scope_coverage.py`
- `git diff --check`
- Local synthetic batched-diff timing probe comparing the current branch implementation against an inline baseline implementation on the same temporary repository workload
