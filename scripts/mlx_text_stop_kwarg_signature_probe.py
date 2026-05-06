from __future__ import annotations

import inspect
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime import mlx_text_runtime
from worker.runtime import runtime_utils
from worker.runtime.mlx_text_runtime import AutoMLXBackend


class _FakeTokenizer:
    eos_token = "</s>"
    eos_token_id = 2


class _FakeGenerationResponse:
    text = "ok"
    raw_text = None
    prompt_tokens = 1
    generation_tokens = 1
    finish_reason = None


def _fake_load(model_source: str, **kwargs: Any) -> tuple[object, _FakeTokenizer]:
    _ = (model_source, kwargs)
    return object(), _FakeTokenizer()


def _fake_sampler_factory(*, temp: float, top_p: float, top_k: int) -> str:
    _ = (temp, top_p, top_k)
    return "fake-sampler"


def _fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler, *, stop=None):
    _ = (model, tokenizer, prompt, max_tokens, sampler)
    if stop != ["</turn>", "</s>"]:
        raise RuntimeError(f"unexpected stop kwarg: {stop!r}")
    yield _FakeGenerationResponse()


def main() -> int:
    iterations = int(os.environ.get("MELIX_MLX_TEXT_STOP_KWARG_PROBE_ITERATIONS", "2000"))
    sample_count = int(os.environ.get("MELIX_MLX_TEXT_STOP_KWARG_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    signature_call_samples: list[int] = []
    stream_signature_call_samples: list[int] = []
    original_signature = inspect.signature
    original_runtime_signature = runtime_utils.inspect.signature
    original_text_signature = getattr(mlx_text_runtime, "inspect", inspect).signature

    model_spec = WorkerModelCatalog.dev_text_model(
        environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"}
    )
    sampling = common_pb2.SamplingConfig(max_output_tokens=8, stop=["</turn>"])

    try:
        for _ in range(sample_count):
            runtime_utils.clear_callable_kwarg_signature_cache()
            signature_calls = 0
            stream_signature_calls = 0

            def tracked_signature(callable_obj: Any) -> inspect.Signature:
                nonlocal signature_calls, stream_signature_calls
                signature_calls += 1
                if callable_obj is _fake_stream_generate:
                    stream_signature_calls += 1
                return original_signature(callable_obj)

            runtime_utils.inspect.signature = tracked_signature
            if hasattr(mlx_text_runtime, "inspect"):
                mlx_text_runtime.inspect.signature = tracked_signature
            backend = AutoMLXBackend(
                load_fn=_fake_load,
                stream_generate_fn=_fake_stream_generate,
                sampler_factory=_fake_sampler_factory,
            )
            loaded_model = backend.load_model(model_spec)
            started = time.perf_counter()
            for _iteration in range(iterations):
                chunks = list(backend.generate_tokens(loaded_model, "prompt", sampling, cancel_event=_NeverCancelled()))
                if len(chunks) != 1 or chunks[0].text != "ok":
                    raise RuntimeError("unexpected generation output")
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            signature_call_samples.append(signature_calls)
            stream_signature_call_samples.append(stream_signature_calls)
    finally:
        runtime_utils.inspect.signature = original_runtime_signature
        if hasattr(mlx_text_runtime, "inspect"):
            mlx_text_runtime.inspect.signature = original_text_signature
        inspect.signature = original_signature
        runtime_utils.clear_callable_kwarg_signature_cache()

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "inspect_signature_calls_mean": statistics.fmean(signature_call_samples),
        "iterations_per_sample": float(iterations),
        "sample_count": float(sample_count),
        "stream_signature_calls_mean": statistics.fmean(stream_signature_call_samples),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


class _NeverCancelled:
    def is_set(self) -> bool:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
