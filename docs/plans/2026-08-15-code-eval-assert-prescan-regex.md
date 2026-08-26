# Code evaluation assert prescan regex fast path

This Python performance slice is limited to `worker.engine.code_eval_runner._may_contain_assert_statement`.

## Registered performance probe

The affected code path is already covered by the registered PR-scoped probe `code-eval-assert-mention-prescan` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_assert_prescan_regex.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_assert_prescan_probe.py`

## Slice

Replace the Python-level repeated `str.find()` assert-token scan with a compiled regular expression that preserves the same statement-boundary rules: start-of-input or newline/semicolon/colon after optional horizontal spacing, followed by `assert` and a non-identifier follower.

## 2026-08-15 follow-up: direct regex-search return

This follow-up keeps the same registered probe and narrows to the compiled-regex
fast path introduced for `_may_contain_assert_statement()`. The helper still
accepts the legacy `_isalnum` test hook for compatibility with existing focused
regression tests, but no longer binds it to a throwaway local because the
compiled regular expression owns the identifier-boundary decision. This removes
one Python bytecode operation from every assert-prescan call while preserving the
same statement-boundary semantics.

Verification remains the same: focused code-eval assert tests, changed-scope
coverage for the registered probe, the local Linux registered probe, and the
GitHub Actions PR-scoped performance report before merge.

## 2026-08-26 follow-up: absent token containment guard

This follow-up keeps the same registered `code-eval-assert-mention-prescan`
probe and adds one exact string containment guard before invoking the compiled
regex. Payloads that do not contain the token `assert` cannot contain an assert
statement, so they can return `False` without paying regex-search setup cost.
Payloads that do contain the token still use the compiled regex as the source of
truth for statement-boundary and identifier-follower semantics.

The slice is Python-only and locally Linux-verifiable. The expected local benefit
is visible on no-assert fallback workloads while preserving the assert-mention
probe behavior and keeping CI's PR-scoped registered report as the merge gate.
