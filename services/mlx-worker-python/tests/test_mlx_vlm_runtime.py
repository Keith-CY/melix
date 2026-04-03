from __future__ import annotations

from threading import Event
import time
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.registry import WorkerRegistry
from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest
from worker.runtime.mlx_vlm_runtime import (
    AutoMLXVLMBackend,
    MLXVLMRuntime,
    _gemma4_multimodal_weight_presence,
)


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
    probe = runtime.last_probe_snapshot()
    assert probe.preprocess_input_bytes == len(b"fake-image-payload")
    assert probe.first_token_latency_ms > 0.0


def test_gemma4_multimodal_weight_presence_detects_text_backed_exports() -> None:
    has_vision, has_audio = _gemma4_multimodal_weight_presence(
        {
            "language_model.model.layers.0.self_attn.q_proj.weight",
            "language_model.model.per_layer_model_projection.weight",
        }
    )

    assert has_vision is False
    assert has_audio is False


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
