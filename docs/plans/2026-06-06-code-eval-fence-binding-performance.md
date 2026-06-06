# Code Evaluation Fence Literal Binding Performance Slice

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
`infra/perf/pr_scoped_probes.json`. The registry entry already includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Change

Bind the Markdown code-fence literal once inside `extract_candidate_code(...)`
and reuse that local binding for the `rfind()` and fallback `count()` calls.
This keeps the same last-complete-code-block parsing semantics while avoiding
repeated literal lookups along the hot extraction path.

## Verification Plan

1. Run the registered focused pytest selection locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered local probe comparing `origin/main` and the candidate
   branch.
4. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Local Probe Result

Local Linux registered probe comparison before PR:

- base `elapsed_ms_mean=0.040521246514150074`, `peak_bytes_mean=245.0`
- head `elapsed_ms_mean=0.03357989979641778`, `peak_bytes_mean=245.0`
- elapsed delta `-0.006941346717732291 ms` (~17.13% lower)
- peak delta `0 bytes`
