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

## Live Request Assembly Follow-up Slice

GitHub issue: #1383 follow-up, attaching planner receipts to accepted live text requests before worker dispatch.

This slice keeps compaction planner-only. It does not drop, summarize, or mutate request messages, and it does not change stored session history. The goal is to connect the existing planner to the live request assembly path so accepted session-backed OpenAI text requests carry a `melix.session_compaction_policy_receipt.v1` receipt in worker `execution.ext`.

Implementation boundary:

- resolve the usable context budget from the accepted request's model context window and output cap;
- read the bounded-tail policy from model metadata, defaulting `max_history_items` to `0` when no bounded policy is configured;
- estimate each normalized message as one session history item using the same lightweight prompt-budget heuristic class already used by gateway admission;
- generate the compaction plan after `ChatRequestTranslator` creates the request id, so the receipt can record the real worker request id;
- merge the receipt through the existing worker execution metadata path.

Receipt fields remain the existing schema fields; this slice adds no schema version bump.

## Performance Probes

Changed code is a pure O(n) planner over already-estimated history rows. Success criteria:

- focused Swift tests cover bounded histories without runtime services;
- protected grounding retention remains O(n) and does not add runtime service dependencies;
- live request assembly integration remains O(n) over normalized message count and does not call external tokenizers or runtime services;
- PR-scoped performance should select no heavy runtime probes unless the shared request files are mapped to a probe;
- if a probe is selected, no in-scope regression is acceptable.

## Verification

Focused commands:

```bash
xcrun swift test --package-path services/control-plane-swift --filter ControlPlaneTests.TextEndpointContractTests/sessionCompactionPolicy
xcrun swift test --package-path services/control-plane-swift --filter 'ControlPlaneTests.TextEndpointContractTests/chatTranslationAttachesSessionCompactionReceipt|ControlPlaneTests.TextEndpointContractTests/chatTranslationMarksCompactionRequired|HTTPGatewayTests.OpenAIHandlerTests/gatewaySessionCompactionReceiptFeedsAcceptedTextRequests'
xcrun swift test --package-path services/control-plane-swift --filter ControlPlaneTests.TextEndpointContractTests
xcrun swift test --package-path services/control-plane-swift --filter 'HTTPGatewayTests.OpenAIHandlerTests/nonStreamChatRejectsOverBudget|HTTPGatewayTests.OpenAIHandlerTests/streamChatRejectsOverBudget|HTTPGatewayTests.OpenAIHandlerTests/maxCompletionTokensRemainsAnOutputCap|HTTPGatewayTests.OpenAIHandlerTests/defaultOutputCapDoesNotExhaust|HTTPGatewayTests.OpenAIHandlerTests/longContextAdmissionStillRejects|HTTPGatewayTests.OpenAIHandlerTests/gatewayContextMetadataFeedsMemoryAdmission|HTTPGatewayTests.OpenAIHandlerTests/gatewaySessionCompactionReceiptFeedsAcceptedTextRequests|HTTPGatewayTests.OpenAIHandlerTests/gatewaySkipsSessionCompactionReceiptWhenModelContextIsUnknown|HTTPGatewayTests.OpenAIHandlerTests/gatewayDefaultsInvalidSessionCompactionHistorySettingsToUnlimited'
xcrun swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneTests.TextEndpointContractTests
xcrun swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneTests.TextEndpointContractTests|HTTPGatewayTests.OpenAIHandlerTests/nonStreamChatRejectsOverBudget|HTTPGatewayTests.OpenAIHandlerTests/streamChatRejectsOverBudget|HTTPGatewayTests.OpenAIHandlerTests/maxCompletionTokensRemainsAnOutputCap|HTTPGatewayTests.OpenAIHandlerTests/defaultOutputCapDoesNotExhaust|HTTPGatewayTests.OpenAIHandlerTests/longContextAdmissionStillRejects|HTTPGatewayTests.OpenAIHandlerTests/gatewayContextMetadataFeedsMemoryAdmission|HTTPGatewayTests.OpenAIHandlerTests/gatewaySessionCompactionReceiptFeedsAcceptedTextRequests|HTTPGatewayTests.OpenAIHandlerTests/gatewaySkipsSessionCompactionReceiptWhenModelContextIsUnknown|HTTPGatewayTests.OpenAIHandlerTests/gatewayDefaultsInvalidSessionCompactionHistorySettingsToUnlimited'
uv run --python 3.12 python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/SessionCompactionPolicy.swift services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift
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

Current focused results for the live request assembly follow-up:

- `ControlPlaneTests.TextEndpointContractTests/sessionCompactionPolicy`: 6 tests passed.
- `ControlPlaneTests.TextEndpointContractTests`: 82 tests passed.
- `HTTPGatewayTests.OpenAIHandlerTests` prompt-budget and session-compaction focused filter: 9 tests passed.
- Combined coverage filter covering `TextEndpointContractTests` plus the prompt-budget/session-compaction handler tests: 91 tests passed.
- Swift changed-line coverage:
  - `services/control-plane-swift/Sources/Requests/SessionCompactionPolicy.swift`: `100.00%` (`58/58`).
  - `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`: `100.00%` (`9/9`).
  - `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`: `98.15%` (`53/54`).
  - `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`: `100.00%` (`192/192`).
  - `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`: `100.00%` (`172/172`).
  - Total changed-line coverage: `99.79%` (`484/485`).
- Runtime metrics: `N/A`; this slice only adds O(n) receipt assembly over already-normalized request messages before worker dispatch.

Local gate results for this follow-up:

- `make swift-test`: passed; the final macOS menubar package stage reported 834 tests passed.
- `make py-test`: passed; `4908 passed`, `14 skipped`.
- `make integration-test`: passed; `123 passed`, `1 skipped`.

Before commit or PR, the repository pre-commit gate must run the scoped performance report according to `AGENTS.md`.
