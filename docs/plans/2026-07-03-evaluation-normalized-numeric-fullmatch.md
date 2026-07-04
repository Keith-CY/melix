# Evaluation Normalized Numeric Fullmatch Slice

## Scope

This slice targets the Python evaluation answer normalization hot path in
`services/mlx-worker-python/worker/engine/evaluation_core.py`.

The affected behavior is already covered by the registered PR-scoped performance
probe `evaluation-answer-normalization-fast-path` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Optimization

`EvaluationCore._normalized_answer(...)` receives an already stripped string from
`_strip_wrapping(...)`. Its numeric fast path previously delegated to
`EvaluationCore._looks_like_numeric(stripped)`, which calls `value.strip()` again
before applying `_NUMERIC_TOKEN_PATTERN.fullmatch(...)`.

This slice keeps the same guard and normalization behavior, but applies the
compiled numeric token pattern directly to the already stripped value. The change
avoids the redundant second strip and static-method call for numeric-looking
answers while leaving `_looks_like_numeric(...)` unchanged for other call sites.

## Behavior Invariants

- Empty values still bypass numeric normalization.
- Single-letter option normalization still wins before numeric checks.
- Numeric literals still use the same `_NUMERIC_TOKEN_PATTERN` acceptance rule.
- Numeric output formatting still goes through `_normalized_numeric_literal(...)`.
- Non-numeric free text still follows the existing whitespace and case handling.

## Validation Plan

Run the registered probe's focused test command and changed-scope coverage command
on Linux, then run the registered probe against `origin/main` and this branch with
`scripts/pr_scoped_performance_run.py`.

## Local Results

- Focused tests: `19 passed`.
- Changed-scope coverage: `TOTAL 1 0 100%`.
- Registered probe `evaluation-answer-normalization-fast-path`:
  - `elapsed_ms_mean`: base `131.749007`, head `124.262952`, delta `-7.486055 ms` (`-5.68%`).
  - `answer_match_elapsed_ms_mean`: base `78.985713`, head `77.617546`, delta `-1.368167 ms` (`-1.73%`).
  - `numeric_extract_calls_mean`: base `0.0`, head `0.0`.
  - `option_extract_calls_mean`: base `0.0`, head `0.0`.

Commands and measured results are also included in the PR body.
