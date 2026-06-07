# Provider Endpoint Health Probes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend provider endpoint health probe that normalizes provider URLs, probes model-list readiness, classifies endpoint capabilities, filters hidden/non-chat models, and returns a redacted receipt for operator diagnostics.

**Architecture:** The first slice lives in the Swift control-plane core next to `RemoteProviderClient`. It adds a focused probe service with injected HTTP transport so tests can cover provider behavior without live network calls. The receipt is intentionally independent from UI persistence so CLI/App surfaces can later store or render the same redacted payload without duplicating probe logic.

**Tech Stack:** Swift, Swift Testing, `RemoteProviderHTTPTransport`, `URLRequest`, `HTTPURLResponse`, JSON decoding through `JSONSerialization`.

---

## Scope

This slice implements the core receipt contract for issue #1757:

- Normalize base URLs for OpenAI-compatible, Anthropic, Ollama/native, and local Melix runtime endpoints.
- Build provider-specific model-list probe URLs.
- Probe model-list endpoints without leaking API keys in receipts.
- Classify capabilities for chat, streaming, tools, JSON/structured output, and embeddings when the provider/model metadata supports it.
- Filter hidden, disabled, and non-chat models from automatic chat selection.
- Return redacted receipt fields: `endpoint_id`, `provider_kind`, `base_url_redacted`, `model_count`, `capabilities`, `latency_ms`, and `failure_reason`.

This slice does not implement full protocol conformance, UI rendering, owner-scoped credential lookup, background helper fallback receipts, pinned model policy, or persistent last-result storage. Those are follow-up slices that should reuse the receipt contract added here.

## Files

- Create: `services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift`
  - Owns request, receipt, normalized endpoint, model summary, capability summary, URL normalization, redaction, provider-specific request construction, model parsing, filtering, and failure classification.
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift`
  - Adds focused Swift Testing coverage using the existing `RecordingRemoteProviderTransport` pattern.
- Modify: `docs/plans/2026-06-07-provider-endpoint-health-probes.md`
  - Tracks scope, performance probes, verification, and task status for the PR evidence.

## Performance Probes And Success Metrics

The probe is off the request hot path and only runs when an operator asks for endpoint readiness. The success metric is therefore deterministic bounded work, not chat latency.

Measurement points:

- `latency_ms` in the receipt records model-list probe duration with a monotonic clock.
- Unit tests assert positive or injected latency values without requiring wall-clock sleeps.
- PR scoped performance should show no regression in changed Swift control-plane probes.

Success metrics:

- URL normalization and model-list URL construction are table-tested for OpenAI-compatible, Anthropic, Ollama/native, and local Melix runtime endpoints.
- Probe receipts never contain the raw API key in `base_url_redacted`, `failure_reason`, or capability/model fields.
- Auth failure, malformed model-list failure, transport failure, and hidden/non-chat filtering are covered by tests.
- Focused Swift tests pass before commit.
- Changed-line coverage for the touched Swift scope is at least 95 percent.
- Full PR gate runs before PR creation: `make swift-test`, `make py-test`, `make integration-test`, plus the repository pre-commit performance report.

## Task 1: Add Failing Tests For URL Normalization And Redaction

**Files:**
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift`

- [x] **Step 1: Write failing tests**

Add Swift Testing cases under the existing `RemoteProviderClientTests` suite:

```swift
@Test("endpoint probe normalizes provider model URLs and redacts secrets")
func endpointProbeNormalizesProviderModelURLsAndRedactsSecrets() async throws {
    let transport = RecordingRemoteProviderTransport(response: .init(
        statusCode: 200,
        headers: ["content-type": "application/json"],
        body: Data(#"{ "data": [{ "id": "gpt-4.1", "object": "model" }] }"#.utf8)
    ))
    let probe = ProviderEndpointHealthProbe(transport: transport, latencyClock: { 12 })

    let receipt = try await probe.probe(
        ProviderEndpointProbeRequest(
            endpointID: "openai-main",
            providerKind: "openai-compatible",
            baseURL: " https://api.example.test/v1/chat/completions?api_key=sk-secret ",
            apiKey: "sk-secret"
        )
    )

    #expect(receipt.endpointID == "openai-main")
    #expect(receipt.providerKind == "openai-compatible")
    #expect(receipt.baseURLRedacted == "https://api.example.test/v1")
    #expect(receipt.modelCount == 1)
    #expect(receipt.capabilities.chat == true)
    #expect(receipt.capabilities.streaming == true)
    #expect(receipt.latencyMS == 12)
    #expect(receipt.failureReason == "")
    #expect(await transport.lastRequest?.url?.absoluteString == "https://api.example.test/v1/models")
    #expect(await transport.lastRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer sk-secret")
    #expect(String(describing: receipt).contains("sk-secret") == false)
}
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests/endpointProbeNormalizesProviderModelURLsAndRedactsSecrets
```

