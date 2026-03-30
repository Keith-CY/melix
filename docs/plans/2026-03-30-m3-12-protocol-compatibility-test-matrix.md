# M3.12 Protocol Compatibility Test Matrix

## Goal

Close the API-compatibility milestone with a repository-owned test matrix that proves protocol behavior across supported endpoint families and client expectations.

## Scope

- add compatibility-focused contract tests
- add live-path integration coverage for protocol families
- keep the test matrix discoverable from the roadmap and docs index

## Matrix Coverage

- Swift protocol matrix:
  - `services/control-plane-swift/Tests/HTTPGatewayTests/ProtocolCompatibilityMatrixTests.swift`
- Live integration matrix:
  - `tests/integration/test_protocol_compatibility_matrix.py`
- Existing endpoint-specific contract suites remain authoritative for detailed request-shape behavior:
  - `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`
  - `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

## Files

- update `services/control-plane-swift/Tests/`
- update `tests/integration/`
- update `docs/README.md`
- update `docs/plans/2026-03-30-full-capability-roadmap.md`

## Implementation Notes

- the matrix should cover both streaming and completed outputs
- prefer repository-owned fixtures and compatibility smoke cases over opaque external scripts
- keep the matrix broad enough to catch protocol drift across future milestones

## Verification

- `make swift-test`
- `make integration-test`
- touched-scope coverage command for the protocol-compatibility slice

## Acceptance

- Melix has a repository-owned compatibility matrix for the completed protocol slice
- protocol drift becomes detectable before future milestones land
