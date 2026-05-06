from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Event
from threading import get_ident
import time
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.registry import WorkerRegistry
from worker.runtime.multimodal_preprocessing import (
    PreparedImageInput,
    PreparedVideoInput,
    PreparedVideoFramePolicy,
    PreparedVisionRequest,
)
from worker.runtime import mlx_vlm_runtime as mlx_vlm_runtime_module
from worker.runtime.mlx_vlm_runtime import (
    AutoMLXVLMBackend,
    MLXVLMRuntime,
    RuntimeUnavailableError,
    _gemma4_loaded_execution_mode,
    _gemma4_multimodal_weight_presence,
)
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.temp_media_lifecycle import TempMediaSession


def imported_gemma4_vlm_model() -> common_pb2.ModelSpec:
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


def test_registry_routes_imported_vlm_models_to_mlx_vlm_runtime() -> None:
    fake_runtime = object()
    registry = WorkerRegistry(mlx_vlm_runtime=fake_runtime)  # type: ignore[arg-type]

    runtime_kind, runtime = registry._runtime_for_model(imported_gemma4_vlm_model())

    assert runtime_kind == "vlm"
    assert runtime is fake_runtime


def test_registry_defaults_imported_vlm_models_to_mlx_vlm_runtime_without_backend_override() -> None:
    fake_runtime = object()
    registry = WorkerRegistry(mlx_vlm_runtime=fake_runtime)  # type: ignore[arg-type]
    model = imported_gemma4_vlm_model()
    del model.ext["melix.vlm.backend_id"]

    runtime_kind, runtime = registry._runtime_for_model(model)

    assert runtime_kind == "vlm"
    assert runtime is fake_runtime


def test_registry_rejects_unsupported_vlm_backend_override() -> None:
    registry = WorkerRegistry()
    model = imported_gemma4_vlm_model()
    model.ext["melix.vlm.backend_id"] = "unsupported-backend"

    with pytest.raises(RuntimeError, match="unsupported backend"):
        registry._runtime_for_model(model)


def test_mlx_vlm_runtime_streams_backend_tokens_and_records_probe() -> None:
    apply_calls: list[tuple[str, int]] = []
    stream_calls: list[tuple[str, list[str], list[bytes]]] = []

    def fake_load(model_path: str, revision: str = "main"):
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="gemma4"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        apply_calls.append((prompt, num_images))
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        image_paths = list(image or [])
        from pathlib import Path

        stream_calls.append((prompt, image_paths, [Path(path).read_bytes() for path in image_paths]))
        for index, chunk in enumerate(("A photo ", "of a cat")):
            time.sleep(0.001)
            yield SimpleNamespace(
                text=chunk,
                prompt_tokens=12,
                generation_tokens=index + 1,
                prompt_tps=110.0,
                generation_tps=24.0,
                peak_memory=1.5,
            )

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )

    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"fake-image-payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="sample.jpg",
                            format="jpg",
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )
    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=16,
            ),
            Event(),
        )
    )

    assert loaded_model["vision_family_id"] == "gemma4-v1"
    assert "".join(event.text for event in events) == "A photo of a cat"
    assert events[-1].completion_tokens == 2
    assert apply_calls == [("Describe the image.", 1)]
    assert stream_calls[0][0] == "formatted::Describe the image."
    assert len(stream_calls[0][1]) == 1
    assert stream_calls[0][2] == [b"fake-image-payload"]
    assert not Path(stream_calls[0][1][0]).exists()
    probe = runtime.last_probe_snapshot()
    assert probe.preprocess_input_bytes == len(b"fake-image-payload")
    assert probe.first_token_latency_ms > 0.0
    assert probe.temp_media_artifact_count == 1
    assert probe.temp_media_artifact_bytes == len(b"fake-image-payload")
    assert probe.temp_media_cleanup_latency_ms >= 0.0
    assert probe.temp_media_cleanup_failure_count == 0
    assert probe.image_feature_cache_misses == 1
    assert probe.image_feature_cache_hits == 0
    assert probe.multimodal_decode_mode == "native_quantized"
    assert probe.multimodal_decode_sync_mode == "executor_stream"
    assert probe.multi_image_scatter_mode == "none"


def test_mlx_vlm_runtime_records_installed_package_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(package_name: str) -> str:
        return {
            "mlx": "0.31.2",
            "mlx-lm": "0.31.3",
            "mlx-vlm": "0.4.4",
        }[package_name]

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="gemma4"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    monkeypatch.setattr(mlx_vlm_runtime_module, "_installed_package_version", fake_version)
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::prompt",
        )
    )

    loaded_model = runtime.load_model(imported_gemma4_vlm_model())

    assert loaded_model["metadata"]["mlx_version"] == "0.31.2"
    assert loaded_model["metadata"]["mlx_lm_version"] == "0.31.3"
    assert loaded_model["metadata"]["mlx_vlm_version"] == "0.4.4"


