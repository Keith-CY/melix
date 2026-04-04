# Rich Output Sanitization

## Purpose

Keep unsafe rich text out of Melix operator-facing surfaces without degrading useful diagnostics.

`M9.5` adds a deterministic Swift-side sanitizer that applies at two boundaries:

- control-plane HTTP JSON responses before they leave the gateway
- menu-bar rendering or export state before reports, logs, previews, and transcript exports reach the operator

The sanitizer is intentionally narrow:

- preserve readable plain text
- preserve fenced code blocks verbatim
- strip HTML tags and active fragments outside code fences
- reject unsafe URI schemes in markdown-like links and raw text

It does not mutate worker truth, benchmark export bundle schemas, or chat context passed back to models.

## Blocked Patterns

The current rules strip or neutralize:

- HTML tags such as `<b>`, `<div>`, `<img>`, and similar fragments
- HTML comments
- active HTML blocks:
  - `<script>...</script>`
  - `<style>...</style>`
  - `<iframe>...</iframe>`
  - `<object>...</object>`
  - `<embed>...</embed>`
  - `<svg>...</svg>`
  - `<math>...</math>`
- unsafe URI schemes:
  - `javascript:`
  - `data:`
  - `vbscript:`
  - `file:`

## Allowed Content

These shapes are intentionally preserved:

- plain text
- markdown-like headings and lists
- safe links
- code fences using triple backticks
- comparison text such as `alpha < beta && gamma > delta`

## Operator Surfaces Covered

- gateway JSON error payloads and typed auth-session payloads
- doctor markdown
- benchmark markdown
- benchmark metric names in menu-bar state
- evaluation sample previews
- local error banners and event logs
- chat transcript rendering
- exported chat markdown files

Chat transcript storage remains raw so model-to-model context does not silently change. Sanitization happens only when the transcript is rendered or exported.

## Metrics

The gateway records these counters whenever a response needs sanitization:

- `sanitized_output.enforcement_count`
- `sanitized_output.blocked_html_fragment_count`
- `sanitized_output.unsafe_uri_rejection_count`

The menu bar does not maintain a second sanitizer metric stream; it reuses the shared Swift rules and validates them through repository-owned tests.

## Verification

Focused verification:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --filter 'RichOutputSanitizerTests|OpenAIHandlerTests'

HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path apps/macos-menubar --scratch-path "$(pwd)/.build/menubar-scratch" \
  --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'
```

Coverage verification:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --enable-code-coverage \
  --filter 'RichOutputSanitizerTests|OpenAIHandlerTests'

HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path apps/macos-menubar --enable-code-coverage \
  --scratch-path "$(pwd)/.build/menubar-coverage" \
  --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'
```

## Troubleshooting

- If sanitized output still shows raw HTML, check whether the surface is fed by typed JSON or manual payload JSON and confirm it uses the shared control-plane helper before rendering.
- If diagnostics look over-sanitized, verify the content is outside fenced code blocks. The sanitizer intentionally preserves fenced blocks but strips active content in normal text.
- If a benchmark or evaluation export needs the original raw payload for debugging, inspect the underlying worker artifact or export bundle directly instead of the operator-facing projection.
