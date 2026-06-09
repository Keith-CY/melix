# Issue 1757 Model-List URL Receipt Slice

## Goal

Extend provider endpoint health receipts with redacted model-list URL
classification evidence so operators can see which endpoint shape was
normalized and which provider-specific model-list URL class was probed.

## Scope

This slice covers the watch-note requirement for endpoint model-list URL
receipts:

- classify input endpoint shape after normalization;
- classify the provider-specific model-list endpoint used by the probe;
- expose a stable probe status field beside the existing last-probe status;
- record whether authentication or URL credentials were redacted from receipt
  evidence;
- record whether a provider-specific model-list fallback transform was applied.

This slice does not add persistent last-result storage, UI controls, owner-scope
credential lookup, pinned model provenance, background-helper resolution, or
full provider conformance tests.

## Architecture

`ProviderEndpointHealthProbe` already owns provider URL normalization, model-list
URL construction, request authentication, capability parsing, and failure
classification. This slice keeps the new evidence in that same receipt path.
The probe will compute a small `ProviderEndpointURLClassification` value while
normalizing the operator-provided URL, then carry it into both success and
failure receipts.

The new receipt fields are metadata only. They must not include API keys, raw
authorization headers, provider response bodies, or full prompt/session content.

## Receipt Semantics

- `normalized_base_kind`
  - `base_url`: input was already a base host or non-versioned root.
  - `versioned_base`: input was a versioned API root such as `/v1`.
  - `chat_completions_endpoint`: input was a chat completions endpoint.
  - `messages_endpoint`: input was an Anthropic messages endpoint.
  - `ollama_chat_endpoint`, `ollama_generate_endpoint`, `ollama_tags_endpoint`:
    input was an Ollama endpoint.
  - `models_endpoint`: input was already a model-list endpoint.
- `models_endpoint_kind`
  - `openai_models`
  - `anthropic_models`
  - `ollama_tags`
  - `local_runtime_models`
- `probe_status`
  - `ok` on successful model-list parsing.
  - the typed failure reason on failures.
- `auth_redacted`
  - `true` when the request has an API key, URL user/password credentials, or a
    query string/fragment that was stripped from receipt evidence.
  - `false` only when no credential-bearing input was present.
- `fallback_attempted`
  - `true` when the probe rewrites a supplied endpoint or provider API root into
    the provider-specific model-list URL.
  - `false` when the supplied URL already targets the model-list endpoint.

## Performance Probes And Metrics

The changed path runs only when an operator asks for provider endpoint health.
The added work is constant-time string classification and boolean derivation per
probe.

Success metrics:

- focused Swift provider endpoint tests pass;
- changed-line coverage for touched Swift scope is at least 95 percent;
- local scoped performance report is `Status: ok` with zero regressions;
- remote PR scoped performance report is `Status: ok` with zero regressions.

## Verification

Focused Swift tests:

```bash
HOME="$PWD/.swift-home/provider-url-receipts" \
CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/provider-url-receipts" \
xcrun swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home/provider-url-receipts-coverage" \
CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/provider-url-receipts-coverage" \
xcrun swift test --enable-code-coverage --package-path services/control-plane-swift --filter RemoteProviderClientTests

python3.11 scripts/swift_changed_line_coverage.py \
  --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests \
  --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift
```

Full gate:

```bash
.githooks/pre-commit
```

## Implementation Steps

1. Add a failing table-driven Swift test for base URL, `/v1`,
   `/v1/chat/completions`, Ollama `/api/chat`, and already-normalized model-list
   inputs. Assert model-list request URLs and new receipt fields.
2. Extend `ProviderEndpointHealthReceipt` with the new Codable fields and stable
   defaults.
3. Refactor URL normalization to return the normalized URL plus
   `normalized_base_kind`, `auth_redacted`, and `fallback_attempted` inputs.
4. Classify model-list endpoint kind when constructing the provider-specific
   probe URL.
5. Update docs and run focused tests, coverage, full local gate, and scoped
   performance before opening the PR.

## Known Gaps

- The receipt is not yet persisted or rendered in App/CLI diagnostics.
- Owner-scoped credential lookup and cross-owner refusal receipts remain future
  #1757 work.
- Pinned/cached/live model provenance remains future #1757 work.
