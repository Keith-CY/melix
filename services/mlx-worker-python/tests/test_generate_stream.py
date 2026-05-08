from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.engine.engine_core import EngineCore
from worker.engine.request_state import RequestState
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent


class StreamingFakeBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(text="Hello", prompt_tokens=5, completion_tokens=1)
        yield RuntimeTokenEvent(text=" world", prompt_tokens=5, completion_tokens=2, finish_reason="length")


class TemplateCapturingTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return "<templated-prompt>"


class TemplateAwareStreamingBackend:
    runtime_name = "fake-mlx"

    def __init__(self) -> None:
        self.tokenizer = TemplateCapturingTokenizer()
        self.prompts: list[str] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "tokenizer": self.tokenizer}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        self.prompts.append(prompt)
        yield RuntimeTokenEvent(text="templated", prompt_tokens=7, completion_tokens=1, finish_reason="stop")


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


class ShortPrefixStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(
            text="",
            raw_text="OK<",
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="stop",
        )


class StopContractTokenizer:
    eos_token = "</s>"
    eos_token_id = 2


class StopContractStreamingBackend:
    runtime_name = "fake-mlx"

    def __init__(self) -> None:
        self.seen_stop_sequences: list[str] = []

    def load_model(self, model_spec):
        return {
            "model_id": model_spec.model_id,
            "metadata": dict(model_spec.ext),
            "tokenizer": StopContractTokenizer(),
        }

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        self.seen_stop_sequences = list(sampling.stop)
        yield RuntimeTokenEvent(
            text="keep</turn>drop",
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="length",
        )


class AccelerationCapturingRuntime:
    runtime_name = "fake-acceleration-runtime"

    def __init__(self) -> None:
        self.seen_acceleration_policies: list[common_pb2.AccelerationPolicy | None] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 0

    def render_prompt(self, messages, loaded_model=None, template_kwargs=None, execution_ext=None):
        _ = messages
        _ = loaded_model
        _ = template_kwargs
        _ = execution_ext
        return "rendered prompt"

    def prompt_token_count(self, prompt):
        _ = prompt
        return 2

    def generate_tokens(
        self,
        loaded_model,
        prompt,
        sampling,
        cancel_event,
        execution_ext=None,
        acceleration_policy=None,
    ):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        self.seen_acceleration_policies.append(acceleration_policy)
        yield RuntimeTokenEvent(text="accelerated", prompt_tokens=2, completion_tokens=1, finish_reason="stop")


class UsageCountingRuntime:
    runtime_name = "fake-usage-counting-runtime"

    def __init__(self, *, prompt_tokens: int = 0) -> None:
        self.prompt_tokens = prompt_tokens
        self.prompt_token_count_calls = 0

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 0

    def render_prompt(self, messages, loaded_model=None, template_kwargs=None, execution_ext=None):
        _ = messages
        _ = loaded_model
        _ = template_kwargs
        _ = execution_ext
        return "count " * 1024

    def prompt_token_count(self, prompt):
        _ = prompt
        self.prompt_token_count_calls += 1
        return 1024

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        yield RuntimeTokenEvent(
            text="counted",
            prompt_tokens=self.prompt_tokens,
            completion_tokens=1,
            finish_reason="stop",
        )


def build_services():
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StreamingFakeBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    return runtime_service, inference_service, load_response.model_handle


def build_usage_counting_services(runtime: UsageCountingRuntime):
    registry = WorkerRegistry(
        runtime=runtime,  # type: ignore[arg-type]
        model_catalog=WorkerModelCatalog(environment={}),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    return inference_service, load_response.model_handle


def generate_usage_request(model_handle: str, *, return_usage: bool) -> inference_pb2.GenerateRequest:
    return inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-usage-count"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="count tokens")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
        return_usage=return_usage,
    )


def test_generate_without_usage_skips_prompt_token_count_fallback() -> None:
    runtime = UsageCountingRuntime(prompt_tokens=0)
    inference_service, model_handle = build_usage_counting_services(runtime)

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=False), context=None))

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["counted"]
    assert not any(event.HasField("usage_delta") for event in events)
    assert runtime.prompt_token_count_calls == 0


