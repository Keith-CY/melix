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
- Assistant and reasoning rows render sanitized Markdown for inline emphasis,
  inline code, lists, fenced code blocks, and simple pipe tables.
- The transcript auto-scrolls to the newest row when pending status, streamed
  content, or completed assistant output extends the conversation.
- User, tool, and error rows remain literal plain text so prompts, logs, and
  diagnostics are not reformatted.

## Safety And Persistence

- Rich output is sanitized with `RichOutputSanitizer` before Markdown parsing.
- Unsafe links and active HTML are never rendered as rich content.
- Empty pending assistant rows are excluded from persisted chat session state.
- Stored transcript text remains the raw model text; Markdown rendering is
  view-only.

## Verification

- Runtime tests cover pending row creation, in-place final assistant replacement,
  stream failure cleanup, and empty completion cleanup.
- View tests cover Markdown block parsing, inline Markdown formatting, row-kind
  scoping, and sanitizer integration.
- Manual UI verification should use the Chat surface with a delayed model
  response to confirm the pending indicator appears and then clears.
