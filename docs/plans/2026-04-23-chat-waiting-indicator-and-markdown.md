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
- Code blocks present a compact language badge, a copy control, and lightweight
  syntax coloring for common local development snippets. The copy control writes
  only the fenced code text and does not mutate transcript state.
- Tables are horizontally scrollable when content is wider than the chat column.
  Column sizing remains content-aware within bounded minimum and maximum widths,
  and very long cell text is line-limited with tail truncation so one cell cannot
  consume the whole transcript row.
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
- Streaming and long-response rendering use a chunked render plan. Stable
  Markdown block chunks are parsed and cached independently, while the trailing
  in-progress chunk is reparsed as tokens arrive. Very long transcripts render
  chunks through a lazy stack so off-screen Markdown blocks do not require eager
  view construction.
- The renderer exposes local performance probes for 5 KB, 50 KB, and 200 KB
  Markdown samples. The probes report first-parse duration, cached-parse
  duration, block count, chunk count, cache hits, cache misses, and eviction
  counts.

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
- Fixture snapshot tests cover representative rich Markdown transcripts,
  including code blocks, tables, nested lists, quotes, and unsafe content.
- Focused tests cover code-block syntax highlighting, language badge
  normalization, copy behavior, table column sizing and truncation policy,
  streaming chunk reuse, lazy render-plan thresholds, and 5 KB / 50 KB / 200 KB
  parse benchmark reporting.
- Manual UI verification should use the Chat surface with a delayed model
  response to confirm the pending indicator appears and then clears.

## Metrics

- Chat Markdown parse cache metrics: parse hit count, parse miss count, eviction
  count, and latest parse duration in milliseconds.
- Chat Markdown streaming metrics: chunk count, stable chunk reuse count, first
  parse duration, cached parse duration, and per-sample parse durations for 5 KB,
  50 KB, and 200 KB local benchmark samples.
- Runtime hot-path metrics: N/A. The change is scoped to local UI rendering and
  does not alter model execution or HTTP serving paths.
