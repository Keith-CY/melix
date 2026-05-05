# Runtime Utils Kwarg Signature Cache

## Goal

Reduce repeated `inspect.signature(...)` work in the Python worker runtime helper that checks whether backend callables accept optional keyword arguments.

## Scope

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_kwarg_cache_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only Constraint

This is a Python-only slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and a base-vs-head PR-scoped performance probe.

## Performance Probe

Register `runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`.

Metrics:

- `elapsed_ms_mean`: lower is better
- `inspect_signature_calls_mean`: lower is better; expected to drop from one call per helper invocation to one call per `(callable, keyword)` pair

## Success Criteria

- Focused runtime utility tests pass.
- PR-scoped probe registry tests for this probe pass.
- Changed-scope coverage is at least 95%.
- Local base-vs-head probe shows fewer `inspect.signature` calls and lower elapsed time.
