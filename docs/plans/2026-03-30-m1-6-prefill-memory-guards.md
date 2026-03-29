# M1.6 Prefill Memory Guards

## Goal

Protect Melix from oversized prefill requests and fallback paths that would exceed safe memory limits during request execution.

## Scope

- add inline prefill memory checks
- protect large-context and quadratic-fallback cases
- make guard failures observable and recoverable

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/Requests/`
- update `packages/protocol/schema/worker/v1/`

## Implementation Notes

- guard logic should run before irreversible allocation work begins
- errors should preserve request identity and be safe to surface through HTTP and XPC
- use the shared memory-accounting schema from the earlier runtime-core slices

## Verification

- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- oversized prefill requests fail with explicit guard errors
- guard behavior is integration-tested on at least one live execution path
