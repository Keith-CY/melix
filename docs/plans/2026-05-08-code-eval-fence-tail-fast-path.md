# Code Evaluation Fence Tail Fast Path

## Context

The code-evaluation runner extracts the final fenced code block from model
responses before compiling and sandboxing candidate Python. The PR-scoped
performance probe `code-eval-code-block-last-match-streaming` exercises large
responses with thousands of complete fenced blocks and records extraction
latency plus peak allocation.

## Slice

Optimize only the complete-tail fenced-block path in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

Many benchmark responses end with a completed code fence. In that common case,
the extractor can locate the final closing fence and the preceding opening fence
with reverse searches and skip the full-response fence count. Responses that have
non-whitespace content after the last fence still keep the existing odd-fence
fallback so an unterminated trailing block does not replace the last complete
block.

## Probe

Registered PR-scoped probe:

- `code-eval-code-block-last-match-streaming`

Focused commands are defined in `infra/perf/pr_scoped_probes.json` and include:

- code-eval extraction regression tests
- changed-scope coverage for the extractor and probe script
- `scripts/code_eval_code_block_extract_probe.py`

## Success Criteria

- Regression tests preserve empty, plaintext, multi-block, non-Python tag, and
  unterminated trailing fence behavior.
- Changed-scope coverage remains at or above 95%.
- The registered probe shows lower `elapsed_ms_mean` for the complete-tail
  multi-block response path without increasing extracted code length or changing
  parse status.