def test_mlx_vlm_runtime_caches_family_config_across_prompt_render_and_token_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_call_count = 0

    class FakeFamilyConfig:
        def capability_metadata(self) -> dict[str, str]:
            return {
                "vision_family_id": "gemma4-v1",
                "vision_prompt_profile_id": "gemma4-chatml-v1",
            }

        def shape_request(self, prepared: PreparedVisionRequest) -> PreparedVisionRequest:
            return prepared

        def prompt_token_count(self, prepared: PreparedVisionRequest) -> int:
            return len(prepared.prompt_text.split())

    def fake_resolve(metadata: dict[str, str]) -> FakeFamilyConfig:
        nonlocal resolve_call_count
        resolve_call_count += 1
        assert metadata["vision_family_id"] == "gemma4-v1"
        return FakeFamilyConfig()

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(config=SimpleNamespace(model_type="gemma4"))
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    monkeypatch.setattr(mlx_vlm_runtime_module, "resolve_vision_family_config", fake_resolve)
    monkeypatch.setattr(mlx_vlm_runtime_module, "_installed_package_version", lambda name: f"{name}-version")

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::prompt",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())

    assert resolve_call_count == 1
    cached_config = loaded_model["_vision_family_config"]

    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Describe the image")])],
        loaded_model=loaded_model,
    )

    assert runtime.prompt_token_count(prepared, loaded_model=loaded_model) == 3
    assert runtime.prompt_token_count(prepared, loaded_model=loaded_model) == 3
    assert loaded_model["_vision_family_config"] is cached_config
    assert resolve_call_count == 1


def test_mlx_vlm_runtime_family_config_backfills_cache_for_legacy_loaded_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_call_count = 0

    class FakeFamilyConfig:
        def capability_metadata(self) -> dict[str, str]:
            return {}

        def shape_request(self, prepared: PreparedVisionRequest) -> PreparedVisionRequest:
            return prepared

        def prompt_token_count(self, prepared: PreparedVisionRequest) -> int:
            return len(prepared.prompt_text)

    def fake_resolve(metadata: dict[str, str]) -> FakeFamilyConfig:
        nonlocal resolve_call_count
        resolve_call_count += 1
        assert metadata["vision_family_id"] == "gemma4-v1"
        return FakeFamilyConfig()

    monkeypatch.setattr(mlx_vlm_runtime_module, "resolve_vision_family_config", fake_resolve)

    legacy_loaded_model = {
        "metadata": {
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "melix.vlm.execution_mode": "multimodal",
        }
    }
    runtime = MLXVLMRuntime()

    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="legacy cache path")])],
        loaded_model=legacy_loaded_model,
    )

    assert runtime.prompt_token_count(prepared, loaded_model=legacy_loaded_model) == len("legacy cache path")
    assert legacy_loaded_model["_vision_family_config"] is not None
    assert resolve_call_count == 1


def test_mlx_vlm_runtime_passes_video_when_backend_accepts_video_argument() -> None:
    stream_calls: list[dict[str, object]] = []

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="qwen2_vl"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = num_images
        _ = kwargs
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, video=None, **kwargs):
        _ = model
        _ = processor
        _ = image
        _ = kwargs
        video_paths = list(video or [])
        stream_calls.append({"prompt": prompt, "video": video_paths})
        yield SimpleNamespace(text="video summary", generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = PreparedVisionRequest(
        prompt_text="Describe the video.",
        images=[],
        videos=[
            PreparedVideoInput(
                source_kind="inline",
                reference="inline:video",
                bytes_data=b"fake-video-payload",
                mime_type="video/mp4",
                format="mp4",
                filename="sample.mp4",
                byte_length=len(b"fake-video-payload"),
                duration_ms=1000,
                frame_budget=4,
                start_ms=0,
                end_ms=1000,
                sha256_hex="beef",
            )
        ],
        video_frame_policies=[
            PreparedVideoFramePolicy(
                reference="inline:video",
                sampling_strategy="uniform",
                requested_frame_budget=4,
                effective_frame_count=4,
                clip_start_ms=0,
                clip_end_ms=1000,
                clip_duration_ms=1000,
            )
        ],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(b"fake-video-payload"),
        preprocess_peak_memory_bytes=len(b"fake-video-payload"),
        prompt_hash_hex="11" * 32,
        multimodal_hash_hex="22" * 32,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=8),
            Event(),
        )
    )

    assert [event.text for event in events] == ["video summary"]
    assert stream_calls[0]["prompt"] == "formatted::Describe the video."
    video_paths = stream_calls[0]["video"]
    assert isinstance(video_paths, list)
    assert len(video_paths) == 1
    assert not Path(video_paths[0]).exists()


