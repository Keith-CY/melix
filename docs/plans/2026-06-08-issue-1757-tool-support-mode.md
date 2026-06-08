# Issue 1757 Endpoint Tool Support Mode Slice

## Goal

Add an explicit tri-state tool-call support mode to provider endpoint
configuration and endpoint health receipts so operators can distinguish
automatic detection from forced-on and forced-off local endpoint behavior.

## Scope

- Add a typed Swift `ProviderEndpointToolSupportMode` with stable raw values:
  `auto`, `force_on`, and `force_off`.
- Let `ProviderEndpointProbeRequest` carry the mode, defaulting to `auto`.
- Extend `ProviderEndpointHealthReceipt` with:
  - `tool_support_mode`
  - `detected_tool_support`
  - `override_source`
  - `last_probe_status`
- Apply the mode after model-list detection:
  - `auto` preserves detected tool support.
  - `force_on` reports tool support even when discovery does not advertise it.
  - `force_off` suppresses tool support even when discovery advertises it.
- Persist the same mode in CLI remote-server state and mutations, defaulting
  legacy JSON without the field to `auto`.
- Keep request dispatch, UI controls, live chat payload shaping, and full
  protocol conformance out of scope for this PR.

## Design

The endpoint health probe already owns model-list capability detection. This
slice keeps detection and operator override separate: model metadata still
drives `detected_tool_support`, then the configured `tool_support_mode` derives
the effective `capabilities.tools` value. The receipt records both values plus
an `override_source` string so operator-facing surfaces can explain whether the
result came from discovery or endpoint configuration.

The CLI remote-server store is the existing durable endpoint configuration
surface. Adding the same enum there gives CLI and future UI callers a stable
round-trip field without requiring UI work in this slice. Unknown or missing
persisted values decode as `auto` so older state files remain readable and do
not silently force tool calls on or off.

## Receipt Semantics

- `tool_support_mode = auto`
  - `detected_tool_support` reflects model-list metadata.
  - `capabilities.tools` equals `detected_tool_support`.
  - `override_source = probe_detection`.
- `tool_support_mode = force_on`
  - `detected_tool_support` reflects model-list metadata.
  - `capabilities.tools = true`.
  - `override_source = endpoint_config`.
- `tool_support_mode = force_off`
  - `detected_tool_support` reflects model-list metadata.
  - `capabilities.tools = false`.
  - `override_source = endpoint_config`.
- Failure receipts keep the configured mode, set `detected_tool_support = false`,
  set `capabilities.tools = false`, and set `last_probe_status` to the typed
  failure reason.

## Performance Probes And Metrics

The changed path is off the chat hot path. It runs only when probing provider
endpoint health or reading/writing remote-server configuration.

Measurement points:

- `latency_ms` remains the network probe duration field.
- `last_probe_status` records `ok` or the typed failure reason without parsing
  provider response bodies into observability logs.
- PR-scoped performance should select Swift control-plane or CLI JSON-envelope
  probes only when the registry maps the changed files.

Success metrics:

- Focused Swift tests pass for provider endpoint health and remote-server
  configuration.
- Changed-line coverage for touched Swift scope is at least 95 percent.
- PR-scoped performance report shows zero in-scope regressions.
- Observability mode is `minimal`: the new fields are deterministic receipt
  metadata and do not add sampling, debug logs, or response-body capture.
- Probe overhead is constant-time enum normalization and boolean derivation per
  health receipt.

## Verification

Focused commands:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --filter RemoteProviderClientTests

HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --filter RemoteServerStoreTests
```

Coverage command:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" \
swift test --enable-code-coverage --filter 'RemoteProviderClientTests|RemoteServerStoreTests'

UV_PYTHON=3.12 uv run --project services/mlx-worker-python python \
scripts/swift_changed_line_coverage.py \
  --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests \
  --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  Sources/MelixCLICore/RemoteServerStore.swift \
  services/control-plane-swift/Sources/XPCService/ProviderEndpointHealthProbe.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/RemoteProviderClientTests.swift \
  tests/MelixCLITests/RemoteServerStoreTests.swift
```

PR gate:

```bash
make swift-test
make py-test
make integration-test
```

## Task Plan

1. Add failing probe tests for the three tool support modes and receipt JSON.
2. Add failing remote-server store tests for persistence, legacy defaulting, and
   unknown-value defaulting.
3. Implement the provider endpoint enum, request/receipt fields, and effective
   tool capability derivation.
4. Implement remote-server store persistence and decoding defaults.
5. Run focused tests, coverage, changed-line coverage, PR-scoped performance,
   and the full local gate before opening the PR.

## Known Gaps

- UI controls are deferred to a later operator-surface slice.
- Chat request dispatch still uses existing provider behavior; this PR only
  makes endpoint configuration and health evidence explicit.
- No live endpoint conformance probe is added beyond the existing model-list
  fixture transport.
