## Summary

Polish the macOS LoRA operator workflow so the real training chain reads as a
single guided product surface instead of a stack of raw registry dumps. The
highest-priority gap is action feedback: `Activate Adapter` currently produces
no visible pending, success, or failure state inside the Training surface,
which makes the workflow look broken even when the underlying operation runs.

This slice aligns the LoRA tooling surfaces with the Melix design system's
"Digital Broadsheet" hierarchy by:

- adding an explicit LoRA workflow status card with pending, success, and
  failure presentation
- restructuring Training into clearer card groups with primary actions and
  lower-frequency artifact detail separated
- tightening Diagnostics empty and result states so Benchmark and Evaluation
  read as validation stages rather than disconnected forms
- reducing the most visible accessibility duplication on Training and
  Diagnostics by removing `GroupBox`-heavy wrappers and exposing one logical
  card/container per section

The design input for this work is:

- `docs/design-system/README.md`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`
- `docs/plans/2026-04-21-lora-experiment-surfaces.md`
- `docs/plans/2026-04-21-lora-adapter-backed-runtime.md`
- the April 24, 2026 Computer Use LoRA walkthrough screenshots under
  `artifacts/lora-marketing-screenshots/2026-04-24/`

## Problems Observed

### 1. No action feedback in Training

The Training page does not surface an inline operation state for `train_lora`,
`activate_adapter`, `upload`, or `remove_derived_model`. Errors only land in
the global `lastError` log channel, and successful operations only update
`lastModelOperation`, which is currently rendered in the Tools overview but not
in the LoRA workflow surface itself.

### 2. Training hierarchy is too flat

The current Training page is one long `GroupBox` stack:

- configuration
- activation picker
- adapters
- jobs
- experiment groups

All of those sections share the same visual weight, while paths and raw
registry details consume more space than the actual workflow decisions.

### 3. Diagnostics reads as a deep form, not a verification step

Benchmark and Evaluation configuration consume the visual hierarchy, while the
empty result states collapse to one-line copy. When there is no history, the
screen looks unfinished instead of "ready to validate."

### 4. Training and Diagnostics expose repeated AX wrappers

Computer Use and the live accessibility tree show repeated controls in the LoRA
surfaces. The current `GroupBox` and nested labeled-control structure appears
multiple times in AX, which makes automation and screen-reader navigation
noisy.

## Scope

### In

- Add app-local operation feedback for LoRA actions in `RuntimeViewModel`
- Render a dedicated LoRA workflow status card in the Training page
- Replace the Training page's top-level `GroupBox` sections with
  `MelixSectionCard`-based cards
- Reformat adapter, training history, and experiment group summaries so primary
  state and metrics come first, with verbose artifact paths visually downgraded
- Improve Benchmark and Evaluation empty states and result summaries in
  Diagnostics
- Add focused view-model and view tests for LoRA workflow status, empty states,
  and section rendering
- Re-run Computer Use against the updated LoRA surface and capture fresh UI
  evidence if the implementation materially changes presentation

### Out

- Backend or proto contract changes
- Changing LoRA job semantics, activation semantics, or model-op payload shape
- Reworking the CLI LoRA commands
- Adding brand-new benchmark or evaluation suites
- Marketing-specific retouching or post-processing of the screenshots

## Design

### A. Introduce a typed LoRA workflow presentation state

Add a derived state in `RuntimeViewModel` for the LoRA workflow, backed by the
existing model-operation plumbing:

- `idle`
- `running(operation)`
- `succeeded(operation)`
- `failed(operation, message)`

This should be app-local presentation state rather than a new backend contract.
It should be set when a LoRA action begins, updated when the action completes,
and populated on failure even if the operation never produced an artifact.

The state should be narrow and workflow-focused:

- operation kind (`train_lora`, `activate_adapter`, `upload`,
  `remove_derived_model`)
- short title
- status text
- secondary detail
- whether the action is currently running

### B. Add a Workflow Status card to Training

Insert a `MelixSectionCard("Workflow Status")` near the top of
`DesktopTrainingToolSectionView`.

The card should:

- show a `ProgressView` and "Activating Adapter" / "Training LoRA" when running
- show a success state with the last completed LoRA operation and its most
  useful output summary
- show an inline failure state using the LoRA workflow message rather than
  requiring the user to inspect logs
- disable duplicate action buttons while a LoRA action is running

This card is the main fix for the current "clicked but nothing happened"
problem.

### C. Rebuild Training as cards with clear hierarchy

Convert the Training page into card sections:

1. `Workflow Status`
2. `Training Configuration`
3. `Adapter Activation`
4. `Experiment Groups`
5. `Saved Adapters`
6. `Training Jobs`

Primary state should come before artifact detail:

- top line: adapter / group / run title + status
- second line: model + dataset summary
- third line: compact metrics summary
- paths only in low-emphasis caption rows or under disclosure

Absolute filesystem paths should remain available, but not dominate the card.

### D. Improve Diagnostics stage framing

Keep the existing capability, but improve how the page reads:

- stronger empty states in `Benchmark Results`, `Benchmark History`,
  `Evaluation Results`, and `Evaluation History`
- empty states should explain what is missing and what action unlocks the next
  result
- retain the existing export and advanced controls, but keep the results region
  visually useful even when history is empty

### E. Reduce AX duplication in LoRA surfaces

Use lightweight cards and avoid extra accessibility wrappers on top-level
Training and Diagnostics sections.

Guardrails:

- one accessibility container per logical card
- repeated helper text should not be exposed as separate duplicated controls
- section wrappers should prefer `.accessibilityElement(children: .contain)`
  where that reduces repeated announcements without hiding child controls

## Files Expected

- `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `apps/macos-menubar/Tests/MenuBarTests/Phase8LoRAWindowSmokeTests.swift`
- `docs/plans/2026-04-24-lora-uiux-polish.md`

## Test Plan

### Focused tests

- `RuntimeViewModelTests`
  - LoRA workflow state enters running before a model operation completes
  - successful activation/training/publish/removal update the workflow status
  - failed LoRA actions expose inline workflow failure details

- `DesktopFoundationViewTests`
  - Training renders the workflow status card
  - Training continues to default to advanced collapsed
  - adapter/job/group cards prefer summary text over path-first presentation
  - Diagnostics empty states render the new guidance copy

- `Phase8LoRAWindowSmokeTests`
  - canonical acceptance evidence still covers the training and compare flow
  - the rendered LoRA surface now includes workflow-status text

### Verification commands

```bash
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|Phase8LoRAWindowSmokeTests|DesktopPolishSmokeTests'
python3 scripts/m15_desktop_polish_smoke.py --json
```

### UI verification

- Computer Use pass on `Tools > Training`
- Computer Use pass on `Tools > Diagnostics`
- confirm LoRA action feedback is visible without opening Logs

## Metrics

This is primarily a UI-state and presentation slice.

Required evidence:

- changed-line automated test coverage >= 95%
- desktop polish smoke remains green
- Computer Use evidence that LoRA actions now expose visible status

Runtime performance metrics:

- `N/A` unless implementation touches long-lived benchmark/evaluation execution
  paths beyond presentation state
