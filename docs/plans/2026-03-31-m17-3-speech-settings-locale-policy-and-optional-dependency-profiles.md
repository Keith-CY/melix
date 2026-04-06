# M17.3 Speech Settings, Locale Policy, And Optional Dependency Profiles

Status: completed on 2026-04-06. Melix now resolves speech locale precedence as
`request > model_default > packaged_default`, exposes the resolved contract through `/v1/audio/speech`
response headers, projects the same metadata into the Swift control-plane catalog and macOS
operator model-info surface, and keeps optional runtime-pack plus managed-model state explicit
through existing `melix.audio.*` metadata.

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

- focused Swift control-plane tests and changed-line coverage for the OpenAI audio-speech path,
  model catalog, and Python bridge metadata
- focused Swift menubar tests and changed-line coverage for speech model-info rendering
- focused Python worker plus integration tests and changed-line coverage for speech metadata and
  support-matrix exports
- `make swift-test`
- `make integration-test`

## Acceptance

- Speech settings and locale policy are explicit, inspectable, and test-covered.
- Optional dependency profiles do not fail silently when requested backends are unavailable.
