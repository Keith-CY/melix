# M17 Speech Backends And Voice Catalog

## Goal

Upgrade Melix from contract-shaped speech support into a real local speech platform with named speech-to-text and text-to-speech backends, multilingual voice catalogs, locale-aware defaults, and reproducible operator guidance.

## Scope

- add real speech-to-text backend adapters
- add real text-to-speech backend adapters and voice catalogs
- define locale, voice, and dependency policy for speech workflows
- publish speech benchmarks, compatibility matrices, and operator evidence

## Coverage

- speech-to-text backend coverage for `Whisper`-class and `Parakeet`-class models
- text-to-speech backend coverage for `Kokoro`-class models and multilingual native-voice paths
- locale-aware voice selection and fallback policy
- operator-visible backend capability metadata, including languages, voices, formats, and install profile requirements
- optional audio dependency profiles that keep non-audio installs lightweight while preserving clear upgrade paths
- speech benchmarks for transcription throughput, transcription latency, synthesis latency, and per-voice output behavior

## Execution Slices

- `M17.1` Speech-to-text backend adapters and model matrix
- `M17.2` Text-to-speech backend adapters and multilingual voice catalog
- `M17.3` Speech settings, locale policy, and optional dependency profiles
- `M17.4` Speech integration benchmarks, runbooks, and operator evidence

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/engine/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/Requests/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`
- update `docs/runbooks/`

## Implementation Notes

- Speech backends should remain capability-driven and adapter-driven rather than being hardcoded into one monolithic audio runtime.
- Locale and voice defaults must remain inspectable after precedence resolution between packaged defaults, model defaults, and per-request overrides.
- Optional audio dependency profiles must fail clearly when a requested backend is unavailable.
- Benchmark evidence should distinguish backend quality tiers from pure latency measurements so operator guidance stays honest.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- speech-backend smoke command for the touched scope

## Acceptance

- Melix exposes real speech backend families with stable capability metadata and routing behavior.
- Voice selection, locale policy, and dependency-profile state are operator-visible and test-covered.
- Speech benchmarks and runbooks record concrete transcription and synthesis evidence for supported backend classes.
