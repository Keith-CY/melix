# Evaluation Final Result Extraction Streaming

## Goal

Reduce transient list materialization and repeated suffix JSON parse attempts in final-result heuristic extraction while preserving the existing extraction contract.

## Scope

Touched files:

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `docs/plans/2026-05-07-evaluation-final-result-extraction-streaming.md`

## Linux-only constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit synthetic extraction probe.

## Performance probe definition

Run a synthetic probe that repeatedly extracts JSON from a long response containing many non-final JSON-looking fragments and one final balanced JSON payload. Compare current branch behavior against a detached `origin/main` worktree.

Metrics:

- `elapsed_ms_mean` for repeated extraction calls; lower is better.
- `peak_bytes_mean` from `tracemalloc`; lower is better.
- `parse_calls_mean` by monkeypatching `_parses_json`; lower is better while preserving identical extracted payloads.

## Success metrics

- Focused extraction tests pass.
- Changed executable scope coverage is at least 95%.
- Synthetic probe shows lower parse-call count and no behavioral drift. Lower elapsed time and/or peak memory is expected but can be noisy for small string helpers.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py::<focused nodes>`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py::<focused nodes> && ... changed_scope_coverage.py ...`
- Local base-vs-head extraction probe using `/tmp/evaluation_final_result_extraction_probe.py`.
- `git diff --check`

## PR-scoped CI

The existing `evaluation-final-result-materialization-streaming` PR-scoped probe watches both the production file and focused test file for this Python path, so the PR-scoped performance workflow will select the evaluation-final-result scope without adding a new registry entry for this narrow extraction helper slice.
