# Code eval code fence tag casefold

## Goal

Reduce Python code-fence extraction overhead in `worker.engine.code_eval_runner` by replacing the import-time mixed-case `python` tag variant table with a direct lower-case comparison for the six-character fence language tag.

## Scope

This Python-only slice is limited to `extract_candidate_code(...)` and `_code_block_content_start(...)` in `services/mlx-worker-python/worker/engine/code_eval_runner.py`. It preserves extraction semantics for lowercase, uppercase, and mixed-case `python` fences, unknown language tags, empty fenced blocks, incomplete trailing fences, and the last-complete-block selection behavior.

## Registered probe

The affected path is covered by the registered PR-scoped probe `code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for this file, the focused code-eval tests, the PR-scoped performance tests, and `scripts/code_eval_code_block_extract_probe.py`.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
