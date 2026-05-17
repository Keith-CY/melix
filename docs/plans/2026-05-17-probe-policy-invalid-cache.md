# Probe Policy Invalid Fallback Cache

## Scope

This slice covers `services/mlx-worker-python/worker/productization/probe_policy.py` and the registered PR-scoped probe `probe-policy-noop-overhead`.

## Registered probe

The affected path is already covered by `infra/perf/pr_scoped_probes.json` through:

- focused probe-policy tests in `test_command`
- changed-scope coverage in `coverage_command`
- `scripts/probe_policy_noop_overhead_probe.py` in `probe_command`

## Optimization

`ProbePolicy.from_value()` already reuses singleton instances for exact supported modes and empty default-mode lookups. Repeated invalid mode strings still constructed a new frozen dataclass instance every call after string normalization.

This slice adds a small bounded `lru_cache` for invalid normalized fallback policies keyed by `(raw_value, default_mode)`. The behavior remains unchanged: invalid inputs still set `fallback_applied=True`, preserve the normalized source value, and respect the requested default mode.

## Verification plan

- Focused probe-policy tests from the registered probe entry.
- Changed-scope coverage command from the registered probe entry.
- Local Linux registered probe execution before push.
- GitHub Actions PR-scoped performance workflow after PR creation.

## Expected outcome

Reduce repeated invalid mode parse overhead in the registered no-op probe policy overhead path without changing supported-mode parsing or default-mode fallback semantics.
