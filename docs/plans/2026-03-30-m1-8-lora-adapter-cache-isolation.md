# M1.8 LoRA Adapter Cache Isolation

## Goal

Prevent cache reuse across incompatible adapter sets by binding dispatch, cache, and restore identity to the active LoRA adapter configuration.

## Scope

- extend cache identity with adapter-set information
- isolate dispatch handles and restore metadata by adapter configuration
- preserve operator-visible adapter workflows

## Files

- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- update `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/DiskCacheStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- update `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

## Implementation Notes

- adapter identity should compose cleanly with parser mode, reasoning profile, and quant profile
- control-plane worker loads should forward `melix.adapter_set_hash` from model settings into worker model specs
- runtime handles should remain stable for a loaded adapter set and visibly differ across incompatible adapter sets
- cache restore must fail safely with `failed_precondition` when adapter identity is incompatible
- unload must purge only the matching adapter scope instead of evicting every cache entry for the base model ID

## Verification

- `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testRuntimeRegistryIsolatesDispatchHandlesAndCacheScopesByAdapterSet`
- `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testBoundarySnapshotRestoreRejectsMismatchedAdapterScope`
- `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testUnloadModelPurgesOnlyMatchingAdapterScope`
- `swift test --package-path services/control-plane-swift --filter PythonBridgeWorkerClientTests/bootstrapWorkerPreparationCarriesAdapterSetHashIntoWorkerModelSpecs`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeWorkerBackedModelLoadForwardsAdapterSetHashFromModelSettings`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/startChatLazyTextLoadsPreserveAdapterSetHashInWorkerRequests`

## Acceptance

- adapter switches do not reuse incompatible cache assets
- adapter-aware worker loads preserve adapter metadata from the control-plane model catalog
- restore requests reject mismatched adapter scopes with a structured `failed_precondition`
- unloading one adapter-scoped model instance does not purge surviving adapter scopes for the same base model
