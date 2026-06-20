# Code eval code-block stripped-slice extraction

This Python-only performance slice is limited to `extract_candidate_code(...)` in `worker.engine.code_eval_runner`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Slice

Avoid constructing a temporary code-block substring and then calling `.strip()` on it. Instead, compute stripped slice boundaries first and allocate only the final extracted candidate string.

## Verification plan

1. Run the focused code-eval extraction tests from the registered probe.
2. Run the changed-scope coverage command from the registered probe.
3. Run the registered probe locally on Linux and compare this branch against `origin/main` with `scripts/pr_scoped_performance_run.py`.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Code block extraction behavior remains unchanged for empty, tagged, case-insensitive, trailing-commentary, and multi-block responses.
- Changed-scope coverage for the touched Python path remains at or above the repository threshold.
- The registered local and CI probes show non-regression for peak bytes, with elapsed time reported as informational.
