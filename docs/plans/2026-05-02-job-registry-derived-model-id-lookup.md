# Job Registry Derived-Model ID Lookup Slice

## Goal

Reduce repeated derived-model target resolution cost in `ModelOpsJobRegistry` when callers provide a `derived_model_id`.

## Scope

- Affected path: `services/mlx-worker-python/worker/model_ops/job_registry.py`.
- Registered PR-scoped probe: `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.
- Probe support path: `scripts/job_registry_derived_model_probe.py`.

## Implementation

The existing active-derived-model row cache avoids rebuilding the active row list, but each repeated `resolve_derived_model_target(derived_model_id=...)` call still scans the cached rows. This slice adds a cache-derived `derived_model_id -> active row` lookup that is invalidated together with the row cache. Manifest-path-only lookups keep the existing row scan semantics.

The probe now resolves an older active model ID (`melix-dev-derived-0001`) so the registered metric exercises the cached-ID path instead of mostly measuring the newest-row fast case.

## Validation Plan

Run the registered probe's focused local Linux commands:

1. Focused tests from `job-registry-derived-model-single-pass`.
2. Changed-scope coverage from `job-registry-derived-model-single-pass`.
3. Registered probe command from `job-registry-derived-model-single-pass`.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows lower `resolve_target_elapsed_ms_mean` for repeated `derived_model_id` resolution.
