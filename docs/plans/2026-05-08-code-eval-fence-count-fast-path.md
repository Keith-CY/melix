# Code Eval Fence Count Fast Path

## Goal

Reduce redundant code-fence scanning in `extract_candidate_code(...)` while preserving the existing candidate extraction contract.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py` (existing focused coverage)

## Linux Constraint

This is a Python-only string parsing slice. It can be verified on Linux with focused pytest, changed-scope coverage, and the existing code-eval code-block extraction performance probe.

## Performance Probe

Registered scoped CI probe: `code-eval-code-block-last-match-streaming`.

Local probe command:

```bash
python scripts/code_eval_code_block_extract_probe.py
```

## Success Metrics

- Preserve output for empty responses, plain code, Python fenced blocks, non-Python fenced blocks, multiple complete blocks, and trailing unterminated blocks.
- Keep changed executable coverage at or above 95%.
- Improve or maintain `elapsed_ms_mean` and `peak_bytes_mean` for the synthetic many-block extraction probe.

## Implementation Plan

1. Count code fences once with `str.count(...)`.
2. Use the count parity to decide whether the final fence is a closing fence or an unmatched trailing opening fence.
3. Locate only the selected closing fence and matching opening fence with bounded `rfind(...)` calls.
4. Return the extracted last complete block through the existing `_code_block_content_start(...)` helper.
5. Reuse existing focused tests and the registered probe for verification.
