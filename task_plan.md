# Task Plan

## Goal

Close `M17.1` by making real speech-to-text backend families first-class across the Melix catalog,
the Swift Python-bridge path, and the repository-owned model-family support matrix.

## Scope

- add `Parakeet`-class transcription metadata to the Swift catalog and bridge so control-plane
  discovery stays aligned with the existing Python worker registry
- extend the repository-owned family support matrix and runbook coverage to include supported
  speech-to-text backend families and their capability metadata
- add or update focused Python, Swift, and integration coverage for transcription-family routing,
  catalog metadata, and matrix rows
- update milestone bookkeeping once acceptance is met

## Measurement Points

- Swift and Python catalog surfaces expose the same transcription backend families and backend IDs
- the family support matrix includes stable rows for `whisper` and `parakeet` with truthful support
  status and capability metadata
- integration coverage proves the matrix exports the new transcription-family rows instead of only
  text, embedding, rerank, and image families
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. M17.1 boundary lock and gap confirmation
   - status: completed
   - evidence:
     - reviewed the dedicated `M17.1` plan, the umbrella `M17` roadmap slice, the current Swift
       catalog and Python bridge implementations, and the existing family support matrix coverage
     - confirmed the Python worker already exposes `whisper` and `parakeet` transcription families,
       while the remaining gaps are Swift catalog parity and repository-owned matrix/runbook
       coverage
2. Swift catalog and bridge parity
   - status: completed
   - evidence:
     - added `mlxParakeetModel()` to `ModelCatalog.swift`, promoted `melix-whisper-mlx` and
       `melix-parakeet-mlx` into the default phase-six contract seed set, and kept the real
       speech-to-text families discoverable through the shared control-plane catalog path
     - added the matching `melix-parakeet-mlx` bridge spec in
       `PythonBridgeWorkerClient.swift` and extended focused Swift tests so transcription metadata
       parity is enforced for deterministic, Whisper, Parakeet, and Kokoro entries
3. Speech family matrix and integration evidence
   - status: completed
   - evidence:
     - extended the Python family support matrix to publish `transcription` rows for `whisper` and
       `parakeet`, including stable `backend_id`, `install_profile`, and `languages` fields with
       truthful `contract_only` live-path status
     - expanded Python and integration coverage so exported matrix rows include the new
       speech-to-text families and remain machine-checkable across catalog, runtime, and matrix
       views
4. Runbook and milestone bookkeeping
   - status: completed
   - evidence:
     - updated the model-family support matrix runbook to describe speech-to-text backend families,
       capability fields, and support-status semantics alongside the existing text, embedding,
       rerank, and image guidance
     - updated `progress.md`, the `M17.1` plan, and the execution index together once acceptance
       and verification evidence landed
5. Verification and commit closure
   - status: completed
   - evidence:
     - focused Python verification passed with `62 passed in 176.80s`, focused Swift verification
       passed with `85 tests in 2 suites`, full `make py-test` passed with `531 passed in 35.07s`,
       and full `make integration-test` passed with `74 passed in 1013.15s`
     - changed-line coverage reached `100.00%` for both touched Python (`35/35`) and touched Swift
       (`76/76`) scope, while `make swift-test` reproduced the pre-existing
       `services/control-plane-swift` repository-wide hang after focused touched-scope suites had
       already passed

## Acceptance

- Melix exposes `Whisper`-class and `Parakeet`-class speech-to-text models consistently across the
  Swift catalog, bridge, and Python worker registry
- the repository-owned family support matrix documents supported speech-to-text backend families
  with stable capability metadata
- verification proves the touched executable scope at or above `95%` changed-line coverage before
  commit

## Risks

- if Swift catalog parity is incomplete, control-plane surfaces will drift from the Python worker
  truth even though the backend already supports the family
- if the family support matrix overstates live support, operator guidance will stop being reliable
- if integration coverage only checks catalog entries and not exported matrix rows, future changes
  can silently drop speech-family visibility
