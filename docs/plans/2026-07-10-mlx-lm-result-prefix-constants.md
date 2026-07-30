# MLX-LM Structured Result Prefix Constants

## Scope

This Python-only performance slice is limited to the MLX-LM subprocess structured
result extractor in `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`.
The extractor already scans from the tail of stdout with `str.rfind()` instead
of materializing `splitlines()`. This slice removes per-call construction of the
newline and carriage-return result marker strings by precomputing them at module
load time.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`mlx-lm-structured-result-tail-parse` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_lm_result_tail_probe.py`

The probe reports `elapsed_ms_mean` and `peak_bytes_mean` for repeated extraction
from a large noisy stdout payload.

## Verification Plan

Run the registered focused tests, changed-scope coverage command,
`git diff --check`, and the registered `mlx-lm-structured-result-tail-parse`
probe locally on Linux before opening the PR. GitHub Actions PR-scoped
performance remains the merge gate for the registered probe report.

## Success Metrics

- Preserve structured-result extraction for terminal newline and carriage-return
  prefixes, embedded prefix noise, and missing-result behavior.
- Keep changed-scope coverage at or above 95 percent for the touched Python
  scope.
- The registered probe should show a non-regressing `elapsed_ms_mean` and
  `peak_bytes_mean` versus `origin/main`; expected benefit is small because the
  existing tail scan is already the dominant optimization.