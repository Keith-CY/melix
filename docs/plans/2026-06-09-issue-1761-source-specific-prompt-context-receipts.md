# Source-Specific Prompt Context Receipt Classification Plan

## Goal

Continue #1761 by making control-plane prompt-context receipts identify source-specific untrusted prompt segments for tool output, retrieved-document/RAG data, skills, memories, and background continuations without persisting raw prompt content.

## Architecture

`PromptContextBoundaryReceipts` remains the single Swift prompt-assembly receipt point for text requests before `Melix_Worker_V1_GenerateRequest` is sent to the worker. This slice classifies untrusted message parts from existing message metadata only: message role and the already-normalized message `name`. It does not invent a retrieval store, change prompt wording, or parse message content.

Message `name` prefixes are the request-local source identifier surface for this slice:

- `retrieved_document:*`, `retrieved-doc:*`, `document:*`, `doc:*`, `rag:*`, `rag_document:*`, and `knowledge:*` classify as `retrieved_document`.
- `skill:*` and `agent_skill:*` classify as `skill`.
- `memory:*`, `retrieved_memory:*`, and `pinned_memory:*` classify as `memory`.
- `background_continuation:*`, `background-continuation:*`, `background_job:*`, and `background-job:*` classify as `background_continuation`.
- `tool` role messages classify as `tool_output`.
- Other non-system/developer messages keep `chat_prompt_message`.

`source_id` is emitted only when a normalized message name is present. It records the message name string, not message text, media URIs, media bytes, tool arguments, or private prompt text.

## Files

- Modify `services/control-plane-swift/Sources/Requests/PromptContextBoundaryReceipt.swift`
  - Classify prompt receipt `source_type`.
  - Add optional `source_id` from message `name`.
  - Keep raw content out of receipt JSON.
- Modify `services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift`
  - Add a focused TDD regression for tool/RAG/skill/memory/background source classification.
  - Assert raw source text and trusted system text do not appear in `melix.prompt_context.receipts_json`.
- Modify `docs/unified-agentic-tool-runtime-contract.md`
  - Document the source-specific chat prompt receipt classification and its `source_id` privacy rule.

## Verification

1. Red: run the new Swift test and confirm it fails because receipts still use `chat_prompt_message` and omit `source_id`.
2. Green: run the focused Swift test:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'PromptContext'
```

3. Coverage for touched Swift scope:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'PromptContext'
python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/PromptContextBoundaryReceipt.swift services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift
```

4. Full commit gate:

```bash
.githooks/pre-commit
```

## Metrics

This is prompt metadata assembly code. Performance success is no PR-scoped regression in the repository performance report, especially no regression in text request translation or Swift control-plane tests. Coverage success is at least 95 percent changed-line coverage for the touched Swift scope.
