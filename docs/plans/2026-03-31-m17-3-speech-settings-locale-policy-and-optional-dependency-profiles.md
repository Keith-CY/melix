# M17.3 Speech Settings, Locale Policy, And Optional Dependency Profiles

## Goal

Make speech backend selection, locale defaults, and optional dependency profiles explicit so speech behavior can be configured and diagnosed without source inspection.

## Scope

- add locale-aware speech settings
- define precedence for model defaults, packaged defaults, and request overrides
- expose optional dependency profile state and missing-backend failures

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- Missing dependency profiles must fail fast with actionable operator-visible errors.
- Locale policy should remain inspectable after precedence resolution.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Speech settings and locale policy are explicit, inspectable, and test-covered.
- Optional dependency profiles do not fail silently when requested backends are unavailable.
