# M9.5 Rich Output Sanitization Slice

**Goal:** Land the first executable `M9.5` slice by adding a shared deterministic rich-output sanitizer, applying it at gateway and operator rendering boundaries, and proving the behavior with repository-owned tests, smoke output, and changed-line coverage.

**Scope Boundary:** This slice sanitizes operator-facing rich text and markdown-like surfaces. It does not change model-generation semantics, does not rewrite benchmark or evaluation export schemas, and does not introduce a full HTML or Markdown parser.

## Recommended Approach

- Add a shared `RichOutputSanitizer` inside `MelixControlPlaneCore` so the control plane and the menu bar use the same rules.
- Preserve fenced code blocks verbatim, but sanitize text outside code fences by:
  - stripping HTML tags and active fragments
  - rejecting `javascript:`, `data:`, `vbscript:`, and `file:` URI schemes in markdown-like links and raw text
  - preserving readable plain text and safe markdown-like content wherever possible
- Apply the sanitizer at gateway JSON-response boundaries and app-side render or export boundaries instead of mutating worker truth or raw export bundle storage.

## Execution Slices

1. Completed: add the shared sanitizer and gateway-side recursive JSON payload sanitization.
2. Completed: sanitize app-side doctor and benchmark report state, chat transcript render and chat markdown export, evaluation sample previews, and local error or event text.
3. Completed: add runbook guidance, targeted verification, changed-line coverage, and milestone backfill.

## Planned Files

- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Add: `services/control-plane-swift/Tests/HTTPGatewayTests/RichOutputSanitizerTests.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Add: `docs/runbooks/rich-output-sanitization.md`

Implementation note:

- the shared sanitizer landed inside `OpenAIHandler.swift` instead of a standalone source file so the type is guaranteed to compile into `MelixControlPlaneCore` and remain directly importable from the menu bar target
- the slice closes on repository-owned Swift tests plus gateway metric assertions rather than a duplicate Python-side sanitizer smoke implementation

## Success Metrics

- `sanitized_output.enforcement_count`
- `sanitized_output.blocked_html_fragment_count`
- `sanitized_output.unsafe_uri_rejection_count`

## Verification Target

- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'RichOutputSanitizerTests|OpenAIHandlerTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/test_m9_sanitization_smoke.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_sanitization_smoke.py --json`

## Commit Target

- `feat: add rich output sanitization`
