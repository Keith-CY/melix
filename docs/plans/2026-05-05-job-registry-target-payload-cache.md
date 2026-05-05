# Job Registry Target Payload Cache Slice

## Goal

Reduce repeated derived-model target payload construction overhead in `ModelOpsJobRegistry.resolve_derived_model_target` after the active derived-model lookup has already been resolved.

## Scope

- Affected path: `services/mlx-worker-python/worker/model_ops/job_registry.py`.
- Behavior remains unchanged: callers still receive a fresh mutable payload dict on every lookup.
- Registered PR-scoped probe: `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.
- Probe support path: `scripts/job_registry_derived_model_probe.py`.

## Implementation

The derived-model lookup cache already stores the matching active row and the resolved activation manifest path. This slice extends the same lookup entry with a cached target payload so repeated `derived_model_id` or manifest-path lookups avoid rebuilding the same string-normalized response fields and runtime-mode value. The public method returns a shallow copy of the cached payload to preserve caller mutation isolation.

## Validation Plan

Run the registered probe's focused local Linux commands:

1. Focused tests from `job-registry-derived-model-single-pass`.
2. Changed-scope coverage from `job-registry-derived-model-single-pass`.
3. Registered probe command from `job-registry-derived-model-single-pass`.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows a lower or stable `resolve_target_elapsed_ms_mean` for repeated derived-model target resolution, without regressing restore metrics beyond the probe warning threshold.
