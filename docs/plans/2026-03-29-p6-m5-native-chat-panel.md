# P6-M5 Native Chat Panel

## Goal

Add a native SwiftUI Chat panel that consumes real control-plane chat execution state, displays chat history plus reasoning and tool-call deltas, and reflects multimodal route readiness without creating a second orchestrator outside the control plane.

## Scope

- Add a control-plane chat execution entry point for the desktop app.
- Reuse `ChatRequestTranslator` and `RequestCoordinator` instead of adding a second text execution stack.
- Add desktop chat session state, transcript rendering, and streaming delta handling.
- Surface Phase 6 multimodal route readiness inside the Chat panel so operators can see which analysis paths are available beside the interactive text path.
- Record menu-bar chat metrics for submit latency, first delta latency, and stream completion.

## Non-Goals

- No new public HTTP endpoints.
- No worker-direct transport from the desktop app.
- No inline binary upload flow for image or audio assets in this slice.
- No session-graph authoring UI beyond the local chat transcript state needed for the panel.

## Files

- Modify `apps/macos-menubar/Sources/AppMain/*`
- Modify `apps/macos-menubar/Tests/MenuBarTests/*`
- Modify `services/control-plane-swift/Sources/XPCService/*`
- Modify `services/control-plane-swift/Tests/ControlPlaneTests/*`
- Modify `docs/README.md`
- Create `docs/runbooks/phase-6-chat-panel.md`

## Implementation

1. Add a dedicated control-plane chat execution API for the desktop app.
   - Expose a chat-start method on the local XPC-facing client contract.
   - Keep the desktop app as a control-plane consumer by routing through `ChatRequestTranslator` and `RequestCoordinator`.
   - Return a typed chat event stream that includes token, reasoning, tool, usage, lifecycle, and terminal states.

2. Add native desktop chat state.
   - Track transcript entries, in-flight assistant output, reasoning text, tool calls, and request status.
   - Record menu-bar metrics for request start, first visible delta, completion, reasoning delta count, and tool delta count.
   - Derive multimodal readiness from the latest model snapshot so the panel can surface OCR, VLM, transcription, and speech availability.

3. Add the SwiftUI Chat panel.
   - Show transcript history and a composer for prompt submission.
   - Render assistant text, reasoning sections, tool-call sections, and request status badges.
   - Show route-readiness chips for the Phase 6 multimodal worker classes alongside the interactive text path.

4. Add tests and runbook evidence.
   - Cover local XPC chat execution and streaming behavior.
   - Cover runtime view-model transcript hydration and metrics updates.
   - Cover chat tab rendering and action dispatch.
   - Document the local operator workflow for launching the stack and exercising the native Chat panel.

## Performance Probes

- `menu.chat_submit_ms`
- `menu.chat_first_delta_ms`
- `menu.chat_stream_ms`
- `menu.chat_reasoning_delta_count`
- `menu.chat_tool_delta_count`

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`

## Acceptance

- The desktop app can submit a real chat request through the control plane without bypassing XPC.
- The Chat panel shows transcript history plus reasoning and tool-call deltas from the real runtime stream.
- The panel reflects current multimodal route readiness from control-plane truth.
- The touched scope meets the `>=95%` coverage rule.
- The metrics report contains non-`N/A` chat-panel numbers for the changed path.
