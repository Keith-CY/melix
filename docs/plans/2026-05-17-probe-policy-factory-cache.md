# Probe policy factory cache optimization

## Slice

This Python-only performance slice keeps probe policy semantics unchanged while removing repeated `ProbePolicy` dataclass construction from the `ProbePolicy.evidence()` and `ProbePolicy.debug()` helper methods. Both helpers now return the existing immutable cached policy instances used by `ProbePolicy.from_value(...)`.

## Registered probe

The affected paths are already covered by the registered PR-scoped probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `scripts/probe_policy_noop_overhead_probe.py`

This slice extends the existing probe metrics with `evidence_policy_*` and `debug_policy_*` timings so the factory-helper cache effect is visible in local and CI PR-scoped reports. It also adds the same `0.00002 ms` absolute tolerance already used by the runtime threshold to the microsecond-level parse/read metrics so scheduler noise around unchanged sub-microsecond calls does not mask the targeted factory-helper metric.

## Verification plan

Run the focused probe-policy tests, changed-scope coverage, and the registered probe locally on Linux. Compare the registered probe output against an `origin/main` baseline captured in the same worktree before pushing.
