# Task Plan

## Goal

Close `M8.6` by persisting admin-surface tool-section navigation in the operator session state,
adding a repository-owned state-persistence smoke command, and documenting the offline-owned
desktop admin assets contract.

## Scope

- persist `selectedToolSection` alongside the existing operator-session state
- keep persisted-state decoding backward compatible with pre-`selected_tool_section` payloads
- add a focused menu bar smoke suite that proves persistence, restore, and secure file ownership
- wrap the Swift smoke in a repository-owned `scripts/m8_admin_state_smoke.py` command
- document the persistence and offline-assets behavior in `docs/runbooks/`
- update milestone bookkeeping after verification

## Phases

1. Tool-section persistence behavior
   - status: completed
   - evidence:
     - add failing runtime-view-model coverage for persisted and restored tool sections
     - wire `OperatorSessionState` and `RuntimeViewModel` to save and restore `selectedToolSection`
     - keep legacy payloads compatible when `selected_tool_section` is absent
2. Repository-owned smoke and docs
   - status: completed
   - evidence:
     - add `OperatorSessionPersistenceSmokeTests`
     - add `scripts/m8_admin_state_smoke.py`
     - add Python coverage for the smoke wrapper
     - add a dedicated runbook for admin-surface persistence and offline assets
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - rerun the relevant Swift, Python, smoke, and repository-default verification commands
     - record changed-line coverage at or above `95%` for the touched executable scope
     - update `progress.md`, `docs/plans/2026-03-30-m8-6-tab-persistence-and-offline-admin-assets.md`, and the execution index

## Acceptance

- selecting a tool section persists it into the operator-session file and restores it across restart
- old operator-session payloads without `selected_tool_section` still restore safely
- a repository-owned smoke command proves persistence, restore, secure permissions, and zero
  external admin-asset references
- the M8.6 plan, runbook, and execution index describe the real repository state

## Risks

- changing the operator-session schema can break restore for existing local state if decoding is not
  backward compatible
- the Python smoke wrapper can fail inside restricted environments if it relies on SwiftPM sandbox
  defaults instead of repository-controlled flags
- documenting offline-owned assets too loosely can create a false claim if remote admin assets are
  added later without updating the runbook

## Outcome

- m8_6_admin_state_persistence_completed
