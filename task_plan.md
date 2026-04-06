# Task Plan

## Goal

Close `M17.2` by making real text-to-speech backend families and voice-catalog metadata
first-class across the Swift control-plane catalog, the Swift Python-bridge model-spec path,
the repository-owned family support matrix, and the macOS operator model-info surface.

## Scope

- add `Qwen3-TTS`-class speech metadata to the Swift catalog and bridge so control-plane discovery
  matches the existing Python worker registry truth
- promote real text-to-speech families into the default phase-six contract seed set so operators
  can inspect them without bespoke wiring
- extend the repository-owned family support matrix with `speech` rows and operator-visible
  capability metadata for languages, voice mode, output formats, instruction support, and voice
  catalog summaries
- expose speech-family identity and voice-catalog details in the macOS Window UI model info panel
- add or update focused Swift, Python, menubar, and integration coverage plus milestone bookkeeping

## Measurement Points

- Swift and Python catalog/bridge surfaces expose the same real `speech` families, backend IDs,
  install profiles, and voice-catalog metadata for `kokoro` and `qwen3-tts`
- the family support matrix publishes stable `speech` rows with truthful `contract_only` or
  `verified` live-path status and machine-readable metadata for voices, languages, and formats
- the operator model-info summary renders speech-family details without requiring raw `ext`
  inspection in tests or by humans
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. M17.2 boundary lock and operator metadata design
   - status: completed
   - success criteria:
     - update the active task plan to reflect the `M17.2` slice and confirm the implementation
       boundary stays inside catalog, bridge, matrix, operator metadata, and tests
     - lock the speech metadata shape to stable `melix.audio.*` keys that can be copied from
       catalog summaries into worker model specs and operator views without a protobuf expansion
2. Swift catalog and bridge parity for real TTS families
   - status: completed
   - success criteria:
     - add `mlxQwen3TTSModel()` to the Swift control-plane catalog and Python bridge
     - keep `mlxKokoroModel()` and `mlxQwen3TTSModel()` discoverable through
       `phaseSixContractSeedModels()`
     - extend focused Swift tests so deterministic speech, Kokoro, and Qwen3-TTS entries all keep
       the expected backend and voice metadata
3. Speech family matrix and integration evidence
   - status: completed
   - success criteria:
     - extend the Python family support matrix to publish `speech` rows for `kokoro` and
       `qwen3-tts`, including stable route, install-profile, voice-mode, output-format, and
       voice-catalog fields
     - expand Python and integration coverage so exported matrix rows remain machine-checkable
       across catalog, runtime routing, and matrix views
4. Operator-visible voice catalog metadata
   - status: completed
   - success criteria:
     - extend the Window UI model info state and summary view to render speech-language, voice
       mode, output formats, instruction support, and voice-catalog summary details
     - add focused menubar tests for both state assembly and rendered summary lines
5. Runbook, milestone bookkeeping, verification, and commit closure
   - status: completed
   - success criteria:
     - update the model-family support matrix runbook, the `M17.2` plan, the execution index, and
       `progress.md` once acceptance evidence lands
     - run focused coverage plus relevant repository verification, record the metrics report, and
       close the slice with a GPG-signed commit

## Acceptance

- Melix exposes real text-to-speech families consistently across the Swift catalog, Python bridge,
  Python worker registry, and operator-facing model info views
- the repository-owned family support matrix documents supported speech families with stable
  language, voice, and output metadata
- verification proves the touched executable scope at or above `95%` changed-line coverage before
  commit

## Risks

- if Swift catalog parity remains incomplete, the control plane will under-report available TTS
  families even though the Python worker already supports them
- if the matrix and operator view do not share the same metadata shape, speech-family guidance
  will drift across the repository
- if voice-catalog metadata overstates named voices or locale behavior, operator guidance becomes
  misleading before `M17.3` introduces full locale policy
