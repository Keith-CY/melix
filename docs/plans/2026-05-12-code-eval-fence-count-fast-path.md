# Code Evaluation Fence Count Fast Path

## Context

`worker.engine.code_eval_runner.extract_candidate_code` selects the last complete fenced code block from model responses before running executable-code evaluation. The registered PR-scoped performance probe `code-eval-code-block-last-match-streaming` covers this path with focused tests, changed-scope coverage, and a command-json probe.

The common probe shape includes many complete code blocks followed by natural-language commentary. Before this slice, that path counted every fence in the full response whenever there was trailing text after the selected closing fence, even when the selected block already had non-empty candidate code.

## Slice

This Python-only slice keeps the existing parsing contract and defers the full-response fence count unless the candidate block is empty or a trailing fenced segment makes the final fence ambiguous. The intended effect is to reduce repeated full-string scans for large responses with non-empty final code blocks and trailing commentary.

## Verification Plan

- Run the focused code-evaluation parser test and registered PR-scoped performance probe tests on Linux.
- Run changed-scope coverage for `code_eval_runner.py`, the focused tests, and the probe script.
- Run the registered `code-eval-code-block-last-match-streaming` probe locally and compare metrics against the `origin/main` baseline.
- Use GitHub Actions PR-scoped performance as the merge gate after the PR is opened.

## Expected Metrics

The probe should report lower `elapsed_ms_mean` for the synthetic multi-block response while preserving `parsed_code_block` output and extracted code length. Peak memory is expected to stay similar because the slice removes a scan rather than changing materialization behavior.
