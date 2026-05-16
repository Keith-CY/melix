# Window UI Productization Plan

## Goal

Productize the current operator-facing CLI, runtime, evidence, model-safety,
and workflow capabilities in the native Window UI. This plan tracks the full
issue tree created for the work and defines the execution constraints for the
single implementation branch.

Root tracking issue: #1090.

## Scope

### Included

- Jobs Center for durable job state, job details, job operations, and selected
  job restoration.
- Batch Runs and Runtime Health for batch configuration, preflight state,
  manifests, resume controls, and readiness blockers.
- Runtime Settings and Discovery for settings rows, set/reset/validate actions,
  discovery payloads, aliases, and metadata copy/open affordances.
- Workflow Recipes and URI Resolver for recipe catalog, URI inspection, recipe
  init preview, variable input, plan summaries, and apply controls.
- Synthetic Dataset Studio for request construction, column editing, preview,
  create results, and failure states.
- Model Load Trust for trust receipts, custom-loader detection, reload guidance,
  opt-in controls, and default-policy regression tests.
- Capability Receipts for model capability details, acceleration receipts,
  unsupported reasons, and pre-dispatch run guards.
- Serving Acceleration Profiles for profile selection, effective config,
  diagnostics evidence, benchmark setup, and profile persistence tests.
- Apple Silicon Memory Fit for model-card receipts, memory summaries, visual
  states, preflight guards, override copy, and selected-run evidence.
- Adapter Capabilities and Training Safety for adapter receipts, activation
  gating, merge support, and saved-job follow-up actions.
- Diagnostics Evidence and Debug Bundles for evidence validity, telemetry gaps,
  debug bundle results, serving diagnostics summaries, artifact actions, and
  redaction display.

### Excluded

- Creating GitHub Milestone objects.
- Adding a second execution engine. New action wiring must route through the
  existing CLI runner, control-plane, policy update, or artifact boundaries.
- Launching, packaging, or manually exercising the App during Unit and
  Milestone implementation.
- Treating walkthrough artifacts under `.runtime/walkthrough` as durable
  repository source.

## Issue Map

| Scope | Issue | Children |
|---|---:|---|
| Tracking | #1090 | #1091, #1100, #1109, #1118, #1127, #1136, #1145, #1154, #1163, #1172, #1181 |
| Jobs Center | #1091 | #1092, #1096 |
| Jobs state and navigation | #1092 | #1093, #1094, #1095 |
| Jobs operations | #1096 | #1097, #1098, #1099 |
| Batch Runs And Runtime Health | #1100 | #1101, #1105 |
| Batch run setup | #1101 | #1102, #1103, #1104 |
| Batch status and resume | #1105 | #1106, #1107, #1108 |
| Runtime Settings And Discovery | #1109 | #1110, #1114 |
| Settings editor | #1110 | #1111, #1112, #1113 |
| Discovery inspector | #1114 | #1115, #1116, #1117 |
| Workflow Recipes And URI Resolver | #1118 | #1119, #1123 |
| Recipe catalog and URI inspect | #1119 | #1120, #1121, #1122 |
| Recipe planning and apply | #1123 | #1124, #1125, #1126 |
| Synthetic Dataset Studio | #1127 | #1128, #1132 |
| Synthetic request builder | #1128 | #1129, #1130, #1131 |
| Preview and create results | #1132 | #1133, #1134, #1135 |
| Model Load Trust | #1136 | #1137, #1141 |
| Trust receipt display | #1137 | #1138, #1139, #1140 |
| Trust opt-in workflow | #1141 | #1142, #1143, #1144 |
| Capability Receipts | #1145 | #1146, #1150 |
| Model capability explorer | #1146 | #1147, #1148, #1149 |
| Capability-aware run guards | #1150 | #1151, #1152, #1153 |
| Serving Acceleration Profiles | #1154 | #1155, #1159 |
| Profile picker and effective config | #1155 | #1156, #1157, #1158 |
| Profile diagnostics and evidence | #1159 | #1160, #1161, #1162 |
| Apple Silicon Memory Fit | #1163 | #1164, #1168 |
| Fit receipts in model cards | #1164 | #1165, #1166, #1167 |
| Fit-aware preflight guards | #1168 | #1169, #1170, #1171 |
| Adapter Capabilities And Training Safety | #1172 | #1173, #1177 |
| Adapter capability receipts | #1173 | #1174, #1175, #1176 |
| Activation and merge gating | #1177 | #1178, #1179, #1180 |
| Diagnostics Evidence And Debug Bundles | #1181 | #1182, #1186 |
| Evidence validity and telemetry gaps | #1182 | #1183, #1184, #1185 |
| Debug and serving diagnostics bundles | #1186 | #1187, #1188, #1189 |

