# LoRA Visual Alignment Round 3

## Summary

Bring the macOS LoRA operator surfaces materially closer to the uploaded PDF
and `docs/design-system/README.md` by shifting the current Training and
Diagnostics views away from “default form UI” and toward Melix’s intended
broadsheet-like presentation style.

This pass is intentionally visual-first. The previous rounds improved runtime
state, workflow priority, and staged navigation. This round should improve:

1. card weight and background density
2. staged reveal of Training configuration
3. results-first Diagnostics composition
4. typography, spacing, and metric hierarchy consistency

## Design Inputs

- `docs/design-system/README.md`
- `docs/plans/2026-04-24-lora-uiux-polish.md`
- `docs/plans/2026-04-24-lora-uiux-polish-round-2.md`
- uploaded reference: `Melix Design System.pdf`
- current branch screenshots under:
  - `artifacts/lora-marketing-screenshots/2026-04-24-polish/`

## Problems To Solve

### 1. Structural cards still read too heavy

The current LoRA pages use too many medium-contrast card fills. The design
system allows low-contrast neutral surfaces, but the current implementation
still reads as a stack of gray tools rather than a sparse editorial layout.

### 2. Training still exposes too much setup too early

The first viewport is improved, but `Training Configuration` still opens into a
large configuration slab. Operators should see the main setup path first and
progressively reveal lower-frequency wiring details.

### 3. Diagnostics still behaves like a configuration page with results below

The stage selector fixed the long-scroll problem, but the active Diagnostics
stage still visually leads with configuration rather than the latest result.
That is the wrong priority for review, comparison, and marketing screenshots.

### 4. Typography and metric hierarchy is not yet system-grade

Labels, captions, metrics, and helper copy are closer than before, but they do
not yet read as one calibrated system. Important values still compete with
section chrome and secondary metadata.

## Scope

### In

- Tools > Training visual restructuring
- Tools > Diagnostics visual restructuring
- shared local styling/helpers needed by those two sections
- refined first-viewport hierarchy for status, actions, summary, and latest
  result evidence
- typography and spacing normalization for section labels, captions, metrics,
  and dense result cards
- refreshed screenshot evidence after implementation

### Out

- backend, protocol, or workflow semantics changes
- new benchmark, evaluation, or LoRA capabilities
- title bar or global shell redesign
- marketing-only post-processing outside the app renderer

## Design Direction

### A. Reduce visual weight before adding new structure

The first principle is subtraction.

Training and Diagnostics should use:

- weaker neutral fills for structural cards
- fewer visually framed regions per viewport
- more whitespace between groups
- stronger reliance on typographic hierarchy instead of container contrast

Status-tinted fills stay where they carry meaning, but neutral sections should
move closer to the design system’s low-border, low-contrast baseline.

### B. Training should become a staged editorial flow

Training should read top-to-bottom as:

1. workflow status
2. primary actions
3. selected configuration snapshot
4. essential setup
5. optional dataset mapping and advanced tuning
6. downstream inventory (activation, saved adapters, jobs)

The essential setup region should keep only the fields needed to define the
next run. Lower-frequency Hugging Face dataset mapping and artifact-heavy
details should remain available, but visually demoted through staged reveal or
secondary disclosure.

### C. Diagnostics should become result-first

Each diagnostics stage should start with a compact evidence header before the
operator reaches the detailed controls.

For each active stage:

- top summary row: selected run, status, key metrics, created time
- result evidence block
- configuration block
- history block

This preserves editability while making the page answer the first operator
question immediately: “what is the current result?”

### D. Typography must become shared infrastructure

This pass should introduce or consolidate shared presentational helpers for:

- section eyebrow labels
- compact metric cards
- secondary metadata rows
- monospaced evidence values
- low-emphasis helper copy

The goal is to stop hand-tuning type weight and spacing in each subsection.
Training and Diagnostics should share the same visual grammar.

## Implementation Plan

### Slice 1 — Shared visual primitives

- add or refine compact metric / summary helpers inside the Tools workspace
- standardize eyebrow label spacing, caption weight, and monospaced value usage
- reduce neutral panel opacity so structural containers recede

### Slice 2 — Training visual restructuring

- split `Training Configuration` into an essential setup block and secondary
  reveal blocks
- keep the first viewport focused on status, actions, summary, and core setup
- push Hugging Face mapping and advanced tuning into quieter expandable regions
- keep destructive / low-frequency actions in overflow only

### Slice 3 — Diagnostics result-first composition

- keep the stage selector from round 2
- move the active stage’s latest result summary above detailed configuration
- tighten result cards so summary evidence reads before charts
- keep configuration accessible but visually secondary to outcomes

### Slice 4 — Typography and spacing sweep

- normalize section spacing, card padding, label spacing, and metric value
  treatment
- reduce noisy medium-emphasis copy in suite cards and history cards
- verify that the active stage or primary workflow action is the first-viewport
  focal point

## Files Expected

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `docs/plans/2026-04-24-lora-visual-alignment-round-3.md`

Additional local helpers may be introduced if the typography and summary-card
system would otherwise stay duplicated inside one file.

## Tests And Verification

### Focused Tests

- update `DesktopFoundationViewTests` to assert:
  - Training summary / staged reveal stays intact
  - lower-frequency actions remain in overflow
  - Diagnostics defaults to the expected stage
  - Diagnostics result-first sections render the active evidence before the
    secondary configuration controls
  - stage-specific pages do not leak unrelated visual sections

### Verification Commands

```bash
swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|Phase8LoRAWindowSmokeTests'
python3 scripts/m15_desktop_polish_smoke.py --json
swift test --package-path apps/macos-menubar --filter TempLoRAScreenshotTests
```

## Success Criteria

- Training first viewport clearly reads as status -> action -> summary -> setup
- only one primary CTA is visually dominant
- neutral structural cards feel materially lighter than the current round 2 UI
- Diagnostics opens each stage around current results instead of configuration
- metrics and captions read as one consistent typographic system
- refreshed screenshots look visibly closer to the uploaded PDF than the round 2
  screenshots

## Metrics

- changed-line automated coverage >= 95%
- runtime metrics: `N/A` unless implementation touches execution paths rather
  than presentation

## Assumptions

- scope is limited to the LoRA workflow inside Tools > Training and
  Tools > Diagnostics
- current runtime behavior and data structures remain valid; this is primarily a
  presentation and hierarchy pass
- the uploaded PDF remains the strongest visual reference when it disagrees with
  the current in-repo screenshots
