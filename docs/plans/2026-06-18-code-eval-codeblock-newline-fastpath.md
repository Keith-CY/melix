# Code Evaluation Code Block Newline Fast Path

## Scope

This Python-only performance slice is limited to `extract_candidate_code(...)` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The parser already targets the last fenced code block and recognizes lowercase
and mixed-case `python` language tags. After stripping that tag, the common
model-output shape has a single newline before the code body. This slice handles
that one-newline case directly before falling back to the existing generic
whitespace loop, preserving behavior for spaces, tabs, CRLF-style whitespace,
and non-`python` tags.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-code-block-last-match-streaming` in
`infra/perf/pr_scoped_probes.json`. The registry entry has focused
`test_command`, `coverage_command`, and `probe_command` values and measures
last-block extraction elapsed time, peak traced bytes, block count, and extracted
character count.

## Verification plan

- Run the registered focused `test_command` locally on Linux.
- Run the registered changed-scope `coverage_command` locally on Linux.
- Run the registered `probe_command` locally on Linux and compare against the
  current `origin/main` worktree baseline.
- Use GitHub Actions PR-scoped performance as the merge gate after opening the
  PR.

## Expected outcome

Avoid one `str.isspace()` loop iteration for the common ` ```python\n... ` code
block form while leaving fallback whitespace semantics unchanged. The expected
local signal is a lower `elapsed_ms_mean` in
`code-eval-code-block-last-match-streaming` with unchanged `peak_bytes_mean`,
`block_count`, and `extracted_chars_mean`.
