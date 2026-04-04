# Task Plan

## Goal

Close the first executable `M9.4` slice by landing persistent gateway auth sessions with remember-me restore, deterministic revocation or expiry behavior, operator-visible snapshot metrics, and repository-owned smoke coverage.

## Scope

- add a dedicated persistent auth-session store under the control-plane HTTP gateway
- restore remembered sessions at bootstrap and reconcile them against the active gateway key policy
- expose gateway session create, inspect, and sign-out routes with structured session-state errors
- project remembered-session state into the menu bar server-session shell and add a runbook plus smoke script
- record changed-line coverage and milestone status so `M9.5` starts from an accurate repository baseline

## Phases

1. Persistent gateway session store and bootstrap restore
   - status: completed
   - evidence:
     - `PersistentAuthSessionStore.swift` now persists hashed remembered-session records under `MELIX_HOME/state/persistent-auth-sessions.json` or `~/.melix/state/persistent-auth-sessions.json`
     - `Bootstrap/main.swift` restores remembered sessions at startup, reconciles them against the live gateway policy, initializes `persistent_session.*` metrics, and now parses `DELETE` requests for sign-out
     - `ControlPlaneService.swift` reconciles remembered sessions whenever gateway access policy changes
2. Gateway route enforcement and session-state errors
   - status: completed
   - evidence:
     - `OpenAIHandler.swift` now supports `POST|GET|DELETE /v1/melix/auth/session`
     - gateway authorization first validates `x-melix-session` for non-create routes and returns structured `missing`, `revoked`, and `expired` session-state payloads
     - remember-me creation now requires a configured gateway credential instead of unauthenticated local trust
3. Operator projection, runbook, and smoke coverage
   - status: completed
   - evidence:
     - the menu bar now projects active remembered-session counts, expiry-prune counts, retention TTL, and sign-out latency through `DesktopServerSessionState`
     - `docs/runbooks/persistent-sessions.md` documents the restore, revoke, and expiry workflow
     - `scripts/m9_persistent_session_smoke.py` and `tests/integration/test_persistent_sessions.py` provide deterministic repository-owned coverage
4. Verification, coverage, and milestone backfill
   - status: completed
   - evidence:
     - control-plane changed-line coverage: `99.15%` (`1047/1056`)
     - menu bar changed-line coverage: `100.00%` (`183/183`)
     - Python smoke and integration changed-line coverage: `95.48%` (`190/199`)
     - aggregate changed-line coverage for the touched executable scope: `98.75%` (`1420/1438`)

## Acceptance

- remembered gateway sessions survive restart only when `remember_me` was requested
- non-remembered gateway sessions do not restore after restart
- invalid, expired, revoked, and missing gateway sessions return structured session-state metadata
- operator-visible snapshot state exposes remembered-session counts, retention TTL, and sign-out latency without leaking raw secrets
- changed-line coverage for the touched executable scope is at least `95%`

## Risks

- repository-owned integration and smoke flows currently reuse a fixed local control-plane port, so they must run sequentially to avoid `Address already in use` during verification

## Outcome

- the M9.4 persistent-session foundation transaction is ready for commit and roadmap closure
