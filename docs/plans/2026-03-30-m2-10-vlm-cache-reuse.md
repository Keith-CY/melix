# M2.10 VLM Cache Reuse

## Goal

Extend the shared cache model into VLM execution so vision requests can participate in prefix reuse, restore, and paged-cache accounting.

## Scope

- adapt VLM execution to the paged-cache model
- align image-aware cache identity with the text-runtime cache identity
- keep reuse semantics correct when image payloads differ

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- image hashing should compose with cache identity rather than bypass it
- VLM reuse must remain correctness-first when multimodal input structure changes
- metrics should distinguish vision reuse from text-only reuse

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- VLM requests can participate in shared cache and restore flows
- multimodal cache identity is explicit and test-covered
