# P5-M1 Capability and Settings Model

## Goal

Introduce typed capability metadata, per-model settings, and explicit worker route classes so the control plane can distinguish text, embeddings, rerank, and model-operations models without relying on ad-hoc naming conventions.

## Scope

- update worker and control-plane protobuf shapes for capability class, route class, and operator-visible settings
- regenerate Swift and Python protocol artifacts
- upgrade the Swift control-plane model catalog to store typed model metadata and default development models for the new capability families
- upgrade worker routing so route selection can resolve from typed model metadata instead of assuming every model is text
- add protocol, model-catalog, and worker-registry tests

## Non-Goals

- implement real embeddings or rerank execution
- add new public HTTP endpoints
- add model-operations job execution, quantization, upload, or download behavior
- change the Swift text hot path

## Files

- `packages/protocol/schema/worker/v1/common.proto`
- `packages/protocol/schema/controlplane/v1/control_plane.proto`
- `packages/protocol/swift/**/*`
- `packages/protocol/python/**/*`
- `services/control-plane-swift/Sources/ModelCatalog/*`
- `services/control-plane-swift/Sources/WorkerClient/*`
- `services/control-plane-swift/Sources/Requests/*`
- `services/control-plane-swift/Tests/WorkerClientTests/*`
- `services/control-plane-swift/Tests/ControlPlaneTests/*`

## Performance Probes

- `control_plane.model_catalog_lookup_ms`
- `control_plane.worker_route_class_lookup_ms`
- `control_plane.model_settings_update_ms`

Metrics report for this milestone may mark runtime throughput as `N/A`, because this slice only changes capability and routing metadata, not live embedding or rerank execution.

## Implementation Steps

1. Add typed enums and settings messages to the shared protobuf contracts.
2. Regenerate Swift and Python protocol outputs.
3. Extend the Swift model catalog with typed capability classes, route classes, and per-model settings.
4. Extend worker routing to resolve from typed model metadata and add non-text Python route classes.
5. Add tests for protocol defaults, catalog typing, settings persistence, and route resolution.

## Verification

```bash
make proto
swift test --package-path services/control-plane-swift
make coverage
```

## Acceptance

- protocol generation succeeds after the new capability and settings shapes land
- the control-plane model catalog can distinguish text, embeddings, rerank, and model-ops entries
- worker routing resolves the correct route class from typed model metadata
- touched-scope automated coverage is at least `95%`

