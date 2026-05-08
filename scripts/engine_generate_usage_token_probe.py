from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

repo_root_env = os.environ.get("MELIX_ENGINE_GENERATE_USAGE_REPO_ROOT")
repo_root = Path(repo_root_env) if repo_root_env else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.engine.request_state import RequestState
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent


class CountingRuntime:
    runtime_name = "probe-counting-runtime"

    def __init__(self, *, prompt_words: int) -> None:
        self.prompt_words = prompt_words
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
        return "probe " * self.prompt_words

    def prompt_token_count(self, prompt):
        _ = prompt
        self.prompt_token_count_calls += 1
        return self.prompt_words

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        yield RuntimeTokenEvent(text="ok", prompt_tokens=0, completion_tokens=1, finish_reason="stop")


def _build_request(model_handle: str, *, request_index: int) -> inference_pb2.GenerateRequest:
    return inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=f"probe-generate-{request_index}"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="skip usage accounting")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=4),
        stream=True,
        return_usage=False,
    )


def run_probe() -> dict[str, float | int | str]:
    request_count = int(os.environ.get("MELIX_ENGINE_GENERATE_USAGE_PROBE_REQUESTS", "300"))
    samples = int(os.environ.get("MELIX_ENGINE_GENERATE_USAGE_PROBE_SAMPLES", "5"))
    prompt_words = int(os.environ.get("MELIX_ENGINE_GENERATE_USAGE_PROBE_PROMPT_WORDS", "4096"))
    elapsed_ms: list[float] = []
    call_counts: list[int] = []
    append_counts: list[int] = []
    token_events: list[int] = []

    for sample in range(samples):
        runtime = CountingRuntime(prompt_words=prompt_words)
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

        token_count = 0
        append_count = 0
        original_append_token = RequestState.append_token

        def counting_append_token(self: RequestState, token: str) -> None:
            nonlocal append_count
            append_count += 1  # pragma: no cover - exercised by base-version probe comparison
            original_append_token(self, token)  # pragma: no cover - exercised by base-version probe comparison

        RequestState.append_token = counting_append_token
        start = time.perf_counter()
        try:
            for request_index in range(request_count):
                request = _build_request(load_response.model_handle, request_index=sample * request_count + request_index)
                events = list(inference_service.Generate(request, context=None))
                token_count += sum(1 for event in events if event.HasField("token_delta"))
        finally:
            RequestState.append_token = original_append_token
        elapsed_ms.append((time.perf_counter() - start) * 1000.0)
        call_counts.append(runtime.prompt_token_count_calls)
        append_counts.append(append_count)
        token_events.append(token_count)

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "prompt_token_count_calls_mean": statistics.fmean(call_counts),
        "prompt_token_count_calls_per_request": statistics.fmean(call_counts) / request_count,
        "request_state_append_calls_mean": statistics.fmean(append_counts),
        "request_state_append_calls_per_request": statistics.fmean(append_counts) / request_count,
        "token_events_mean": statistics.fmean(token_events),
        "request_count": request_count,
        "samples": samples,
        "prompt_words": prompt_words,
    }


def main() -> int:
    metrics = run_probe()
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
