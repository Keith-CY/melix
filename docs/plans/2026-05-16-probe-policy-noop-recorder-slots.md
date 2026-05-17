# Probe policy no-op recorder slots performance slice

## Scope

This Python-only performance slice is limited to the no-op probe policy overhead helper in `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `scripts/probe_policy_noop_overhead_probe.py`
- PR-scoped performance registry tests

## Optimization

The no-op recorder participates in disabled-probe hot paths and should stay allocation-light. This slice gives `NoOpProbeRecorder` explicit empty slots and makes the `ProbeOverheadMetrics` dataclass slotted as well. The change preserves the existing static `record` call surface while removing per-instance dictionaries from the recorder and metrics result objects.

## Validation Plan

1. Run the focused registered pytest command for `probe-policy-noop-overhead`.
2. Run changed-scope coverage through the registered coverage command.
3. Run the registered `probe-policy-noop-overhead` probe locally on Linux before and after the change and compare `no_op_recorder_call_ms_mean`, `no_op_recorder_overhead_pct`, and `threshold_passed`.
4. Require the PR-scoped performance workflow to run the registered probe in CI before merge.

## Linux Boundary

This slice is Python-only and locally verifiable on Linux. Swift/macOS runtime effects are not involved.
