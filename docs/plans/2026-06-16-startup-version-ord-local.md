# Startup Update Result Tuple Record

This Python performance slice is limited to the update-check result record in `worker.productization.startup_signals`.

## Scope

- Keep startup version comparison and update-check semantics unchanged.
- Avoid broad startup signal behavior changes.
- Represent `UpdateCheckResult` as a typed tuple record instead of a frozen dataclass so repeated update-check result construction avoids frozen dataclass initialization overhead while preserving attribute access and immutable fields.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe already declares focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `scripts/startup_signals_version_probe.py`

## Verification Plan

1. Run the focused pytest command from the registered probe.
2. Run changed-scope coverage from the registered probe and keep the generated coverage artifact out of the commit.
3. Run `scripts/startup_signals_version_probe.py` locally on Linux before and after the change.
4. Use GitHub Actions PR-scoped performance as the merge gate.
