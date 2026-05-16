# Code Evaluation Assert Count Performance Slice

## Scope

This slice optimizes the Python code-evaluation test counter for valid test
payloads that contain many `assert` statements. The behavior stays unchanged:
valid Python tests still count `ast.Assert` nodes, syntax-error payloads still
fall back to nonblank-line counting, and no-assert payloads still skip AST
parsing.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.
This slice extends the checked-in probe script to report a valid assert-node
count metric (`assert_elapsed_ms_mean`) over a pre-parsed AST alongside the
existing syntax-error and no-assert fallback metrics.

## Verification plan

- Focused pytest for `code_eval_runner` test-count behavior and the registered
  probe smoke.
- Changed-scope coverage command from the registered probe.
- Local Linux registered probe execution before push.
- GitHub Actions PR-scoped performance workflow after PR creation.

## Expected outcome

Reduce mean elapsed time for uncached valid assert-heavy `_count_tests()` calls
by binding the AST walker, assert type, and `isinstance` lookup once in a helper
instead of resolving those globals inside each generator predicate call.