def test_mlx_vlm_runtime_records_video_fallback_when_backend_omits_video_argument(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stream_calls: list[dict[str, object]] = []

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="qwen2_vl"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0):
        _ = processor
        _ = config
        _ = num_images
        return f"formatted::{prompt}"

    def fake_stream_generate(
        model,
        processor,
        prompt: str,
        image=None,
        max_tokens: int = 64,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 0,
        verbose: bool = False,
    ):
        _ = model
        _ = processor
        stream_calls.append(
            {
                "prompt": prompt,
                "image": image,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "verbose": verbose,
            }
        )
        yield SimpleNamespace(text="fallback summary", generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = PreparedVisionRequest(
        prompt_text="Describe the video.",
        images=[],
        videos=[
            PreparedVideoInput(
                source_kind="inline",
                reference="inline:video",
                bytes_data=b"fake-video-payload",
                mime_type="video/mp4",
                format="mp4",
                filename="sample.mp4",
                byte_length=len(b"fake-video-payload"),
                duration_ms=1000,
                frame_budget=4,
                start_ms=0,
                end_ms=1000,
                sha256_hex="beef",
            )
        ],
        video_frame_policies=[
            PreparedVideoFramePolicy(
                reference="inline:video",
                sampling_strategy="uniform",
                requested_frame_budget=4,
                effective_frame_count=4,
                clip_start_ms=0,
                clip_end_ms=1000,
                clip_duration_ms=1000,
            )
        ],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(b"fake-video-payload"),
        preprocess_peak_memory_bytes=len(b"fake-video-payload"),
        prompt_hash_hex="11" * 32,
        multimodal_hash_hex="22" * 32,
    )

    caplog.set_level("WARNING", logger=mlx_vlm_runtime_module.__name__)
    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=8),
            Event(),
        )
    )

    assert [event.text for event in events] == ["fallback summary"]
    assert stream_calls == [
        {
            "prompt": "formatted::Describe the video.",
            "image": None,
            "max_tokens": 8,
            "temperature": 0.0,
            "top_p": 0.0,
            "top_k": 0,
            "verbose": False,
        }
    ]
    probe = runtime.last_probe_snapshot()
    assert probe.multimodal_decode_mode == "fallback"
    assert probe.multimodal_fallback_reason == "backend_video_kwarg_unsupported"
    assert "does not accept video=" in caplog.text


def test_mlx_vlm_runtime_plans_fast_path_when_generate_is_called_directly() -> None:
    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return (
            SimpleNamespace(
                config=SimpleNamespace(model_type="gemma4"),
                vision_tower=object(),
                embed_vision=object(),
            ),
            SimpleNamespace(image_processor=object()),
        )

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = num_images
        _ = kwargs
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        _ = kwargs
        yield SimpleNamespace(
            text="A photo of a cat",
            prompt_tokens=12,
            generation_tokens=1,
            prompt_tps=110.0,
            generation_tps=24.0,
            peak_memory=1.5,
        )

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    image_bytes = b"direct-generate-image"
    prepared = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=image_bytes,
                source_kind="inline",
                reference="inline:sample.jpg",
                mime_type="image/jpeg",
                format="jpg",
                filename="sample.jpg",
                sha256_hex=hashlib.sha256(image_bytes).hexdigest(),
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=1.0,
        preprocess_input_bytes=len(image_bytes),
        preprocess_peak_memory_bytes=len(image_bytes),
        prompt_hash_hex="11" * 32,
        multimodal_hash_hex="22" * 32,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=16),
            Event(),
        )
    )

    assert "".join(event.text for event in events) == "A photo of a cat"
    probe = runtime.last_probe_snapshot()
    assert probe.image_feature_cache_hits == 0
    assert probe.image_feature_cache_misses == 1
    assert probe.multimodal_decode_mode == "native_quantized"


def test_mlx_vlm_runtime_load_template_and_stream_run_on_executor_thread() -> None:
    main_thread_id = get_ident()
    seen: dict[str, int] = {}

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        seen["load_thread_id"] = get_ident()
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="gemma4"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = prompt
        _ = num_images
        _ = kwargs
        seen["template_thread_id"] = get_ident()
        return "formatted::prompt"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        _ = kwargs
        seen["stream_thread_id"] = get_ident()
        yield SimpleNamespace(text="VLM", prompt_tokens=8, generation_tokens=1)

    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        ),
        executor=executor,
    )
    try:
        loaded_model = runtime.load_model(imported_gemma4_vlm_model())
        prepared = runtime.render_prompt(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="Say hello.")],
                )
            ],
            loaded_model=loaded_model,
        )
        events = list(
            runtime.generate_tokens(
                loaded_model,
                prepared,
                common_pb2.SamplingConfig(max_output_tokens=8),
                Event(),
            )
        )
        executor_thread_id = executor.run(get_ident)
    finally:
        executor.shutdown()

    assert [event.text for event in events] == ["VLM"]
    assert seen == {
        "load_thread_id": executor_thread_id,
        "template_thread_id": executor_thread_id,
        "stream_thread_id": executor_thread_id,
    }
    assert executor_thread_id != main_thread_id


