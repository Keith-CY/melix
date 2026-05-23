#!/usr/bin/env python3

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2  # noqa: E402
from worker.runtime import mlx_vlm_runtime as mlx_vlm_runtime_module  # noqa: E402
from worker.runtime.mlx_vlm_runtime import AutoMLXVLMBackend, MLXVLMRuntime  # noqa: E402

ITERATION_COUNT = 200
SAMPLE_COUNT = 5
PROMPT_TEXT = "Describe the image"


class _ProbeFamilyConfig:
    def capability_metadata(self) -> dict[str, str]:
        return {
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
        }

    def shape_request(self, prepared):
        return prepared

    def prompt_token_count(self, prepared) -> int:
        return len(prepared.prompt_text.split())


class _ResolveCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, metadata: dict[str, str]) -> _ProbeFamilyConfig:
        self.count += 1
        if metadata.get("vision_family_id") != "gemma4-v1":
            raise SystemExit("unexpected vision family metadata")
        return _ProbeFamilyConfig()


def _model_spec() -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_path="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_kind="vlm",
        revision="main",
        tokenizer_hash="hf.unsloth.gemma-4-E4B-it-MLX-8bit",
        quant_profile_id="q8",
        parser_mode="text",
        reasoning_mode="off",
        max_context=4096,
        ext={
            "melix.vlm.backend_id": "mlx_vlm",
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "vision_tokenization_mode": "interleaved",
            "vision_max_images_per_prompt": "8",
            "vision_supports_tool_calls": "true",
            "melix.multimodal_adapter_hash": "vision-family-gemma4-v1",
        },
    )


def _messages() -> list[common_pb2.ChatMessage]:
    return [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text=PROMPT_TEXT)])]


def _build_runtime() -> tuple[MLXVLMRuntime, _ResolveCounter]:
    counter = _ResolveCounter()

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(config=SimpleNamespace(model_type="gemma4"))
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    mlx_vlm_runtime_module.resolve_vision_family_config = counter
    mlx_vlm_runtime_module._installed_package_version = lambda name: f"{name}-version"
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::prompt",
        )
    )
    return runtime, counter


def _attach_scheduler_stats(runtime: MLXVLMRuntime, loaded_model: dict[str, object]) -> dict[str, float]:
    scheduler = runtime._text_only_batch_generator_scheduler(loaded_model)
    scheduler._stats.prefill_response_count = 3
    scheduler._stats.prefill_step_count = 3
    scheduler._stats.prefill_processed_token_count = 1536
    scheduler._stats.prefill_total_token_count = 4096
    scheduler._stats.prefill_completed_request_count = 0
    probe = runtime.last_probe_snapshot()
    runtime.close_loaded_model(loaded_model)
    if runtime._loaded_models_with_schedulers:
        raise SystemExit("scheduler model tracking was not cleared")
    return {
        "live_prefill_response_count": float(probe.text_batch_generator_prefill_response_count),
        "live_prefill_step_count": float(probe.text_batch_generator_prefill_step_count),
        "live_prefill_processed_token_count": float(probe.text_batch_generator_prefill_processed_token_count),
        "live_prefill_total_token_count": float(probe.text_batch_generator_prefill_total_token_count),
        "live_prefill_completed_request_count": float(probe.text_batch_generator_prefill_completed_request_count),
        "live_prefill_step_size": float(probe.text_batch_generator_prefill_step_size),
    }


def main() -> int:
    elapsed_samples: list[float] = []
    resolve_samples: list[float] = []
    prompt_token_count = 0
    scheduler_metrics: dict[str, float] = {}
    for _ in range(SAMPLE_COUNT):
        runtime, counter = _build_runtime()
        loaded_model = runtime.load_model(_model_spec())
        started = time.perf_counter()
        for _ in range(ITERATION_COUNT):
            prepared = runtime.render_prompt(_messages(), loaded_model=loaded_model)
            prompt_token_count = runtime.prompt_token_count(prepared, loaded_model=loaded_model)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        resolve_samples.append(float(counter.count))
        if prompt_token_count != 3:
            raise SystemExit("unexpected prompt token count")
        if not scheduler_metrics:
            scheduler_metrics = _attach_scheduler_stats(runtime, loaded_model)
    metrics = {
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "iteration_count": float(ITERATION_COUNT),
        "prompt_token_count": float(prompt_token_count),
        "resolve_calls_mean": round(statistics.fmean(resolve_samples), 6),
        "sample_count": float(SAMPLE_COUNT),
    }
    metrics.update(scheduler_metrics)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
