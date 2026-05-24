import json

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

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


@pytest.mark.parametrize(
    ("case_id", "raw_text", "expected"),
    [
        (
            "plain",
            "plain final answer",
            {
                "reasoning_finalized": "false",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "false",
            },
        ),
        (
            "reasoning",
            "<think>hidden trace</think>visible answer",
            {
                "reasoning_finalized": "true",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "false",
            },
        ),
        (
            "tool",
            '<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>',
            {
                "reasoning_finalized": "false",
                "tool_calls_finalized": "true",
                "malformed_channel_recovered": "false",
            },
        ),
        (
            "malformed",
            "<|channel>thought hidden\n\nFinal answer",
            {
                "reasoning_finalized": "true",
                "tool_calls_finalized": "false",
                "malformed_channel_recovered": "true",
            },
        ),
        (
            "truncated",
            'visible <tool_call>{"name":"search","arguments":{"q":"unfinished"}',
            {
                "reasoning_finalized": "false",
                "tool_calls_finalized": "true",
                "malformed_channel_recovered": "true",
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
    )
    non_stream_events = _generate_finalizer_events(
        raw_text=raw_text,
        stream=False,
        request_id=f"req-finalizer-non-stream-{case_id}",
    )

    stream_receipt = _finalizer_receipt(stream_events)
    non_stream_receipt = _finalizer_receipt(non_stream_events)

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
    assert stream_receipt["finish_reason"] == "length"
    assert stream_receipt["usage_prompt_tokens"] == "11"
    assert stream_receipt["usage_completion_tokens"] == "3"
    assert stream_receipt["usage_total_tokens"] == "14"
    for key, value in expected.items():
        assert stream_receipt[key] == value


def _token_route_request(
    model_handle: str,
    *,
    compat_receipt: str,
    stream: bool,
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
        stream=stream,
    )


def _generate_finalizer_events(
    *,
    raw_text: str,
    stream: bool,
    request_id: str,
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
    completed = next(event.completed for event in events if event.HasField("completed"))
    return dict(completed.parser_metrics)


def _normalized_finalizer_receipt(receipt: dict[str, str]) -> dict[str, str]:
    ignored = {"response_id", "stream_mode", "usage_trailer_emitted", "finalizer_path"}
    return {key: value for key, value in receipt.items() if key not in ignored}
