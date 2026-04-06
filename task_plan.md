# Task Plan

## Goal

Close `M15.2` by unifying update availability and runtime-state messaging into one shared desktop
signal model, adding dismissible update banners with persisted policy, and aligning the workspace
banner plus status-menu surfaces to the same prioritized signal truth.

## Scope

- add a shared desktop signal or banner model with explicit priority and dismissibility
- make update-availability signals dismissible and persist dismissal state through operator-session
  storage without hiding critical runtime recovery signals
- route the workspace banner and status menu through the same runtime or update signal source
- add focused menu-bar tests for dismissal, persistence, and unified status-menu or workspace
  rendering
- update milestone bookkeeping once the slice is verified and committed

## Measurement Points

- update availability appears as a dismissible banner only when it is actionable or when update
  checks fail
- dismissing an update signal suppresses it across restart until the update summary changes
- critical runtime banners remain non-dismissible and keep priority over update notices
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Current-state review and signal-gap mapping
   - status: completed
   - evidence:
     - reviewed `M15.2`, the current workspace banner logic, `StatusMenu`, and update-status
       refresh paths and confirmed that runtime signals, audio warnings, and update availability are
       currently rendered through separate branches with no shared dismissal policy
     - confirmed the main gap is inside the desktop shell package: runtime truth already exists, but
       the menubar surfaces do not consume it through one prioritized signal model
2. Shared signal model and dismissal persistence
   - status: completed
   - evidence:
     - extended banner state with stable ids and dismissibility, persisted dismissed banner ids in
       `OperatorSessionState`, and added a runtime-view-model dismissal entry point
     - made update availability and update-check-failure signals map into the same shared signal
       list while preserving critical runtime or session banners ahead of update notices
3. Surface unification
   - status: completed
   - evidence:
     - updated the workspace banner view and status menu to consume the shared top-priority desktop
       signal instead of independent ad hoc update or runtime branches
     - kept foundation settings rows intact so update detail remains inspectable even after a banner
       is dismissed
4. Focused coverage, metrics, and milestone bookkeeping
   - status: completed
   - evidence:
     - ran coverage-enabled focused menu-bar verification, changed-line coverage reporting,
       `git diff --check`, repository `make swift-test`, and repository `make integration-test`
     - captured the existing out-of-scope `services/mlx-text-worker-swift` `signal 11` failure
       boundary while the touched menu-bar suites and repository integration tests passed

## Acceptance

- update banners and runtime signals derive from one shared desktop signal source
- dismissing an update banner persists according to policy without hiding critical runtime recovery
  signals
- the touched menu-bar scope is test-covered well enough to keep changed-line coverage at or above
  `95%`

## Risks

- if update dismissal ids are not version-specific, dismissing one update can hide future update
  notifications unintentionally
- if status menu and workspace banner do not consume the same prioritized signal, operator messaging
  will remain inconsistent across surfaces
- if runtime critical banners become dismissible by accident, the slice will violate the product
  policy in `M15.2`

## Outcome

- m15_2_update_banners_and_runtime_signal_unification_completed
