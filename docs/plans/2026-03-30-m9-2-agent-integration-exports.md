# M9.2 Agent Integration Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add data-driven export and integration paths for external coding-agent tools so Melix can project one local runtime identity into reproducible `OpenClaw`, `Hermes Agent`, `OpenCode`, `Codex`, and related client setups.

**Architecture:** Keep integration definitions in repository-owned data models rather than hardcoded UI copy, derive every export from the effective Melix listener or auth state, and let the menu bar shell and runbooks render the same canonical export payloads. Use deterministic smoke validation so examples do not drift from actual supported routes.

**Tech Stack:** Swift 6, SwiftUI, XCTest, Python smoke utilities, repository-owned runbooks and README guidance.

---

## Scope Notes

- Reuse the currently supported local HTTP surfaces instead of inventing tool-specific transport shims.
- Exports must be reproducible from live Melix state and must not diverge from the actual selected server session.
- Tool-specific instructions may differ in file format, but all exports must flow from one canonical Melix runtime projection.

## Performance Probes And Success Metrics

- `integration.export_generation_ms`
- `integration.setup_success_rate`
- `integration.export_target_count`

## Task 1: Add Canonical External-Agent Export Models

**Files:**
- Add: `apps/macos-menubar/Sources/AppMain/Models/AgentIntegrationExport.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

- [x] Define typed export targets for `OpenClaw`, `Hermes Agent`, `OpenCode`, `Codex`, and a generic OpenAI-compatible client.
- [x] Derive each export from the selected Melix server session, including base URL, auth header style, config-file fragments, and shell snippets.
- [x] Keep bearer-token and future shared-access exports explicit by rendering token placeholders or key IDs instead of secret values.
- [x] Add failing and then passing view-model tests for reproducible export generation, auth-mode-specific variants, and empty-state behavior.

## Task 2: Surface Export Actions In The Desktop Shell

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

- [x] Replace hardcoded tool-integration copy text with the new export model so the shell can render the supported targets from canonical data.
- [x] Add copy or export actions for config fragments, curl snippets, and target-specific instructions without changing the underlying runtime state.
- [x] Add UI tests for target switching, selected-session rebinding, and fallback behavior when no server session is running.
- [x] Record `integration.export_generation_ms` and `integration.export_target_count` in the touched scope.

## Task 3: Add Repository-Owned Documentation And Smoke Validation

**Files:**
- Add: `docs/runbooks/external-agent-integrations.md`
- Modify: `README.md`
- Add: `scripts/m9_agent_export_smoke.py`

- [x] Document the supported external tools, exported artifact shapes, and the exact Melix state each export depends on.
- [x] Add a deterministic smoke command that renders all supported exports from a fixture server session and validates required fields for each tool.
- [x] Capture a metrics report for `integration.setup_success_rate`; use deterministic smoke evidence if live end-to-end setup is not yet practical inside the worktree.

## Verification And Commit Gate

- [x] Run targeted verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_agent_export_smoke.py --json`
- [x] Measure changed-line coverage for the touched app scope and confirm coverage is at least `95%`.
  - Swift changed-line coverage: `97.98% (340/347)` across the touched menu bar source and test files.
  - Python smoke-wrapper coverage: `N/A` for diff-executable changed lines because `scripts/python_changed_line_coverage.py` reported `0/0` executable changed lines for `scripts/m9_agent_export_smoke.py`; the wrapper still executed successfully under `coverage run`.
- [x] Record the changed-scope metrics report for `integration.export_generation_ms`, `integration.setup_success_rate`, and `integration.export_target_count`.
  - Deterministic smoke metrics: `integration.export_generation_ms = 0.03695487976074219`, `integration.setup_success_rate = 1.0`, `integration.export_target_count = 5`.
  - Coverage-enabled smoke fixture recorded runtime metrics inside `AgentIntegrationExportSmokeTests`: `integration.export_generation_ms = 0.0059604644775390625`, `integration.export_target_count = 5`.
- [x] Commit Task 2:
  - `git add apps/macos-menubar/Sources/AppMain/Models/AgentIntegrationExport.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift docs/runbooks/external-agent-integrations.md README.md scripts/m9_agent_export_smoke.py docs/plans/2026-03-30-m9-2-agent-integration-exports.md`
  - `git commit -m "feat: add external agent integration exports"`
  - Result: committed as `3fd8ddb`.
