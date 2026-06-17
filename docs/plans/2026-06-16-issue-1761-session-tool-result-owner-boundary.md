# Session Tool Result Owner Boundary Plan

## Issue

GitHub issue #1761 tracks untrusted-context boundaries for retrieved docs,
skills, memories, tool output, and owner-scoped execution surfaces.

## Goal

Fail closed when a non-native tool result or resume snapshot is replayed against
the wrong control-plane session or branch, so cross-session tool output cannot
mutate session graph state or become a follow-up resume boundary.

## Architecture

`SessionGraphStore` already owns the mutable control-plane session graph for
`session.register_tool_result`, `session.resume_after_tool`, and request-stream
hydration. This slice keeps the existing protocol shape and adds a store-level
scope check before mutation:

- a `toolCallID` already recorded on another branch or session is refused with
  `ownerScopeMismatch`;
- a `snapshotID` already recorded on another branch or session is refused with
  `ownerScopeMismatch`;
- first-time tool and snapshot IDs keep the current behavior and are recorded on
  the requested session/branch;
- `RequestCoordinator` treats stream-hydration mismatches as refused side
  effects, increments a metric, and does not overwrite the existing branch
  owner.

The control-plane command response maps the new store error to
`owner_scope_mismatch` rather than `not_found`, making the boundary visible to
operators without adding private content to receipts or protocol payloads.

## Scope

- Add focused `SessionGraphStore` tests for cross-branch and cross-session tool
  result and resume-snapshot replays.
- Add focused `ControlPlaneService` coverage for typed
  `owner_scope_mismatch` responses and no state-change event on refusal.
- Add focused `RequestCoordinator` stream-hydration coverage so worker tool
  result deltas cannot silently move a known tool result across branches.
- Update the unified agentic tool runtime contract with the session tool-result
  owner boundary.

## Out of Scope

- Adding protobuf fields for explicit owner IDs, privileges, or receipt arrays.
- Persisting tool result payloads, parsing tool output, or changing SSE payload
  shapes.
- Changing session creation, branch creation, request-head hydration, or
  first-time tool result registration behavior.

## Verification

- Focused Swift tests:
  - `swift test --package-path services/control-plane-swift --filter 'ControlPlaneTests.SnapshotStoreTests/sessionGraphStoreTracksToolAndResumeMetadata|ControlPlaneTests.SnapshotStoreTests/sessionGraphStoreRejectsUnknownMutations|ControlPlaneTests.SnapshotStoreTests/sessionGraphStoreRejectsCrossScopeToolResultAndResumeReplays|ControlPlaneTests.SnapshotStoreTests/sessionGraphStoreAcceptsLegacySnapshotsWithoutRecordedOwners'`
  - `swift test --package-path services/control-plane-swift --filter 'ControlPlaneTests.SnapshotStoreTests/sessionGraphStoreRejectsBranchOwnedResumeMetadataReplays'`
  - `swift test --package-path services/control-plane-swift --filter 'ControlPlaneTests.ControlPlaneServiceTests/executeHandlesToolResumeAndCloseForSessions|ControlPlaneTests.ControlPlaneServiceTests/executeReturnsNotFoundForInvalidSessionMutations|ControlPlaneTests.ControlPlaneServiceTests/executeRejectsCrossScopeSessionToolResultMutations|ControlPlaneTests.ControlPlaneServiceTests/sessionMutationResponsesPreserveCorrelationMetadata'`
  - `swift test --package-path services/control-plane-swift --filter 'HTTPGatewayTests.RequestCoordinatorTests/toolCallDeltasHydrateSessionGraphToolMetadata|HTTPGatewayTests.RequestCoordinatorTests/annotationAndToolResultDeltasAreSemanticStreamEventsWithMetrics|HTTPGatewayTests.RequestCoordinatorTests/toolResultDeltasCannotMoveKnownToolResultsAcrossSessionBranches|HTTPGatewayTests.RequestCoordinatorTests/sessionTaggedRequestsHydrateSessionGraphRequestHeads'`
- Changed-scope Swift coverage for the touched control-plane store, service,
  coordinator, and tests; required threshold is at least 95 percent for touched
  executable lines.
- Full local pre-commit gate before PR:
  `make swift-test`, `make py-test`, `make integration-test`, and the scoped
  performance report.
- Remote PR checks and PR-scoped performance must report `Status: ok` with
  regressions `0`.

## Performance Probe

The new check is an in-memory scan over the session graph's existing branch and
snapshot metadata on session mutation and stream-hydration paths. The expected
overhead is negligible for current local session counts. The PR-scoped
performance workflow remains the merge gate; any regression in session or
request-coordinator probes is a blocker unless direct evidence shows it is out
of scope.
