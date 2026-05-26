import json

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.engine import engine_core as engine_core_module
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent


class StructuredStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(
            text="",
            raw_text=(
                '<think>trace</think>'
                '<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>'
                "visible"
            ),
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="stop",
        )


class TokenRoutedStructuredBackend:
    runtime_name = "fake-mlx"

    def __init__(self, *, token_ids: tuple[int, ...]) -> None:
        self.token_ids = token_ids

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        yield RuntimeTokenEvent(
            text="",
            raw_text=(
                '<think>trace</think>'
                '<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>'
                "visible"
            ),
            token_ids=self.token_ids,
            prompt_tokens=3,
            completion_tokens=3,
            finish_reason="stop",
        )

class TokenRoutedMultispanBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        yield RuntimeTokenEvent(
            text="",
            raw_text=(
                "<think>alpha beta gamma</think>"
                '<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>'
                "visible"
            ),
            token_ids=(101, 102, 103, 104, 105, 106),
            prompt_tokens=3,
            completion_tokens=6,
            finish_reason="stop",
        )


class TokenRoutedVisibleBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        yield RuntimeTokenEvent(
            text="",
            raw_text="visible text",
            token_ids=(201, 202),
            prompt_tokens=3,
            completion_tokens=2,
            finish_reason="stop",
        )


class FinalizerParityBackend:
    runtime_name = "fake-mlx"

    def __init__(self, *, raw_text: str, prompt_tokens: int = 11, completion_tokens: int = 3) -> None:
        self.raw_text = raw_text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        yield RuntimeTokenEvent(
            text="",
            raw_text=self.raw_text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            finish_reason="length",
        )


def test_generate_completed_event_preserves_compatibility_policy_receipt() -> None:
    inference_service, model_handle = _build_services(StructuredStreamingBackend())
    receipt = (
        '{"compat_surface":"openai.chat.completions",'
        '"effective_config_hash":"abc123",'
        '"reasoning_mode":"enabled",'
        '"stream_mode":"stream"}'
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-compat-policy-receipt"),
            model_handle=model_handle,
            ext={
                "melix.compat.policy_receipt_json": receipt,
                "melix.compat.effective_config_hash": "abc123",
                "melix.compat.reasoning_mode": "enabled",
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use a tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert completed.parser_metrics["compat_policy_receipt_json"] == receipt
    assert completed.parser_metrics["compat_effective_config_hash"] == "abc123"
    assert "hidden" not in completed.parser_metrics["compat_policy_receipt_json"]


def test_plain_compatibility_receipt_keeps_metadata_without_route_tracking() -> None:
    inference_service, model_handle = _build_services(FinalizerParityBackend(raw_text="plain answer"))
    receipt = json.dumps(
        {
            "compat_surface": "openai.chat.completions",
            "reasoning_mode": "disabled",
            "stream_mode": "stream",
            "tool_choice_resolved": "auto",
        },
        sort_keys=True,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-plain-compat-policy-receipt"),
            model_handle=model_handle,
            ext={
                "melix.compat.policy_receipt_json": receipt,
                "melix.compat.effective_config_hash": "plain123",
                "melix.response.created": "1716500000",
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    completed = next(
        event.completed for event in inference_service.Generate(request, context=None)
        if event.HasField("completed")
    )
    token_route_receipt = json.loads(completed.parser_metrics["token_route_receipt_json"])

    assert completed.parser_metrics["compat_policy_receipt_json"] == receipt
    assert completed.parser_metrics["compat_effective_config_hash"] == "plain123"
    assert completed.parser_metrics["created"] == "1716500000"
    assert token_route_receipt["route_tracking_enabled"] is False


def test_plain_fast_path_finalizes_through_shared_text_receipt_state(monkeypatch) -> None:
    receipts: list[object] = []
    original_apply = engine_core_module.apply_text_response_metrics

    def record_apply(parser_metrics: dict[str, str], *, receipt: object) -> None:
        receipts.append(receipt)
        original_apply(parser_metrics, receipt=receipt)

    monkeypatch.setattr(engine_core_module, "apply_text_response_metrics", record_apply)
    inference_service, model_handle = _build_services(
        FinalizerParityBackend(raw_text="plain answer", prompt_tokens=7, completion_tokens=2)
    )

    for stream in (True, False):
        request = inference_pb2.GenerateRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(
                    request_id=f"req-plain-finalizer-{'stream' if stream else 'non-stream'}"
                ),
                model_handle=model_handle,
                ext={"melix.response.created": "1716500001"},
            ),
            messages=[
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="plain finalizer")],
                )
            ],
            sampling=common_pb2.SamplingConfig(max_output_tokens=8),
            stream=stream,
            return_usage=True,
        )
        completed = next(
            event.completed for event in inference_service.Generate(request, context=None)
            if event.HasField("completed")
        )
        assert completed.parser_metrics["finalizer_path"] == (
            "stream" if stream else "non_stream"
        )

    assert [receipt.stream_mode for receipt in receipts] == [True, False]
    assert [receipt.usage_trailer_emitted for receipt in receipts] == [True, False]
    assert all(receipt.usage.prompt_tokens == 7 for receipt in receipts)
    assert all(receipt.usage.completion_tokens == 2 for receipt in receipts)


