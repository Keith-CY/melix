# Issue 1526 Token-Routed Output Assembly

## Goal

Add request-local token-routed output assembly receipts that keep hidden
reasoning, tool calls, and visible text separated for both stream and
non-stream generation finalization.

## Governing Inputs

- Issue #1526: token-routed output assembly for reasoning, tools, and visible text.
- `docs/control-plane-protocol.md`
- `docs/plans/2026-04-26-issue-41-structured-streaming-reasoning-continuity.md`

## Architecture

The Python worker remains the assembly authority for generated token spans. The
control plane supplies request-local policy context through `ExecutionMetadata`
and `ToolConfig`; `RequestStreamAssembler` consumes that context, emits typed
reasoning/tool/visible deltas, and `TokenRouteReceipt` records the token route
receipt without deriving tool calls from final visible text.

The stream and non-stream paths share the same `RequestStreamAssembler` and text
finalizer receipt state. Fallback raw-text parsing is allowed only as an
observable fallback path and must remain distinguishable from token-id-backed
routing through receipt fields.

## Implementation Slices

1. Merge current `origin/main` and preserve the upstream multi-token span
   routing behavior.
2. Keep route receipts active for reasoning, structured-output, tool parser,
   declared tool, and non-auto tool-choice requests.
3. Extend receipt coverage so each routed span records channel,
   `channel_source`, `reasoning_mode`, and `tool_choice_policy`.
4. Record request-local allowed-tool context and distinguish declared tools,
   explicit empty tool lists, omitted tools, and suppressed/unknown tool deltas.
5. Add regression fixtures for partial or healed tool JSON suppression, pure
   content reasoning fallback, reasoning-only truncation, alternate final
   terminators, and stream/non-stream normalized receipt parity.
6. Update the structured streaming runbook with the receipt fields and metrics
   needed to diagnose routing decisions.
7. Add a request-local channel assembly state that records the preferred
   classified channel source, preserves incomplete marker tails across chunks,
   exposes annotation-dependent segment state for future protocol-bearing
   annotation payloads, and terminally closes orphan tool-call markers with typed
   metrics.

## Current Slice Status

Completed:

- Token route receipts report router identity, channel, channel source,
  reasoning mode, tool-choice policy, visible token count, hidden reasoning
  token count, and raw-text fallback use.
- Allowed-tool receipts distinguish declared tools, explicit empty tool lists,
  omitted tools, schema conflicts, and parser suppression reasons.
- Partial and argumentless tool objects are suppressed and counted with
  `partial_tool_candidate_count` instead of being promoted to structured tool
  calls.
- `RequestStreamAssembler` owns an explicit request-local
  `ChannelAssemblyState` for the preferred channel source, pending marker tail,
  annotation-dependent segment count, and open tool events.
- Split marker prefixes and terminal partial markers are covered by fixtures and
  reported through `max_pending_marker_tail_chars`,
  `pending_marker_tail_chars`, and `terminal_marker_tail_flush_count`.
- Orphan tool-call markers are terminally flushed without visible markup leaks
  and reported through `orphan_tool_event_flush_count`.
- Add worker `ExecuteEvent` payloads for typed `AnnotationDelta` and
  `ToolResultDelta` so annotation and tool-result payloads travel separately
  from visible assistant text.
- Add Python runtime event types for annotation and tool-result payloads, and
  pass them through `EngineCore.generate`.
- Keep annotation/tool-result payloads out of `assistant_text`; use
  `ChannelAssemblyState` to record pending/resolved annotation counts and
  buffered tool-result counts in completed parser metrics.
- Control-plane chat execution and HTTP SSE bridging preserve typed annotation
  and tool-result frames without promoting their payload JSON to visible text.
- Regenerate protocol artifacts after schema changes.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- Focused Python coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_generate_stream_receipts.py services/mlx-worker-python/tests/test_stream_assembler_receipts.py -q`
- Python changed-line coverage:
  `UV_PYTHON=3.12 UV_CACHE_DIR="$PWD/.uv-cache" uv run python scripts/python_changed_line_coverage.py --coverage-json .runtime/coverage/issue-1526-python-coverage.json --diff-from origin/main services/mlx-worker-python/worker/engine/engine_core.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/worker/runtime/stream_assembler.py services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_stream_assembler.py`
  reported 100.00% changed-line coverage, 113/113 measurable changed lines.
- Focused control-plane Swift coverage:
  `HOME="$PWD/.swift-home/control-coverage" CLANG_MODULE_CACHE_PATH="$PWD/services/control-plane-swift/.build/ModuleCache.noindex/control-coverage" xcrun swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneChatExecutionTests|SSEStreamWriterTests|RequestCoordinatorTests'`
  plus `scripts/swift_changed_line_coverage.py` reported 97.24% changed-line
  coverage, 352/362 measurable changed lines.
- Focused macOS menubar Swift coverage:
  `HOME="$PWD/.swift-home/menubar-coverage" CLANG_MODULE_CACHE_PATH="$PWD/apps/macos-menubar/.build/ModuleCache.noindex/coverage" xcrun swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests/chatPromptIgnoresAnnotationAndToolResultPayloadsInVisibleTranscript'`
  plus `scripts/swift_changed_line_coverage.py` reported 100.00% changed-line
  coverage, 38/38 measurable changed lines.
- Metrics report: worker parser metrics now include
  `annotation_delta_count`, `tool_result_delta_count`,
  `annotation_payload_resolved_count`, `annotation_payload_missing_count`, and
  `tool_result_payload_buffered_count`; HTTP metrics include
  `http.annotation_delta_count` and `http.tool_result_delta_count`.
