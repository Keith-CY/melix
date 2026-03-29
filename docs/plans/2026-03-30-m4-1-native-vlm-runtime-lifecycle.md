# M4.1 Native VLM Runtime Lifecycle

## Goal

Introduce a native VLM runtime lifecycle with explicit prefill, decode, and runtime-state handling rather than a contract-only path.

## Scope

- define VLM runtime lifecycle entrypoints
- add lifecycle metrics and state transitions
- preserve multimodal request normalization while runtime depth lands

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/registry.py`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- the VLM lifecycle should align with the shared scheduling and cache model
- keep OCR-specific behavior out of the generic VLM runtime contract
- avoid a second control-plane path just for vision execution

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- VLM execution has an explicit runtime lifecycle with observable state transitions
- live VLM requests no longer depend only on deterministic placeholder behavior
