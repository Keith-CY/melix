# Task Plan

## Goal

Close `M8.9` by adding a repository-owned Homebrew distribution path with service management that
reuses Melix local-product launch semantics instead of introducing a second packaging truth.

## Scope

- define a checked-in Homebrew formula under `infra/homebrew/Formula/`
- add a Homebrew service wrapper that supervises the Melix three-process bundle
- provide repository-owned smoke commands for formula validation and service lifecycle behavior
- document install, upgrade, stop, and prune flows for the Homebrew path
- update milestone bookkeeping only after verification and changed-line coverage are recorded

## Phases

1. Homebrew distribution contract
   - status: completed
   - evidence:
     - add a checked-in formula that installs from the repository checkout
     - keep formula metadata aligned with the repository version and service wrapper contract
     - document the repository-owned Homebrew asset location under `infra/homebrew/`
2. Service wrapper and supervision path
   - status: completed
   - evidence:
     - build Homebrew service specs from the existing product layout and launch-agent semantics
     - supervise the control plane, Swift text worker, and Python worker through one Homebrew
       service entrypoint
     - expose a machine-readable manifest mode for inspection and smoke validation
3. Smoke coverage and operator docs
   - status: completed
   - evidence:
     - add deterministic formula and service smoke commands
     - add focused Python tests for Homebrew formula rendering and service supervision helpers
     - update README, `docs/README.md`, and a dedicated runbook for install and service lifecycle
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - rerun focused Python tests plus Homebrew smoke commands
     - rerun repository-default verification commands required for the touched scope
     - record changed-line coverage at or above `95%` and update `progress.md` plus the execution
       index

## Acceptance

- Melix has a checked-in Homebrew formula that installs from the repository checkout and exposes a
  service entrypoint
- the Homebrew service wrapper supervises the same three Melix runtime processes using the
  repository-owned local-product layout semantics
- repository-owned smoke commands validate both the formula contract and the deterministic service
  lifecycle path
- install, upgrade, stop, and prune behavior are documented and reproducible
- `M8.9` can be closed with explicit verification and changed-line coverage evidence

## Risks

- formula install logic can silently drift from the checked-in repository layout if the wrapper and
  formula derive repo paths independently
- a Homebrew service wrapper that invents its own runtime roots would fragment packaging truth away
  from the product-owned layout contract
- smoke coverage that validates only formula text without exercising service supervision would miss
  lifecycle regressions

## Outcome

- m8_9_homebrew_formula_and_services_completed
