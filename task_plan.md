# Task Plan

## Goal

Close `M17.3` by making speech locale policy, resolved speech settings, and optional dependency
profile state explicit across the OpenAI audio-speech request path, the Swift control-plane model
catalog, and the macOS operator model-info surface.

## Scope

- add locale-aware speech request normalization without expanding protobuf contracts
- define and expose precedence for request locale, model default locale, and packaged default locale
- surface audio dependency profile state through existing install-profile and runtime-pack metadata
- extend operator-visible model info so speech settings and dependency state are inspectable
- add focused Swift, menubar, and integration coverage plus milestone bookkeeping

## Measurement Points

- `/v1/audio/speech` accepts an explicit `locale` field and publishes resolved locale metadata
  through operator-visible response headers
- control-plane and operator surfaces expose stable speech metadata for locale policy, model
  defaults, packaged defaults, and dependency-profile state
- missing runtime-pack or managed-model state remains actionable and explicit rather than silent
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. M17.3 boundary lock and settings contract
   - status: completed
   - success criteria:
     - lock the `M17.3` slice to request normalization, speech metadata, operator surfaces, and
       tests without expanding worker protobufs
     - define the stable `melix.audio.*` keys for locale policy, default locale, packaged default
       locale, and dependency-profile state
2. Speech request normalization and HTTP exposure
   - status: completed
   - success criteria:
     - extend the OpenAI audio-speech request contract with an optional `locale`
     - resolve locale precedence as `request > model default > packaged default`
     - publish resolved locale and dependency-profile state through response headers and focused
       HTTP/control-plane tests
3. Catalog and operator metadata parity
   - status: completed
   - success criteria:
     - add locale-policy metadata to speech-capable seed models in the Swift catalog and Python
       worker registry truth
     - extend the Window UI model-info state and summary view to render locale defaults, packaged
       defaults, runtime-pack state, runtime-pack ID, and managed-model state
4. Verification, runbook, and milestone closure
   - status: completed
   - success criteria:
     - update the relevant runbook, the `M17.3` plan, the execution index, and `progress.md`
     - run focused coverage plus relevant repository verification, record the metrics report, and
       close the slice with a GPG-signed commit

## Acceptance

- speech locale policy is explicit, inspectable, and test-covered
- dependency profile state and required setup actions remain operator-visible and actionable
- verification proves the touched executable scope at or above `95%` changed-line coverage before
  commit

## Risks

- if locale policy exists only in the HTTP handler and not in catalog metadata, operator guidance
  will drift from runtime behavior
- if response headers and UI state use different precedence rules, speech debugging becomes
  misleading
- if dependency-profile state stays implicit, first-use failures will remain hard to diagnose