def test_structured_tool_calls_finalize_through_shared_text_receipt_state(monkeypatch) -> None:
    receipts: list[object] = []
    original_apply = engine_core_module.apply_text_response_metrics

    def record_apply(parser_metrics: dict[str, str], *, receipt: object) -> None:
        receipts.append(receipt)
        original_apply(parser_metrics, receipt=receipt)

    monkeypatch.setattr(engine_core_module, "apply_text_response_metrics", record_apply)
    inference_service, model_handle = _build_services(StructuredStreamingBackend())
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-structured-finalizer-tool-call"),
            model_handle=model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.response.created": "1716500002",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=True,
                mode_source="request_enable_thinking",
            ),
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="search",
                        json_schema='{"type":"object"}',
                    )
                ],
                tool_choice="required",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use a tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    completed = next(
        event.completed for event in inference_service.Generate(request, context=None)
        if event.HasField("completed")
    )

    assert [receipt.tool_calls_finalized for receipt in receipts] == [True]
    assert completed.parser_metrics["tool_calls_finalized"] == "true"
    assert completed.parser_metrics["reasoning_finalized"] == "true"


def test_generate_token_route_receipt_uses_compat_policy_context_and_matches_stream_modes() -> None:
    inference_service, model_handle = _build_services(StructuredStreamingBackend())
    compat_receipt = (
        '{"compat_surface":"openai.chat.completions",'
        '"reasoning_mode":"enabled",'
        '"tool_choice_resolved":"required",'
        '"stream_mode":"stream"}'
    )

    stream_completed = next(
        event.completed
        for event in inference_service.Generate(
            _token_route_request(model_handle, compat_receipt=compat_receipt, stream=True),
            context=None,
        )
        if event.HasField("completed")
    )
    non_stream_completed = next(
        event.completed
        for event in inference_service.Generate(
            _token_route_request(model_handle, compat_receipt=compat_receipt, stream=False),
            context=None,
        )
        if event.HasField("completed")
    )
    stream_receipt = json.loads(stream_completed.parser_metrics["token_route_receipt_json"])
    non_stream_receipt = json.loads(non_stream_completed.parser_metrics["token_route_receipt_json"])

    assert stream_completed.assistant_text == non_stream_completed.assistant_text == "visible"
    assert stream_completed.reasoning_text == non_stream_completed.reasoning_text == "trace"
    assert stream_receipt["tool_choice_policy"] == "required"
    assert stream_receipt["reasoning_mode"] == "enabled"
    assert stream_receipt["visible_text_tokens"] == non_stream_receipt["visible_text_tokens"] == 1
    assert stream_receipt["hidden_reasoning_tokens"] == non_stream_receipt["hidden_reasoning_tokens"] == 1
    assert stream_receipt["routes"] == non_stream_receipt["routes"]


