# macOS UI/UX Follow-Up

> **For agentic workers:** Keep this plan current as implementation and verification evidence changes.

## Goal

Align the native Melix macOS operator UI with the uploaded `Melix Design System.pdf` and the
repository design system while preserving the existing control-plane and worker boundaries.

## Design Inputs

- Uploaded `Melix Design System.pdf` design reference
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
- [x] Redesign Command Center as a standalone Apple-style utility window using the uploaded PDF,
  repository design system, and existing state-first operator plan:
  - replace default `GroupBox`-heavy layout with lightweight broadsheet sections and quiet tiles;
  - keep global health, pressure, recovery, workflow, error, activity, and session summaries visible
    without moving object-local editing into the window;
  - preserve the existing `RuntimeViewModel` data and recovery actions while improving scan order,
    spacing, typography, SF Symbol usage, and compact/wide adaptability.
- [ ] Replace nested API quick-start and agent integration `GroupBox` layouts with lightweight
  section cards so accessibility exposes one logical copy of each group/control.
- [ ] Polish Server, Tools, API, Downloads, Diagnostics, and Image so primary actions stay visible
  and lower-frequency actions move behind menus or disclosures.
- [x] Follow up on the Chat and Dock review pass:
  - enlarge the packaged Dock icon glyph while preserving the Melix mark and use a very light
    neutral icon background;
  - keep the new chat button out of launch focus highlight;
  - remove the instructional empty transcript card from Chat;
  - hide the default `Main` branch chip while preserving explicit fork labels;
  - rename the inspector capability section from `Analysis Routes` to `Model Capabilities`, because
    it reflects snapshot-derived model readiness rather than live route traces.
  - require each new Chat session to choose a server/provider explicitly before prompts can be sent,
    so deterministic fixture sessions cannot be mistaken for a real LLM-backed chat;
  - hide transcript-side technical model/request IDs from normal user and assistant messages;
  - replace the Chat inspector runtime card with compact capability icons.
  - keep packaged preview apps on the real `auto`/`swift` backend defaults and export package-local
    model-ops/evaluation job roots so live-server review does not silently fall back to fixture
    Echo behavior.
  - sync managed registry models before native Chat lazy-loads a selected server model, so local
    managed downloads are loaded by filesystem path instead of being resolved again as Hugging Face
    repo IDs.
  - treat `model_kind: "text"` as capability metadata rather than a Python runtime selector; managed
    Hugging Face downloads must use explicit route metadata or a refreshed worker-owned registry
    snapshot to select `python_text_compatibility`.
  - keep `python_text_compatibility` Chat sessions on the worker `generate` path rather than the
    phase-aware prefill/decode path, because the Python worker only implements prefill/decode for
    native VLM runtime sessions; this prevents local text sessions from surfacing `unavailable`
    after selecting a downloaded server.
  - send Chat prompts with the bound server session model even if the app-local model table has not
    yet refreshed that model row; the control plane remains responsible for registry sync and
    lazy-load before dispatch.
  - skip the app-side pre-load call when the bound server model is not yet present in the app-local
    model table, avoiding a premature `model.load` `not_found` banner before control-plane registry
    sync can surface the managed model.
  - refresh the desktop foundation snapshot before dispatching Chat when the selected server model
    is absent from app-local state, forcing control-plane registry sync to complete before
    lazy-load/dispatch.
  - accept `python_text_compatibility` as a WorkerRegistry metadata alias for the Python
    compatibility route, so canonical registry metadata cannot fall back to the Swift text worker
    when enum route fields are absent.
  - make the packaged macOS app treat `MELIX_APP_SUPPORT_DIR` as `MELIX_HOME` when no explicit
    home override is present, keeping operator-session state, managed model roots, and runtime
    review state on the same Application Support source of truth instead of falling back to
    `~/.melix`.
  - keep persisted server-session `modelID` authoritative when applying gateway listener
    projections; gateway config still hydrates requested/effective endpoint fields, but stale
    `served_model_id` values no longer overwrite Chat's selected server model.

## Verification

```bash
swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests|DesktopPolishSmokeTests|StatusMenuTests'
python3 scripts/m15_desktop_polish_smoke.py --json
```

Latest Command Center redesign evidence:

- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`: passed,
  173 Swift Testing cases.
- `swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests`: passed, 1
  Swift Testing case; emitted canonical M15 desktop polish metrics.
- `python3 scripts/m15_desktop_polish_smoke.py --json`: passed with `ok: true`,
  `grounded_surface_count: 5`, `grounded_tool_section_count: 6`,
  `top_banner_title: "Download Recovery Available"`.
- `git diff --check`: passed.
- Review follow-up: removed production references to the local PDF path, moved Command Center
  health presentation onto `DesktopFoundationHealthState` semantics, and reused the shared
  `melixCard()` modifier for broadsheet panel surfaces.

Manual evidence:

- Rebuild/open the macOS app and review Chat, Server, Tools, Downloads, Image, and API with
  Computer Use.
- Confirm no top audio banner appears at startup.
- Confirm inspector is collapsed by default.
- Confirm collapsed side panes do not leave restore rails in the content area.
- Confirm API quick starts and copy controls are no longer duplicated in the accessibility tree.
- Confirm callable API/agent export URLs use the same effective listener URL.
- Confirm Command Center opens as a standalone utility-style window, shows state-first global
  health/recovery/workflow summaries, uses design-system broadsheet sections instead of default
  `GroupBox` chrome, and keeps recovery/download actions reachable.
- Confirm Chat opens without the empty transcript copy, the default branch chip, transcript-side
  model/request IDs, runtime request metadata, or a highlighted new chat button; new sessions must
  choose a server/provider before Send is enabled, and the inspector should show capability readiness
  as compact icons.
- Confirm a Chat session targeting a downloaded managed model does not pass a Hugging Face repo ID
  to the worker load request when the local registry manifest exposes a managed filesystem path.
- Confirm bare text registry snapshots without `melix.capability.route_kind` continue to route
  through the default text worker, while managed Python-compatible text models route through
  explicit `python_text_compatibility` metadata after worker registry refresh.
- Confirm a Chat session targeting a downloaded text model routes through generate, not
  phase-aware prefill/decode, and returns worker text instead of `Error unavailable`.
- Confirm selecting `Primary Server` in Chat submits that server's configured model ID rather than
  falling back to `melix-dev-text` while the model list is stale.
- Confirm the same stale-list Chat path does not issue a premature `model.load` call before
  `startChat`.
- Confirm the stale-list Chat path requests a fresh server snapshot before dispatch.
- Confirm the packaged app restores the Application Support operator-session state and does not
  seed Chat from stale `~/.melix` state.
- Confirm stale gateway listener `served_model_id` values cannot override a restored server
  session's model when Chat dispatches.

## Metrics

- Runtime performance probes: `registry.reload_latency_ms` and
  `registry.discovered_model_count` remain the control-plane metrics for the added native Chat
  registry sync. The text-route correction reuses existing scheduler/HTTP route metrics and adds no
  new inference hot-path metrics.
- UI evidence: focused Swift tests, desktop polish smoke JSON, and Computer Use visual/AX review.
- Command Center redesign metrics: runtime probes N/A because the change is a SwiftUI layout and
  composition update over existing read models and actions; UI evidence is the focused Swift view
  suite plus desktop polish smoke checks listed above.
