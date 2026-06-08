# Issue 1766 Streaming UI Render Cadence Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every chat stream token event intact while bounding desktop chat transcript render updates during high-rate local decode.

**Architecture:** `RuntimeViewModel` remains the client-side owner of chat stream presentation. The stream loop records raw event cadence and transcript bytes separately from visible transcript flushes, while the presentation queue gates non-terminal visible updates to one bounded frame interval. Terminal `completed` and failure events force-flush pending presentation text before the final status update.

**Tech Stack:** Swift, Swift Testing, macOS menu bar AppMain, `MenuBarMetricsStore`, fake `ControlPlaneXPCClient` stream fixtures.

---

## Source Documents

- `AGENTS.md`
- `docs/plans/2026-03-31-m15-1-token-stream-presentation-smoothing.md`
- `docs/plans/2026-03-31-m15-desktop-signals-download-recovery-and-streaming-polish.md`
- `docs/runbooks/desktop-polish.md`

## Files

- Modify `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
  - Add a stress fixture with many zero-delay token events.
  - Count server token events separately from `RuntimeViewModel.onStateChanged` render callbacks.
  - Assert final transcript parity with the concatenated token payload.
- Modify `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
  - Track raw chat stream event, token event, and transcript byte counts.
  - Gate non-terminal presentation flushes with `chatPresentationFlushInterval`.
  - Avoid per-token outer `notifyStateChanged()` calls when no visible state was flushed.
  - Record separate stream and presentation flush metrics.
- Modify `apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`
  - Extend smoke payload metrics while keeping nested JSON construction compiler-friendly.
- Modify `services/control-plane-swift/Tests/ControlPlaneTests/EventSubscriptionHubTests.swift`
  - Stabilize CI verification by waiting for the first queued admission snapshot instead of relying on a fixed scheduler sleep.
- Modify `docs/runbooks/desktop-polish.md`
  - Document the new stream and presentation metrics used to diagnose cadence regressions.

## Performance Probes and Success Metrics

- Measurement points:
  - raw stream event count: `menu.chat_stream_event_count`
  - raw token delta count: `menu.chat_token_delta_count`
  - raw assistant transcript bytes: `menu.chat_stream_transcript_bytes`
  - presentation flush count and lag: existing `menu.chat_presentation_flush_count` and `menu.chat_presentation_lag_ms`
  - visible assistant transcript callback count: `RuntimeViewModel.onStateChanged` test observer
  - transcript parity mismatch count: `menu.chat_transcript_parity_mismatch_count`
- Success metrics:
  - a high-rate 240-token fixture records all 240 token events
  - final assistant transcript equals the concatenated token fixture exactly
  - visible render callbacks for non-empty assistant transcript stay below the token event count and within the bounded cadence budget for the synthetic stream
  - terminal completion presents the full transcript by the first completed-state render callback
  - `make swift-test` and the repository pre-commit gate complete without performance regression

## Tasks

### Task 1: Add a failing stress test

- [x] Add `chatPromptCoalescesRenderCadenceWithoutDroppingStreamTranscriptEvents` beside the existing chat streaming tests in `RuntimeViewModelTests.swift`.
- [x] Build 240 token events with deterministic text fragments and append a terminal `.completed` event whose `assistantText` is the concatenated fixture.
- [x] Use `viewModel.onStateChanged` to count visible assistant transcript render callbacks separately from fixture token count.
- [x] Assert stream metrics exist, raw token count is 240, render callbacks are far below token count, and final completed-state callback already contains the full transcript.
- [x] Run the focused test and confirm it fails before production changes.

### Task 2: Gate presentation flush cadence

- [x] Add `chatPresentationLastFlushAt` state and reset it with other presentation state.
- [x] Keep the first presentation flush immediate when no recent visible flush exists.
- [x] When token deltas arrive faster than `chatPresentationFlushInterval`, queue the text and start a presentation task that sleeps until the next allowed flush.
- [x] Keep `flushPendingChatPresentation()` force-complete behavior synchronous for terminal events.
- [x] Run the focused test and existing bursty smoothing tests.

### Task 3: Separate raw stream and render metrics

- [x] Count all stream events in the `for try await event in execution.stream` loop.
- [x] Count token deltas separately from reasoning/tool side-channel deltas.
- [x] Accumulate raw assistant transcript bytes from token deltas.
- [x] Record presentation flush count as the UI cadence metric.
- [x] Record transcript parity mismatch count by comparing non-empty raw assistant text with non-empty terminal assistant text.
- [x] Re-run the focused tests.

### Task 4: Update runbook and verify

- [x] Update `docs/runbooks/desktop-polish.md` with the new metrics and troubleshooting guidance.
- [x] Run the focused macOS menu bar tests for the touched chat streaming behavior.
- [x] Run `make swift-test`.
- [x] Run the repository pre-commit hook before commit and include coverage/metrics evidence in the PR body.

### Task 5: Address PR CI follow-up failures

- [x] Split the desktop polish smoke JSON payload into explicit sub-dictionaries so CI Swift type-checking does not time out.
- [x] Replace fixed sleeps in the impacted AdmissionGate cohort tests with the existing snapshot wait helper.
- [x] Run `make swift-test-menubar` and `make swift-test-control-core`.
- [x] Record follow-up changed-line coverage for the smoke payload and AdmissionGate test changes.

### Task 6: Address PR review feedback

- [x] Replace wall-clock presentation cadence state with `ContinuousClock.Instant`.
- [x] Keep cadence sleeps and eligibility checks on `Duration` arithmetic.
- [x] Remove the duplicate `menu.chat_render_update_count` metric because presentation flush count already records that cadence boundary.
- [x] Remove redundant discard assignments at token, reasoning, and tool delta call sites.

### Task 7: Stabilize release-gates cadence assertions

- [x] Treat the GitHub release-gates failure with 11 presentation flushes for the 240-token synthetic stream as the red verification signal.
- [x] Keep the test contract focused on stream fidelity, completed-state transcript parity, and render callback coalescing relative to raw token count instead of a host-speed-dependent fixed flush count.
