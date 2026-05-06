# Code evaluation code-block extraction streaming plan

## Goal

Avoid materializing every fenced code block when `extract_candidate_code(...)` only needs the final candidate block emitted by a model response.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_code_block_extract_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only verification path

This is a Python-only worker change and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local probe.

## Performance probe

Register `code-eval-code-block-last-match-streaming` in the PR-scoped performance registry. The probe builds a synthetic response with thousands of fenced code blocks and measures `extract_candidate_code(...)` elapsed time and peak traced allocation while asserting that the last block is still selected.

## Success metrics

- Focused tests pass.
- Changed executable scope coverage is at least 95%.
- Probe preserves `parsed_code_block` semantics and concrete metrics are reported for elapsed time and peak bytes.