def test_generate_token_route_receipt_records_actual_token_ids_by_channel_span() -> None:
    inference_service, model_handle = _build_services(
        TokenRoutedStructuredBackend(token_ids=(101, 102, 103))
    )
    completed = next(
        event.completed
        for event in inference_service.Generate(
            _token_route_request(
                model_handle,
                compat_receipt='{"reasoning_mode":"enabled","tool_choice_resolved":"required"}',
                stream=True,
            ),
            context=None,
        )
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["token_route_receipt_json"])

    assert completed.assistant_text == "visible"
    assert completed.reasoning_text == "trace"
    assert receipt["fallback_raw_text_used"] is False
    assert receipt["visible_text_tokens"] == 1
    assert receipt["hidden_reasoning_tokens"] == 1
    assert [
        (route["token_id"], route["channel"], route["channel_source"])
        for route in receipt["routes"]
    ] == [
        (101, "hidden_reasoning", "reasoning_tag"),
        (102, "tool_call", "tool_call_tag"),
        (103, "visible_text", "raw_text"),
    ]

def test_generate_token_route_receipt_keeps_multitoken_hidden_and_tool_spans() -> None:
    inference_service, model_handle = _build_services(TokenRoutedMultispanBackend())
    completed = next(
        event.completed
        for event in inference_service.Generate(
            _token_route_request(
                model_handle,
                compat_receipt='{"reasoning_mode":"enabled","tool_choice_resolved":"required"}',
                stream=True,
            ),
            context=None,
        )
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["token_route_receipt_json"])

    assert completed.assistant_text == "visible"
    assert completed.reasoning_text == "alpha beta gamma"
    assert receipt["fallback_raw_text_used"] is False
    assert receipt["visible_text_tokens"] == 1
    assert receipt["hidden_reasoning_tokens"] == 3
    assert receipt["route_count"] == 6
    assert [
        (route["token_id"], route["channel"], route["channel_source"])
        for route in receipt["routes"]
    ] == [
        (101, "hidden_reasoning", "reasoning_tag"),
        (102, "hidden_reasoning", "reasoning_tag"),
        (103, "hidden_reasoning", "reasoning_tag"),
        (104, "tool_call", "tool_call_tag"),
        (105, "tool_call", "tool_call_tag"),
        (106, "visible_text", "raw_text"),
    ]


def test_generate_token_route_receipt_marks_raw_text_fallback_without_token_ids() -> None:
    inference_service, model_handle = _build_services(
        TokenRoutedStructuredBackend(token_ids=())
    )
    completed = next(
        event.completed
        for event in inference_service.Generate(
            _token_route_request(
                model_handle,
                compat_receipt='{"reasoning_mode":"enabled","tool_choice_resolved":"required"}',
                stream=True,
            ),
            context=None,
        )
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["token_route_receipt_json"])

    assert receipt["fallback_raw_text_used"] is True
    assert [
        (route["token_id"], route["channel"], route["channel_source"])
        for route in receipt["routes"]
    ] == [
        (0, "hidden_reasoning", "reasoning_tag"),
        (1, "tool_call", "tool_call_tag"),
        (2, "visible_text", "raw_text"),
    ]


def test_generate_token_route_receipt_counts_all_tokens_in_visible_span() -> None:
    inference_service, model_handle = _build_services(TokenRoutedVisibleBackend())
    completed = next(
        event.completed
        for event in inference_service.Generate(
            _token_route_request(
                model_handle,
                compat_receipt='{"reasoning_mode":"disabled","tool_choice_resolved":"none"}',
                stream=True,
                reasoning_enabled=False,
            ),
            context=None,
        )
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["token_route_receipt_json"])

    assert completed.assistant_text == "visible text"
    assert receipt["fallback_raw_text_used"] is False
    assert receipt["visible_text_tokens"] == 2
    assert [
        (route["token_id"], route["channel"], route["channel_source"])
        for route in receipt["routes"]
    ] == [
        (201, "visible_text", "raw_text"),
        (202, "visible_text", "raw_text"),
    ]


def test_generate_records_request_local_allowed_tools_receipt() -> None:
    inference_service, model_handle = _build_services(TokenRoutedVisibleBackend())
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-allowed-tools-receipt"),
            model_handle=model_handle,
            ext={
                "melix.tool_config.source": "openai_chat_tools",
                "melix.tool_config.tool_count": "3",
                "melix.mcp.source_ids": "shared,task",
            },
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="search",
                        description="shared search",
                        json_schema='{"type":"object","properties":{"q":{"type":"string"}}}',
                    ),
                    common_pb2.ToolDefinition(
                        name="search",
                        description="task override",
                        json_schema='{"type":"object","properties":{"query":{"type":"string"}}}',
                    ),
                    common_pb2.ToolDefinition(
                        name="lookup",
                        description="lookup docs",
                        json_schema='{"type":"object"}',
                    ),
                ],
                tool_choice="auto",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="List tools")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    completed = next(
        event.completed
        for event in inference_service.Generate(request, context=None)
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["allowed_tools_receipt_json"])

    assert receipt == {
        "allowed_tool_names": ["search", "lookup"],
        "allowed_tool_count": 2,
        "tool_choice_policy": "auto",
        "tool_config_source": "openai_chat_tools",
        "tool_source_ids": ["shared", "task"],
        "tool_config_state": "declared",
        "schema_conflict_count": 1,
        "schema_conflicts": ["search"],
        "suppressed_reason": "",
    }


