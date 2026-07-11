# Issue 1384 Tool-Call Parser Policy Conformance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OpenAI conformance slice that makes tool-call parser policy evidence machine-readable by model family, parser mode, and tag dialect.

**Architecture:** Keep the proof at the Swift control-plane boundary described by ADR 0002. Extend `OpenAIConformanceRow` with optional metadata fields so existing rows and harness output remain compatible, then add stream and non-stream malformed tool-call fixtures that build their report rows from real request-local compatibility receipts in `GenerateRequest.execution.ext`.

**Tech Stack:** Swift Testing, `OpenAIConformanceReport`, `OpenAIConformanceMatrixTests`, `TextCompatibilityPolicyReceipt`, `ChatRequestTranslator`, and the existing `RecordingConformanceWorker` fixture.

---

## Scope

This slice covers:

- `OpenAIConformanceRow` optional metadata for `model_family`, `parser_mode`, `tag_dialect`, `requested_parser`, `resolved_parser`, `parser_fallback_mode`, and `parser_refusal_reason`.
- Request-local compatibility receipt fields for the same parser policy evidence: `requested_parser`, `resolved_parser`, `parser_fallback_mode`, and `parser_refusal_reason`.
- A table-driven conformance fixture keyed by `{model_family, parser_mode, tag_dialect}`.
- Stream and non-stream malformed tool-call text fixtures proving raw delimiters are suppressed and no backend text skeleton is promoted to an OpenAI `tool_calls` payload.

This slice does not implement worker-side parser recovery, bounded retry nudges, or real backend proxy parity.

## Success Metrics

- Existing conformance report JSON remains schema `melix.openai_conformance_report.v1`.
- Rows without parser metadata still encode and decode with the existing field set.
- Parser fixture rows include the new snake-case metadata fields in JSON.
- Compatibility receipts include requested, resolved, fallback, and refusal parser evidence.
- Focused Swift tests pass with coverage at or above 95 percent for touched Swift scope.
- PR-scoped performance report is `ok` with no in-scope regression.

## Implementation Tasks

### Task 1: Conformance Row Metadata

**Files:**

- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIConformanceReport.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceMatrixTests.swift`

- [x] **Step 1: Write the failing report metadata test**

Add a test that constructs an `OpenAIConformanceRow` with parser metadata:

```swift
@Test("conformance report rows can carry parser policy fixture metadata")
func conformanceReportRowsCanCarryParserPolicyFixtureMetadata() throws {
    let row = OpenAIConformanceRow(
        field: "tool_call_parser_policy:qwen3moe:qwen:qwen_xml_tool_call",
        route: "/v1/chat/completions -> parser policy evidence",
        expectedBehavior: "parser policy fixtures expose model family, parser mode, tag dialect, and resolved parser receipt evidence.",
        observedStatus: .pass,
        observedReason: "parser_policy=resolved",
        modelFamily: "qwen3moe",
        parserMode: "qwen",
        tagDialect: "qwen_xml_tool_call",
        requestedParser: "qwen",
        resolvedParser: "qwen",
        parserFallbackMode: "xml",
        parserRefusalReason: ""
    )
    let reportJSON = try OpenAIConformanceReport(rows: [row]).jsonString()

    #expect(reportJSON.contains(#""model_family":"qwen3moe""#))
    #expect(reportJSON.contains(#""parser_mode":"qwen""#))
    #expect(reportJSON.contains(#""tag_dialect":"qwen_xml_tool_call""#))
    #expect(reportJSON.contains(#""requested_parser":"qwen""#))
    #expect(reportJSON.contains(#""resolved_parser":"qwen""#))
    #expect(reportJSON.contains(#""parser_fallback_mode":"xml""#))
    #expect(reportJSON.contains(#""parser_refusal_reason":"""#))
}
```

- [x] **Step 2: Run the focused red test**

Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests/conformanceReportRowsCanCarryParserPolicyFixtureMetadata
```

Expected: fail to compile because `OpenAIConformanceRow` does not accept the parser metadata arguments.

- [x] **Step 3: Add optional metadata fields**

Extend `OpenAIConformanceRow` with optional `String?` properties and defaulted initializer arguments:

```swift
public let modelFamily: String?
public let parserMode: String?
public let tagDialect: String?
public let requestedParser: String?
public let resolvedParser: String?
public let parserFallbackMode: String?
public let parserRefusalReason: String?
```

Add coding keys:

```swift
case modelFamily = "model_family"
case parserMode = "parser_mode"
case tagDialect = "tag_dialect"
case requestedParser = "requested_parser"
case resolvedParser = "resolved_parser"
case parserFallbackMode = "parser_fallback_mode"
case parserRefusalReason = "parser_refusal_reason"
```

- [x] **Step 4: Run the focused green test**

Run the same focused Swift test. Expected: pass.

### Task 2: Parser Policy Receipts and Malformed Fixtures

