# Statistical evidence bootstrap local bindings

This Python-only performance slice is limited to `worker.productization.statistical_evidence._paired_bootstrap_interval()`.

## Scope

- Preserve paired bootstrap percentile interval behavior and emitted evidence payloads.
- Keep the existing single in-place sort behavior for bootstrap replicates.
- Bind hot builtins used by the replicate list-comprehension (`sum` and `range`) once in the function before the bootstrap loop.

## Registered probe

The affected path is covered by the registered PR-scoped probe `statistical-evidence-bootstrap-single-sort` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_bootstrap_probe.py`

## Verification plan

1. Run the focused statistical evidence tests and PR-scoped registry selection tests.
2. Run changed-scope coverage through the registered probe coverage command.
3. Run the registered bootstrap probe locally on Linux and compare pre/post metrics, especially `elapsed_ms_mean` and `peak_bytes_mean`.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
