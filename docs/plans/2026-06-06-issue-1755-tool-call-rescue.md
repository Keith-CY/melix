# Issue 1755: Local Tool-Call Format Rescue

## Goal

Add a worker-side rescue path for local-model tool-call formats that are not
the canonical Qwen `<tool_call>{...}</tool_call>` envelope. The parser should
convert accepted XML, fenced, and vendor-style outputs into Melix
`AssembledToolCall` deltas without exposing raw tool-call markup as assistant
text.

## Scope

- Extend `RequestStreamAssembler` so production streaming and offline
  tool-call evaluation share the same rescue behavior.
- Accept these wire formats when tool parsing is enabled:
  - canonical Qwen XML tool calls
  - fenced JSON tool calls
  - `[TOOL_CALL]...[/TOOL_CALL]` JSON blocks
  - XML `<invoke>` tool invocations
  - MiniMax-style `<tool_code>` invocations
  - normalized DeepSeek-style XML tool-call blocks
- Normalize common external aliases into declared Melix tool names through the
  existing allowed-tool-name resolution path.
- Emit a typed retryable parser diagnostic when a model puts a JSON tool call
  in a wrong envelope such as a `python` code fence.
- Preserve parser metrics for malformed fragments, markup leaks, name
  normalization, unknown tools, and the effective parser configuration receipt.
- Treat `stream_parser_rescue_path` as a parser configuration receipt. The
  field records that local tool-call rescue parsing was wired for the request;
  it is not a per-fragment "rescue fired" signal. Actual malformed or unknown
  tool activity remains reported through the existing parser counters.

## Non-Goals

- No protobuf schema change.
- No control-plane request-shaping change.
- No new network-backed provider integration.

## Performance Probes

The changed path is token-stream parsing. The relevant probes are the existing
PR-scoped stream assembler parser-mode cache probe, structural-prefix probe,
and token-byte fast-decode probe if selected by the performance harness.
Success is no in-scope regression in the PR performance report and no increase
in parser failure metrics for the existing tool-call fixture dataset.

The parser-mode probe keeps the same metrics and thresholds but uses 512
samples by default so sub-2 ms parser measurements are not dominated by a
single scheduler outlier.

## Verification

- Add failing assembler tests for XML invoke, fenced JSON, MiniMax tool code,
  normalized DeepSeek XML, malformed JSON, wrong-envelope retry diagnostics,
  and markup stripping.
- Run focused Python tests for `test_generate_stream.py` and
  `test_tool_call_system_prompt_eval.py`.
- Run scoped coverage for the changed Python worker files and tests.
- Run the full pre-commit gate before committing.
