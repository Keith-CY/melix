# Task Plan

## Goal

Close `M17.4` by turning speech support into a repository-owned live-path operator workflow with
backend-family integration smoke coverage, machine-readable benchmark evidence, and runbooks for
transcription plus synthesis diagnosis.

## Scope

- add lazy-load coverage on the HTTP audio routes so cataloged speech families can serve requests
  without bespoke preload wiring
- add a repository-owned speech smoke workflow that exercises `Whisper`, `Parakeet`, `Kokoro`,
  and `Qwen3-TTS` through the real local HTTP path using reproducible fake `mlx_audio` fixtures
- record backend-family and locale or voice-specific operator metrics in a stable machine-readable
  report
- update the family support matrix, runbooks, and docs index so speech families graduate from
  `contract_only` to repository-owned live-path evidence
- add focused Python, Swift, and integration coverage plus milestone bookkeeping

## Measurement Points

- `/v1/audio/transcriptions` and `/v1/audio/speech` can lazy-load cataloged speech-family models
  once runtime-pack and managed-model prerequisites are satisfied
- the repository-owned speech smoke report records reproducible checks and metrics for
  `melix-whisper-mlx`, `melix-parakeet-mlx`, `melix-kokoro-mlx`, and `melix-qwen3-tts-mlx`
- speech-family live-path evidence distinguishes backend family, locale resolution, and
  voice-specific synthesis behavior rather than collapsing everything into one generic audio probe
- the support matrix and runbooks point operators to concrete proof commands and integration tests
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. M17.4 boundary lock and runtime-smoke design
   - status: completed
   - success criteria:
     - lock the slice to audio-route lazy loading, backend-family smoke evidence, runbooks, and
       coverage without expanding unrelated API contracts
     - define the stable report shape for transcription families, synthesis families, locale
       evidence, and voice-specific synthesis behavior
2. Live-path speech-family execution
   - status: completed
   - success criteria:
     - enable on-demand loading for cataloged audio models on the HTTP transcription and speech
       paths
     - add a repository-owned fake `mlx_audio` package injection path for integration smoke so
       `Whisper`, `Parakeet`, `Kokoro`, and `Qwen3-TTS` can run end to end without network or
       heavyweight backend dependencies
3. Metrics report and support-matrix graduation
   - status: completed
   - success criteria:
     - add a machine-readable speech smoke report builder plus a reproducible script or make target
     - promote speech and transcription family rows in the support matrix from `contract_only` to
       verified live-path evidence backed by the new integration smoke
4. Runbooks, verification, and milestone closure
   - status: completed
   - success criteria:
     - add or update runbooks and docs indexes for speech smoke execution, dependency setup, and
       failure diagnosis
     - run focused coverage plus the relevant repository verification, record a metrics report, and
       close `M17.4` with a GPG-signed commit

## Acceptance

- speech-family HTTP paths are reproducibly live-verified rather than only contract-described
- operator evidence records transcription plus synthesis latency and backend-specific locale or
  voice behavior for the supported speech families
- support-matrix rows, smoke scripts, and runbooks stay aligned and test-covered

## Risks

- if audio routes still depend on bespoke preload state, speech-family smoke coverage will remain
  fragile and operator evidence will not generalize beyond dev models
- if fake `mlx_audio` injection diverges from the runtime contract, smoke evidence will become less
  trustworthy than the unit tests
- if the support matrix is promoted without a reproducible smoke script, `verified` status will
  overstate repository guarantees