def test_generate_treats_equivalent_duplicate_tool_schemas_as_same() -> None:
    inference_service, model_handle = _build_services(TokenRoutedVisibleBackend())
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-equivalent-tool-schemas"),
            model_handle=model_handle,
            ext={
                "melix.tool_config.source": "openai_chat_tools",
                "melix.tool_config.tool_count": "2",
            },
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="search",
                        json_schema='{"type":"object","properties":{"q":{"type":"string"}}}',
                    ),
                    common_pb2.ToolDefinition(
                        name="search",
                        json_schema=(
                            '{\n'
                            '  "properties": {"q": {"type": "string"}},\n'
                            '  "type": "object"\n'
                            "}"
                        ),
                    ),
                ],
                tool_choice="auto",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="List tools")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    completed = next(
        event.completed
        for event in inference_service.Generate(request, context=None)
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["allowed_tools_receipt_json"])

    assert receipt["allowed_tool_names"] == ["search"]
    assert receipt["schema_conflict_count"] == 0
    assert receipt["schema_conflicts"] == []


def test_generate_keeps_invalid_duplicate_tool_schema_comparison_observable() -> None:
    inference_service, model_handle = _build_services(TokenRoutedVisibleBackend())
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-invalid-tool-schema"),
            model_handle=model_handle,
            ext={
                "melix.tool_config.source": "openai_chat_tools",
                "melix.tool_config.tool_count": "3",
            },
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(name="empty", json_schema=""),
                    common_pb2.ToolDefinition(name="search", json_schema='{"type":'),
                    common_pb2.ToolDefinition(name="search", json_schema='{"type":"object"}'),
                ],
                tool_choice="auto",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="List tools")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    completed = next(
        event.completed
        for event in inference_service.Generate(request, context=None)
        if event.HasField("completed")
    )
    receipt = json.loads(completed.parser_metrics["allowed_tools_receipt_json"])

    assert receipt["allowed_tool_names"] == ["empty", "search"]
    assert receipt["schema_conflict_count"] == 1
    assert receipt["schema_conflicts"] == ["search"]


def test_generate_distinguishes_omitted_and_explicit_empty_allowed_tools() -> None:
    inference_service, model_handle = _build_services(TokenRoutedVisibleBackend())
    omitted_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-tools-omitted"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hi")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    explicit_empty_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-tools-empty"),
            model_handle=model_handle,
            ext={
                "melix.tool_config.source": "openai_chat_tools",
                "melix.tool_config.tool_count": "0",
                "melix.tool_parser.suppressed_reason": "request_tools_empty",
            },
            tool_config=common_pb2.ToolConfig(tool_choice="none"),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hi")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    omitted_completed = next(
        event.completed
        for event in inference_service.Generate(omitted_request, context=None)
        if event.HasField("completed")
    )
    explicit_empty_completed = next(
        event.completed
        for event in inference_service.Generate(explicit_empty_request, context=None)
        if event.HasField("completed")
    )
    omitted_receipt = json.loads(omitted_completed.parser_metrics["allowed_tools_receipt_json"])
    explicit_empty_receipt = json.loads(
        explicit_empty_completed.parser_metrics["allowed_tools_receipt_json"]
    )

    assert omitted_receipt["tool_config_state"] == "omitted"
    assert omitted_receipt["tool_choice_policy"] == "auto"
    assert omitted_receipt["allowed_tool_names"] == []
    assert explicit_empty_receipt["tool_config_state"] == "explicit_empty"
    assert explicit_empty_receipt["tool_choice_policy"] == "none"
    assert explicit_empty_receipt["suppressed_reason"] == "request_tools_empty"


