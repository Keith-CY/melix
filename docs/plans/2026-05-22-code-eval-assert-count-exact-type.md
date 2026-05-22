# Code-eval assert counter exact-type fast path

## Scope

This Python-only performance slice keeps code-eval test counting behavior unchanged while reducing the hot-path cost of counting direct `assert` AST nodes in `worker.engine.code_eval_runner._count_assert_nodes()`.

## Registered performance probe

Affected path coverage is registered in `infra/perf/pr_scoped_probes.json` under `code-eval-count-tests-line-scan`.

This slice extends that registered probe metadata to track `assert_elapsed_ms_mean` from `scripts/code_eval_count_tests_probe.py`, because the optimization targets assert-node traversal rather than the syntax-error/no-assert fallback line counter. The probe keeps focused `test_command`, `coverage_command`, and `probe_command` entries.

## Implementation

Use exact `type(node) is ast.Assert` checks for assert nodes while retaining `isinstance(...)` for statement-container traversal. Python AST parse output uses exact `ast.Assert` nodes, so this avoids repeated general-purpose `isinstance` work on the direct assert-counting path without changing nested assert discovery.

## Verification plan

- Run the registered focused test command for `code-eval-count-tests-line-scan` locally on Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run the registered probe locally on Linux and compare `assert_elapsed_ms_mean` with `origin/main` samples.
- Use the PR-scoped performance workflow as the merge gate after opening the PR.

## Success criteria

- Focused behavior tests pass, including a regression guard that direct assert checks do not call the injected assert `isinstance` path.
- Changed-scope coverage for touched files remains at or above the repository threshold.
- Registered probe reports stable non-regression or improvement for `assert_elapsed_ms_mean`, with unchanged assert/fallback counts.
