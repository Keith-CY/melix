# Code-eval nonblank splitline binding

## Scope

This Python-only performance slice touches `services/mlx-worker-python/worker/engine/code_eval_runner.py` for the large-test fallback in `_count_nonblank_test_lines()`.

## Hypothesis

The registered `code-eval-test-count-nonblank-streaming` probe exercises a large generated test body that uses the streaming nonblank-line counter rather than the small-input `splitlines()` path. The hot loop currently resolves the module-level splitline boundary string on every character and combines the `line_has_content` guard with the whitespace test in one expression. Binding the boundary string once and nesting the whitespace check under the false `line_has_content` branch should reduce repeated global lookup and avoid calling `isspace()` after a line has already been counted, while preserving full Python splitline compatibility.

## Registered probe coverage

`infra/perf/pr_scoped_probes.json` already registers `code-eval-test-count-nonblank-streaming` for `code_eval_runner.py` with focused `test_command`, `coverage_command`, and `probe_command` entries. No registry change is needed for this slice.

## Verification plan

- Run the registered focused test command for `code-eval-test-count-nonblank-streaming`.
- Run the registered changed-scope coverage command for the same probe.
- Run `scripts/code_eval_test_count_probe.py` locally on Linux and compare base vs head with `scripts/pr_scoped_performance_run.py`.
- Run `git diff --check` before committing.

## Success criteria

- Existing nonblank counting semantics remain identical for normal and uncommon splitline boundaries.
- Changed-scope coverage is at least 95% for the touched files.
- Local and CI registered probes show a directionally clear elapsed-time improvement.
