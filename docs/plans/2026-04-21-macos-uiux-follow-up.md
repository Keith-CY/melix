# macOS UI/UX Follow-Up

> **For agentic workers:** Keep this plan current as implementation and verification evidence changes.

## Goal

Align the native Melix macOS operator UI with the uploaded `Melix Design System.pdf` and the
repository design system while preserving the existing control-plane and worker boundaries.

## Design Inputs

- `/Users/ChenYu/Downloads/Melix Design System.pdf`
- `docs/design-system/README.md`
- `docs/design-system/ui_kits/macos-app/`
- `docs/plans/2026-04-18-window-menubar-ui-optimization.md`

## Implementation Slices

- [ ] Move sidebar and inspector visibility into app-local `RuntimeViewModel` state, with sidebars
  visible by default and inspectors collapsed by default.
- [ ] Replace in-content pane toggles with titlebar controls for left panel and right panel. Keep
  the original command-style titlebar action for the Command Center; Preferences remains available
  through `Tools > Settings`.
- [ ] Remove audio setup from ambient desktop banners. Keep audio setup contextual and present it as
  a sheet before invoking install or download remediation.
- [ ] Derive one runtime endpoint/model projection from the selected server session and use it for
  callable API, Chat, Command Center, and agent integration output.
- [ ] Replace nested API quick-start and agent integration `GroupBox` layouts with lightweight
  section cards so accessibility exposes one logical copy of each group/control.
- [ ] Polish Server, Tools, API, Downloads, Diagnostics, and Image so primary actions stay visible
  and lower-frequency actions move behind menus or disclosures.

## Verification

```bash
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests|DesktopPolishSmokeTests|StatusMenuTests'
python3 scripts/m15_desktop_polish_smoke.py --json
```

Manual evidence:

- Rebuild/open the macOS app and review Chat, Server, Tools, Downloads, Image, and API with
  Computer Use.
- Confirm no top audio banner appears at startup.
- Confirm inspector is collapsed by default.
- Confirm collapsed side panes do not leave restore rails in the content area.
- Confirm API quick starts and copy controls are no longer duplicated in the accessibility tree.
- Confirm callable API/agent export URLs use the same effective listener URL.

## Metrics

- Runtime performance probes: `N/A`; this slice changes app UI composition and state projection only.
- UI evidence: focused Swift tests, desktop polish smoke JSON, and Computer Use visual/AX review.