def test_mlx_vlm_runtime_skips_empty_backend_chunks() -> None:
    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        _ = kwargs
        yield SimpleNamespace(text="", prompt_tokens=4, generation_tokens=1)
        yield SimpleNamespace(text="visible", prompt_tokens=4, generation_tokens=2)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::prompt",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=8),
            Event(),
        )
    )

    assert [event.text for event in events] == ["visible"]


def test_mlx_vlm_runtime_stops_stream_when_cancelled_before_backend_chunk() -> None:
    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        _ = kwargs
        yield SimpleNamespace(text="hidden", prompt_tokens=4, generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::prompt",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )
    cancel_event = Event()
    cancel_event.set()

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=8),
            cancel_event,
        )
    )

    assert events == []


def test_mlx_vlm_runtime_records_temp_media_cleanup_failures_in_probe(tmp_path: Path) -> None:
    sessions: list[TempMediaSession] = []

    def fake_load(model_path: str, revision: str = "main"):
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="gemma4"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        _ = kwargs
        yield SimpleNamespace(
            text="A photo of a cat",
            prompt_tokens=12,
            generation_tokens=1,
            prompt_tps=110.0,
            generation_tps=24.0,
            peak_memory=1.5,
        )

    def failing_cleanup(_path: Path) -> None:
        raise OSError("cleanup failed")

    def session_factory(**kwargs) -> TempMediaSession:
        session = TempMediaSession(
            cleanup_impl=failing_cleanup,
            **kwargs,
        )
        sessions.append(session)
        return session

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        ),
        temp_root=tmp_path,
        temp_media_session_factory=session_factory,
    )

    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"fake-image-payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="sample.jpg",
                            format="jpg",
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=16),
            Event(),
        )
    )

    assert "".join(event.text for event in events) == "A photo of a cat"
    assert sessions
    assert sessions[0].session_root is not None
    assert sessions[0].session_root.exists()
    probe = runtime.last_probe_snapshot()
    assert probe.temp_media_artifact_count == 1
    assert probe.temp_media_artifact_bytes == len(b"fake-image-payload")
    assert probe.temp_media_cleanup_failure_count == 1
    assert probe.temp_media_cleanup_latency_ms >= 0.0


def test_gemma4_multimodal_weight_presence_detects_text_backed_exports() -> None:
    has_vision, has_audio = _gemma4_multimodal_weight_presence(
        {
            "language_model.model.layers.0.self_attn.q_proj.weight",
            "language_model.model.per_layer_model_projection.weight",
        }
    )

    assert has_vision is False
    assert has_audio is False


def test_gemma4_multimodal_weight_presence_scans_weight_names_once() -> None:
    class CountingWeightNames:
        def __init__(self, names: tuple[str, ...]) -> None:
            self.names = names
            self.iteration_count = 0
            self.visited_names: list[str] = []

        def __iter__(self):
            self.iteration_count += 1
            for name in self.names:
                self.visited_names.append(name)
                yield name

    weight_names = CountingWeightNames(
        (
            "language_model.model.layers.0.self_attn.q_proj.weight",
            "vision_tower.encoder.layers.0.weight",
            "audio_tower.encoder.layers.0.weight",
            "language_model.model.layers.99.self_attn.o_proj.weight",
        )
    )

    assert _gemma4_multimodal_weight_presence(weight_names) == (True, True)
    assert weight_names.iteration_count == 1
    assert weight_names.visited_names == [
        "language_model.model.layers.0.self_attn.q_proj.weight",
        "vision_tower.encoder.layers.0.weight",
        "audio_tower.encoder.layers.0.weight",
    ]


def test_gemma4_multimodal_weight_presence_accepts_dict_keys_view() -> None:
    weights = {
        "language_model.model.layers.0.self_attn.q_proj.weight": object(),
        "embed_audio.proj.weight": object(),
    }

    assert _gemma4_multimodal_weight_presence(weights.keys()) == (False, True)


def test_mlx_vlm_runtime_overrides_stale_text_backed_metadata_for_loaded_gemma4_vision_models() -> None:
    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="gemma4"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    model_spec = imported_gemma4_vlm_model()
    model_spec.ext["melix.vlm.execution_mode"] = "text_backed"

    loaded_model = runtime.load_model(model_spec)

    assert loaded_model["metadata"]["melix.vlm.execution_mode"] == "multimodal"


def test_gemma4_loaded_execution_mode_treats_image_processor_as_multimodal() -> None:
    model = SimpleNamespace(vision_tower=None, embed_vision=None)
    processor = SimpleNamespace(image_processor=object())

    assert _gemma4_loaded_execution_mode(model, processor) == "multimodal"


