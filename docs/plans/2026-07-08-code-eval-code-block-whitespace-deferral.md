# Code Eval Code-Block Whitespace Deferral Slice

## Scope

This Python-only performance slice is limited to `extract_candidate_code` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The code-block extractor already scans from the tail to select the final fenced
code block. This slice keeps that behavior unchanged while deferring the
full-response whitespace scan until after the no-fence plaintext fallback is
known to be needed. The common code-block path can then avoid an up-front
`str.isspace()` pass over large model responses without changing fence pairing,
fallback, stripping, or language-tag handling.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`code-eval-code-block-last-match-streaming` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` for extraction latency on a synthetic multi-block response.
- `peak_bytes_mean` for allocation guardrails.

## Verification plan

Run the registered probe locally on Linux against `origin/main` and this branch
through `scripts/pr_scoped_performance_run.py`. The CI PR-scoped performance
workflow remains the merge gate after the PR is opened.

## Acceptance criteria

- Focused code-eval extraction tests and registered probe tests pass.
- Changed-scope coverage for touched lines is at least 95%.
- Registered probe preserves `peak_bytes_mean` and shows no behavior checksum drift.
- GitHub Actions, including the PR-scoped performance report, completes green.
