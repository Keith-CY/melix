# M4.7 OCR Prompting And Sampling Profiles

## Goal

Add OCR-family-specific prompting, stop-token handling, and default sampling profiles so OCR behavior is model-aware rather than generic.

## Scope

- add OCR prompt templates and stop-token rules
- add default OCR sampling policy
- keep OCR overrides explicit and operator-visible

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- OCR defaults should be data-driven rather than hardcoded to one development model
- stop-token handling should remain compatible with stream assembly
- model settings should allow override without hiding the default effective profile

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- OCR-capable models can resolve to model-aware prompt and sampling defaults
- default and overridden OCR behavior are test-covered
