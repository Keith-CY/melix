# Issue 1759 Companion Read-Only Auth Scope

## Goal

Land the first executable server-side slice for issue #1759 by giving paired
companion/mobile clients a durable read-only session scope before building the
mobile dashboard surface.

## Best End-State Architecture

Companion access should be a scoped gateway session, not another shared API key
family. The operator should create or revoke companion sessions through trusted
local UI/CLI pairing, while the HTTP gateway enforces a narrow read-only
allowlist regardless of which browser or LAN client presents the token.

The durable model is:

- gateway credentials remain the authority that can issue sessions;
- session metadata records an explicit `operator_control` or
  `companion_read_only` scope;
- companion sessions can read status-oriented endpoints and inspect/revoke their
  own session;
- companion sessions cannot start inference, mutate runtime state, run jobs, or
  receive raw request bodies in denial responses;
- later slices can add QR/code pairing and a mobile viewport without changing
  the authorization contract.

## Slice Boundary

This transaction implements the auth and route-enforcement foundation only.
It does not add a production companion UI, QR-code pairing, LAN discovery, or a
new protocol message.

## Implementation Plan

1. Extend `PersistentAuthSessionStore` metadata and persistence with a
   backwards-compatible session scope.
2. Allow `POST /v1/melix/auth/session` to request
   `{ "scope": "companion_read_only" }`, defaulting omitted scope to
   `operator_control`.
3. Teach `OpenAIHandler` to allow companion sessions only on status/discovery
   GET routes plus self-inspection and self-revocation.
4. Return a structured 403 for companion scope violations and increment a
   gateway metric.
5. Cover token creation, read access, mutation rejection, private-prompt
   non-echoing, and revocation with focused Swift tests.

## Performance Probes and Metrics

- Authorization overhead remains on the existing HTTP gateway route admission
  path; no new worker or model runtime path is introduced.
- Runtime metric: `companion_auth.rejected_request_count` records rejected
  companion-scope requests.
- Success metric: companion read-only requests preserve existing
  `operator.health_diagnostics_latency_ms`, `operator.cache_stats_latency_ms`,
  and gateway rate-limit metrics for allowed status routes.
- PR merge gate: the scoped performance report must stay `Status: ok` with zero
  regressions. This slice does not add a synthetic PR-scoped probe because the
  changed path is Swift gateway authorization logic, not a repeated Python
  performance workload.

## Verification

Run focused Swift tests first:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests'
```

Before commit and PR:

```bash
make swift-test
make py-test
make integration-test
```

The pre-commit hook must also produce a scoped performance report with no
regressions before the branch is pushed.

## Verification Results

- `PersistentAuthSessionStoreTests|OpenAIHandlerTests`: passed, 216 tests.
- Swift changed-line coverage for the changed gateway files: 99.34 percent
  total, 301/303 changed lines covered.
- `PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests`:
  passed, 430 tests.
- `make swift-test`: passed.
- `make py-test`: passed, 3999 tests, 14 skipped.
- `make integration-test`: passed, 120 tests, 1 skipped.

## Deferred Work

- QR/code pairing UX.
- Mobile/narrow viewport dashboard smoke.
- Status cards for active jobs, recent receipts, and log-tail redaction.
- Companion-token issuance and revocation controls in the desktop UI.
