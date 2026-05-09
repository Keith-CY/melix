# Evaluation Answer Normalization Fast Path

## Goal

Reduce redundant answer-normalization work in `EvaluationCore._normalized_answer` for free-text answers by avoiding numeric and option extractor scans unless the stripped answer shape can actually be accepted as numeric or single-option output.

## Scope

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only verification path

This is a Python-only slice and can be verified on Linux with focused pytest, changed-scope coverage, and a base-vs-head PR-scoped performance probe.

## Probe definition

Add `evaluation-answer-normalization-fast-path` to the PR-scoped performance registry. The probe repeatedly normalizes a mix of free-text, numeric, and option answers, while structurally counting extractor calls for free-text answers.

Success metrics:

- Preserve normalized output checksum and numeric/option behavior.
- Reduce `numeric_extract_calls_mean` and `option_extract_calls_mean` for the synthetic mostly-free-text workload.
- Keep changed executable coverage at or above 95%.

## Verification commands

- Focused pytest for evaluation helper behavior and PR-scoped registry selection/smoke tests.
- Changed-scope coverage using `scripts/changed_scope_coverage.py`.
- Local `scripts/pr_scoped_performance_run.py` run for `evaluation-answer-normalization-fast-path` against `origin/main` and head.
- `git diff --check`.