def test_mlx_vlm_runtime_supports_prompt_only_generation_for_text_backed_models() -> None:
    apply_calls: list[tuple[str, int]] = []
    stream_calls: list[tuple[str, object]] = []

    def fake_load(model_path: str, revision: str = "main"):
        model = SimpleNamespace(config=SimpleNamespace(model_type="gemma4"))
        processor = SimpleNamespace()
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        apply_calls.append((prompt, num_images))
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        stream_calls.append((prompt, image))
        yield SimpleNamespace(
            text="Hello!",
            prompt_tokens=9,
            generation_tokens=1,
            prompt_tps=80.0,
            generation_tps=20.0,
            peak_memory=1.25,
        )

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    loaded_model["metadata"]["melix.vlm.execution_mode"] = "text_backed"
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello.")],
            )
        ],
        loaded_model=loaded_model,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=16,
            ),
            Event(),
        )
    )

    assert "".join(event.text for event in events) == "Hello!"
    assert apply_calls == [("Say hello.", 0)]
    assert stream_calls == [("formatted::Say hello.", None)]


def test_mlx_vlm_runtime_uses_mtp_drafter_for_gemma4_text_backed_prompt_only_generation() -> None:
    drafter_loads: list[tuple[str, str]] = []
    batch_calls: list[dict[str, object]] = []

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_stream_generate(*args, **kwargs):  # pragma: no cover
        _ = args
        _ = kwargs
        raise AssertionError("MTP speculative decode should not call stream_generate")

    def fake_load_drafter(model_id: str, *, kind: str = "mtp"):
        drafter_loads.append((model_id, kind))
        return {"draft_model_id": model_id, "kind": kind}

    def fake_batch_generate(
        model,
        processor,
        *,
        prompts,
        max_tokens: int,
        temperature: float,
        draft_model,
        draft_kind: str,
        draft_block_size: int,
        **kwargs,
    ):
        _ = model
        _ = processor
        batch_calls.append(
            {
                "prompts": list(prompts),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "draft_model": draft_model,
                "draft_kind": draft_kind,
                "draft_block_size": draft_block_size,
                "kwargs": dict(kwargs),
            }
        )
        return [
            SimpleNamespace(
                text="MTP hello",
                prompt_tokens=5,
                generation_tokens=2,
                speculative_acceptance_rate=0.75,
                speculative_rollback_rate=0.25,
                speculative_accepted_tokens=6,
                speculative_rejected_tokens=2,
                speculative_draft_propose_ms=4.5,
                speculative_target_verify_ms=5.5,
            )
        ]

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::unused",
            load_drafter_fn=fake_load_drafter,
            batch_generate_fn=fake_batch_generate,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        num_draft_tokens=6,
        allow_baseline_fallback=False,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=0,
                max_output_tokens=16,
            ),
            Event(),
            acceleration_policy=policy,
        )
    )

    assert [event.text for event in events] == ["MTP hello"]
    assert drafter_loads == [("mlx-community/gemma-4-E2B-it-assistant-bf16", "mtp")]
    assert batch_calls == [
        {
            "prompts": ["Say hello."],
            "max_tokens": 16,
            "temperature": 0.0,
            "draft_model": {
                "draft_model_id": "mlx-community/gemma-4-E2B-it-assistant-bf16",
                "kind": "mtp",
            },
            "draft_kind": "mtp",
            "draft_block_size": 6,
            "kwargs": {},
        }
    ]
    event = events[-1]
    assert event.prompt_tokens == 5
    assert event.completion_tokens == 2
    assert event.speculative_fallback_count == 0
    assert event.speculative_num_draft_tokens == 6
    assert event.speculative_draft_model_configured is True
    assert event.speculative_acceptance_rate == 0.75
    assert event.speculative_rollback_rate == 0.25
    assert event.speculative_accepted_tokens == 6
    assert event.speculative_rejected_tokens == 2
    assert event.speculative_draft_propose_ms == 4.5
    assert event.speculative_target_verify_ms == 5.5


def test_auto_mlx_vlm_backend_detects_installed_optional_mtp_api() -> None:
    backend = AutoMLXVLMBackend()
    if not getattr(backend, "_available", False):
        pytest.skip("mlx-vlm is not installed")

    backend._ensure_runtime()

    assert backend.runtime_name == "mlx-vlm"
    assert backend.load_fn is not None
    assert backend.stream_generate_fn is not None
    assert backend.apply_chat_template_fn is not None
    assert backend.supports_mtp_speculative() is (
        backend.batch_generate_fn is not None and backend.load_drafter_fn is not None
    )


