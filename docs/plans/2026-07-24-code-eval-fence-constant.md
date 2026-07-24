# Code Evaluation Fence Constant Reuse

## Scope

This Python-only performance slice is limited to `extract_candidate_code()` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The affected path is covered by the registered PR-scoped performance probe
`code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for the code evaluation runner, focused tests, and
`scripts/code_eval_code_block_extract_probe.py`.

## Optimization

Reuse a module-level code fence constant instead of recreating the literal inside
every `extract_candidate_code()` call. The parsing behavior remains unchanged for
plain text, normal code blocks, mixed-case `python` tags, empty trailing blocks,
and unmatched trailing fences.

## Verification Plan

1. Keep the focused code-block extraction test as the behavior guard.
2. Run the registered focused test command for `code-eval-code-block-last-match-streaming`.
3. Run the registered changed-scope coverage command.
4. Run `scripts/code_eval_code_block_extract_probe.py` locally on Linux before and after the change.
5. Use GitHub Actions PR-scoped performance as the final merge gate.
