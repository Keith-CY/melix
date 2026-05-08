# Code Evaluation Test Count Cache Plan

## Goal

Reduce repeated parent-side test counting overhead in the code-evaluation runner when the same benchmark or evaluation test payload is reused across multiple candidate executions.

## Scope

This slice is intentionally limited to the Python code-evaluation test-count helper. It does not change sandbox execution, candidate extraction, stdio truncation, payload parsing, or generated protocol artifacts.

## Implementation

- Add a bounded in-process cache around `worker.engine.code_eval_runner._count_tests`.
- Preserve the existing behavior for valid Python tests, syntax-error fallback text, and no-assert fallback text.
- Keep the existing nonblank-line fallback semantics unchanged.
- Update the registered PR-scoped performance probe command to run the cache regression test with the code-eval count-tests probe.

## Probe

Registered probe: `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

Primary metrics:

- `elapsed_ms_mean`: lower is better.
- `peak_bytes_mean`: lower is better.

Success criteria:

- Focused code-evaluation and PR-scoped performance tests pass.
- Changed-scope coverage for touched Python paths is at least 95 percent.
- The registered local probe shows a clear elapsed-time reduction without increasing peak memory.
