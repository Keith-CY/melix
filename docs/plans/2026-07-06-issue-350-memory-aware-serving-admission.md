# Issue 350 Memory-Aware Serving Admission Receipt Plan

## Goal

Add a memory-aware serving admission receipt that records the dry-run context
and batch fit decision before a request is dispatched to worker load or decode.

## Scope

This slice covers the latest executable #350 watch note: make serving admission
memory-aware before load/decode and expose the effective values in diagnostics.

In scope:

- Add a deterministic control-plane dry-run estimator for serving context and
  batch fit.
- Emit namespaced `melix.serving.memory_admission.*` metadata on worker request
  execution metadata.
- Materialize a top-level `serving_memory_admission` receipt in
  `effective-config.json` when diagnostics receives complete metadata.
- Preserve explicit operator context overrides when metadata supplies one.
- Step down conservative defaults only when memory telemetry is present and the
  dry-run estimate cannot fit with headroom.
- Document the receipt contract and safety limits.

Out of scope:

- Adding new protobuf fields for runtime context length.
- Changing model loader, sampler, KV allocation, or worker decode behavior.
- Claiming a measured load-time OOM reduction.
- Running model discovery, health checks, or memory probes during diagnostics
  bundle writing.

## Architecture

The Swift control plane remains the admission source of truth. A new
`ServingMemoryAdmissionReceipt` in `ModelCapabilityReceipts.swift` computes a
dry-run result from model metadata, requested context, requested batch, and
optional detected memory telemetry. `RequestCoordinator` attaches the receipt
metadata beside the existing serving capability and resolved acceleration
metadata. The Python diagnostics writer stays passive and only converts a
complete metadata set into a stable top-level receipt.

The first estimator is intentionally conservative and deterministic:

- repository default context cap: `8192` tokens for non-explicit long-context
  sessions;
- minimum memory step-down context: `2048` tokens;
- default reserved headroom: `2147483648` bytes when memory telemetry is known;
- default KV estimate: `262144` bytes per token per active batch lane unless
  model metadata supplies `melix.serving.memory.bytes_per_token`;
- model resident estimate: `model.settings.memoryBudgetBytes`, overridden by
  `melix.serving.memory.estimated_model_bytes` when present.

Unknown memory telemetry must not invent precision. In that case the receipt
records `memory_telemetry_source=unknown`, `memory_headroom_bytes=0`, and does
not perform memory-based step-down beyond the repository default context cap.

## Receipt Contract

The diagnostics top-level receipt is:

```json
{
  "serving_memory_admission": {
    "schema_version": "melix.serving_memory_admission.v1",
    "requested_context": 131072,
    "effective_context": 4096,
    "requested_batch": 4,
    "effective_batch": 1,
    "memory_headroom_bytes": 2147483648,
    "estimated_active_bytes": 2147483648,
    "memory_telemetry_source": "detected",
    "admission_reason": "memory_step_down",
    "fits_memory": true
  }
}
```

Required metadata keys:

- `melix.serving.memory_admission.schema_version`
- `melix.serving.memory_admission.requested_context`
- `melix.serving.memory_admission.effective_context`
- `melix.serving.memory_admission.requested_batch`
- `melix.serving.memory_admission.effective_batch`
- `melix.serving.memory_admission.memory_headroom_bytes`
- `melix.serving.memory_admission.estimated_active_bytes`
- `melix.serving.memory_admission.memory_telemetry_source`
- `melix.serving.memory_admission.admission_reason`
- `melix.serving.memory_admission.fits_memory`

If any required key is missing or an integer/boolean field is invalid,
diagnostics leaves the original metadata in place and does not synthesize a
partial receipt.

## Test Plan

Follow TDD:

1. Add Swift RED tests for the memory receipt resolver:
   - long-context model without explicit context caps to `8192`;
   - explicit requested context is preserved when memory telemetry is unknown;
   - detected low memory steps down context and batch only when needed;
   - audit metadata includes stable `melix.serving.memory_admission.*` keys.
2. Add a RequestCoordinator RED assertion proving worker request metadata
   includes the memory admission receipt before prefill dispatch.
3. Add Python diagnostics RED tests proving complete metadata materializes the
   top-level receipt and invalid integer/boolean metadata is skipped.
4. Implement the Swift receipt resolver and RequestCoordinator wiring.
5. Implement passive Python receipt derivation.
6. Update this plan and the serving diagnostics runbook with final evidence.

Focused verification:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter ModelCatalogTests/memoryAwareServingAdmissionReceipt
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/gatewaySpeculativeDefaultsPopulateWorkerAccelerationWhenModelDefaultsAreUnspecified
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
```

Full pre-PR verification:

```bash
make bootstrap
make proto
git diff --check
git diff --cached --check
.githooks/pre-commit
```

## Performance And Metrics

Observability mode: debug diagnostics. Runtime overhead is bounded to integer
parsing, a small deterministic candidate loop, and metadata string emission
before existing worker dispatch. No model load, memory probe, optional runtime
import, sampler change, or worker-side allocation is introduced.

Success metrics:

- Focused Swift model-catalog and request-coordinator tests pass.
- Focused Python serving diagnostics tests pass.
- Changed-scope Python coverage remains at least 95 percent when measurable.
- PR-scoped performance report status is `ok` with regressions `0` and
  verification failures `0`.

## Local Verification Evidence

Completed on 2026-07-06:

```bash
make bootstrap
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter ModelCatalogTests/memoryAwareServingAdmissionReceiptCapsDefaultsAndPreservesExplicitOverrides
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests/gatewaySpeculativeDefaultsPopulateWorkerAccelerationWhenModelDefaultsAreUnspecified
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py
make proto
git diff --check
```

Results:

- `make bootstrap` passed.
- Swift model-catalog focused test passed.
- Swift request-coordinator focused test passed.
- Python serving diagnostics suite passed: `67 passed`.
- Changed-scope Python coverage passed: `TOTAL 58 0 100%`.
- `make proto` passed with no generated artifact changes.
- `git diff --check` passed.
