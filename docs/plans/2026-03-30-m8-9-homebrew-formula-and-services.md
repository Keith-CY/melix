# M8.9 Homebrew Formula And Services

## Goal

Add Homebrew-based distribution and service management so Melix can be installed and managed through standard local packaging flows.

## Scope

- define a Homebrew formula
- support service management through Homebrew
- document the install, upgrade, and service lifecycle

## Files

- create `infra/homebrew/`
- update `docs/runbooks/`
- update `README.md`
- update `docs/README.md`

## Implementation Notes

- package metadata should remain aligned with Melix release artifacts and startup behavior
- service management should reuse product-owned launch semantics
- documentation should distinguish development startup from packaged service operation

## Verification

- package validation command for the touched scope
- service lifecycle smoke command for the touched scope

## Acceptance

- Melix has a repository-owned Homebrew distribution plan with service support
- install and service behavior are documented and reproducible