def test_sampling_with_resolved_stop_reuses_sampling_when_stop_sequences_match() -> None:
    sampling = common_pb2.SamplingConfig(max_output_tokens=4)

    resolved = EngineCore._sampling_with_resolved_stop(sampling, ())

    assert resolved is sampling


def test_sampling_with_resolved_stop_clones_when_stop_sequences_change() -> None:
    sampling = common_pb2.SamplingConfig(max_output_tokens=4, stop=["old"])

    resolved = EngineCore._sampling_with_resolved_stop(sampling, ("new",))

    assert resolved is not sampling
    assert list(resolved.stop) == ["new"]
    assert list(sampling.stop) == ["old"]


def test_generate_usage_reuses_runtime_event_prompt_tokens_without_fallback_count() -> None:
    runtime = UsageCountingRuntime(prompt_tokens=7)
    inference_service, model_handle = build_usage_counting_services(runtime)

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=True), context=None))

    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert usage.prompt_tokens == 7
    assert usage.completion_tokens == 1
    assert runtime.prompt_token_count_calls == 0


def test_generate_usage_counts_prompt_tokens_only_for_missing_event_total() -> None:
    runtime = UsageCountingRuntime(prompt_tokens=0)
    inference_service, model_handle = build_usage_counting_services(runtime)

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=True), context=None))

    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert usage.prompt_tokens == 1024
    assert usage.completion_tokens == 1
    assert runtime.prompt_token_count_calls == 1


def test_generate_streams_token_and_terminal_completion_without_request_token_accumulation() -> None:
    _, inference_service, model_handle = build_services()
    original_append_token = RequestState.append_token

    def fail_append_token(self: RequestState, token: str) -> None:
        _ = self  # pragma: no cover - regression-only failure path
        _ = token  # pragma: no cover - regression-only failure path
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "generate should use the stream assembler instead of RequestState token accumulation"
        )

    RequestState.append_token = fail_append_token
    try:
        events = list(
            inference_service.Generate(generate_usage_request(model_handle, return_usage=True), context=None)
        )
    finally:
        RequestState.append_token = original_append_token

    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))
    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert token_text == ["Hello", " world"]
    assert completed.assistant_text == "Hello world"
    assert usage.completion_tokens == 2


def test_generate_streams_token_and_terminal_completion() -> None:
    _, inference_service, model_handle = build_services()

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-generate-1"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == ["Hello", " world"]
    assert completed.finish_reason == "length"
    assert completed.assistant_text == "Hello world"
    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert usage.prompt_tokens == 5
    assert usage.completion_tokens == 2


def test_generate_streams_reasoning_tool_and_content_channels_from_raw_text() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StructuredStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-structured-stream"),
            model_handle=load_response.model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=True,
                mode_source="request_enable_thinking",
                effort="low",
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
    )

    events = list(inference_service.Generate(request, context=None))
    reasoning = next(event.reasoning_delta for event in events if event.HasField("reasoning_delta"))
    tool_call = next(event.tool_call_delta for event in events if event.HasField("tool_call_delta"))
    token = next(event.token_delta for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert reasoning.text == "trace"
    assert reasoning.mode_source == "request_enable_thinking"
    assert tool_call.tool_name == "search"
    assert tool_call.arguments_json_fragment == '{"q":"one"}'
    assert tool_call.fragment_index == 1
    assert tool_call.parser_mode == "qwen"
    assert tool_call.complete is True
    assert token.text == "visible"
    assert completed.assistant_text == "visible"
    assert completed.reasoning_text == "trace"
    assert completed.reasoning_mode_source == "request_enable_thinking"
    assert completed.reasoning_effort == "low"
    assert completed.parser_metrics["duplicate_tool_delta_count"] == "0"


def test_generate_stream_preserves_explicit_tool_parser_with_structured_json_mode() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StructuredStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-structured-tools"),
            model_handle=load_response.model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.structured_output.mode": "json_schema",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=True,
                mode_source="request_enable_thinking",
                effort="low",
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
    )

    events = list(inference_service.Generate(request, context=None))
    tool_call = next(event.tool_call_delta for event in events if event.HasField("tool_call_delta"))
    token = next(event.token_delta for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert tool_call.tool_name == "search"
    assert tool_call.arguments_json_fragment == '{"q":"one"}'
    assert token.text == "visible"
    assert completed.assistant_text == "visible"
    assert completed.parser_metrics["stream_parser_request_context_mode"] == "tool_parser"
    assert completed.parser_metrics["tool_call_markup_leak_count"] == "0"
    assert completed.parser_metrics["reasoning_leak_count"] == "0"


def test_generate_stream_flushes_short_visible_prefix_before_marker_hold() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=ShortPrefixStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-short-prefix"),
            model_handle=load_response.model_handle,
            ext={"melix.tool_parser.mode": "qwen"},
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="short")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=4),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == ["OK"]
    assert completed.assistant_text == "OK<"
    assert completed.parser_metrics["stream_prefix_hold_chars"] == "1"
    assert completed.parser_metrics["stream_short_reply_flush_count"] == "1"


