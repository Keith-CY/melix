import threading

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class BlockingFakeBackend:
    runtime_name = "fake-mlx"

    def __init__(self) -> None:
        self.first_token_emitted = threading.Event()
        self.allow_finish = threading.Event()

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield "First"
        self.first_token_emitted.set()
        self.allow_finish.wait(timeout=2)
        if cancel_event.is_set():
            return
        yield " Second"


def test_abort_stops_active_generation_and_marks_completion_cancelled() -> None:
    backend = BlockingFakeBackend()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)

    model_handle = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    ).model_handle

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-abort-1"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Need a long answer")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
    )

    events = []

    def consume() -> None:
        for event in inference_service.Generate(request, context=None):
            events.append(event)

    thread = threading.Thread(target=consume)
    thread.start()
    assert backend.first_token_emitted.wait(timeout=2)

    abort_response = inference_service.Abort(
        inference_pb2.AbortRequest(request_id="req-abort-1"),
        context=None,
    )
    backend.allow_finish.set()
    thread.join(timeout=2)

    assert abort_response.ok is True
    assert abort_response.found is True
    completed = next(event.completed for event in events if event.HasField("completed"))
    assert completed.finish_reason == "cancelled"
