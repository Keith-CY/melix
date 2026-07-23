# Code evaluation empty fence prefix count

## Scope

This Python-only performance slice is limited to `extract_candidate_code()` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The affected path is covered by the registered PR-scoped performance probe
`code-eval-code-block-last-match-streaming` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the code
evaluation runner, focused tests, and `scripts/code_eval_code_block_extract_probe.py`.

## Optimization

When the last fence pair extracts an empty candidate, the parser must decide
whether that empty block is a real final block or whether the final fence is an
unmatched trailing fence after a previous complete answer. The current fallback
counts all fences in the full response. This slice narrows that parity count to
the prefix before the candidate opening fence, because the final candidate pair
adds exactly two fences and does not affect parity.

The behavior remains unchanged for empty final blocks, unmatched trailing fences,
plain text, and normal non-empty last code blocks. The optimization avoids
rescanning large trailing text after the candidate fence pair on the empty-block
fallback path.

## Verification Plan

1. Add a focused regression assertion that records the `str.count` range used by
   the empty-candidate fallback.
2. Run the registered focused test command for `code-eval-code-block-last-match-streaming`.
3. Run the registered changed-scope coverage command.
4. Run the registered `scripts/code_eval_code_block_extract_probe.py` locally on Linux.
5. Use GitHub Actions PR-scoped performance as the final merge gate.
