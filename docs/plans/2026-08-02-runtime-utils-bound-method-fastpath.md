# Runtime utils bound-method kwarg cache target fast path

## Scope

This Python-only performance slice is limited to `worker/runtime/runtime_utils.py`, specifically repeated `callable_accepts_kwarg(...)` and `callable_kwarg_signature(...)` checks against ordinary Python bound methods.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_kwarg_cache_probe.py`

This slice uses the existing registered probe as the PR-scoped CI gate for the shared runtime-utils kwarg cache path, while the focused unit coverage exercises the bound-method-specific branch locally.

## Optimization slice

Ordinary Python bound methods have exact type `types.MethodType`. The previous cache target path discovered these through generic `getattr(..., "__func__")` and `getattr(..., "__self__")` checks. This slice adds exact `MethodType` fast paths so the hot bound-method cases can reach the shared underlying-function cache without the generic descriptor probing.

The existing generic descriptor fallback remains for custom callable objects that expose compatible `__func__`/`__self__` attributes, and unhashable callables still use the uncached fallback behavior.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
