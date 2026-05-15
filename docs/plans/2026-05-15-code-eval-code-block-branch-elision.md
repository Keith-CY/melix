# Code Evaluation Code Block Branch Elision

## Scope

This Python-only slice keeps the code evaluation candidate extraction semantics
unchanged while removing a redundant nested `opening >= 0` guard from the hot
path in `extract_candidate_code`.

## Affected Paths

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`code-eval-code-block-last-match-streaming` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and measures
last-code-block extraction over a synthetic response containing 2,500 fenced
blocks.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and local
probe on Linux before pushing. GitHub Actions remain the merge gate for the
full PR-scoped performance report.

## Expected Outcome

The branch removes one always-true conditional from the last-match extraction
path. The primary metric is probe `elapsed_ms_mean`; because the edit is very
small, stable parity with no probe regression is acceptable, with any speedup
reported from the local and CI probe output.
