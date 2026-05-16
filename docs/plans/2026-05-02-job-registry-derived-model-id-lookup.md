# Job Registry Derived-Model ID Lookup Slice

## Goal

Reduce repeated derived-model target resolution cost in `ModelOpsJobRegistry` when callers provide a `derived_model_id`.

## Scope

- Affected path: `services/mlx-worker-python/worker/model_ops/job_registry.py`.
- Registered PR-scoped probe: `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.
- Probe support path: `scripts/job_registry_derived_model_probe.py`.

## Implementation

The existing active-derived-model row cache avoids rebuilding the active row list, and the first derived-model ID slice added a cache-derived `derived_model_id -> active row` lookup. This follow-up slice keeps the resolved activation manifest path inside the cached lookup row so repeated `resolve_derived_model_target(derived_model_id=...)` calls do not re-run `Path(...).expanduser().resolve()` while constructing the response payload. Manifest-path-only lookups keep the existing normalized manifest-path cache semantics.

The probe resolves an older active model ID (`melix-dev-derived-0001`) so the registered metric exercises the cached-ID path instead of mostly measuring the newest-row fast case. The direct lookup and manifest-path lookup timing metrics use a 0.01 ms absolute noise floor because their optimized warm-cache values are intentionally in the low microsecond range. `restore_elapsed_ms_mean` remains the larger end-to-end restore signal, with a 5 ms absolute warning floor so filesystem and scheduler variance from the temp restore workload does not override the warm lookup signals.

## Validation Plan

Run the registered probe's focused local Linux commands:

1. Focused tests from `job-registry-derived-model-single-pass`.
2. Changed-scope coverage from `job-registry-derived-model-single-pass`.
3. Registered probe command from `job-registry-derived-model-single-pass`.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows lower `resolve_target_elapsed_ms_mean` for repeated `derived_model_id` resolution.
