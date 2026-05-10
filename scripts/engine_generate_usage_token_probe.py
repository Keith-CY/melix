from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

repo_root_env = os.environ.get("MELIX_ENGINE_GENERATE_USAGE_REPO_ROOT")
repo_root = Path(repo_root_env) if repo_root_env else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2
from worker.engine.request_state import RequestState
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
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


class FallbackRuntime:
    runtime_name = "probe-fallback-runtime"

    def __init__(self, *, prompt_words: int) -> None:
        self.prompt_words = prompt_words

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
        # Include mixed whitespace so fallback behavior matches str.split(None).
        words = ("probe" for _ in range(self.prompt_words))
        return "\n\t ".join(words)

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        yield RuntimeTokenEvent(text="ok", prompt_tokens=0, completion_tokens=1, finish_reason="stop")


def _load_services(runtime) -> tuple[WorkerInferenceService, str]:
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


def _build_request(model_handle: str, *, request_index: int, return_usage: bool) -> inference_pb2.GenerateRequest:
    return inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=f"probe-generate-{request_index}"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="usage accounting probe")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=4),
        stream=True,
        return_usage=return_usage,
    )


def _run_no_usage_sample(*, request_count: int, prompt_words: int, sample: int) -> tuple[float, int, int, int]:
    runtime = CountingRuntime(prompt_words=prompt_words)
    inference_service, model_handle = _load_services(runtime)
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
            request = _build_request(
                model_handle,
                request_index=sample * request_count + request_index,
                return_usage=False,
            )
            events = list(inference_service.Generate(request, context=None))
            token_count += sum(1 for event in events if event.HasField("token_delta"))
    finally:
        RequestState.append_token = original_append_token
    return (time.perf_counter() - start) * 1000.0, runtime.prompt_token_count_calls, append_count, token_count


def _run_fallback_sample(*, request_count: int, prompt_words: int, sample: int) -> tuple[float, float, int]:
    runtime = FallbackRuntime(prompt_words=prompt_words)
    inference_service, model_handle = _load_services(runtime)
    prompt_tokens = 0
    tracemalloc.start()
    start = time.perf_counter()
    try:
        for request_index in range(request_count):
            request = _build_request(
                model_handle,
                request_index=sample * request_count + request_index,
                return_usage=True,
            )
            events = list(inference_service.Generate(request, context=None))
            usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
            prompt_tokens = int(usage.prompt_tokens)
    finally:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    if prompt_tokens != prompt_words:
        raise SystemExit(f"unexpected fallback prompt tokens: {prompt_tokens} != {prompt_words}")  # pragma: no cover
    return (time.perf_counter() - start) * 1000.0, float(peak), prompt_tokens


def run_probe() -> dict[str, float | int | str]:
    request_count = int(os.environ.get("MELIX_ENGINE_GENERATE_USAGE_PROBE_REQUESTS", "300"))
    fallback_request_count = int(os.environ.get("MELIX_ENGINE_GENERATE_FALLBACK_PROBE_REQUESTS", "60"))
    samples = int(os.environ.get("MELIX_ENGINE_GENERATE_USAGE_PROBE_SAMPLES", "5"))
    prompt_words = int(os.environ.get("MELIX_ENGINE_GENERATE_USAGE_PROBE_PROMPT_WORDS", "4096"))
    elapsed_ms: list[float] = []
    call_counts: list[int] = []
    append_counts: list[int] = []
    token_events: list[int] = []
    fallback_elapsed_ms: list[float] = []
    fallback_peak_bytes: list[float] = []

    for sample in range(samples):
        elapsed, calls, appends, tokens = _run_no_usage_sample(
            request_count=request_count,
            prompt_words=prompt_words,
            sample=sample,
        )
        elapsed_ms.append(elapsed)
        call_counts.append(calls)
        append_counts.append(appends)
        token_events.append(tokens)

        fallback_elapsed, fallback_peak, _ = _run_fallback_sample(
            request_count=fallback_request_count,
            prompt_words=prompt_words,
            sample=sample,
        )
        fallback_elapsed_ms.append(fallback_elapsed)
        fallback_peak_bytes.append(fallback_peak)

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "prompt_token_count_calls_mean": statistics.fmean(call_counts),
        "prompt_token_count_calls_per_request": statistics.fmean(call_counts) / request_count,
        "request_state_append_calls_mean": statistics.fmean(append_counts),
        "request_state_append_calls_per_request": statistics.fmean(append_counts) / request_count,
        "token_events_mean": statistics.fmean(token_events),
        "fallback_elapsed_ms_mean": statistics.fmean(fallback_elapsed_ms),
        "fallback_peak_bytes_mean": statistics.fmean(fallback_peak_bytes),
        "fallback_request_count": fallback_request_count,
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
