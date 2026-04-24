# LoRA UI/UX Polish Round 2

## Summary

Refine the macOS LoRA operator surfaces so Training and Diagnostics read as
guided workflow stages instead of long, flat forms. The first LoRA polish pass
added workflow state and reduced the most obvious structural clutter. The next
pass should improve scanability, CTA priority, and validation-stage focus.

This pass is driven by the current branch screenshots under:

- `artifacts/lora-marketing-screenshots/2026-04-24-polish/`

and follows:

- `docs/design-system/README.md`
- `docs/plans/2026-04-24-lora-uiux-polish.md`

## Problems Observed

### 1. Training first view still reads as one long form

The top of Training currently mixes setup, dataset wiring, activation mode,
and every action button inside one card. The user has to visually parse too
much before they can identify the next primary action.

### 2. Advanced parameters are not clearly interactive

`Advanced Training Parameters` is technically collapsible, but the collapsed
row reads like helper copy instead of a clear interactive control. That hurts
discoverability and also makes automation/AX less reliable.

### 3. Workflow actions have weak priority cues

`Train LoRA`, `Activate Adapter`, `Remove Derived Model`, and `Publish Adapter`
currently sit at the same level. The main happy path is not clearly separated
from occasional or destructive actions.

### 4. Diagnostics is too deep as a single scrolling page

Benchmark, Matrix, and Evaluation content all render in one long vertical
surface. Once results exist, the operator has to scroll through unrelated
sections to get back to the stage they care about.

### 5. Result summaries are weaker than the surrounding forms

Benchmark, Matrix, and Evaluation results already include useful summary data,
but the results do not establish a clear “latest validation snapshot” before
the denser charts, rows, and histories.

### 6. Suite cards are visually flat

Benchmark and Evaluation suite cards give equal visual weight to title,
dataset, and defaults. Important choices are selectable, but they are not fast
to scan.

## Scope

### In

- Rebuild the Training configuration card into a shorter “core setup” stage
- Move lower-frequency actions into an overflow menu and keep only the main
  workflow CTAs visible
- Replace the current advanced `DisclosureGroup` with a more explicit
  button-like toggle row and compact summary
- Add a Diagnostics stage selector so the operator focuses on one validation
  mode at a time: `Benchmark`, `Matrix`, or `Evaluation`
- Strengthen result summaries for Benchmark, Matrix, and Evaluation with a
  compact top summary row before charts/history
- Tighten suite-card typography and information order
- Add focused tests covering the new layout and selection behavior

### Out

- Backend or proto changes
- New LoRA or evaluation semantics
- New benchmark/evaluation suites
- Marketing-only post-processing of screenshots

## Design

### A. Training becomes staged rather than monolithic

Keep the existing card structure, but restructure the main configuration card
into:

1. Core setup summary
2. Dataset details
3. Activation mode
4. Workflow actions

The visible CTA row should keep only:

- `Train LoRA`
- `Activate Adapter`
- one overflow menu for `Publish Adapter` and `Remove Derived Model`

`Remove Derived Model` remains available but is visually downgraded because it
is not part of the primary loop and is destructive.

### B. Advanced parameters get an explicit interactive affordance

Replace the plain `DisclosureGroup` label with a full-width button row that:

- shows a chevron
- shows collapsed/expanded state
- includes a compact summary such as `Rank`, `Epochs`, and `LR`

This should read as an action, not static text.

### C. Diagnostics gets stage focus

Add a local stage selector to `DesktopDiagnosticsToolSectionView`:

- `Benchmark`
- `Matrix`
- `Evaluation`

The selector should default from current shared state:

- `.standard` benchmark mode -> `Benchmark`
- `.matrix` benchmark mode -> `Matrix`
- explicit evaluation actions or selection -> `Evaluation`

Only the active stage’s configuration, results, and history should be rendered
at one time. Shared top-level actions remain visible.

### D. Result regions lead with a validation snapshot

For each active diagnostics stage, show a compact summary row before detailed
charts/history:

- selected run title
- status
- key metrics
- creation time

This gives the user a strong “what happened last” answer before they scan the
rest of the evidence.

### E. Suite cards prioritize title first, metadata second

Suite cards should render:

1. title
2. dataset/source label
3. defaults/status line in smaller secondary text

Keep the selection checkmark, but reduce the amount of medium-emphasis copy per
card so the grid is faster to scan.

## Files Expected

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `docs/plans/2026-04-24-lora-uiux-polish-round-2.md`

## Verification

```bash
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests'
python3 scripts/m15_desktop_polish_smoke.py --json
```

## Metrics

- changed-line automated coverage >= 95%
- runtime metrics: `N/A` unless this pass changes execution paths rather than
  presentation