def test_allowed_tools_receipt_reuses_static_omitted_receipt() -> None:
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-tools-omitted-fast-path"),
            model_handle="model-dev-text",
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hi")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    receipt_json = engine_core_module.EngineCore._allowed_tools_receipt_json(request)

    assert receipt_json is engine_core_module._DEFAULT_OMITTED_ALLOWED_TOOLS_RECEIPT_JSON
    assert json.loads(receipt_json) == {
        "allowed_tool_count": 0,
        "allowed_tool_names": [],
        "schema_conflict_count": 0,
        "schema_conflicts": [],
        "suppressed_reason": "",
        "tool_choice_policy": "auto",
        "tool_config_source": "",
        "tool_config_state": "omitted",
        "tool_source_ids": [],
    }


@pytest.mark.parametrize(
    ("case_id", "raw_text", "expected"),
    [
        (
            "auto",
            "visible final answer",
            {
                "assistant_text": "visible final answer",
                "reasoning_text": "",
                "reasoning_finalized": "false",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "false",
                "tool_choice_policy": "auto",
            },
        ),
        (
            "none",
            "visible answer without tools",
            {
                "assistant_text": "visible answer without tools",
                "reasoning_text": "",
                "reasoning_finalized": "false",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "false",
                "tool_choice_policy": "none",
            },
        ),
        (
            "forced-valid",
            '<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>',
            {
                "assistant_text": "",
                "reasoning_text": "",
                "reasoning_finalized": "false",
                "tool_calls_finalized": "true",
                "malformed_channel_recovered": "false",
                "tool_choice_policy": "required",
            },
        ),
        (
            "forced-missing-tool",
            '<tool_call>{"name":"missing","arguments":{"q":"one"}}</tool_call>visible',
            {
                "assistant_text": "visible",
                "reasoning_text": "",
                "reasoning_finalized": "false",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "false",
                "unknown_tool_delta_count": "1",
                "tool_choice_policy": "required",
            },
        ),
        (
            "reasoning-only-truncation",
            "<think>unfinished hidden reasoning",
            {
                "assistant_text": "",
                "reasoning_text": "",
                "reasoning_finalized": "false",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "true",
                "malformed_reasoning_count": "1",
                "tool_choice_policy": "auto",
            },
        ),
        (
            "alternate-final-terminator",
            "<think>hidden trace\nAnswer: 42",
            {
                "assistant_text": "Answer: 42",
                "reasoning_text": "hidden trace",
                "reasoning_finalized": "true",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "true",
                "tool_choice_policy": "auto",
            },
        ),
        (
            "malformed",
            "<|channel>thought hidden\n\nFinal answer",
            {
                "assistant_text": "Final answer",
                "reasoning_text": "hidden",
                "reasoning_finalized": "true",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "true",
                "tool_choice_policy": "auto",
            },
        ),
        (
            "truncated",
            'visible <tool_call>{"name":"search","arguments":{"q":"unfinished"}',
            {
                "assistant_text": "visible ",
                "reasoning_text": "",
                "reasoning_finalized": "false",
                "tool_calls_finalized": "true",
                "malformed_channel_recovered": "true",
                "tool_choice_policy": "required",
            },
        ),
    ],
)
def test_generate_finalizer_receipt_matches_for_stream_and_non_stream_modes(
    case_id: str,
    raw_text: str,
    expected: dict[str, str],
) -> None:
    stream_events = _generate_finalizer_events(
        raw_text=raw_text,
        stream=True,
        request_id=f"req-finalizer-stream-{case_id}",
        tool_choice=expected["tool_choice_policy"],
    )
    non_stream_events = _generate_finalizer_events(
        raw_text=raw_text,
        stream=False,
        request_id=f"req-finalizer-non-stream-{case_id}",
        tool_choice=expected["tool_choice_policy"],
    )

    stream_completed = _finalizer_completed(stream_events)
    non_stream_completed = _finalizer_completed(non_stream_events)
    stream_receipt = dict(stream_completed.parser_metrics)
    non_stream_receipt = dict(non_stream_completed.parser_metrics)

    for field in (
        "response_id",
        "created",
        "stream_mode",
        "finish_reason",
        "usage_prompt_tokens",
        "usage_completion_tokens",
        "usage_total_tokens",
        "usage_trailer_emitted",
        "reasoning_finalized",
        "tool_calls_finalized",
        "malformed_channel_recovered",
        "finalizer_path",
    ):
        assert field in stream_receipt
        assert field in non_stream_receipt

    assert stream_receipt["response_id"] == f"req-finalizer-stream-{case_id}"
    assert non_stream_receipt["response_id"] == f"req-finalizer-non-stream-{case_id}"
    assert stream_receipt["stream_mode"] == "true"
    assert non_stream_receipt["stream_mode"] == "false"
    assert stream_receipt["finalizer_path"] == "stream"
    assert non_stream_receipt["finalizer_path"] == "non_stream"
    assert stream_receipt["usage_trailer_emitted"] == "true"
    assert non_stream_receipt["usage_trailer_emitted"] == "false"
    assert _normalized_finalizer_receipt(stream_receipt) == _normalized_finalizer_receipt(
        non_stream_receipt
    )
    assert stream_completed.assistant_text == non_stream_completed.assistant_text
    assert stream_completed.reasoning_text == non_stream_completed.reasoning_text
    assert stream_completed.raw_assistant_text == non_stream_completed.raw_assistant_text
    assert stream_completed.assistant_text == expected["assistant_text"]
    assert stream_completed.reasoning_text == expected["reasoning_text"]
    stream_route_receipt = json.loads(stream_receipt["token_route_receipt_json"])
    non_stream_route_receipt = json.loads(non_stream_receipt["token_route_receipt_json"])
    assert stream_route_receipt["tool_choice_policy"] == expected["tool_choice_policy"]
    assert non_stream_route_receipt["tool_choice_policy"] == expected["tool_choice_policy"]
    assert stream_receipt["finish_reason"] == "length"
    assert stream_receipt["usage_prompt_tokens"] == "11"
    assert stream_receipt["usage_completion_tokens"] == "3"
    assert stream_receipt["usage_total_tokens"] == "14"
    for key, value in expected.items():
        if key in {"assistant_text", "reasoning_text", "tool_choice_policy"}:
            continue
        assert stream_receipt[key] == value


