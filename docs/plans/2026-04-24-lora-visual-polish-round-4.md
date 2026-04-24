# LoRA Visual Polish Round 4

## Summary

Complete a final presentation-first pass on the macOS LoRA workflow so the
Training and Diagnostics surfaces read less like default AppKit forms and more
like the sparse editorial layout defined by `docs/design-system/README.md` and
the uploaded PDF reference.

This round is intentionally narrower than the earlier UI/UX work:

1. reduce residual form chrome in Training
2. reduce chart and selection noise in Diagnostics
3. improve first-viewport visual emphasis for marketing screenshots
4. refresh the screenshot set with stronger framing per workflow step

## Design Inputs

- `docs/design-system/README.md`
- `docs/plans/2026-04-24-lora-visual-alignment-round-3.md`
- uploaded reference: `Melix Design System.pdf`
- current screenshot baseline:
  - `artifacts/lora-marketing-screenshots/2026-04-24-polish/`

## Problems To Solve

### 1. Training still reads as a system form

The current Training section has the right information order, but the core setup
still relies on large default segmented controls and rounded text fields that
dominate the viewport. The page needs a lighter editorial field rhythm.

### 2. Diagnostics still over-emphasizes controls and chart ink

The result-first structure is in place, but the benchmark and matrix charts
still read as default blue chart output, and selected history rows are too
prominent. The result narrative should be calmer and more typographic.

### 3. Marketing screenshots are too literal and too tall

The current generated screenshots capture the whole scroll surface, which makes
the images useful for inspection but weak for promotion. The framing should show
one strong story per image instead of a full-page dump.

## Scope

### In

- final visual polish for `Tools > Training`
- final visual polish for `Tools > Diagnostics`
- shared local presentation helpers needed to reduce form weight
- screenshot renderer updates for stronger marketing framing

### Out

- new workflow semantics
- backend, protocol, or persistence changes
- non-LoRA product surfaces
- manual post-processing outside repository artifacts

## Design Direction

### A. Replace default form slabs with editorial field groups

Training should use compact label-above-control groups and tighter two-column
grids where possible. Large full-width segmented controls should be contained
inside a quieter field wrapper rather than spanning the whole section.

### B. Keep structural cards nearly invisible

Neutral section backgrounds should become weaker again. The page should be held
together by spacing, eyebrow labels, and metric hierarchy rather than stacked
gray containers.

### C. Make Diagnostics charts feel like evidence, not decoration

Charts should use Melix’s restrained accent treatment and occupy less visual
weight than the selected result summary. Selection backgrounds should stay in
the design-system weak accent range rather than reading as filled blue tiles.

### D. Frame screenshots around a single point of attention

Each exported image should emphasize one workflow moment:

- Training overview
- Training configuration
- Adapter activation / history
- Benchmark result
- Matrix result
- Evaluation result

The screenshot renderer should prefer focused crops and shorter panel captures
over full-page dumps.

## Implementation Plan

### Slice 1 — Shared visual primitives

- introduce lightweight editorial field wrappers for label / helper / control
- reduce neutral surface opacity for section and metric cards
- normalize compact caption and mono metric styling where Training and
  Diagnostics still diverge

### Slice 2 — Training presentation polish

- refactor core setup into a cleaner editorial grid
- reduce repeated inline labels and full-width form chrome
- tighten experiment group / adapter / job rows so the summary reads first and
  paths stay secondary

### Slice 3 — Diagnostics presentation polish

- restyle benchmark and matrix charts with restrained accent treatment
- further demote selected-row backgrounds and secondary metadata
- keep summary metrics visually ahead of configuration and history

### Slice 4 — Screenshot framing refresh

- update `TempLoRAScreenshotTests` captures to export tighter, story-first
  frames
- refresh the screenshot artifact directory after the visual pass

## Files Expected

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `apps/macos-menubar/Tests/MenuBarTests/TempLoRAScreenshotTests.swift`
- `docs/plans/2026-04-24-lora-visual-polish-round-4.md`

## Tests And Verification

### Focused Tests

- extend `DesktopFoundationViewTests` to cover:
  - editorial Training field grouping
  - lighter Diagnostics history / results presentation invariants
  - result-first snapshots remaining present after visual restyling

### Verification Commands

```bash
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests|TempLoRAScreenshotTests'
python3 scripts/m15_desktop_polish_smoke.py --json
```

## Success Criteria

- Training first viewport feels materially lighter than the current round-3
  baseline
- Diagnostics charts and selected rows no longer dominate the page with default
  blue treatment
- the refreshed screenshot set reads like curated product imagery instead of raw
  inspection captures
- changed-line automated coverage remains at or above 95 percent for the touched
  scope

## Metrics

- changed-line automated coverage >= 95%
- runtime metrics: `N/A` unless the implementation unexpectedly touches runtime
  execution paths

## Assumptions

- the screenshot renderer remains a temporary local artifact path and does not
  define production runtime behavior
- the final polish should stay inside existing LoRA workflow affordances rather
  than adding new commands or navigation
