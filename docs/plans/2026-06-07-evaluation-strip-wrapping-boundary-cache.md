# Evaluation answer wrapping boundary cache

## Scope

This Python-only performance slice is limited to `EvaluationCore._strip_wrapping(...)`, which is called by the registered answer normalization path in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Slice plan

1. Preserve answer normalization semantics for empty, quoted, backtick-wrapped, trailing-period, numeric, option, ASCII, and Unicode answers.
2. Cache the current first/last boundary characters inside `_strip_wrapping(...)` so common unwrapped free-text answers avoid repeated string indexing and `endswith(...)` dispatch.
3. Extend the focused normalization test with a mixed backtick/quote/trailing-period case to protect the staged boundary updates.
4. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from `evaluation-answer-normalization-fast-path` (lower is better). Guard metrics: `numeric_extract_calls_mean` and `option_extract_calls_mean` must stay at `0.0` for free-text normalization.
