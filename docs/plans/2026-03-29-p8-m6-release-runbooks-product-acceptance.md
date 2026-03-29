# P8-M6 Release Runbooks and Product Acceptance

## Goal

Leave Phase 8 with a final product-level metrics report and a repository-discoverable runbook set for install, upgrade, rollback, diagnostics, training, recovery, and release acceptance.

## Scope

- add a final Phase 8 metrics report entrypoint
- aggregate cold boot, operator action, install, training, benchmark, and recovery evidence into one machine-readable report
- document install, upgrade, rollback, diagnostics, training, and recovery from the repository entrypoints
- make the final product acceptance flow discoverable from `README.md` and `docs/README.md`

## Files

- create `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- create `services/mlx-worker-python/tests/test_acceptance_metrics.py`
- create `scripts/phase8_runtime_probes.py`
- create `scripts/phase8_metrics_report.py`
- create `docs/runbooks/phase-8-product-acceptance.md`
- update `scripts/phase8_release_gate.py`
- update `Makefile`
- update `README.md`
- update `docs/README.md`
- update `docs/runbooks/README.md`

## Implementation Notes

- keep the final metrics report machine-readable and deterministic
- reuse the checked-in release gate policy for benchmark and recovery interpretation
- define one operator-facing latency based on a backend-backed registry refresh workflow
- do not reintroduce manual release steps into the acceptance runbook

## Verification

- `make py-test`
- `make integration-test`
- `make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"`
- `make phase8-metrics PHASE8_METRICS_ARGS="--json"`
- `make py-coverage`
- `git diff --check`

## Acceptance

- the repository exposes a final Phase 8 metrics report with non-`N/A` product numbers
- install, upgrade, rollback, diagnostics, training, and recovery steps are documented from one product acceptance runbook
- the final report includes cold boot, operator action, install success, training duration, adapter publish, benchmark regression, and recovery success
