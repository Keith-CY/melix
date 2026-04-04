# Task Plan

## Goal

Close `M8.7` by completing the operator-visible per-model settings surface so menu bar users can
inspect and update typed model settings, including type override, TTL, adaptive thinking, fallback
flags, and merged effective settings.

## Scope

- expand the model-settings edit path beyond alias/pin/memory/acceleration-only controls
- keep control-plane policy parsing typed for adaptive thinking and existing model settings fields
- make effective settings visible from menu bar state without inventing a second source of truth
- preserve OCR and parser-related defaults as read-only effective settings ahead of `M8.8`
- update milestone bookkeeping only after repository-default verification and changed-line coverage

## Phases

1. Typed settings contract and control-plane parsing
   - status: completed
   - evidence:
     - audit `ModelSettings` fields and existing `model.set_policy` mapping
     - add missing typed parsing for adaptive-thinking controls while preserving existing ext passthrough
     - add focused control-plane coverage for the new typed settings fields
2. Menu bar operator surface and effective settings visibility
   - status: completed
   - evidence:
     - extend runtime model row/info state to surface type override, TTL, adaptive thinking, fallback, and effective OCR/parser defaults
     - add menu bar draft state and apply actions for the expanded model settings form
     - render the completed settings surface in the desktop workspace without breaking existing model tooling flows
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - run focused red/green tests for control plane and menu bar settings flows
     - rerun repository-default verification commands for the touched scope
     - record changed-line coverage at or above `95%` and update `progress.md` plus the execution index

## Acceptance

- operators can update alias, type override, TTL, pin-on-load, memory policy, acceleration mode,
  acceleration profile, adaptive thinking mode, adaptive thinking budget, and parser fallback from
  the native menu bar workspace
- the menu bar model info surface shows effective typed settings and merged OCR/parser defaults from
  control-plane state
- control-plane parsing remains deterministic and non-destructive for typed settings and ext-backed
  fallbacks
- `M8.7` can be closed with repository-default verification and explicit coverage evidence

## Risks

- overloading the existing settings action with loosely named string keys can create silent parsing
  drift between menu bar and control plane if typed keys are not normalized
- exposing effective settings from the wrong source can make the operator surface diverge from the
  control-plane snapshot
- broadening the menu bar model form without tight tests can regress existing latency-profile and
  model-info flows

## Outcome

- m8_7_model_settings_completion_completed