def test_generate_stream_exports_stop_contract_metrics_and_stops_at_turn_boundary() -> None:
    backend = StopContractStreamingBackend()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model = WorkerModelCatalog.dev_text_model()
    model.ext["melix.stop_sequences"] = "</model>"
    load_response = runtime_service.LoadModel(runtime_pb2.LoadModelRequest(model=model), context=None)
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-stop-contract"),
            model_handle=load_response.model_handle,
            reasoning=common_pb2.ReasoningConfig(mode_source="request"),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="stop at boundary")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8, stop=["</turn>"]),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert backend.seen_stop_sequences == ["</turn>", "</model>", "</s>"]
    assert token_text == ["keep"]
    assert completed.finish_reason == "stop_sequence"
    assert completed.assistant_text == "keep"
    assert completed.parser_metrics["resolved_stop_token_count"] == "4"
    assert completed.parser_metrics["reasoning_flag_source"] == "request"
    assert completed.parser_metrics["turn_boundary_stop_reason"] == "stop_sequence"


def test_text_prefill_returns_structured_unimplemented_error() -> None:
    _, inference_service, model_handle = build_services()

    response = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id="req-prefill-1"),
                model_handle=model_handle,
            )
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "unimplemented"


def test_generate_applies_chat_template_kwargs_from_execution_metadata() -> None:
    backend = TemplateAwareStreamingBackend()
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

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-template-kwargs"),
            model_handle=load_response.model_handle,
            ext={
                "melix.chat_template_kwargs.effective_json": "{\"add_generation_prompt\":false,\"continue_final_message\":true}"
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="assistant",
                name="planner",
                parts=[common_pb2.MessagePart(text="Continue the reply")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["templated"]
    assert backend.prompts == ["<templated-prompt>"]
    assert backend.tokenizer.calls == [
        (
            [{"role": "assistant", "name": "planner", "content": "Continue the reply"}],
            {
                "tokenize": False,
                "add_generation_prompt": False,
                "continue_final_message": True,
            },
        )
    ]


def test_generate_rejects_non_object_chat_template_kwargs_payloads() -> None:
    _, inference_service, model_handle = build_services()

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-template-invalid-root"),
            model_handle=model_handle,
            ext={
                "melix.chat_template_kwargs.effective_json": "[1,2,3]"
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Continue the reply")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))

    error = next(event.error.error for event in events if event.HasField("error"))
    assert error.code == "runtime_error"
    assert "must decode to an object" in error.message


def test_generate_forwards_acceleration_policy_to_runtimes_that_accept_it() -> None:
    runtime = AccelerationCapturingRuntime()
    registry = WorkerRegistry(
        runtime=runtime,  # type: ignore[arg-type]
        model_catalog=WorkerModelCatalog(environment={}),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        num_draft_tokens=6,
        allow_baseline_fallback=True,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-acceleration-policy"),
            model_handle=load_response.model_handle,
            acceleration=policy,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["accelerated"]
    assert len(runtime.seen_acceleration_policies) == 1
    seen_policy = runtime.seen_acceleration_policies[0]
    assert seen_policy is not None
    assert seen_policy.mode == common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE
    assert seen_policy.draft_model_id == "mlx-community/gemma-4-E2B-it-assistant-bf16"
    assert seen_policy.num_draft_tokens == 6
    assert seen_policy.allow_baseline_fallback is True
