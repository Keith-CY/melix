# Task Plan

## Goal

Close `M15.3` by persisting desktop download-queue state across shell restarts, restoring
paused-download metadata from registry-backed truth, and surfacing readable recovery or queue
signals in the Window UI and status menu.

## Scope

- persist download-queue rows through `OperatorSessionStore` so the shell can reopen with the last
  known queue state before live refresh completes
- extend model-operations registry download rows with the metadata needed for shell-side resume and
  operator inspection
- hydrate the desktop Downloads surface from `registry_snapshot`, not from ad hoc UI-local guesses
- add operator-visible resume actions, progress text, and queue-aware banner or status messaging
- verify the slice with focused Swift plus Python coverage and a restart-oriented download recovery
  smoke path

## Measurement Points

- reopening the shell restores persisted download rows before live control-plane refresh completes
- `registry_snapshot` download rows include stable resume metadata such as `output_dir` and resume
  readiness
- stalled or partial downloads surface a recovery signal and can re-dispatch `download` with the
  original output directory
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Current-state review and failing-test definition
   - status: completed
   - evidence:
     - reviewed `M15.3`, the worker download pipeline, job registry download rows, desktop
       download workflows, and operator-session persistence
     - confirmed the current shell only shows `lastModelOperation`, does not persist queue rows,
       and does not parse the existing `downloads` payload returned by `registry_snapshot`
2. Download queue persistence and resume metadata
   - status: completed
   - evidence:
     - extended the worker model-ops registry snapshot so download rows now expose `output_dir`
       and machine-readable `resume_ready` state derived from partial bytes plus terminal status
     - persisted `downloadQueue` through `OperatorSessionStore` schema version `3` so the Window
       shell can reopen with last-known queue truth before a live refresh finishes
     - stabilized download destinations under per-model temp roots so resumed downloads reuse the
       original output directory and mirror metadata deterministically
3. Window UI hydration, recovery actions, and shared signal updates
   - status: completed
   - evidence:
     - `RuntimeViewModel` now parses `downloads` rows from `registry_snapshot`, restores them from
       operator-session state, and surfaces queue-aware desktop signals for active or recoverable
       downloads
     - the desktop Downloads section now renders queue rows with readable progress, transfer
       details, output-directory inspection, refresh, and `Resume Download` actions when recovery
       is possible
     - the status menu now surfaces download-recovery titles from the same shared signal state used
       by the workspace banner
4. Focused coverage, metrics, and milestone bookkeeping
   - status: completed
   - evidence:
     - focused Swift coverage command for `RuntimeViewModelTests|DesktopFoundationViewTests|StatusMenuTests`
       passed with `254 tests in 3 suites`
     - Swift changed-line coverage for the touched menu-bar scope is `97.42%` (`793/814`)
     - focused Python download tests passed and Python changed-line coverage for the touched worker
       scope is `100.00%` (`4/4`)
     - `make py-test` passed with `501 passed`; `make swift-test` still fails outside the touched
       scope when `services/mlx-text-worker-swift` exits with unexpected signal `11`

## Acceptance

- paused downloads are visible again after restarting the desktop shell
- queue state and recovery behavior come from persisted or registry-backed truth rather than UI
  heuristics
- the touched executable scope is covered well enough to keep changed-line coverage at or above
  `95%`

## Risks

- if queue state is restored only from `lastModelOperation`, the shell will drop long-running or
  paused downloads after restart
- if resumed downloads do not preserve the original output directory, partial bytes cannot be
  reused deterministically
- if download signals are dismissible or lower-priority than non-actionable notices, operators will
  miss stalled-transfer recovery work
