# Task Plan

## Goal

Close `M8.8` by importing `generation_config.json` defaults into the discovered-model metadata path
and exposing OCR-specific sampling controls through the native operator shell without creating a
second settings source of truth.

## Scope

- load `generation_config.json` defaults non-destructively during worker registry discovery
- preserve explicit manifest and operator override precedence over imported defaults
- surface imported generation-config values as inspectable metadata in control-plane model state
- let operators edit OCR sampling profile, temperature, top-p, and max-token overrides from the
  existing model-settings workflow
- apply imported or overridden defaults during request shaping for text and OCR requests
- update milestone bookkeeping only after repository-default verification and changed-line coverage

## Phases

1. Worker metadata import and precedence contract
   - status: completed
   - evidence:
     - add registry-scan support for `generation_config.json`
     - import inspectable generation-config keys into model ext without overwriting explicit
       manifest values
     - cover local registry discovery precedence in Python tests
2. Control-plane sampling resolution
   - status: completed
   - evidence:
     - introduce a model-sampling policy for imported generation-config defaults
     - let OCR policies fall back to generation-config defaults when OCR-specific overrides are not
       set
     - add focused control-plane coverage for text and OCR request shaping precedence
3. Menu bar OCR sampling controls and info surface
   - status: completed
   - evidence:
     - extend runtime model state with imported generation-config and effective OCR sampling fields
     - add native model-settings controls for OCR sampling profile, temperature, top-p, and max
       tokens
     - preserve inspect-only presentation for imported defaults while edits continue to flow
       through `model.set_policy`
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - rerun focused Python, Swift, and menu bar tests for the touched paths
     - rerun repository-default verification commands for the touched scope
     - record changed-line coverage at or above `95%` and update `progress.md` plus the execution
       index

## Acceptance

- registry-discovered models import `generation_config.json` defaults into inspectable metadata when
  the file exists
- explicit manifest ext values and operator overrides continue to win over imported defaults
- text request shaping can consume imported generation-config defaults when the request and preset
  do not specify sampling values
- OCR request shaping uses OCR-specific overrides when present and otherwise falls back to imported
  generation-config defaults
- operators can edit OCR sampling controls from the native menu bar workspace and inspect effective
  generation-config/OCR defaults from control-plane state
- `M8.8` can be closed with repository-default verification and explicit coverage evidence

## Risks

- collapsing imported defaults and operator overrides into the same ext keys would make clears
  destructive and erase provenance
- request-shaping precedence can silently drift if text and OCR paths resolve defaults through
  different key hierarchies
- menu bar drafts can accidentally persist imported defaults as explicit overrides if the form is
  hydrated from effective values instead of explicit settings values

## Outcome

- m8_8_generation_config_and_ocr_sampling_controls_completed
