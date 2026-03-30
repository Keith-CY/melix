# M17.2 Text-To-Speech Backend Adapters And Multilingual Voice Catalog

## Goal

Add real text-to-speech backend families and a multilingual voice catalog so Melix can expose voice-aware synthesis behavior rather than a generic speech placeholder.

## Scope

- add `Kokoro`-class backend adapters and multilingual native-voice support
- expose voice, language, and output-format metadata
- validate per-voice synthesis routing and fallback behavior

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- Voice identity should be first-class metadata, not an unstructured string buried inside request arguments.
- Fallback behavior must be deterministic when a requested language or voice is unavailable.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Text-to-speech backends and voices are operator-visible, routable, and test-covered.
- Voice and language fallback behavior remains explicit and reproducible.