**Files:**

- Modify: `services/control-plane-swift/Sources/Requests/TextCompatibilityPolicyReceipt.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceMatrixTests.swift`

- [x] **Step 1: Write failing receipt assertions**

Extend `translated text requests attach request-local compatibility policy receipts` to require:

```swift
#expect(ext["melix.compat.requested_parser"] == "qwen")
#expect(ext["melix.compat.resolved_parser"] == "qwen")
#expect(ext["melix.compat.parser_fallback_mode"] == "")
#expect(ext["melix.compat.parser_refusal_reason"] == "")
#expect(receipt.contains(#""requested_parser":"qwen""#))
#expect(receipt.contains(#""resolved_parser":"qwen""#))
```

Also extend `compatReceiptFieldNames()` with the four new JSON fields.

- [x] **Step 2: Run the focused red receipt test**

Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter ToolParserRegistryTests/translatedTextRequestsAttachRequestLocalCompatibilityPolicyReceipts
```

Expected: fail because the new compatibility receipt fields are absent.

- [x] **Step 3: Implement receipt fields**

Add these `TextCompatibilityPolicyReceipt` properties:

```swift
public let requestedParser: String
public let resolvedParser: String
public let parserFallbackMode: String
public let parserRefusalReason: String
```

Populate them from `ShapedTextRequest`:

```swift
"requested_parser": shapedRequest.toolParser?.source == "request" ? shapedRequest.toolParser?.mode.rawValue ?? "none" : "none",
"resolved_parser": shapedRequest.toolParser?.mode.rawValue ?? "none",
"parser_fallback_mode": shapedRequest.toolParser?.fallbackMode?.rawValue ?? "",
"parser_refusal_reason": shapedRequest.toolParserSuppressedReason ?? "",
```

Mirror them in `extFields` under `melix.compat.*` and include them in the canonical receipt dictionary so the effective config hash changes when parser policy changes.

- [x] **Step 4: Add parser fixture conformance rows**

Add a table-driven matrix test with two fixtures:

```swift
private struct ToolCallParserPolicyFixture: Sendable {
    let modelFamily: String
    let parserMode: String
    let tagDialect: String
    let stream: Bool
}
```

Use `tool_parser: { "mode": "qwen", "namespaces": ["tools.search"], "xml_fallback": true }` and `tools: [weatherToolJSON]`. For the non-stream fixture, return malformed assistant text containing an unclosed `<tool_call>` block. For the stream fixture, split a `<|tool_call>` marker across token events. Assert:

```swift
#expect(payload.contains("<tool_call>") == false)
#expect(payload.contains("<|tool_call>") == false)
#expect(payload.contains("\"tool_calls\"") == false)
#expect(ext["melix.compat.requested_parser"] == fixture.parserMode)
#expect(ext["melix.compat.resolved_parser"] == fixture.parserMode)
#expect(ext["melix.compat.parser_fallback_mode"] == "xml")
```

Build `OpenAIConformanceRow` values from the fixture and ext receipt fields, then assert report JSON contains the parser metadata.

- [x] **Step 5: Run focused conformance tests**

Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIConformanceMatrixTests|ToolParserRegistryTests'
```

Expected: pass.

### Task 3: Verification and PR Evidence

**Files:**

- Modify: `docs/plans/2026-07-11-issue-1384-tool-call-parser-policy-conformance.md`
- Read before PR: `.github/pull_request_template.md`, `docs/contributing.md`, `docs/templates/pr-evidence-checklist.md`

- [x] **Step 1: Run diff hygiene**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; only the planned files are modified.

- [x] **Step 2: Run focused coverage**

Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIConformanceMatrixTests|ToolParserRegistryTests'
```

Expected: tests pass and changed-scope coverage is at least 95 percent.

- [x] **Step 3: Run repository gates**

Run:

```bash
make swift-test
make py-test
make integration-test
```

Expected: all pass.

Actual:

- `make swift-test` passed.
- `make py-test` passed: 4908 passed, 14 skipped, 2 warnings in 194.15s.
- `make integration-test` passed: 123 passed, 1 skipped in 712.07s.

- [x] **Step 4: Run scoped performance report**

Run:

```bash
.githooks/pre-commit
```

Expected: scoped performance report status is `ok` with zero in-scope regressions.

Actual: `.githooks/pre-commit` passed. Performance report status was `ok` with 0 regressions, 0 context regressions, 0 verification failures, and no selected probes for this change set. Report path: `.runtime/pre-commit-performance/20260711-105700-4d3915c0/report/report.md`.

## Known Deferred Work

- Worker-side parser recovery and retry/nudge behavior remain part of broader #1384/#1382 follow-up work.
- Real remote-provider proxy parity remains out of scope for this in-process conformance slice.
- Additional parser families can reuse the metadata fields and fixture table after their backend parser behavior is stable enough to pin.