def test_auto_mlx_vlm_backend_load_drafter_requires_loader() -> None:
    backend = AutoMLXVLMBackend(
        load_fn=lambda model_path, revision="main": (object(), object()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        apply_chat_template_fn=lambda *args, **kwargs: "",
    )

    with pytest.raises(RuntimeUnavailableError, match="drafter loading"):
        backend.load_drafter("mlx-community/gemma-4-E2B-it-assistant-bf16")


def test_auto_mlx_vlm_backend_caches_drafter_loads_with_legacy_loader_signature() -> None:
    loads: list[str] = []
    drafter = object()

    def fake_batch_generate(
        model,
        processor,
        *,
        prompts,
        draft_model,
        draft_kind,
        draft_block_size,
    ):
        _ = model
        _ = processor
        _ = prompts
        _ = draft_model
        _ = draft_kind
        _ = draft_block_size
        return []

    def fake_load_drafter(model_id: str):
        loads.append(model_id)
        return drafter

    backend = AutoMLXVLMBackend(
        load_fn=lambda model_path, revision="main": (object(), object()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        apply_chat_template_fn=lambda *args, **kwargs: "",
        batch_generate_fn=fake_batch_generate,
        load_drafter_fn=fake_load_drafter,
    )

    assert backend.supports_mtp_speculative() is True
    assert backend.load_drafter("draft-model", kind="mtp") is drafter
    assert backend.load_drafter("draft-model", kind="mtp") is drafter
    assert loads == ["draft-model"]


def test_mlx_vlm_runtime_falls_back_when_mtp_drafter_api_is_unavailable_and_fallback_allowed() -> None:
    stream_calls: list[str] = []

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = image
        _ = kwargs
        stream_calls.append(prompt)
        yield SimpleNamespace(text="baseline", prompt_tokens=5, generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda processor, config, prompt, num_images=0: f"formatted::{prompt}",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        num_draft_tokens=6,
        allow_baseline_fallback=True,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0, max_output_tokens=16),
            Event(),
            acceleration_policy=policy,
        )
    )

    assert [event.text for event in events] == ["baseline"]
    assert stream_calls == ["formatted::Say hello."]
    assert events[-1].speculative_fallback_count == 1
    assert events[-1].speculative_num_draft_tokens == 0
    assert events[-1].speculative_draft_model_configured is False


def test_mlx_vlm_runtime_stops_mtp_path_when_cancelled_before_backend_work() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
            load_drafter_fn=lambda model_id, *, kind="mtp": object(),
            batch_generate_fn=lambda *args, **kwargs: [SimpleNamespace(text="unexpected")],
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="draft-model",
        num_draft_tokens=6,
    )
    cancel_event = Event()
    cancel_event.set()

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0, max_output_tokens=16),
            cancel_event,
            acceleration_policy=policy,
        )
    )

    assert events == []


def test_mlx_vlm_runtime_stops_mtp_path_when_cancelled_after_batch_generate() -> None:
    cancel_event = Event()

    def fake_batch_generate(*args, **kwargs):
        _ = args
        _ = kwargs
        cancel_event.set()
        return [SimpleNamespace(text="hidden")]

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
            load_drafter_fn=lambda model_id, *, kind="mtp": object(),
            batch_generate_fn=fake_batch_generate,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0, max_output_tokens=16),
            cancel_event,
            acceleration_policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
                draft_model_id="draft-model",
                num_draft_tokens=6,
            ),
        )
    )

    assert events == []


def test_mlx_vlm_runtime_skips_empty_mtp_batch_response() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
            load_drafter_fn=lambda model_id, *, kind="mtp": object(),
            batch_generate_fn=lambda *args, **kwargs: [SimpleNamespace(text="")],
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0, max_output_tokens=16),
            Event(),
            acceleration_policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
                draft_model_id="draft-model",
                num_draft_tokens=6,
            ),
        )
    )

    assert events == []


def test_mlx_vlm_runtime_errors_when_mtp_drafter_api_is_unavailable_and_fallback_disabled() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        num_draft_tokens=6,
        allow_baseline_fallback=False,
    )

    with pytest.raises(RuntimeError, match="MTP speculative decode"):
        list(
            runtime.generate_tokens(
                loaded_model,
                prepared,
                common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0, max_output_tokens=16),
                Event(),
                acceleration_policy=policy,
            )
        )


def test_mlx_vlm_runtime_falls_back_for_non_greedy_mtp_requests_when_allowed() -> None:
    stream_calls: list[str] = []

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = image
        _ = kwargs
        stream_calls.append(prompt)
        yield SimpleNamespace(text="sampled baseline", prompt_tokens=5, generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda processor, config, prompt, num_images=0: f"formatted::{prompt}",
            load_drafter_fn=lambda model_id, *, kind="mtp": object(),
            batch_generate_fn=lambda *args, **kwargs: [SimpleNamespace(text="unexpected")],
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        num_draft_tokens=6,
        allow_baseline_fallback=True,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(temperature=0.7, top_p=0.95, top_k=40, max_output_tokens=16),
            Event(),
            acceleration_policy=policy,
        )
    )

    assert [event.text for event in events] == ["sampled baseline"]
    assert stream_calls == ["formatted::Say hello."]
    assert events[-1].speculative_fallback_count == 1
    assert events[-1].speculative_draft_model_configured is False


