# M4.3 Image Hash Cache Identity

## Goal

Carry multimodal fingerprint hashes through the control-plane cache bridge so image-aware cache identity survives session hydration, cache observability, and restore metadata serialization.

## Scope

- expose `fingerprint_hash` on control-plane cache and restore protocol types
- preserve worker-provided multimodal scope identity in control-plane cache metadata
- hydrate session branch head cache keys with multimodal fingerprint-aware metadata

## Files

- update `packages/protocol/schema/controlplane/v1/control_plane.proto`
- regenerate `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- regenerate `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- regenerate `packages/protocol/descriptors/melix.pb`
- update `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- update `services/control-plane-swift/Sources/Snapshots/CacheRestoreMetadata.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/SnapshotStoreTests.swift`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

## Implementation Notes

- worker multimodal hashing already existed on the Python runtime path; this slice bridges that fingerprint into control-plane protocol surfaces
- `CacheKey.fingerprint_hash` is now preserved in session head cache keys, hot-prefix metadata, block tables, and restore boundaries
- `CacheScopeKey.multimodal_adapter_hash` and `scope_id` now survive worker-to-control-plane cache snapshot conversion

## Verification

- `make proto`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'SnapshotStoreTests|RequestCoordinatorTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/Snapshots/CacheRestoreMetadata.swift services/control-plane-swift/Tests/ControlPlaneTests/SnapshotStoreTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- `git diff --check`

## Acceptance

- control-plane cache snapshots retain multimodal fingerprint and scope identity from worker cache stats
- session graph hydration preserves worker cache fingerprints on branch heads
- restore plans serialize fingerprint-aware block tables and restore boundaries without dropping multimodal cache identity

## Metrics

- Swift changed-line coverage: `100.00% (50/50)`
- Runtime or performance metrics: `N/A` for this slice because the change is protocol and metadata propagation rather than a new measurable runtime path
