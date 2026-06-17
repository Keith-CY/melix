# Issue 1759 Companion Mobile Status Page

## Goal

Add a minimal browser/mobile companion status page that a paired local device can
open directly, without adding remote control or changing the read-only gateway
scope.

## Best End-State Architecture

The gateway remains the source of truth for companion authorization and
redaction. `POST /v1/melix/auth/session` continues to issue a
`companion_read_only` session and returns the existing pairing descriptor. This
slice adds a `mobile_url` field to that descriptor and serves a static
`GET /v1/melix/companion` HTML shell.

The HTML shell is intentionally small and dependency-free. It stores an
operator-entered companion session token in browser-local storage on that local
device, fetches `GET /v1/melix/companion/status` with the descriptor
`x-melix-session` header, renders runtime status, visible model/job/log-tail
summaries, and never exposes mutating controls.

## Slice Boundary

Included:

- Add `GET /v1/melix/companion` as a companion-read-only route.
- Return a static mobile-first HTML page with no external assets.
- Add `pairing.mobile_url` pointing to `/v1/melix/companion`.
- Include the page in pairing `allowed_routes`.
- Preserve `pairing.mobile_url` in desktop pairing bundles and pairing codes.
- Prove the page is served to companion tokens and local trusted access.
- Prove companion tokens still cannot call mutating routes.
- Document the manual mobile status page flow.

Excluded:

- Public internet exposure.
- Push/live websocket updates.
- Persisting tokens server-side.
- QR scanner/import parsing in the browser.
- Any mutating companion controls.

## Performance Probes and Metrics

- Runtime metric: add `companion.mobile_page_served_count` for page responses.
- The page is a static string response and should not select heavy performance
  probes.
- PR merge gate: scoped performance report must remain `Status: ok` with zero
  regressions.

## Implementation Plan

1. Add a failing Swift gateway test that creates a companion session, asserts
   `pairing.mobile_url`, asserts allowed route `GET /v1/melix/companion`, fetches
   the page with the companion token, and verifies the response is HTML with
   mobile viewport metadata, `x-melix-session`, `/v1/melix/companion/status`,
   visible redaction/status labels, and no mutating route strings.
2. Add the route to `OpenAIHandler.handle` and `authorizationRoute(for:)`.
3. Add a static `CompanionMobileStatusPage.html` response helper with local
   storage, token entry, refresh, sign-out-from-device storage clearing, and
   read-only status rendering.
4. Add `mobileURL` to `OpenAICompanionPairingPayload` and derive it from the same
   normalized host/port as `statusURL`.
5. Add `GET /v1/melix/companion` to the pairing allowed routes.
6. Add `mobileURL` to the desktop companion pairing model so copied bundles and
   pairing codes can carry the browser entry point to trusted local devices.
7. Update `docs/runbooks/persistent-sessions.md` with the mobile page URL,
   token-handling boundary, and manual verification.
8. Run focused Swift tests, changed-line coverage, a scoped performance report,
   and the full pre-commit gate before opening the PR.

## Verification

Focused Swift:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companionAuthSessionCreationReturnsPairingDescriptor|companionMobileStatusPageServesReadOnlyShellForCompanionTokens|companionAuthSessionsCanReadStatusAndRevokeThemselvesButCannotMutateRuntime)'
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIHandlerTests/(companionAuthSessionCreationReturnsPairingDescriptor|companionMobileStatusPageServesReadOnlyShellForCompanionTokens|companionAuthSessionsCanReadStatusAndRevokeThemselvesButCannotMutateRuntime)'
uv run --python 3.12 python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift
```

## Deferred Work

- Browser-side QR/pairing-code import.
- Installable PWA manifest and app icon assets.
- Live refresh/push updates.