def test_mlx_vlm_runtime_reports_mtp_unsupported_reasons_without_loading_drafter() -> None:
    runtime = MLXVLMRuntime()
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="draft-model",
        num_draft_tokens=6,
    )
    loaded_gemma4 = {
        "metadata": {
            "vision_family_id": "gemma4-v1",
            "melix.vlm.execution_mode": "text_backed",
        },
        "model": SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
    }
    prompt_only = PreparedVisionRequest(
        prompt_text="Say hello.",
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
    )
    with_image = PreparedVisionRequest(
        prompt_text="Describe.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="deadbeef",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(b"image"),
        preprocess_peak_memory_bytes=len(b"image"),
    )

    missing_draft = common_pb2.AccelerationPolicy(mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE)
    assert "draft_model_id" in runtime._mtp_speculative_unsupported_reason(
        loaded_model=loaded_gemma4,
        prepared_request=prompt_only,
        sampling=common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0),
        execution_mode="text_backed",
        acceleration_policy=missing_draft,
    )
    assert "not Gemma 4" in runtime._mtp_speculative_unsupported_reason(
        loaded_model={"metadata": {"vision_family_id": "llava-v1"}},
        prepared_request=prompt_only,
        sampling=common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0),
        execution_mode="text_backed",
        acceleration_policy=policy,
    )
    assert "target execution mode" in runtime._mtp_speculative_unsupported_reason(
        loaded_model=loaded_gemma4,
        prepared_request=prompt_only,
        sampling=common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0),
        execution_mode="multimodal",
        acceleration_policy=policy,
    )
    assert "media inputs" in runtime._mtp_speculative_unsupported_reason(
        loaded_model=loaded_gemma4,
        prepared_request=with_image,
        sampling=common_pb2.SamplingConfig(temperature=0.0, top_p=1.0, top_k=0),
        execution_mode="text_backed",
        acceleration_policy=policy,
    )
    assert MLXVLMRuntime._is_gemma4_target(object()) is False
    assert MLXVLMRuntime._is_gemma4_target({"metadata": object(), "model": loaded_gemma4["model"]}) is True


def test_mlx_vlm_runtime_mtp_response_helpers_handle_alternate_shapes() -> None:
    assert MLXVLMRuntime._first_batch_response("direct") == "direct"
    assert MLXVLMRuntime._batch_response_text("text") == "text"
    assert MLXVLMRuntime._batch_response_text(SimpleNamespace(response="reply")) == "reply"
    assert MLXVLMRuntime._batch_response_text(SimpleNamespace()) == "namespace()"
    assert MLXVLMRuntime._optional_response_float(SimpleNamespace(), "missing") is None
    assert MLXVLMRuntime._optional_response_int(SimpleNamespace(), "missing") is None


def test_mlx_vlm_runtime_supports_prompt_only_generation_for_multimodal_models() -> None:
    apply_calls: list[tuple[str, int]] = []
    stream_calls: list[tuple[str, object]] = []

    def fake_load(model_path: str, revision: str = "main"):
        model = SimpleNamespace(config=SimpleNamespace(model_type="gemma4"))
        processor = SimpleNamespace()
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        apply_calls.append((prompt, num_images))
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        stream_calls.append((prompt, image))
        yield SimpleNamespace(
            text="Hello from multimodal!",
            prompt_tokens=11,
            generation_tokens=1,
            prompt_tps=90.0,
            generation_tps=18.0,
            peak_memory=1.5,
        )

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello.")],
            )
        ],
        loaded_model=loaded_model,
    )

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=16,
            ),
            Event(),
        )
    )

    assert "".join(event.text for event in events) == "Hello from multimodal!"
    assert prepared.prompt_text == "Say hello."
    assert prepared.images == []
    assert prepared.videos == []
    assert apply_calls == [("Say hello.", 0)]
    assert stream_calls == [("formatted::Say hello.", None)]


def test_mlx_vlm_runtime_render_prompt_preserves_text_backed_image_inputs_until_generation() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    loaded_model["metadata"]["melix.vlm.execution_mode"] = "text_backed"

    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"fake-image-payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="sample.jpg",
                            format="jpg",
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )

    assert prepared.prompt_text == "Describe the image."
    assert len(prepared.images) == 1
    assert prepared.videos == []
    probe = runtime.last_probe_snapshot()
    assert probe.multimodal_decode_mode == "fallback"
    assert probe.multimodal_fallback_reason == "text_backed_no_vision_weights"


