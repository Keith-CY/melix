from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from threading import Event
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2
from worker.runtime.mlx_vlm_runtime import (
    AutoMLXVLMBackend,
    MLXVLMRuntime,
    _gemma4_multimodal_weight_presence,
)
from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest

WEIGHT_NAME_COUNT = 50000
ITERATION_COUNT = 40
SAMPLE_COUNT = 5


class _ProbeFeatureBatch:
    def __init__(self, rows: list[str]) -> None:
        self.rows = list(rows)
        self.shape = (len(self.rows), 1)
        self.nbytes = max(1, len(self.rows) * 16)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return _ProbeFeatureBatch(self.rows[index])
        if isinstance(index, list | tuple):
            return _ProbeFeatureBatch([self.rows[item] for item in index])
        return _ProbeFeatureBatch([self.rows[index]])


def build_weights() -> dict[str, object]:
    names = [f"language_model.model.layers.{index}.self_attn.q_proj.weight" for index in range(WEIGHT_NAME_COUNT)]
    names[-3] = "vision_tower.encoder.layers.0.self_attn.q_proj.weight"
    names[-2] = "audio_tower.encoder.layers.0.self_attn.q_proj.weight"
    names[-1] = "language_model.model.layers.tail.mlp.down_proj.weight"
    sentinel = object()
    return {name: sentinel for name in names}


def measure_once(weight_names: Iterable[str]) -> tuple[float, int, int, bool, bool]:
    visited = 0
    checksum = 0
    has_vision = False
    has_audio = False
    started = time.perf_counter()
    for _ in range(ITERATION_COUNT):
        has_vision, has_audio = _gemma4_multimodal_weight_presence(weight_names)
        if not has_vision or not has_audio:
            raise RuntimeError("expected multimodal weight names")
        visited += WEIGHT_NAME_COUNT - 1
        checksum += int(has_vision) + int(has_audio)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, visited, checksum, has_vision, has_audio


def warm_up(weight_names: Iterable[str]) -> None:
    measure_once(weight_names)


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


def _image_request(payload: bytes) -> PreparedVisionRequest:
    image = PreparedImageInput(
        bytes_data=payload,
        source_kind="inline",
        reference="inline:gemma4-weight-probe.jpg",
        mime_type="image/jpeg",
        format="jpg",
        filename="gemma4-weight-probe.jpg",
        sha256_hex=sha256(payload).hexdigest(),
    )
    return PreparedVisionRequest(
        prompt_text="Describe the image",
        images=[image],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(payload),
        preprocess_peak_memory_bytes=len(payload),
        prompt_hash_hex="gemma4-weight-probe",
        multimodal_hash_hex="gemma4-weight-probe-image",
    )


def _image_feature_cache_metrics() -> dict[str, float]:
    encode_calls: list[list[str]] = []
    vision_cache_payloads: list[list[_ProbeFeatureBatch | None]] = []

    class FeatureModel:
        config = SimpleNamespace(model_type="gemma4")
        vision_tower = object()
        embed_vision = object()

        def encode_image(self, pixel_values):
            encode_calls.append(list(pixel_values.rows))
            return _ProbeFeatureBatch([f"feature:{row}" for row in pixel_values.rows])

    def fake_stream_generate(model, processor, prompt: str, image=None, vision_cache=None, **kwargs):
        _ = processor
        _ = prompt
        if "cached_image_features" in kwargs or "missing_image_indexes" in kwargs:
            raise SystemExit("legacy image feature kwargs should not be forwarded")
        if vision_cache is None:
            raise SystemExit("vision_cache was not forwarded to mlx-vlm stream_generate")
        image_paths = list(image or [])
        cached = vision_cache.get(image_paths)
        vision_cache_payloads.append(list(vision_cache.payloads))
        if cached is None:
            pixel_values = _ProbeFeatureBatch(
                [Path(path).read_bytes().decode("utf-8") for path in image_paths]
            )
            features = model.encode_image(pixel_values)
            vision_cache.put(image_paths, features)
        yield SimpleNamespace(text="ok", prompt_tokens=4, generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                FeatureModel(),
                SimpleNamespace(image_processor=object()),
            ),
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::image",
        )
    )
    loaded_model = runtime.load_model(_model_spec())
    prepared = _image_request(b"gemma4-weight-image")
    sampling = common_pb2.SamplingConfig(max_output_tokens=1)

    list(runtime.generate_tokens(loaded_model, prepared, sampling, cancel_event=Event()))
    runtime._record_fast_path_probe(loaded_model, prepared)
    list(runtime.generate_tokens(loaded_model, prepared, sampling, cancel_event=Event()))
    runtime._record_fast_path_probe(loaded_model, prepared)
    probe = runtime.last_probe_snapshot()

    if encode_calls != [["gemma4-weight-image"]]:
        raise SystemExit(f"unexpected image feature encode calls: {encode_calls!r}")
    if not vision_cache_payloads or vision_cache_payloads[0] != [None]:
        raise SystemExit("initial image feature cache lookup did not miss")
    if len(vision_cache_payloads) < 2 or not isinstance(vision_cache_payloads[1][0], _ProbeFeatureBatch):
        raise SystemExit("repeated image feature cache lookup did not reuse stored features")

    return {
        "image_feature_cache_artifact_count": float(probe.image_feature_cache_artifact_count),
        "image_feature_cache_bytes": float(probe.image_feature_cache_bytes),
        "image_feature_encoder_calls_saved": float(probe.image_feature_encoder_calls_saved),
        "image_feature_reuse_hit_count": float(probe.image_feature_cache_hits),
        "image_feature_work_saved_bytes": float(probe.image_feature_work_saved_bytes),
    }


def run_probe() -> dict[str, float]:
    weights = build_weights()
    weight_names = weights.keys()
    tracemalloc.start()
    warm_up(weight_names)
    tracemalloc.stop()
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    visited_samples: list[float] = []
    checksum = 0
    has_vision = False
    has_audio = False
    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        elapsed_ms, visited, sample_checksum, has_vision, has_audio = measure_once(weight_names)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak_bytes))
        visited_samples.append(float(visited))
        checksum += sample_checksum
    runtime = MLXVLMRuntime()
    loaded_model = {
        "model": SimpleNamespace(),
        "processor": SimpleNamespace(eos_token_id=1),
    }
    scheduler = runtime._text_only_batch_generator_scheduler(loaded_model)
    scheduler._stats.prefill_response_count = 2
    scheduler._stats.prefill_step_count = 2
    probe = runtime.last_probe_snapshot()
    runtime.close_loaded_model(loaded_model)
    if runtime._loaded_models_with_schedulers:
        raise SystemExit("scheduler model tracking was not cleared")

    metrics = {
        "checksum": float(checksum),
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "has_audio": float(has_audio),
        "has_vision": float(has_vision),
        "iteration_count": float(ITERATION_COUNT),
        "live_prefill_response_count": float(probe.text_batch_generator_prefill_response_count),
        "live_prefill_step_count": float(probe.text_batch_generator_prefill_step_count),
        "peak_bytes_mean": round(statistics.fmean(peak_samples), 6),
        "sample_count": float(SAMPLE_COUNT),
        "visited_names_mean": round(statistics.fmean(visited_samples), 6),
        "weight_name_count": float(len(weights)),
    }
    metrics.update(_image_feature_cache_metrics())
    return metrics


def main() -> int:
    print(json.dumps(run_probe(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
