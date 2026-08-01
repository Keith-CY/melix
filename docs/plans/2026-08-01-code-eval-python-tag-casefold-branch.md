# Code evaluation Python fence tag case branch

## Scope

This Python-only performance slice is limited to `worker/engine/code_eval_runner.py`, specifically the case-insensitive `python` code-fence tag check used by `extract_candidate_code()`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Optimization slice

The case-insensitive Python fence helper now checks each character with direct equality branches instead of one-character membership tests. Exact lowercase `python` fences still use the existing `str.startswith()` fast path; this slice targets mixed-case Python fences in repeated code-block extraction without changing handling for unknown language tags.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
