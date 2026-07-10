# Issue 1383 Session Compaction Policy Slice

## Issue

GitHub issue: #1383, "Add context budget watermarks, tiered compaction, and compaction receipts".

## Scope

This slice adds a planner-only session history policy resolver in the Swift control plane. It does not wire compaction into live request assembly, does not summarize content, and does not mutate stored session history.

The slice defines:

- a bounded session-history policy where `max_history_items = 0` means unlimited;
- deterministic planning results for unlimited, bounded-tail, and compaction-required states;
- a redacted `melix.session_compaction_policy_receipt.v1` receipt with before/after item counts, token estimates, usable context budget, watermark state, and policy decision;
- focused Swift unit coverage for the three policy modes.

## End-State Architecture

The end-state context system should sit between session graph replay and worker request assembly:

1. Resolve the effective model/session context budget once.
2. Estimate session history and pending request token pressure.
3. Apply bounded-tail replay only when configured.
4. Escalate to tiered compaction when tail replay alone still exceeds usable context.
5. Emit receipts before any prompt mutation so the operator can understand why context was kept, dropped, or marked for compaction.

This PR only introduces step 3/4 planning and the receipt shape. Later slices can feed real session graph entries into the planner, preserve tool-call pairs and protected grounding metadata, and attach the receipt to execution metadata.

## Protected Grounding Follow-up Slice

GitHub issue: #1383 follow-up, preserving metadata-marked grounding during planner-only bounded-tail compaction.

This slice keeps the existing planner-only boundary and adds one retention invariant: session history items marked as protected grounding must survive bounded-tail history trimming even when they are older than the retained tail window. The planner still does not summarize content, mutate stored session history, or attach receipts to live execution metadata.

Receipt fields added by this slice:

- `protected_grounding_items_before`
- `protected_grounding_items_after`
- `protected_grounding_preserved`

The policy should escalate to `compaction_required` if the protected grounding plus retained tail still exceeds the usable context budget. That escalation is explicit; the planner must not silently drop protected grounding to fit the window.

## Performance Probes

Changed code is a pure O(n) planner over already-estimated history rows. Success criteria:

- focused Swift tests cover bounded histories without runtime services;
- protected grounding retention remains O(n) and does not add runtime service dependencies;
- PR-scoped performance should select no heavy runtime probes unless the shared request files are mapped to a probe;
- if a probe is selected, no in-scope regression is acceptable.

## Verification

Focused commands:

```bash
xcrun swift test --package-path services/control-plane-swift --filter ControlPlaneTests.TextEndpointContractTests/sessionCompactionPolicy
xcrun swift test --package-path services/control-plane-swift --filter ControlPlaneTests.TextEndpointContractTests
xcrun swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneTests.TextEndpointContractTests
uv run --python 3.12 python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/SessionCompactionPolicy.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift
git diff --check
```

Current focused results for the protected-grounding follow-up:

- `ControlPlaneTests.TextEndpointContractTests/sessionCompactionPolicy`: 6 tests passed.
- `ControlPlaneTests.TextEndpointContractTests`: 72 tests passed.
- Swift changed-line coverage:
  - `services/control-plane-swift/Sources/Requests/SessionCompactionPolicy.swift`: `100.00%` (`25/25`).
  - `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`: `100.00%` (`75/75`).
  - Total changed-line coverage: `100.00%` (`100/100`).
- Runtime metrics: `N/A`; this slice adds a pure planner invariant and does not wire the live request assembly path.

Before commit or PR, the repository pre-commit gate must run the full local test gate and scoped performance report according to `AGENTS.md`.
