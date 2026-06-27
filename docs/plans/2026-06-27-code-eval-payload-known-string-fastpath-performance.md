# Code Evaluation Payload Known String Fast Path Performance

## Summary

This slice keeps the registered code-evaluation payload parser behavior unchanged while reducing allocations on the successful runner payload path. The parser already extracts the fixed payload fields from bytes before falling back to `json.loads`; this slice adds a narrow fast path for the small set of known status string values emitted by the runner.

## Scope

- Path: `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- Tests: `services/mlx-worker-python/tests/test_code_eval_runner.py`
- Registered probe: `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`

## Plan

1. Keep the byte parser and JSON fallback contract intact.
2. For unescaped JSON strings, return interned known status values directly when the payload slice matches the runner's fixed status vocabulary.
3. Fall back to UTF-8 decoding for unknown strings such as non-empty failure details.
4. Verify with the focused code-eval tests, changed-scope coverage, and the registered code-eval payload probe on Linux.

## Performance Evidence

The expected benefit is lower elapsed time and lower traced peak allocation on the registered `code-eval-payload-json-bytes` probe. The PR body records the local before/after probe numbers and CI is the merge gate for the registered probe report.