Expected: FAIL because `ProviderEndpointHealthProbe` and related types do not exist.

## Task 2: Implement URL Normalization, Redaction, And Probe Requests

**Files:**
- Create: `services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift`

- [x] **Step 1: Add minimal types and OpenAI-compatible model-list probing**

Implement:

```swift
public struct ProviderEndpointProbeRequest: Equatable, Sendable { ... }
public struct ProviderEndpointHealthReceipt: Equatable, Sendable, CustomStringConvertible { ... }
public struct ProviderEndpointCapabilities: Equatable, Sendable { ... }
public struct ProviderEndpointHealthProbe: Sendable { ... }
```

The OpenAI-compatible path removes `/models`, `/chat/completions`, query, and fragment suffixes before appending `/models`. Receipt redaction includes scheme, host, optional port, and normalized path, but no query string, fragment, raw API key, or credential-bearing userinfo.

- [x] **Step 2: Run focused test to verify it passes**

Run:

```bash
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests/endpointProbeNormalizesProviderModelURLsAndRedactsSecrets
```

Expected: PASS.

## Task 3: Add Failing Tests For Provider Matrix And Hidden Model Filtering

**Files:**
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift`

- [x] **Step 1: Write provider matrix and filtering tests**

Add tests that assert:

- Anthropic model-list URL uses `/v1/models`, `x-api-key`, and `anthropic-version`.
- Ollama/native model-list URL uses `/api/tags` and no bearer header when the API key is empty.
- Local runtime model-list URL strips `/v1/chat/completions` and uses `/v1/models`.
- Hidden, disabled, embedding-only, rerank-only, and audio-only models are excluded from automatic chat selection.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests
```

Expected: FAIL until provider-specific URL construction and model filtering are implemented.

## Task 4: Implement Provider-Specific Parsing And Capability Classification

**Files:**
- Modify: `services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift`

- [x] **Step 1: Add provider request construction**

Support:

- `openai-compatible`: `GET <base>/models`
- `anthropic`: `GET <base>/models`
- `ollama-native`: `GET <base>/api/tags`
- `local-runtime`: `GET <base>/v1/models`

- [x] **Step 2: Add model parsing and filtering**

Parse OpenAI-style `data`, Anthropic-style `data`, Ollama-style `models`, and Melix local `/v1/models` responses. Exclude model entries when metadata marks them as hidden, disabled, or non-chat-only. Include embeddings capability when at least one visible model advertises embeddings or has embedding kind/capability metadata.

- [x] **Step 3: Run focused tests**

Run:

```bash
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests
```

Expected: PASS.

## Task 5: Add Failing Tests For Failure Receipts

**Files:**
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift`

- [x] **Step 1: Write failure receipt tests**

Add tests for:

- HTTP 401 returns `failure_reason == "auth_failed"` and `model_count == 0`.
- HTTP 500 returns `failure_reason == "model_list_failed"`.
- Malformed JSON returns `failure_reason == "model_list_malformed"`.
- Transport errors return `failure_reason == "transport_failed"`.
- Failure receipt stringification does not include API keys or provider response bodies.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests
```

Expected: FAIL until typed failure receipts are implemented.

## Task 6: Implement Failure Classification And Final Verification

**Files:**
- Modify: `services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift`

- [x] **Step 1: Implement failure receipts**

Return a receipt for invalid requests, provider auth failures, provider model-list failures, malformed model-list payloads, and transport errors. Keep raw provider response bodies out of receipts.

- [x] **Step 2: Run focused Swift tests**

Run:

```bash
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests
```

Expected: PASS.

- [x] **Step 3: Run diff and broader verification**

Run:

```bash
git diff --check
make swift-test
make py-test
make integration-test
```

Expected: all commands exit 0.

Observed:

- `git diff --check`: exited 0.
- Changed-line coverage: `TOTAL 98.91% 636/643`; implementation file `97.94% 285/291`.
- `make swift-test`: exited 0.
- `make py-test`: `3624 passed, 14 skipped, 2 warnings`.
- `make integration-test`: `117 passed, 1 skipped`.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/plans/2026-06-07-provider-endpoint-health-probes.md \
  services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift
git commit -m "Add provider endpoint health probes"
```
