# Server UI Walkthrough Finalization Plan

## Summary

Finalize the Server page changes that were validated through the local HTML walkthrough. The App should match the accepted walkthrough state: compact unified Server rows, a user-facing acceleration mode selector, a read-only LoRA adapter state layout, and documentation that makes the walkthrough workflow a required agent practice for substantial UI changes.

## Scope

- Update the macOS Server UI and view-model formatting to reflect the walkthrough decisions.
- Keep the internal `baseline` acceleration value, but show it to users as `None`.
- Keep Server row content to three lines and use badge/icon-friendly state fields:
  - session name
  - Local/Remote type
  - model name
  - endpoint
  - status
  - LoRA active state, omitted when inactive
  - acceleration mode
  - context
- Change Server acceleration selection to a single dropdown with five modes:
  - `None`
  - `Speculative Decode`
  - `Accelerated Prefill`
  - `Active KV Quantized`
  - `Sparse Prefill`
- Show mode-specific settings only for the selected acceleration mode.
- Change the LoRA adapter area so the adapter selector appears first and the derived-model state is read-only below it.
- Add a durable UI walkthrough runbook and require agents to use the workflow from `AGENTS.md`.

## Out Of Scope

- Adding new protocol fields for raw adapter serving.
- Automatically activating LoRA adapters during Server startup.
- Enabling remote benchmark execution.
- Committing `.runtime/walkthrough` artifacts.

## Implementation Steps

1. Add focused Swift tests for the accepted user-facing labels and server row state.
2. Update `RuntimeViewModel` acceleration formatting and request mapping for all five acceleration modes.
3. Update Server page SwiftUI for the acceleration dropdown and LoRA adapter read-only layout.
4. Add the UI walkthrough runbook and link the workflow from `AGENTS.md`.
5. Run focused Swift tests, then `make swift-test`.
6. Build and launch the local macOS App for manual walkthrough.

## Verification

- `make swift-test`
- Rebuild the macOS App.
- Launch the packaged/local App and confirm the window opens for manual walkthrough.

## Metrics

- Coverage target follows the repository rule for the changed Swift scope. If the existing command does not emit coverage for this scope, report coverage as not available and include the focused tests that exercise the changed behavior.
