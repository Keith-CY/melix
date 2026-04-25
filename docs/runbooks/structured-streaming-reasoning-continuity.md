# Structured Streaming And Reasoning Continuity Runbook

Use this runbook when debugging Chat Completions, Completions, Responses, or Messages streaming behavior involving reasoning, tool calls, structured JSON output, or repeated-turn session continuity.

## Scope

Covered:

- shipped stream-capable text endpoints
- Swift request normalization and reasoning policy resolution
- Python request-local stream assembly
- JSON-only structured-output parser suppression
- hidden reasoning continuity markers and cache compatibility fields

Not covered:

- native Ollama `/api/*` routes
- new non-stream HTTP behavior
- direct worker cache payload inspection

## Expected Request Metadata

For a reasoning-enabled request, inspect the worker `GenerateRequest.execution` metadata:

- `melix.reasoning.mode`
- `melix.reasoning.mode_source`
- `melix.reasoning.effort`
- `melix.reasoning.auto_detect_model_family`
- `melix.reasoning.continuity_rehydrated`
- `ReasoningConfig.mode`
- `ReasoningConfig.mode_source`
- `ReasoningConfig.effort`
- `ReasoningConfig.continuity_rehydrated`

Cache compatibility must include:

- `melix.cache.fingerprint.reasoning_mode`
- `melix.cache.fingerprint.reasoning_effort`
- `melix.cache.fingerprint.parser_mode`
- `melix.cache.fingerprint.structured_output_mode`
- `melix.cache.fingerprint.chat_template_kwargs`
- `melix.cache.fingerprint.reasoning_continuity_present`

## Parser Diagnostics

The worker stream assembler reports parser metrics on completed events:

- `parser_state_bleed_count`
- `duplicate_tool_delta_count`
- `reasoning_leak_count`
- `malformed_tool_fragment_count`

Expected healthy values:

- 1,000 independent assembler instances keep `parser_state_bleed_count == 0`
- repeated cumulative tool chunks keep `duplicate_tool_delta_count == 0`
- structured JSON output keeps `reasoning_leak_count == 0`
- truncated tool calls increment `malformed_tool_fragment_count` without failing the stream

## JSON Structured Output Checks

For JSON-only requests without explicit tools:

1. Confirm `melix.structured_output.mode` is `json_object` or `json_schema`.
2. Confirm `melix.tool_parser.mode` is absent.
3. Confirm `melix.tool_parser.suppressed_reason` is `structured_output_json_without_tools`.
4. Confirm completed assistant text starts at the first JSON delimiter and has no reasoning preamble.

If an explicit tool parser was requested, the parser must remain enabled.

## Continuity Checks

For a repeated session turn:

1. The parent completed event may carry `reasoning_text`; the control plane stores it internally.
2. The follow-up request should set `ReasoningConfig.continuity_rehydrated = true`.
3. The follow-up request should include `melix.reasoning.continuity_key` and `melix.reasoning.continuity_request_id`.
4. Effective template kwargs should include `melix_reasoning_continuity`.
5. No worker ext field, public session state, or public assistant content should include the raw hidden reasoning text.

## Verification Commands

Run focused checks first:

```bash
make proto
HOME="$(pwd)/.swift-home/control-plane-swift" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex/control-plane-swift" xcrun swift test --no-parallel --package-path services/control-plane-swift --filter 'TextEndpointContractTests|StructuredOutputValidationTests|RequestCoordinatorTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_generate_stream.py -q
```

Before handoff, run the repository workflow:

```bash
make swift-test
make py-test
make integration-test
```

Coverage evidence for this scope should include Swift request/coordinator tests and Python stream assembler tests. If full coverage tooling is unavailable, report the exact command failure and the targeted pass/fail evidence above.
