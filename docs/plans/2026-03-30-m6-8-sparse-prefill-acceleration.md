# M6.8 Sparse Prefill Acceleration

## Goal

Add an experimental sparse-prefill acceleration mode behind a feature flag while preserving system-prompt safety and operator observability.

## Scope

- add sparse-prefill runtime policy
- preserve protected prompt regions
- expose measurable gain and rollback signals

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- feature gating should make the mode easy to disable globally or per model
- prompt-protection rules must be explicit and test-covered
- acceleration metrics should distinguish accepted skips from rejected opportunities

## Verification

- `make swift-test`
- `make integration-test`
- touched-scope benchmark command for sparse prefill

## Acceptance

- sparse-prefill acceleration can be enabled and disabled explicitly
- protected prompt regions remain correct and test-covered
