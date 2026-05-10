# Issue 615 Structured Streaming Follow-ups Implementation Plan

## Goal

Close the post-closure #41 follow-up gap tracked by #615 by making Python text generation streaming option-aware, token-metadata-aware, safer for malformed reasoning channels, and observable through parser/effective-config receipts.

## Architecture

Keep the shipped worker protocol stable and extend the Python request-local streaming layer. Runtime token events become the metadata boundary: they may carry token ids, logprobs, byte fragments, and per-token parser observations. `RequestStreamAssembler` remains request-scoped, but records generated-token/logprob parity, byte-fallback detokenization, disabled/empty reasoning discipline, and effective parser configuration on the final `Completed.parser_metrics` map. Prompt history normalization is implemented in the Python prompt renderer as a final safety layer before tokenizer chat-template rendering; Swift translation remains the primary normalized request producer. Typed `ToolConfig.tools` are converted into tokenizer-native tool exemplars only when no explicit native `tools` kwargs are already present.

## Files

- Modify `services/mlx-worker-python/worker/runtime/stream_assembler.py`
  - Add token metadata fields to `StreamFragment` and `AssemblyDelta`.
  - Add byte-fallback decoding state.
  - Add generated-token/logprob counters and effective-config metrics.
  - Add empty thinking sentinel and unclosed reasoning recovery heuristics.
- Modify `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
  - Add optional token metadata fields to `RuntimeTokenEvent`.
  - Normalize chat-template history so non-leading system/developer messages are merged into one leading system block before template rendering.
  - Forward tokenizer byte fragments and metadata from MLX-LM stream responses when present.
- Modify `services/mlx-worker-python/worker/engine/engine_core.py`
  - Pass runtime token metadata into the assembler.
  - Emit token parser observations when available.
  - Export effective parser/tool/reasoning config in completion metrics.
  - Convert typed `ToolConfig.tools` into native chat-template `tools` payloads.
- Modify `services/mlx-worker-python/tests/test_stream_assembler.py`
  - Add fixtures for stream interval/logprob parity, byte-fallback Unicode, empty thinking sentinels, disabled reasoning, and unclosed reasoning recovery.
- Modify `services/mlx-worker-python/tests/test_generate_stream.py`
  - Add integration-style worker tests for metadata forwarding, parser observations, effective-config receipts, and prompt-history normalization.
- Update `docs/runbooks/structured-streaming-reasoning-continuity.md`
  - Document new metrics and focused verification commands.

## Performance Probes And Metrics

- `generated_token_count`: count of runtime token metadata records accepted by the request assembler.
- `logprob_entry_count`: count of accepted token metadata records with logprob metadata.
- `stream_interval_delta_flush_count`: count of visible deltas emitted from cumulative multi-token flushes.
- `byte_fallback_merge_count`: count of byte-fragment merges that completed into visible Unicode text.
- `empty_thinking_sentinel_count`: count of whitespace-only closed thinking blocks suppressed as explicit thinking-off sentinels.
- `reasoning_parser_bypassed_count`: count of hidden-reasoning blocks suppressed while reasoning is disabled.
- `reasoning_channel_recovery_count`: existing recovery counter, extended to recover visible answer tails from malformed unclosed reasoning channels.
- `response_history_normalized_count`: count of non-leading system/developer messages merged before chat-template rendering.
- `native_tool_exemplar_injected_count`: count of requests where typed `ToolConfig.tools` was injected into tokenizer-native template kwargs.
- `effective_parser_config_json`: compact JSON receipt for request-scoped parser/tool/reasoning config before first response.

## Tasks

1. Write RED tests in `test_stream_assembler.py` for token/logprob parity, byte-fallback decoding, empty thinking sentinel suppression, and visible tail recovery from unclosed reasoning.
2. Write RED tests in `test_generate_stream.py` for runtime metadata forwarding, token parser observations, effective parser config receipts, and prompt-history normalization.
3. Implement `RuntimeTokenEvent` and `StreamFragment` metadata fields, byte decoding, and parser metric accounting.
4. Implement prompt-history normalization in `MLXTextRuntime._render_prompt` and wire a normalization-count receipt into execution metadata.
5. Implement native tool exemplar injection from typed `ToolConfig.tools` into tokenizer `tools` kwargs when no explicit `tools` kwarg is already present.
6. Implement engine wiring for metadata forwarding, token observations, and effective config metrics.
7. Update the structured streaming runbook with the new receipt fields and verification commands.
8. Run focused Python tests with coverage for changed scope.
9. Run the repository-required verification that is practical for the touched scope, and record any unavailable full-suite gaps honestly in the PR body.

## Acceptance Criteria

- Streamed and non-streamed byte-fallback Unicode fixtures render the same visible text.
- Runtime token metadata reports equal generated-token/logprob counts under cumulative multi-token flushes.
- Disabled reasoning and empty thinking-off sentinels emit no reasoning delta and no visible reasoning leakage.
- Malformed unclosed reasoning channels preserve recoverable visible answer tails at EOS.
- Dict/object tool-call arguments remain serialized only at the schema boundary.
- Native tool/parser effective config is present in completion metrics before first response completion.
- Typed `ToolConfig.tools` is injected as tokenizer-native `tools` kwargs when the request does not already provide concrete native tools.
- Previous-response replay plus non-leading system/developer instructions normalizes into a single leading system block before tokenizer template rendering.
- Existing stream assembler and generate-stream tests remain green.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_generate_stream.py -q
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run --source=worker.runtime.stream_assembler,worker.runtime.mlx_text_runtime,worker.engine.engine_core -m pytest services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_generate_stream.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /private/tmp/issue615_coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /private/tmp/issue615_coverage.json --diff-from origin/main services/mlx-worker-python/worker/runtime/stream_assembler.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/worker/engine/engine_core.py
make py-test
```
