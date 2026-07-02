# Runtime kwarg function fast-path performance

## Context

`worker.runtime.runtime_utils.callable_accepts_kwarg()` is on text runtime hot paths that repeatedly test whether a backend helper accepts optional keyword arguments. The affected path is already covered by the registered PR-scoped probe `runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`, including focused test, coverage, and probe commands.

## Slice

Add a narrow fast path for plain Python functions in `callable_accepts_kwarg()` so repeated hot-path calls can consult the cached signature directly without re-running the generic callable cache-target normalization.

## Validation

- Focused unit tests from the registered probe entry.
- Changed-scope coverage from the registered probe entry.
- Registered local probe `scripts/runtime_utils_kwarg_cache_probe.py` on Linux.
- PR-scoped CI performance validation after push.

## Boundaries

This slice only changes Python runtime utility dispatch for plain functions. Bound methods and other callable objects continue to use the generic `callable_kwarg_signature()` path.
