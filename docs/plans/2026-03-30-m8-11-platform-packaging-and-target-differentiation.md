# M8.11 Platform Packaging And Target Differentiation

## Goal

Define platform packaging and Apple Silicon target differentiation so Melix can package optimized product variants without fragmenting the runtime model.

## Scope

- define target differentiation strategy
- preserve one logical product identity across packaging variants
- keep packaging outputs compatible with install and update flows

## Files

- update `infra/`
- update `docs/runbooks/`
- update `README.md`
- update `docs/README.md`

## Implementation Notes

- target differentiation should remain explicit in packaging metadata and documentation
- packaging variants should not create diverging protocol or operator semantics
- keep the path open for future hardware-specific optimizations without product confusion

## Verification

- packaging validation command for the touched scope

## Acceptance

- Melix has a repository-owned plan for packaging differentiation across supported targets
- packaging behavior is documented and compatible with install and update flows
