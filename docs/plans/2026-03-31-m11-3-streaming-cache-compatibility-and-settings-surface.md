# M11.3 Streaming Cache Compatibility And Settings Surface

## Goal

Expose the cache-policy and settings surface needed to run disk-streamed sessions without hidden compatibility rules.

## Scope

- define cache compatibility under disk streaming
- expose cache memory and directory controls
- expose memory-aware cache and multimodal-cache budget controls
- keep cache policy visible after settings resolution

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `services/mlx-text-worker-swift/Sources/Core/`

## Implementation Notes

- Settings should explain when cache tiers are disabled, limited, or downgraded.
- Memory-aware policy should show tracked-byte budgets, RAM-percentage budgets, and the explicit disable path.
- Directory and size controls must remain deterministic and inspectable.
- UI should show effective policy, not only requested settings.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Cache compatibility rules under disk streaming are operator-visible and test-covered.
- Effective cache settings can be inspected after merges and overrides.
- Multimodal cache budgets and memory-aware policy remain visible after settings resolution.
