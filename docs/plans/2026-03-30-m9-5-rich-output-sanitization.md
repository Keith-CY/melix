# M9.5 Rich Output Sanitization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository-owned rich-output sanitization so Melix strips unsafe HTML-capable content before rendering or exporting operator-facing text surfaces while preserving safe plain-text and markdown-like fidelity.

**Architecture:** Centralize sanitization rules in shared Swift-side logic, apply them at rendering and report-ingress boundaries, and make every sanitization decision machine-readable through counters and tests. Preserve operator-readable markdown and code fences where safe, but strip active HTML, scripts, inline event handlers, and unsafe URI schemes.

**Tech Stack:** Swift 6, SwiftUI, XCTest, repository-owned smoke scripts and runbooks.

---

## Scope Notes

- Treat sanitization as a boundary concern: sanitize when data enters UI-facing or export-facing rendering surfaces.
- Keep original unsafe payloads out of user-visible rich-text rendering paths; only safe text leaves the sanitizer.
- Version the sanitizer rules and enforcement counters so later release gates can assert them.

## Performance Probes And Success Metrics

- `sanitized_output.enforcement_count`
- `sanitized_output.blocked_html_fragment_count`
- `sanitized_output.unsafe_uri_rejection_count`

## Task 1: Add Shared Sanitizer Rules For Rich Output

**Files:**
- Add: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/RichOutputSanitizer.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [ ] Define a deterministic sanitizer that strips HTML tags, inline event handlers, `javascript:` and `data:` URI execution paths, and other active content while preserving plain text, code fences, and safe links.
- [ ] Apply the sanitizer to report markdown, error payload text, and other gateway-side rich output before it reaches downstream rendering consumers.
- [ ] Add failing and then passing tests for script stripping, unsafe-link rejection, multiline markdown preservation, and idempotent repeated sanitization.
- [ ] Record `sanitized_output.enforcement_count`, `sanitized_output.blocked_html_fragment_count`, and `sanitized_output.unsafe_uri_rejection_count`.

## Task 2: Sanitize App-Side Rendering And Export Boundaries

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

- [ ] Sanitize chat transcript rows, diagnostics markdown, bench reports, and exported chat markdown before display or file export.
- [ ] Preserve readable formatting for safe markdown and code blocks so diagnostics remain useful after sanitization.
- [ ] Add failing and then passing app tests for sanitized transcript rendering, sanitized doctor or bench report display, and export-path sanitization.

## Task 3: Add Runbook And Smoke Validation

**Files:**
- Add: `docs/runbooks/rich-output-sanitization.md`
- Add: `scripts/m9_sanitization_smoke.py`

- [ ] Add a deterministic smoke script that feeds unsafe and safe fixtures through the sanitizer and emits machine-readable counts for stripped fragments and preserved safe content.
- [ ] Document the sanitizer contract, blocked patterns, allowed markdown subset, and operator troubleshooting steps.
- [ ] Capture an explicit metrics report for the changed scope; if no live render pipeline metrics are available, record `N/A` with the deterministic smoke output.

## Verification And Commit Gate

- [ ] Run targeted verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_sanitization_smoke.py --json`
- [ ] Measure changed-line coverage for the touched Swift scope and confirm coverage is at least `95%`.
- [ ] Record the changed-scope metrics report for `sanitized_output.enforcement_count`, `sanitized_output.blocked_html_fragment_count`, and `sanitized_output.unsafe_uri_rejection_count`.
- [ ] Commit Task 5:
  - `git add services/control-plane-swift/Sources/HTTPGateway/OpenAI/RichOutputSanitizer.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift docs/runbooks/rich-output-sanitization.md scripts/m9_sanitization_smoke.py docs/plans/2026-03-30-m9-5-rich-output-sanitization.md`
  - `git commit -m "feat: add rich output sanitization"`
