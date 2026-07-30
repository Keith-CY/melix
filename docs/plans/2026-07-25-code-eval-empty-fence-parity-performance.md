# Code Evaluation Empty Fence Parity Performance Slice

## Scope

This Python-only performance slice is limited to `extract_candidate_code(...)` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The parser keeps the existing behavior for empty predictions, plain-text code,
lowercase and mixed-case Python fenced code blocks, empty fenced blocks,
unterminated trailing fences, and trailing commentary after the final complete
code block.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`code-eval-code-block-last-match-streaming` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Change

When the final fenced block is empty, `extract_candidate_code(...)` now checks
whether the immediately preceding pair of fences is already balanced before
falling back to the full prefix `count()` parity scan. This preserves the
unterminated trailing-fence guard while avoiding the full prefix scan on the
registered probe's common empty trailing block path.

## Verification Plan

1. Run the registered focused pytest selection locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered local probe against `origin/main` and the candidate branch.
4. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Local Probe Result

Local Linux registered probe comparison before PR:

- base `elapsed_ms_mean=0.039001560903021266`, `empty_fallback_elapsed_ms_mean=0.16923870758286544`, `peak_bytes_mean=198.0`
- head `elapsed_ms_mean=0.03634769070361342`, `empty_fallback_elapsed_ms_mean=0.07705417062555041`, `peak_bytes_mean=198.0`
- elapsed delta `-0.0026538701994078445 ms` (~6.80% lower)
- empty fallback delta `-0.09218453695731403 ms` (~54.47% lower)
- peak delta `0 bytes`
