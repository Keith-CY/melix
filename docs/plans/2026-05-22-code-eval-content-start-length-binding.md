# Code eval content-start length binding

## Scope

This Python-only performance slice is limited to `_code_block_content_start(...)`
in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`code-eval-code-block-last-match-streaming` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the code eval
runner, focused tests, PR-scoped performance tests, and
`scripts/code_eval_code_block_extract_probe.py`.

## Change

Bind `len(text)` once before the whitespace-skip loop after a fenced code block
language tag is handled. This preserves extraction semantics while avoiding a
repeated global length call during whitespace-heavy fence headers.

## Verification plan

1. Run the registered focused code-eval tests locally on Linux.
2. Run changed-scope coverage for the touched source, focused tests, registry
   tests, and probe script.
3. Run the registered local Linux probe against `origin/main` and the branch.
4. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Rejected adjacent slice

During candidate selection, the OpenAI tool-registry property tuple experiment
was measured and rejected before commit because the local registered probe was
slower than `origin/main` (`441.853 ms` base versus `472.988 ms` candidate for
50,000 iterations, five samples). This PR therefore contains only the code-eval
length-binding slice.