## Walkthrough Decisions

The overview walkthrough artifact lives at
`.runtime/walkthrough/window-ui-productization.html` and is intentionally not
tracked. Durable information-architecture decisions copied from that artifact:

- Add a top-level operator navigation group for the new Window UI surfaces
  rather than hiding them under diagnostics-only panels.
- Keep each Milestone as a stable section with dense lists, detail panes, and
  explicit empty or disabled states.
- Keep state decoding and action eligibility in AppMain view models so SwiftUI
  views render derived state and do not parse CLI output directly.
- Reuse existing artifact open/copy affordances and CLI runner boundaries for
  all actions that already exist in CLI form.
- Surface backend gaps as visible disabled states or receipts instead of
  zero-like placeholders.

## Execution Rules

1. Implement Units in issue-number order from #1093 through #1189.
2. For each Unit, write or extend focused tests before production code.
3. Keep each Unit scoped to the acceptance criteria in its issue body.
4. Run the smallest focused Swift/UI view-model test that proves the Unit.
5. Commit each Unit locally with the Unit issue number in the commit message.
6. Do not compile, package, launch, or manually exercise the App until all Unit
   and Milestone focused tests are complete.
7. Focused Swift tests may compile their test target because that is required
   to verify AppMain and SwiftUI behavior.
8. After all Units are complete, run the cross-surface automated smoke suite,
   then build and launch the App for UI E2E.
9. Use Computer Use only in the final E2E stage to operate the real app UI.
10. Open one final draft PR after final E2E passes.

## Test Strategy

Per Unit:

- Add focused coverage to `RuntimeViewModelTests`,
  `DesktopFoundationViewTests`, `DesktopShellStateTests`, or a targeted
  section-specific test file.
- Prefer fixture-based decoding tests for JSON payload work.
- Prefer disabled-state and derived-row tests before adding view controls.
- Use smoke rendering tests for every new mounted section.

Per Milestone:

- Add at least one rendered SwiftUI smoke path proving the section is mounted,
  selectable, and non-placeholder.
- Add action-eligibility tests for any operation that can be blocked, retried,
  resumed, copied, opened, or cancelled.

Cross-surface smoke before final E2E:

```bash
swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests
swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests
swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests
swift test --package-path apps/macos-menubar --filter Phase8LoRAWindowSmokeTests
python3 scripts/m15_desktop_polish_smoke.py --json
```

Final E2E:

- Start a named Melix runtime instance with an explicit port, worktree-local
  runtime directory, and worktree-local `MELIX_HOME`.
- Build and launch the macOS app.
- Use Computer Use to verify every Milestone workflow end to end.
- Capture screenshots or structured notes for PR evidence.

## Performance And Metrics

The productization work is UI state and action wiring. It must not add
background polling, direct log parsing, or duplicate execution machinery.

Measurement points:

- JSON decode paths for job, settings, discovery, recipe, synthetic, trust,
  capability, fit, adapter, and diagnostics receipts.
- View-model action construction latency for CLI-backed operations.
- SwiftUI smoke paths for mounted sections and selected detail panes.
- Changed-line coverage for the touched AppMain and test scope.

Success metrics:

- Changed-scope coverage is at least 95 percent before any commit that touches
  measurable Swift production code.
- Every Milestone has at least one non-placeholder rendered smoke path.
- Every refused or unsupported dispatch has a visible reason before worker or
  CLI dispatch.
- Final PR evidence includes plan/spec, commands run, coverage and metrics, and
  known gaps using the repository PR template headings.

## Related Work

- #350 remains related background for serving acceleration, capability receipts,
  and diagnostics bundles.
- #1009 through #1029 remain the separate multi-model server issue tree and
  must not be duplicated by this Window UI parent.
- Existing runbooks and specs remain authoritative for backend contracts; this
  plan owns only the Window UI productization execution path.
