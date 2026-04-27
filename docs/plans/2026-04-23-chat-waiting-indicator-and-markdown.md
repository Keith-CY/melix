# Chat Waiting Indicator And Markdown Rendering

## Summary

This follow-up refines the macOS Chat surface from the UI/UX pass documented in
`docs/plans/2026-04-21-macos-uiux-follow-up.md`. The Chat transcript should
show that a submitted prompt is actively waiting for model output, and assistant
or reasoning responses should render common Markdown instead of displaying raw
formatting markers. As the transcript grows, the Chat view should keep the
latest exchange in view without requiring manual scrolling.

## Behavior

- After a prompt is accepted, Chat inserts a transient assistant row with a
  compact spinner and `Thinking...` before the first token arrives.
- The pending row is presentation state only: it is replaced by the first
  assistant token or final assistant text, and it is removed after failures or
  empty completions.
- Assistant and reasoning rows render sanitized Markdown through an AST-backed
  renderer. Supported blocks include paragraphs, headings, nested ordered and
  unordered lists, block quotes, fenced and indented code blocks, tables with
  column alignment, and thematic breaks. Supported inline constructs include
  emphasis, strong emphasis, inline code, strikethrough, and readable link or
  image labels.
- The transcript auto-scrolls to the newest row when pending status, streamed
  content, or completed assistant output extends the conversation.
- User, tool, and error rows remain literal plain text so prompts, logs, and
  diagnostics are not reformatted.

## Rendering Architecture

- Chat Markdown parsing uses the `swift-markdown` AST rather than a hand-written
  line scanner. A block visitor converts parsed Markdown into small view models,
  and a separate inline visitor builds safe `AttributedString` values for SwiftUI
  text rendering.
- The renderer keeps Markdown as presentation state only. The chat transcript,
  persisted session history, exports, and runtime messages continue to store the
  raw model output.
- Parsed block output and inline attributed strings are cached after
  sanitization. The cache is lock-protected, bounded, and reports internal hit,
  miss, eviction, and latest parse-duration counters for tests and local metrics.
- Code fence contents are preserved after sanitization, with the closing-fence
  parser newline normalized to match the previous display behavior.

## Safety And Persistence

- Rich output is sanitized with `RichOutputSanitizer` before Markdown parsing or
  inline formatting.
- Unsafe links and active HTML are never rendered as rich content. Links render
  as readable label text without active navigation attributes, and images render
  safe alternate text only; remote image loading is not performed.
- Empty pending assistant rows are excluded from persisted chat session state.
- Stored transcript text remains the raw model text; Markdown rendering is
  view-only.

## Verification

- Runtime tests cover pending row creation, in-place final assistant replacement,
  stream failure cleanup, and empty completion cleanup.
- View tests cover Markdown block parsing, nested lists, block quotes, headings,
  thematic breaks, aligned tables, escaped table pipes, image-alt fallback, safe
  link-label rendering, row-kind scoping, sanitizer integration, and cache hit,
  miss, eviction, and repeated-render behavior.
- Manual UI verification should use the Chat surface with a delayed model
  response to confirm the pending indicator appears and then clears.

## Metrics

- Chat Markdown parse cache metrics: parse hit count, parse miss count, eviction
  count, and latest parse duration in milliseconds.
- Runtime hot-path metrics: N/A. The change is scoped to local UI rendering and
  does not alter model execution or HTTP serving paths.
