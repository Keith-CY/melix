from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

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


def test_prefill_returns_structured_unimplemented_error() -> None:
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
