# Probe policy overhead sampler local binding slice

This slice is limited to the Python probe-policy overhead measurement path covered by the registered PR-scoped probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`.

## Registered probe

The existing registry entry covers:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/probe_policy_noop_overhead_probe.py`

The probe has focused `test_command`, `coverage_command`, and `probe_command` entries. No registry change is required for this sampler-only optimization.

## Optimization

Bind `time.perf_counter`, `range`, the measurement list append method, and the callable under measurement to locals in `_sample_call_ms`. This removes repeated global/bound lookup overhead from the million-iteration sampler loop without changing the measured callable sequence or result shape.

## Verification

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. The PR-scoped performance GitHub Actions workflow remains the merge gate for the registered probe report.

## 2026-07-27 Follow-up: Reused sampler ranges

The next sampler-only slice keeps the same registered `probe-policy-noop-overhead`
probe and reuses the `range(samples)` plus `range(iterations)` objects across
sample loops inside `_sample_call_ms`. The callable order, iteration count, and
reported metrics remain unchanged, but the measurement harness avoids rebuilding
range objects for every sample of every measured probe-policy path.

Success is accepted only if the registered focused tests, changed-scope coverage,
and local Linux probe pass with lower or non-regressing call means, and CI reports
the registered PR-scoped probe successfully before merge.
