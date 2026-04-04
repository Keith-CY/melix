# Task Plan

## Goal

Close `M8.10` by adding repository-owned update checks, install-manifest startup diagnostics, and
operator-visible startup failure handling for packaged Melix installs without introducing a second
runtime-control truth outside the existing local-product layout.

## Scope

- extend packaged install metadata with product version, update-channel, log-path, and host-port
  diagnostics fields
- add deterministic update-check and startup-failure classification helpers plus a repository-owned
  smoke command
- enrich menu bar startup failure messaging and desktop/status surfaces with packaged product
  signals
- update runbooks and milestone bookkeeping only after verification and changed-line coverage are
  recorded

## Phases

1. Install-manifest and update-feed foundations
   - status: completed
   - evidence:
     - extend `install_assets.py` with versioned manifest metadata and optional available-port
       selection
     - add a repository-owned update-channel file and deterministic version-comparison helpers
     - keep the packaged-install manifest authoritative for ready probe, log locations, and update
       inputs
2. Startup failure diagnostics and smoke coverage
   - status: completed
   - evidence:
     - add deterministic startup-failure classification helpers for host-port conflict, crash, and
       hang cases
     - add a repository-owned smoke command that exercises update detection plus startup-failure
       classification
     - cover the touched Python scope with focused tests
3. Menu bar projection and operator messaging
   - status: completed
   - evidence:
     - add a packaged-product signal provider for update status and startup diagnostics
     - project the resulting status into the startup error copy plus the existing menu/desktop
       surfaces without introducing banner-dismissal policy yet
     - cover the touched Swift scope with focused tests
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - rerun focused Python and Swift verification for the touched scope
     - rerun repository-default verification commands required by the touched code paths
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M8.10`
       completed in the execution index

## Acceptance

- packaged Melix installs can detect update availability from a repository-owned update feed
- install-manifest metadata supports actionable startup failure diagnostics, including host-port
  conflicts, crash clues, and hang fallback
- the native menu bar operator shell surfaces packaged-product update state and richer startup
  failure guidance without relying on heuristic banners
- a deterministic startup-failure smoke command and focused tests cover the touched productization
  and menu bar paths
- `M8.10` can be closed with explicit verification and changed-line coverage evidence

## Risks

- update checks that bypass the install manifest would create packaging truth that the operator UI
  cannot explain or reproduce
- startup diagnostics that only mirror the original handshake error would fail to give actionable
  host-port and log guidance for packaged installs
- premature banner work would overlap with `M15.2` and blur the boundary between state foundations
  and later runtime-signal presentation policy

## Outcome

- m8_10_auto_update_and_startup_failure_handling_completed
