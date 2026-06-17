# Issue 1759 Companion Pairing Descriptor

## Goal

Add a small, explicit pairing descriptor to companion read-only session creation
responses so future QR/code and desktop token-control surfaces can consume a
stable contract without inferring companion capability from a raw session token.

## Best End-State Architecture

Companion pairing should remain a gateway-scoped session flow. Trusted operator
surfaces use an existing gateway credential to issue a `companion_read_only`
session, then present a pairing descriptor that tells the companion client which
header to use, which status URL to open, which read-only routes are allowed,
and which control capabilities are forbidden. The descriptor must not duplicate
the raw session token; the existing `resume.token` field remains the only raw
token carrier in this endpoint response.

This keeps the security boundary in the HTTP gateway and gives later desktop UI
and QR-code work a deterministic payload to render.

## Slice Boundary

This slice only extends `POST /v1/melix/auth/session` responses for
`scope = companion_read_only`.

Included:

- a `pairing` response object for companion sessions;
- schema, scope, header name, status URL, allowed routes, forbidden capability
  names, token transport, and expiry metadata;
- focused Swift tests proving the pairing object is returned for companion
  sessions, absent for operator sessions, and does not duplicate the raw token;
- runbook documentation for companion session creation.

Excluded:

- QR image/code rendering;
- desktop UI controls for issuing or revoking tokens;
- mobile/narrow viewport smoke;
- LAN discovery or public internet exposure;
- changing the existing route authorization allowlist.

## Performance Probes and Metrics

- Runtime metric: existing persistent-session metrics continue to cover active,
  remembered, expired, restore, and sign-out counts. This slice does not add a
  new runtime metric because response assembly is a fixed-size DTO projection on
  the existing auth-session route.
- Observability mode: `minimal`, using existing route/session metrics only.
- Probe overhead: N/A; no sampled or debug probe is introduced.
- PR merge gate: scoped performance report must remain `Status: ok` with zero
  regressions.

## Implementation Plan

1. Add a failing Swift gateway test that creates a remembered
   `companion_read_only` auth session and expects `pairing.schema_version =
   melix.companion.pairing.v1`, `pairing.status_url`, `pairing.resume_header`,
   `pairing.token_transport = resume_header`, read-only route entries, and
   forbidden mutating capability names. Assert `pairing` does not contain the
   raw `resume.token`.
2. Add an adjacent regression assertion proving ordinary operator-control
   session creation still has no `pairing` object.
3. Extend `OpenAIAuthSessionResponse` with optional `pairing` and populate it
   only when the issued session scope is `companion_read_only`.
4. Derive the status URL from the active gateway runtime binding as
   `http://<host>:<port>/v1/melix/companion/status`.
5. Update `docs/runbooks/persistent-sessions.md` with a companion pairing
   creation example and safe-token note.
6. Run focused tests, changed-line coverage, full local gate, pre-commit
   performance report, then PR monitoring.

## Verification

Focused Swift tests:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companionAuthSessionCreationReturnsPairingDescriptor|gatewayAuthSessionsCanBeCreatedReusedAndRevoked|companionAuthSessionsCanReadStatusAndRevokeThemselvesButCannotMutateRuntime)'
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIHandlerTests/(companionAuthSessionCreationReturnsPairingDescriptor|gatewayAuthSessionsCanBeCreatedReusedAndRevoked|companionAuthSessionsCanReadStatusAndRevokeThemselvesButCannotMutateRuntime)'
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift
```

Verification results on 2026-06-15:

- Red check: `OpenAIHandlerTests/companionAuthSessionCreationReturnsPairingDescriptor`
  failed before implementation because `payload["pairing"]` was absent.
- Red check: after changing the test binding host to `0.0.0.0`, the same test
  failed because `pairing.status_url` exposed `0.0.0.0` instead of the
  client-usable `127.0.0.1` URL.
- Green check: the companion pairing test passed after adding the pairing DTO
  and display-host normalization.
- Adjacent focused tests passed: 3 tests in 1 suite.
- Changed-line coverage: `TOTAL 99.29% 140/141`.
- `git diff --check`: passed.
- `make swift-test`: passed.
- `make py-test`: passed, `4014 passed, 14 skipped, 2 warnings`.
- `make integration-test`: passed, `120 passed, 1 skipped`.
- After merging `origin/main` at `36a94fd5`, focused Swift tests passed again,
  changed-line coverage remained `TOTAL 99.29% 140/141`, and
  `git diff --check` passed again.
- Review follow-up: static pairing route/capability lists were hoisted out of
  the initializer, empty bind hosts now fall back to `127.0.0.1`, IPv4 hosts are
  no longer bracketed, and IPv6 literal/bracketed hosts remain URL-safe.
- After the review follow-up, focused Swift tests passed again and changed-line
  coverage was `TOTAL 100.00% 155/155`.
- Scoped performance report:
  `.runtime/pre-commit-performance/20260614-180426-36a94fd5/report/report.md`,
  `Status: ok`, 0 regressions, 0 selected probes.

Full gate before PR:

```bash
make swift-test
make py-test
make integration-test
```

## Deferred Work

- QR/code rendering and copyable pairing sheet.
- Desktop companion-token issuance and revocation controls.
- Mobile/narrow viewport smoke for the companion status flow.
