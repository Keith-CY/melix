# Code Evaluation Sorted Payload Unrolled Fast Path

## Summary

This slice keeps the code-evaluation payload parser contract unchanged while reducing Python overhead on the registered sorted JSON payload workload. The existing parser already extracts required runner result fields from bytes before falling back to `json.loads`; this slice specializes the successful no-`compile_status`, `sort_keys=True` shape used by payload probe artifacts so the hot path avoids the generic field-token loop, value-kind branch, and generic string extraction for fixed status values.

## Scope

- Path: `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- Tests: `services/mlx-worker-python/tests/test_code_eval_runner.py`
- Registered probe: `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`

## Plan

1. Keep the byte parser and JSON fallback contract intact.
2. Route successful sorted payloads without `compile_status` to a narrow unrolled extractor for the fixed required fields and fixed status string values.
3. Preserve `None` return behavior for missing, malformed, or non-success fixed fields so `_load_payload_file` can fall back to `json.loads`.
4. Update the registered probe's focused test and coverage commands to include the new sorted payload fast-path regression tests.
5. Verify with focused tests, changed-scope coverage, and the registered code-eval payload probe on Linux.

## Performance Evidence

The expected benefit is lower elapsed time on the registered `code-eval-payload-json-bytes` probe. The PR body records local before/after probe numbers; CI remains the merge gate for the registered PR-scoped performance report.