def _token_route_request(
    model_handle: str,
    *,
    compat_receipt: str,
    stream: bool,
    reasoning_enabled: bool = True,
) -> inference_pb2.GenerateRequest:
    return inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(
                request_id=f"req-token-route-{'stream' if stream else 'non-stream'}"
            ),
            model_handle=model_handle,
            ext={
                "melix.compat.policy_receipt_json": compat_receipt,
                "melix.compat.reasoning_mode": "enabled",
                "melix.compat.tool_choice_resolved": "required",
                "melix.reasoning.mode": "enabled",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=reasoning_enabled,
                mode_source="request_enable_thinking",
            ),
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="search",
                        json_schema='{"type":"object"}',
                    )
                ],
                tool_choice="required",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use a tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=stream,
    )


def _generate_finalizer_events(
    *,
    raw_text: str,
    stream: bool,
    request_id: str,
    tool_choice: str = "auto",
    return_usage: bool = True,
):
    inference_service, model_handle = _build_services(FinalizerParityBackend(raw_text=raw_text))
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=request_id),
            model_handle=model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.tool_parser.mode": "qwen",
                "melix.response.created": "1716500000",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=True,
                mode_source="request_enable_thinking",
                effort="medium",
            ),
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="search",
                        description="Search local fixtures.",
                        json_schema='{"type":"object"}',
                    )
                ],
                parser="qwen",
                tool_choice="" if tool_choice == "auto" else tool_choice,
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="finalizer parity")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=stream,
        return_usage=return_usage,
    )
    return list(inference_service.Generate(request, context=None))


def _build_services(backend):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    return inference_service, load_response.model_handle


def _finalizer_receipt(events) -> dict[str, str]:
    return dict(_finalizer_completed(events).parser_metrics)


def _finalizer_completed(events):
    return next(event.completed for event in events if event.HasField("completed"))


def _normalized_finalizer_receipt(receipt: dict[str, str]) -> dict[str, str]:
    ignored = {"response_id", "stream_mode", "usage_trailer_emitted", "finalizer_path"}
    return {key: value for key, value in receipt.items() if key not in ignored}
