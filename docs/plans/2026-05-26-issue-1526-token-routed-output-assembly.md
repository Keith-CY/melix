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

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_generate_stream_receipts.py services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_stream_assembler_receipts.py -q`
- `make py-test` before PR handoff when the focused tests are stable.
- Metrics report: Python worker receipt scope, with coverage measured for
  `worker/runtime/stream_assembler.py`, `worker/runtime/token_route_receipt.py`,
  and `worker/engine/engine_core.py` when preparing the final commit.