def test_mlx_vlm_runtime_records_repeated_image_fast_path_probe() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(
                    config=SimpleNamespace(model_type="gemma4"),
                    vision_tower=object(),
                    embed_vision=object(),
                ),
                SimpleNamespace(image_processor=object()),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Describe the image."),
                common_pb2.MessagePart(
                    image_bytes=b"fake-image-payload",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        filename="sample.jpg",
                        format="jpg",
                    ),
                ),
            ],
        )
    ]

    runtime.render_prompt(messages, loaded_model=loaded_model)
    first_probe = runtime.last_probe_snapshot()
    runtime.render_prompt(messages, loaded_model=loaded_model)
    second_probe = runtime.last_probe_snapshot()

    assert first_probe.multimodal_decode_mode == "native_quantized"
    assert first_probe.image_feature_cache_misses == 1
    assert second_probe.multimodal_decode_mode == "image_cache_reuse"
    assert second_probe.image_feature_cache_hits == 1
    assert second_probe.image_feature_cache_misses == 0


def test_mlx_vlm_runtime_records_partial_multi_image_reuse_probe() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(
                    config=SimpleNamespace(model_type="gemma4"),
                    vision_tower=object(),
                    embed_vision=object(),
                ),
                SimpleNamespace(image_processor=object()),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    first_image = common_pb2.MessagePart(
        image_bytes=b"fake-image-payload",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_IMAGE,
            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
            filename="sample.jpg",
            format="jpg",
        ),
    )
    runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Describe."), first_image],
            )
        ],
        loaded_model=loaded_model,
    )

    runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Compare."),
                    first_image,
                    common_pb2.MessagePart(
                        image_bytes=b"new-image-payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="second.jpg",
                            format="jpg",
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )

    probe = runtime.last_probe_snapshot()
    assert probe.multimodal_decode_mode == "image_cache_reuse"
    assert probe.image_feature_cache_hits == 1
    assert probe.image_feature_cache_misses == 1
    assert probe.multi_image_scatter_mode == "per_sample"


def test_mlx_vlm_runtime_rewrites_video_only_requests_for_text_backed_models() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    loaded_model["metadata"]["melix.vlm.execution_mode"] = "text_backed"

    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the clip."),
                    common_pb2.MessagePart(
                        video_bytes=b"video-fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="video/mp4",
                            format="mp4",
                            filename="clip.mp4",
                            frame_budget=5,
                            start_ms=400,
                            end_ms=2_400,
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )

    assert prepared.prompt_text == (
        "Video 1: clip.mp4; format=mp4; frames=5; start_ms=400; end_ms=2400\n"
        "Prompt: Summarize the clip."
    )
    assert prepared.images == []
    assert len(prepared.videos) == 1
    assert prepared.multimodal_hash_hex != prepared.prompt_hash_hex
    probe = runtime.last_probe_snapshot()
    assert probe.video_effective_frame_count == 5
    assert probe.video_requested_frame_budget == 5
    assert probe.video_window_ms == 2_000


def test_mlx_vlm_runtime_text_backed_video_prompt_defaults_when_prompt_is_blank() -> None:
    prepared = PreparedVisionRequest(
        prompt_text="",
        images=[],
        videos=[
            SimpleNamespace(  # type: ignore[list-item]
                filename="blank-prompt.mp4",
                format="mp4",
                reference="inline:video",
                sha256_hex="00" * 32,
            )
        ],
        video_frame_policies=[
            PreparedVideoFramePolicy(
                reference="inline:video",
                sampling_strategy="uniform_sample",
                requested_frame_budget=0,
                effective_frame_count=8,
                clip_start_ms=0,
                clip_end_ms=0,
                clip_duration_ms=0,
            )
        ],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex="11" * 32,
        multimodal_hash_hex="22" * 32,
    )

    prompt_text = MLXVLMRuntime._text_backed_video_prompt(prepared)

    assert prompt_text == (
        "Video 1: blank-prompt.mp4; format=mp4; frames=8; start_ms=0; end_ms=0\n"
        "Prompt: Describe the video."
    )


def test_mlx_vlm_runtime_rejects_image_inputs_for_text_backed_models() -> None:
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
                SimpleNamespace(),
            ),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    loaded_model["metadata"]["melix.vlm.execution_mode"] = "text_backed"
    prepared = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=b"fake-image-payload",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="sample.jpg",
                sha256_hex="deadbeef",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(b"fake-image-payload"),
        preprocess_peak_memory_bytes=len(b"fake-image-payload"),
    )

    try:
        list(
            runtime.generate_tokens(
                loaded_model,
                prepared,
                common_pb2.SamplingConfig(max_output_tokens=8),
                Event(),
            )
        )
    except RuntimeError as exc:
        assert "does not include vision weights" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected text-backed Gemma 4 runtime to reject image inputs.")
