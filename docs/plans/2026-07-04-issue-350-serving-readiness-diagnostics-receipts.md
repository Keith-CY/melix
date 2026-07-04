# Issue 350 Serving Readiness Diagnostics Receipts

## Goal

Add a narrow diagnostics-only serving readiness receipt so `effective-config.json`
can preserve model identity, budget, readiness, progress, and dependency-policy
facts without starting or probing a real serving backend.

## Scope

- Preserve an explicit `serving_readiness` receipt when a caller already supplies
  one in diagnostics `effective_config`.
- Derive a stable `serving_readiness` receipt from namespaced execution metadata
  when all required readiness fields are present.
- Keep partial metadata out of the derived receipt so diagnostics do not imply a
  complete readiness decision when upstream code has not emitted one yet.
- Document the receipt fields and interpretation in the serving diagnostics
  evidence runbook.

## Out Of Scope

- Changing serving admission, model loading, health polling, or dependency
  resolution behavior.
- Detecting package versions or known-incompatible dependency ranges in this
  slice.
- Adding Swift control-plane metadata emission. This diagnostics slice only
  establishes the artifact contract for later producers.
- Claiming acceleration or readiness improvements.

## Receipt Contract

`effective-config.json` may contain:

```json
{
  "serving_readiness": {
    "requested_model_id": "operator requested identity",
    "effective_model_id": "backend/runtime identity selected for serving",
    "identity_source": "explicit_request | cached_catalog | backend_health | fallback",
    "budget_source": "explicit_request | profile_default | runtime_default",
    "health_ready_at": "ISO-8601 timestamp or empty string when not ready",
    "progress_source": "backend_health | cached_status | not_ready",
    "dependency_policy_status": "allowed | blocked | unknown"
  }
}
```

When deriving from metadata, the diagnostics writer reads the following keys
from the same metadata sources already used for serving profile receipts:

- `melix.serving.readiness.requested_model_id`
- `melix.serving.readiness.effective_model_id`
- `melix.serving.readiness.identity_source`
- `melix.serving.readiness.budget_source`
- `melix.serving.readiness.health_ready_at`
- `melix.serving.readiness.progress_source`
- `melix.serving.readiness.dependency_policy_status`

All seven fields are required for a derived receipt. This keeps partial upstream
state observable in its original metadata location while preventing the
top-level `serving_readiness` object from looking complete before it is.

## Implementation Plan

1. Add focused Python diagnostics tests:
   - explicit `serving_readiness` survives stable JSON serialization;
   - complete readiness audit metadata derives `serving_readiness`;
   - incomplete readiness audit metadata is left in-place without a derived
     receipt.
2. Implement readiness field mapping and required-field validation beside the
   existing serving profile receipt derivation.
3. Update `docs/runbooks/serving-diagnostics-evidence.md` with the readiness
   receipt fields, metadata keys, and diagnostics-only scope.
4. Keep bundle serialization within the existing serving diagnostics queue
   performance gate by using compact stable JSON writes for structured bundle
   files and avoiding unnecessary nested directory creation work.
5. Verify focused tests, changed-scope coverage, PR-scoped performance, and
   whitespace.

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json`
- `UV_PYTHON=3.12 uv run python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `git diff --check`

## Metrics

This slice adds only small dictionary scans over existing diagnostics metadata
sources during bundle writing. It does not add runtime probes, model loading,
network calls, dependency imports, or token-path instrumentation. Success is a
stable receipt contract in generated diagnostics artifacts with 95% or higher
changed-line coverage for the touched Python scope and a PR-scoped performance
report with no serving diagnostics regressions.
