from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from threading import Event
from threading import get_ident
import time
from types import ModuleType, SimpleNamespace

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
from worker.runtime import runtime_utils
from worker.runtime.mlx_vlm_runtime import (
    AutoMLXVLMBackend,
    MLXVLMRuntime,
    RuntimeUnavailableError,
    _CallableTokenizerProcessor,
    _Gemma4TextBackedModelShim,
    _TEXT_ONLY_BATCH_GENERATOR_EXT_KEY,
    _TEXT_ONLY_BATCH_DONE,
    _TextOnlyBatchGeneratorScheduler,
    _TextOnlyBatchRequest,
    _TextOnlyVLMDecodeAdapter,
    maybe_apply_native_mtp_preload_patches,
    _text_batch_generator_probe_kwargs,
    _text_only_streaming_decoder,
    _gemma4_loaded_execution_mode,
    _gemma4_multimodal_weight_presence,
    _isolated_streaming_detokenizer,
    _mlx_peak_memory_gb,
    _patch_gemma4_scaled_linear_quantization,
)
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.temp_media_lifecycle import TempMediaSession


class _FakeMLXArray:
    def __init__(self, value):
        self._value = value
        self.shape = self._shape(value)

    def __getitem__(self, index):
        return _FakeMLXArray(self._value[index])

    def __mul__(self, scalar):
        return _FakeMLXArray(self._map_values(lambda value: value * scalar))

    def tolist(self):
        return self._value

    @classmethod
    def _shape(cls, value) -> tuple[int, ...]:
        if isinstance(value, list | tuple):
            if not value:
                return (0,)
            return (len(value), *cls._shape(value[0]))
        return ()

    def _map_values(self, callback):
        def apply(value):
            if isinstance(value, list):
                return [apply(item) for item in value]
            if isinstance(value, tuple):
                return tuple(apply(item) for item in value)
            return callback(value)

        return apply(self._value)


def _install_fake_mlx_core(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mlx = ModuleType("mlx")
    fake_core = ModuleType("mlx.core")
    fake_core.array = lambda value: _FakeMLXArray(value)
    fake_core.ones = lambda shape: _FakeMLXArray(_fake_ones(shape))
    fake_core.eval = lambda _parameters: None
    fake_core.load = lambda _path: {}
    fake_core.metal = SimpleNamespace(get_peak_memory=lambda: 0)
    fake_nn = ModuleType("mlx.nn")

    class FakeQuantizedLinear:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def __call__(self, value):
            return value

    fake_nn.QuantizedLinear = FakeQuantizedLinear
    fake_nn.quantize = lambda *args, **kwargs: None
    fake_mlx.core = fake_core
    fake_mlx.nn = fake_nn
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_core)
    monkeypatch.setitem(sys.modules, "mlx.nn", fake_nn)


def _install_native_mtp_fake_mlx(
    monkeypatch: pytest.MonkeyPatch,
    fake_mx: ModuleType,
    fake_nn: ModuleType | None = None,
) -> None:
    fake_mlx = ModuleType("mlx")
    fake_mlx.core = fake_mx
    fake_nn = fake_nn or ModuleType("mlx.nn")
    if not hasattr(fake_nn, "Module"):
        fake_nn.Module = object
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mx)
    fake_mlx.nn = fake_nn
    monkeypatch.setitem(sys.modules, "mlx.nn", fake_nn)


def _fake_ones(shape):
    dimensions = tuple(shape)
    if not dimensions:
        return 1
    return [_fake_ones(dimensions[1:]) for _ in range(dimensions[0])]


def _install_fake_mlx_vlm_modules(monkeypatch: pytest.MonkeyPatch) -> dict[str, ModuleType]:
    fake_mlx_vlm = ModuleType("mlx_vlm")
    fake_mlx_vlm.__path__ = []
    fake_models = ModuleType("mlx_vlm.models")
    fake_models.__path__ = []
    fake_base = ModuleType("mlx_vlm.models.base")
    fake_gemma4 = ModuleType("mlx_vlm.models.gemma4")
    fake_gemma4.__path__ = []
    fake_language = ModuleType("mlx_vlm.models.gemma4.language")
    fake_utils = ModuleType("mlx_vlm.utils")

    class InputEmbeddingsFeatures:
        def __init__(self, *, inputs_embeds=None, per_layer_inputs=None) -> None:
            self.inputs_embeds = inputs_embeds
            self.per_layer_inputs = per_layer_inputs

    fake_base.InputEmbeddingsFeatures = InputEmbeddingsFeatures
    fake_language.ScaledLinear = type("ScaledLinear", (), {})
    fake_language.TextConfig = type("TextConfig", (), {})
    fake_language.LanguageModel = type("LanguageModel", (), {})
    fake_utils.get_model_and_args = lambda *args, **kwargs: None
    fake_utils.get_model_path = lambda *args, **kwargs: None
    fake_utils.load_config = lambda *args, **kwargs: {}
    fake_utils.load_processor = lambda *args, **kwargs: None
    fake_utils.load_tokenizer = lambda *args, **kwargs: None
    fake_utils.update_module_configs = lambda *args, **kwargs: None
    fake_gemma4.language = fake_language
    fake_models.base = fake_base
    fake_models.gemma4 = fake_gemma4
    fake_mlx_vlm.models = fake_models
    fake_mlx_vlm.utils = fake_utils

    modules = {
        "mlx_vlm": fake_mlx_vlm,
        "mlx_vlm.models": fake_models,
        "mlx_vlm.models.base": fake_base,
        "mlx_vlm.models.gemma4": fake_gemma4,
        "mlx_vlm.models.gemma4.language": fake_language,
        "mlx_vlm.utils": fake_utils,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return modules


def _install_fake_mlx_vlm_prepare_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    modules = _install_fake_mlx_vlm_modules(monkeypatch)
    fake_utils = modules["mlx_vlm.utils"]

    def fake_prepare_inputs(processor, **kwargs):
        prepared = processor(kwargs["prompts"], **{key: value for key, value in kwargs.items() if key != "prompts"})
        return {
            "input_ids": prepared.input_ids,
            "attention_mask": prepared.attention_mask,
        }

    fake_utils.prepare_inputs = fake_prepare_inputs


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
            response = SimpleNamespace(
                text=chunk,
                prompt_tokens=12,
                generation_tokens=index + 1,
                prompt_tps=110.0,
                generation_tps=24.0,
                peak_memory=1.5,
            )
            if index == 0:
                response.token = 17
                response.logprob = -0.25
                response.parser_observation = "vlm-token=17"
            yield response

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
    assert [event.raw_text for event in events] == ["A photo ", "A photo of a cat"]
    assert events[0].token_ids == (17,)
    assert events[0].token_logprobs == (-0.25,)
    assert events[0].parser_observation == "vlm-token=17"
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


def test_mlx_vlm_runtime_forwards_trust_remote_code_when_loader_supports_it() -> None:
    seen: dict[str, object] = {}

    def fake_load(
        model_path: str,
        *,
        revision: str = "main",
        trust_remote_code: bool = False,
    ):
        seen["load"] = (model_path, revision, trust_remote_code)
        model = SimpleNamespace(config=SimpleNamespace(model_type="gemma4"))
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )

    runtime.load_model(imported_gemma4_vlm_model(), trust_remote_code=True)

    assert seen["load"] == ("unsloth/gemma-4-E4B-it-MLX-8bit", "main", True)


def test_auto_vlm_backend_rejects_trust_when_loader_cannot_accept_kwarg() -> None:
    def fake_load(model_path: str, *, revision: str = "main"):  # pragma: no cover - must be blocked.
        _ = model_path, revision
        model = SimpleNamespace(config=SimpleNamespace(model_type="gemma4"))
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    backend = AutoMLXVLMBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        apply_chat_template_fn=lambda *args, **kwargs: "",
    )

    with pytest.raises(RuntimeError, match="trust_remote_code"):
        backend.load_model(imported_gemma4_vlm_model(), trust_remote_code=True)


def test_mlx_vlm_runtime_rejects_trust_when_backend_cannot_accept_kwarg() -> None:
    class LegacyBackend:
        runtime_name = "mlx-vlm"

        def load_model(self, model_spec):  # pragma: no cover - must be blocked before invocation.
            return {"model_id": model_spec.model_id}

        def estimate_resident_bytes(self, model_spec) -> int:  # pragma: no cover - not used by this test.
            _ = model_spec
            return 0

    runtime = MLXVLMRuntime(backend=LegacyBackend())

    with pytest.raises(RuntimeError, match="trust_remote_code"):
        runtime.load_model(imported_gemma4_vlm_model(), trust_remote_code=True)


def test_mlx_vlm_runtime_uses_explicit_trust_support_override() -> None:
    class BackendWithExplicitSupport:
        runtime_name = "wrapped-runtime"
        supports_trust_policy = True

        def load_model(self, model_spec):  # pragma: no cover - property checks only.
            return {"model_id": model_spec.model_id}

    class BackendWithExplicitOptOut:
        runtime_name = "mlx-vlm"
        supports_trust_policy = False

        def load_model(self, model_spec):  # pragma: no cover - property checks only.
            return {"model_id": model_spec.model_id}

    assert MLXVLMRuntime(backend=BackendWithExplicitSupport()).supports_trust_policy is True
    assert MLXVLMRuntime(backend=BackendWithExplicitOptOut()).supports_trust_policy is False
    assert MLXVLMRuntime(backend=AutoMLXVLMBackend(load_fn=lambda *args, **kwargs: None)).supports_trust_policy is True


def test_mlx_vlm_runtime_records_installed_package_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(package_name: str) -> str:
        return {
            "mlx": "0.31.2",
            "mlx-lm": "0.31.3",
            "mlx-vlm": "0.5.0",
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
    assert loaded_model["metadata"]["mlx_vlm_version"] == "0.5.0"


def test_mlx_vlm_runtime_uses_generate_step_fast_path_for_text_only_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_vlm_prepare_inputs(monkeypatch)
    apply_calls: list[tuple[str, int]] = []
    stream_calls = 0
    generate_step_calls: list[dict[str, object]] = []
    temp_media_session_calls = 0

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.text = ""
            self.last_segment = ""

        def reset(self) -> None:
            self.text = ""
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = {101: "Direct ", 102: "step"}.get(token, "")
            self.text += self.last_segment

        def finalize(self) -> None:
            self.last_segment = ""

    class FakeProcessor:
        chat_template = "{{ prompt }}"
        eos_token = "<eos>"
        pad_token = None

        def __init__(self) -> None:
            self.detokenizer = FakeDetokenizer()
            self.eos_token_id = 1
            self.all_special_ids = [1, 106]

        def __call__(self, prompts, **kwargs):
            import mlx.core as mx

            assert prompts == ["formatted::Say hello."]
            assert kwargs["return_tensors"] == "mlx"
            return SimpleNamespace(
                input_ids=mx.array([[1, 2, 3]]),
                attention_mask=mx.array([[1, 1, 1]]),
            )

        def stopping_criteria(self, token: int) -> bool:
            return token == 0

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), FakeProcessor()

    def fake_stream_generate(*args, **kwargs):
        _ = args
        _ = kwargs
        nonlocal stream_calls
        stream_calls += 1
        raise AssertionError("text-only fast path should not call stream_generate")

    def fake_apply_chat_template(_processor, _config, prompt, **kwargs):
        apply_calls.append((prompt, kwargs.get("num_images", -1)))
        return f"formatted::{prompt}"

    def fake_generate_step(input_ids, model, pixel_values, mask, **kwargs):
        generate_step_calls.append(
            {
                "input_ids_shape": tuple(input_ids.shape),
                "model": model,
                "pixel_values": pixel_values,
                "mask_shape": tuple(mask.shape),
                "max_tokens": kwargs["max_tokens"],
                "temperature": kwargs["temperature"],
                "top_p": kwargs["top_p"],
                "top_k": kwargs["top_k"],
                "prefill_step_size": kwargs["prefill_step_size"],
            }
        )
        yield 101, [-0.1]
        yield 102, [-0.2]

    def fake_temp_media_session_factory(**_kwargs):
        nonlocal temp_media_session_calls
        temp_media_session_calls += 1
        pytest.fail("text-only fast path should not create a temp media session")

    peak_memory_calls = 0

    def fake_peak_memory(_mx_module) -> float:
        nonlocal peak_memory_calls
        peak_memory_calls += 1
        return 7.0

    monkeypatch.setattr(mlx_vlm_runtime_module, "_installed_package_version", lambda name: f"{name}-version")
    monkeypatch.setattr(mlx_vlm_runtime_module, "_mlx_peak_memory_gb", fake_peak_memory)
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
            generate_step_fn=fake_generate_step,
        ),
        temp_media_session_factory=fake_temp_media_session_factory,
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
            common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=0,
                max_output_tokens=16,
            ),
            Event(),
        )
    )

    assert "".join(event.text for event in events) == "Direct step"
    assert [event.raw_text for event in events] == ["Direct ", "Direct step"]
    assert events[0].token_ids == (101,)
    assert events[0].token_logprobs == (-0.1,)
    assert [event.prompt_tokens for event in events] == [3, 3]
    assert events[-1].completion_tokens == 2
    assert [event.peak_memory for event in events] == [7.0, 7.0]
    assert peak_memory_calls == 1
    assert stream_calls == 0
    assert temp_media_session_calls == 0
    assert apply_calls == [("Say hello.", 0)]
    assert generate_step_calls == [
        {
            "input_ids_shape": (1, 3),
            "model": loaded_model["model"],
            "pixel_values": None,
            "mask_shape": (1, 3),
            "max_tokens": 16,
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 0,
            "prefill_step_size": None,
        }
    ]
    probe = runtime.last_probe_snapshot()
    assert probe.first_token_latency_ms > 0.0
    assert probe.multimodal_decode_mode == "text_only_step"
    assert loaded_model["metadata"]["melix.vlm.text_only_step_cooperative"] == "true"
    assert loaded_model["melix.vlm.text_only_step_cooperative"] == "true"


def _run_text_only_step_with_buffered_detokenizer(
    monkeypatch: pytest.MonkeyPatch,
    generated_tokens: list[int],
):
    _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_vlm_prepare_inputs(monkeypatch)

    class FakeDetokenizer:
        def __init__(self) -> None:
            self._tokens: list[int] = []
            self.text = ""
            self.last_segment = ""

        def __copy__(self):
            copy = FakeDetokenizer()
            copy._tokens = list(self._tokens)
            copy.text = self.text
            copy.last_segment = self.last_segment
            return copy

        def reset(self) -> None:
            self._tokens = []
            self.text = ""
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self._tokens.append(token)
            self.last_segment = ""

        def finalize(self) -> None:
            self.last_segment = "".join({101: "Hello", 102: "!"}.get(token, "") for token in self._tokens)
            self.text += self.last_segment

    class FakeProcessor:
        chat_template = "{{ prompt }}"
        eos_token = "<eos>"
        pad_token = None

        def __init__(self) -> None:
            self.detokenizer = FakeDetokenizer()
            self.eos_token_id = 1
            self.all_special_ids = [1, 106]

        def __call__(self, prompts, **kwargs):
            import mlx.core as mx

            _ = prompts
            _ = kwargs
            return SimpleNamespace(
                input_ids=mx.array([[1, 2, 3]]),
                attention_mask=mx.array([[1, 1, 1]]),
            )

        def stopping_criteria(self, token: int) -> bool:
            return token == 106

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), FakeProcessor()

    def fake_generate_step(*_args, **_kwargs):
        for token_id in generated_tokens:
            yield token_id, [-0.1]

    monkeypatch.setattr(mlx_vlm_runtime_module, "_installed_package_version", lambda name: f"{name}-version")
    monkeypatch.setattr(mlx_vlm_runtime_module, "_mlx_peak_memory_gb", lambda _mx_module: 7.0)
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *_args, **_kwargs: "formatted::prompt",
            generate_step_fn=fake_generate_step,
        ),
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )

    return list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=16),
            Event(),
        )
    )


def test_mlx_vlm_runtime_text_only_step_flushes_buffer_before_stop_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _run_text_only_step_with_buffered_detokenizer(monkeypatch, [101, 102, 106])

    assert [event.text for event in events] == ["Hello!"]
    assert events[-1].raw_text == "Hello!"
    assert events[-1].completion_tokens == 2
    assert mlx_vlm_runtime_module._text_only_batch_prefill_step_size(None) == 512
    assert mlx_vlm_runtime_module._text_only_batch_prefill_step_size("") == 512
    assert mlx_vlm_runtime_module._text_only_batch_prefill_step_size("invalid") == 512
    assert mlx_vlm_runtime_module._text_only_batch_prefill_step_size("0") == 1
    assert mlx_vlm_runtime_module._text_only_batch_prefill_step_size("9000") == 8192
    assert mlx_vlm_runtime_module._text_only_batch_max_batch_size(None) == 8
    assert mlx_vlm_runtime_module._text_only_batch_max_batch_size("") == 8
    assert mlx_vlm_runtime_module._text_only_batch_max_batch_size("invalid") == 8
    assert mlx_vlm_runtime_module._text_only_batch_max_batch_size("0") == 1
    assert mlx_vlm_runtime_module._text_only_batch_max_batch_size("9000") == 256

    class FakePromptResponse:
        def __init__(self, progress: tuple[object, object] | list[object]) -> None:
            self.uid = 7
            self.progress = progress

    class FakeGenerationResponse:
        uid = 7
        token = 11
        finish_reason = "stop"

    class FakeBatchGenerator:
        def __init__(self, **kwargs) -> None:
            self.prefill_step_size = kwargs["prefill_step_size"]
            self.next_calls = 0
            self.removed: list[list[int]] = []

        def insert(self, requests, *, max_tokens, caches=None, all_tokens=None):
            _ = requests
            _ = max_tokens
            _ = caches
            _ = all_tokens
            return [7]

        def next(self):
            self.next_calls += 1
            if self.next_calls == 1:
                return [
                    FakePromptResponse(("bad", 3)),
                    FakePromptResponse((-1, -2)),
                    FakePromptResponse((2, 5)),
                ], []
            return [FakePromptResponse([5, 5])], [FakeGenerationResponse()]

        def remove(self, uids):
            self.removed.append(list(uids))

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = f"tok-{token}"

        def finalize(self) -> None:
            self.last_segment = ""

    fake_generate = ModuleType("mlx_lm.generate")
    fake_generate.BatchGenerator = FakeBatchGenerator
    fake_sample_utils = ModuleType("mlx_lm.sample_utils")
    fake_sample_utils.make_sampler = lambda **_kwargs: object()
    monkeypatch.setitem(sys.modules, "mlx_lm.generate", fake_generate)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", fake_sample_utils)

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
        prefill_step_size=256,
    )
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3, 4, 5],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=5,
    )

    batch_events = list(scheduler.submit(request))
    batch_generator = scheduler._adapter._melix_batch_generator
    stats = scheduler.stats_snapshot()
    scheduler.close()

    assert batch_generator.prefill_step_size == 256
    assert [event.text for event in batch_events] == ["tok-11"]
    assert stats.step_count == 2
    assert stats.prefill_response_count == 4
    assert stats.prefill_step_count == 4
    assert stats.prefill_processed_token_count == 5
    assert stats.prefill_total_token_count == 5
    assert stats.prefill_completed_request_count == 1

    cancel_event = Event()
    cancel_event.set()
    cancelled_scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(_melix_batch_generator=FakeBatchGenerator(prefill_step_size=512)),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
    )
    cancelled_request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=cancel_event,
        prompt_tokens=3,
    )
    cancelled_request.uid = 7
    cancelled_scheduler._active_by_uid[7] = cancelled_request
    cancelled_scheduler._stats.active_batch_size = 1

    cancelled_scheduler._remove_cancelled_active_requests()
    cancelled_stats = cancelled_scheduler.stats_snapshot()
    done = cancelled_request.queue.get_nowait()
    cancelled_batch_generator = cancelled_scheduler._adapter._melix_batch_generator
    cancelled_scheduler.close()

    assert cancelled_batch_generator.removed == [[7]]
    assert done is _TEXT_ONLY_BATCH_DONE
    assert cancelled_stats.completed_request_count == 1
    assert cancelled_stats.active_batch_size == 0

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda *args, **kwargs: (SimpleNamespace(), SimpleNamespace()),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = {
        "model": SimpleNamespace(),
        "processor": SimpleNamespace(eos_token_id=1),
    }
    live_scheduler = runtime._text_only_batch_generator_scheduler(loaded_model)
    live_scheduler._stats.prefill_response_count = 3
    live_scheduler._stats.prefill_step_count = 3
    live_scheduler._stats.prefill_processed_token_count = 1536
    live_scheduler._stats.prefill_total_token_count = 4096
    live_scheduler._stats.prefill_completed_request_count = 0
    live_probe = runtime.last_probe_snapshot()
    runtime.close_loaded_model(loaded_model)

    assert live_probe.text_batch_generator_prefill_response_count == 3
    assert live_probe.text_batch_generator_prefill_step_count == 3
    assert live_probe.text_batch_generator_prefill_processed_token_count == 1536
    assert live_probe.text_batch_generator_prefill_total_token_count == 4096
    assert live_probe.text_batch_generator_prefill_completed_request_count == 0
    assert live_probe.text_batch_generator_prefill_step_size == 512
    assert runtime._loaded_models_with_schedulers == []


def test_mlx_vlm_runtime_text_only_step_flushes_buffer_after_natural_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _run_text_only_step_with_buffered_detokenizer(monkeypatch, [101, 102])

    assert [event.text for event in events] == ["Hello!"]
    assert events[-1].raw_text == "Hello!"
    assert events[-1].completion_tokens == 2


def test_mlx_vlm_runtime_text_only_step_skips_empty_final_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _run_text_only_step_with_buffered_detokenizer(monkeypatch, [103])

    assert events == []


def test_mlx_vlm_runtime_text_only_step_fast_path_releases_executor_between_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_vlm_prepare_inputs(monkeypatch)
    checkpoints: list[tuple[str, int]] = []
    release_seen = Event()

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.text = ""
            self.last_segment = ""

        def reset(self) -> None:
            self.text = ""
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = {101: "First", 102: "Second"}.get(token, "")
            self.text += self.last_segment

        def finalize(self) -> None:
            self.last_segment = ""

    class FakeProcessor:
        chat_template = "{{ prompt }}"
        eos_token = "<eos>"
        pad_token = None

        def __init__(self) -> None:
            self.detokenizer = FakeDetokenizer()

        def __call__(self, prompts, **kwargs):
            import mlx.core as mx

            _ = prompts
            _ = kwargs
            return SimpleNamespace(
                input_ids=mx.array([[1, 2, 3]]),
                attention_mask=mx.array([[1, 1, 1]]),
            )

        def stopping_criteria(self, token: int) -> bool:
            return token == 0

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), FakeProcessor()

    def fake_generate_step(*_args, **_kwargs):
        checkpoints.append(("step-1", get_ident()))
        yield 101, [-0.1]
        assert release_seen.is_set()
        checkpoints.append(("step-2", get_ident()))
        yield 102, [-0.2]

    monkeypatch.setattr(mlx_vlm_runtime_module, "_installed_package_version", lambda name: f"{name}-version")
    monkeypatch.setattr(mlx_vlm_runtime_module, "_mlx_peak_memory_gb", lambda _mx_module: 7.0)
    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *_args, **_kwargs: "formatted::prompt",
            generate_step_fn=fake_generate_step,
        ),
        executor=executor,
    )

    try:
        loaded_model = runtime.load_model(imported_gemma4_vlm_model())
        prepared = runtime.render_prompt(
            [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
            loaded_model=loaded_model,
        )
        iterator = runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=16),
            Event(),
        )

        first_event = next(iterator)
        owner_thread_id = checkpoints[-1][1]
        assert first_event.text == "First"
        assert executor.run(lambda: release_seen.set()) is None
        remaining_events = list(iterator)
    finally:
        executor.shutdown()

    assert [event.text for event in remaining_events] == ["Second"]
    assert checkpoints == [
        ("step-1", owner_thread_id),
        ("step-2", owner_thread_id),
    ]


def test_mlx_vlm_runtime_text_only_step_uses_isolated_detokenizer() -> None:
    class FakeDetokenizer:
        def __init__(self, label: str) -> None:
            self.label = label
            self.text = label
            self.last_segment = ""

        def __copy__(self):
            return FakeDetokenizer(f"{self.label}-copy")

        def reset(self) -> None:
            self.text = ""
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = str(token)
            self.text += self.last_segment

        def finalize(self) -> None:
            pass

    processor = SimpleNamespace(detokenizer=FakeDetokenizer("shared"))

    isolated = _isolated_streaming_detokenizer(processor)

    assert isolated is not None
    assert isolated is not processor.detokenizer
    assert isolated.text == ""
    assert processor.detokenizer.text == "shared"


def test_mlx_vlm_runtime_applies_native_mtp_preload_patch_before_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen36-mtp"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        '{"model_type":"qwen3_5","text_config":{"mtp_num_hidden_layers":1}}\n'
    )
    patch_calls: list[tuple[str, dict[str, str]]] = []
    load_seen_after_patch = False

    def fake_preload_patch(model_path: str, *, metadata: dict[str, str]):
        patch_calls.append((model_path, dict(metadata)))
        return {
            "melix.native_mtp.compatible": "true",
            "melix.native_mtp.patch_applied": "true",
            "melix.native_mtp.active": "true",
        }

    def fake_load(model_path: str, revision: str = "main"):
        nonlocal load_seen_after_patch
        _ = revision
        assert model_path == str(model_dir)
        assert patch_calls
        load_seen_after_patch = True
        return (
            SimpleNamespace(config=SimpleNamespace(model_type="qwen3_5")),
            SimpleNamespace(detokenizer=None),
        )

    monkeypatch.setattr(
        mlx_vlm_runtime_module,
        "maybe_apply_native_mtp_preload_patches",
        fake_preload_patch,
    )
    monkeypatch.setattr(
        mlx_vlm_runtime_module,
        "_installed_package_version",
        lambda name: f"{name}-version",
    )
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *_args, **_kwargs: "formatted::prompt",
        )
    )
    model = common_pb2.ModelSpec(
        model_id="qwen36-mtp",
        model_path=str(model_dir),
        model_kind="vlm",
        revision="main",
        ext={"melix.native_mtp.enabled": "true"},
    )

    loaded = runtime.load_model(model)

    assert load_seen_after_patch is True
    assert len(patch_calls) == 1
    assert patch_calls[0][0] == str(model_dir)
    assert patch_calls[0][1]["melix.native_mtp.enabled"] == "true"
    assert loaded["metadata"]["melix.native_mtp.patch_applied"] == "true"
    assert loaded["metadata"]["melix.native_mtp.active"] == "true"
    assert loaded["metadata"][_TEXT_ONLY_BATCH_GENERATOR_EXT_KEY] == "true"


def test_native_mtp_preload_patch_detects_qwen36_mtp_weights(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen36-mtp"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_5",
                "text_config": {
                    "model_type": "qwen3_5",
                    "mtp_num_hidden_layers": 1,
                },
            }
        )
    )
    (model_dir / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "weight_map": {
                    "language_model.mtp.fc.weight": "mtp.safetensors",
                    "language_model.model.embed_tokens.weight": "model.safetensors",
                }
            }
        )
    )
    calls: list[tuple[str, bool]] = []

    class FakeNativeMTP:
        @staticmethod
        def set_mtp_active(active: bool) -> None:
            calls.append(("active", active))

        @staticmethod
        def set_mtp_weight_attachment(active: bool) -> None:
            calls.append(("attach", active))

        @staticmethod
        def apply_native_mtp_patches() -> bool:
            calls.append(("patch", True))
            return True

    import worker.runtime as worker_runtime_pkg

    monkeypatch.setitem(sys.modules, "worker.runtime.native_mtp", FakeNativeMTP)
    monkeypatch.setattr(
        worker_runtime_pkg,
        "native_mtp",
        FakeNativeMTP,
        raising=False,
    )

    metadata = maybe_apply_native_mtp_preload_patches(
        str(model_dir),
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert metadata["melix.native_mtp.compatible"] == "true"
    assert metadata["melix.native_mtp.weights_present"] == "true"
    assert metadata["melix.native_mtp.weight_count"] == "1"
    assert metadata["melix.native_mtp.patch_applied"] == "true"
    assert metadata["melix.native_mtp.active"] == "true"
    assert ("attach", True) in calls
    assert calls[-1] == ("active", True)


def test_text_only_vlm_decode_adapter_exposes_native_mtp_methods() -> None:
    calls: list[tuple[str, object]] = []

    class FakeLanguageModel:
        mtp = object()

        def mtp_forward(self, hidden_states, next_token_ids, mtp_cache):
            calls.append(("mtp_forward", (hidden_states, next_token_ids, mtp_cache)))
            return "mtp-logits"

        def make_mtp_cache(self):
            calls.append(("make_mtp_cache", None))
            return ["mtp-cache"]

        def rollback_speculative_cache(self, caches, gdn_states, accepted, block_size):
            calls.append(
                (
                    "rollback",
                    (caches, gdn_states, accepted, block_size),
                )
            )
            return "rolled-back"

    adapter = _TextOnlyVLMDecodeAdapter(SimpleNamespace(language_model=FakeLanguageModel()))

    assert adapter.mtp is not None
    assert adapter.make_mtp_cache() == ["mtp-cache"]
    assert adapter.mtp_forward("hidden", "token", ["cache"]) == "mtp-logits"
    assert adapter.rollback_speculative_cache(["kv"], ["gdn"], 0, 2) == "rolled-back"
    assert [call[0] for call in calls] == [
        "make_mtp_cache",
        "mtp_forward",
        "rollback",
    ]


def test_text_only_vlm_decode_adapter_forces_text_only_rope_context() -> None:
    calls: list[str] = []

    class FakeRoPEContext:
        def __enter__(self):
            calls.append("enter-rope")

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type
            _ = exc
            _ = tb
            calls.append("exit-rope")
            return False

    class FakeLanguageModel:
        def _melix_force_text_only_rope_context(self):
            calls.append("context")
            return FakeRoPEContext()

        def __call__(self, input_ids, cache=None, **kwargs):
            calls.append(f"call:{input_ids}:{cache}:{kwargs}")
            return SimpleNamespace(logits="logits")

    adapter = _TextOnlyVLMDecodeAdapter(SimpleNamespace(language_model=FakeLanguageModel()))

    assert adapter([1, 2], cache=["kv"], return_hidden=True) == "logits"
    assert calls == [
        "context",
        "enter-rope",
        "call:[1, 2]:['kv']:{'return_hidden': True}",
        "exit-rope",
    ]


def test_text_only_vlm_decode_adapter_uses_forced_plain_rope_without_position_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mx = ModuleType("mlx.core")

    class FakeArray:
        def __init__(self, label: str, shape=(1,)):
            self.label = label
            self.shape = shape
            self.ndim = len(shape)

        def __getitem__(self, item):
            return FakeArray(f"{self.label}[{item!r}]", self.shape)

        def __add__(self, other):
            return FakeArray(f"({self.label}+{getattr(other, 'label', other)!r})", self.shape)

        def __radd__(self, other):
            return FakeArray(f"({getattr(other, 'label', other)!r}+{self.label})", self.shape)

        def reshape(self, *shape):
            return FakeArray(f"{self.label}.reshape{shape!r}", shape)

    fake_mx.array = FakeArray
    fake_mx.arange = lambda value: FakeArray(f"arange:{value}", (value,))
    fake_mx.broadcast_to = lambda value, shape: FakeArray(
        f"broadcast:{getattr(value, 'label', value)}:{shape}",
        shape,
    )
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mx)

    calls: list[Any] = []
    context_calls: list[str] = []

    class FakeInputIDs:
        shape = (1, 2)

    class FakeCache:
        offset = 7

    class FakeLanguageModel:
        def _melix_force_text_only_rope_context(self):
            class Context:
                def __enter__(self_inner):
                    context_calls.append("enter")

                def __exit__(self_inner, exc_type, exc, tb):
                    _ = exc_type
                    _ = exc
                    _ = tb
                    context_calls.append("exit")
                    return False

            return Context()

        def __call__(self, input_ids, cache=None, **kwargs):
            _ = input_ids
            _ = cache
            calls.append(kwargs)
            return SimpleNamespace(logits="logits")

    text_config = SimpleNamespace(rope_parameters={"mrope_section": [16, 24, 24]})
    vlm_model = SimpleNamespace(
        language_model=FakeLanguageModel(),
        config=SimpleNamespace(text_config=text_config),
    )
    adapter = _TextOnlyVLMDecodeAdapter(vlm_model)

    assert adapter(FakeInputIDs(), cache=[FakeCache()]) == "logits"
    assert calls == [{}]
    assert context_calls == ["enter", "exit"]


def test_text_only_vlm_decode_adapter_skips_position_state_in_forced_plain_rope_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mx = ModuleType("mlx.core")

    class FakeArray:
        def __init__(self, label: str, shape=(1,)):
            self.label = label
            self.shape = shape
            self.ndim = len(shape)

        def __getitem__(self, item):
            return FakeArray(f"{self.label}[{item!r}]", self.shape)

        def __add__(self, other):
            return FakeArray(f"({self.label}+{getattr(other, 'label', other)!r})", self.shape)

        def __radd__(self, other):
            return FakeArray(f"({getattr(other, 'label', other)!r}+{self.label})", self.shape)

        def reshape(self, *shape):
            return FakeArray(f"{self.label}.reshape{shape!r}", shape)

    fake_mx.array = FakeArray
    fake_mx.arange = lambda value: FakeArray(f"arange:{value}", (value,))
    fake_mx.broadcast_to = lambda value, shape: FakeArray(
        f"broadcast:{getattr(value, 'label', value)}:{shape}",
        shape,
    )
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mx)

    calls: list[str] = []

    class FakeInputIDs:
        shape = (1, 2)

    class FakeCache:
        offset = 7

    class FakeLanguageModel:
        def _melix_force_text_only_rope_context(self):
            class Context:
                def __enter__(self_inner):
                    return None

                def __exit__(self_inner, exc_type, exc, tb):
                    _ = exc_type
                    _ = exc
                    _ = tb
                    return False

            return Context()

        def __call__(self, input_ids, cache=None, **kwargs):
            _ = input_ids
            _ = cache
            if "position_ids" in kwargs:
                calls.append("position_ids")
            return SimpleNamespace(logits="logits")

    class FakeVLMModel:
        language_model = FakeLanguageModel()
        config = SimpleNamespace(
            text_config=SimpleNamespace(rope_parameters={"mrope_section": [16, 24, 24]})
        )

        def _set_position_state(self, input_ids):
            _ = input_ids
            calls.append("set_position_state")

    adapter = _TextOnlyVLMDecodeAdapter(FakeVLMModel())

    assert adapter(FakeInputIDs(), cache=[FakeCache()]) == "logits"
    assert calls == []


def test_native_mtp_qwen35_attention_forced_plain_skips_mrope_position_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeTensor:
        dtype = "float16"

        def __init__(self, label: str, shape=(1,)) -> None:
            self.label = label
            self.shape = tuple(shape)
            self.ndim = len(self.shape)

        def __getitem__(self, item):
            return FakeTensor(f"{self.label}[{item!r}]", self.shape)

        def __neg__(self):
            return FakeTensor(f"-{self.label}", self.shape)

        def __add__(self, other):
            return FakeTensor(f"{self.label}+{getattr(other, 'label', other)!r}", self.shape)

        def __radd__(self, other):
            return FakeTensor(f"{getattr(other, 'label', other)!r}+{self.label}", self.shape)

        def __mul__(self, other):
            return FakeTensor(f"{self.label}*{getattr(other, 'label', other)!r}", self.shape)

        def __rmul__(self, other):
            return FakeTensor(f"{getattr(other, 'label', other)!r}*{self.label}", self.shape)

        def reshape(self, *shape):
            return FakeTensor(f"{self.label}.reshape", shape)

        def transpose(self, *axes):
            if len(axes) == len(self.shape):
                shape = tuple(self.shape[index] for index in axes)
            else:
                shape = self.shape
            return FakeTensor(f"{self.label}.transpose", shape)

        def astype(self, dtype):
            return FakeTensor(f"{self.label}.astype:{dtype}", self.shape)

    fake_mx = ModuleType("mlx.core")
    fake_mx.array = FakeTensor
    fake_mx.float32 = "float32"

    def fake_arange(start, stop=None):
        calls.append(f"arange:{start}:{stop}")
        length = int((stop if stop is not None else start) - (start if stop is not None else 0))
        return FakeTensor("arange", (length,))

    def forbidden(name):
        def fail(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"{name} should not be used in forced plain-RoPE")

        return fail

    fake_mx.arange = fake_arange
    fake_mx.expand_dims = forbidden("expand_dims")
    fake_mx.tile = forbidden("tile")
    fake_mx.split = lambda value, _sections, axis=-1: (
        FakeTensor(f"{value.label}.q", value.shape),
        FakeTensor(f"{value.label}.gate", value.shape),
    )
    fake_mx.concatenate = lambda values, axis=0: FakeTensor(
        "concat",
        getattr(values[0], "shape", (1,)),
    )
    fake_mx.cos = lambda value: FakeTensor(f"cos:{value.label}", value.shape)
    fake_mx.sin = lambda value: FakeTensor(f"sin:{value.label}", value.shape)
    fake_mx.sigmoid = lambda value: FakeTensor(f"sigmoid:{value.label}", value.shape)
    _install_native_mtp_fake_mlx(monkeypatch, fake_mx)

    import worker.runtime.native_mtp.qwen35_vlm_runtime as qwen35_runtime

    monkeypatch.setattr(qwen35_runtime, "mx", fake_mx)

    class FakeAttention:
        num_attention_heads = 1
        num_key_value_heads = 1
        scale = 1.0

        def __init__(self) -> None:
            self.rotary_emb = SimpleNamespace(inv_freq=FakeTensor("inv_freq", (1,)))

        def q_proj(self, x):
            return FakeTensor("q_proj", (x.shape[0], x.shape[1], 4))

        def k_proj(self, x):
            return FakeTensor("k_proj", (x.shape[0], x.shape[1], 2))

        def v_proj(self, x):
            return FakeTensor("v_proj", (x.shape[0], x.shape[1], 2))

        def q_norm(self, value):
            return value

        def k_norm(self, value):
            return value

        def o_proj(self, value):
            return ("out", value)

    fake_language_module = SimpleNamespace(
        Qwen3_5Attention=FakeAttention,
        scaled_dot_product_attention=lambda *_args, **_kwargs: FakeTensor(
            "attn_out",
            (1, 1, 2, 2),
        ),
        apply_multimodal_rotary_pos_emb=forbidden("mrope"),
    )

    qwen35_runtime._patch_attention_plain_rope(fake_language_module)

    with qwen35_runtime._ForceTextOnlyRoPE():
        cache = SimpleNamespace(
            offset=7,
            update_and_fetch=lambda keys, values: (keys, values),
        )
        assert FakeAttention()(
            FakeTensor("x", (1, 2, 8)),
            cache=cache,
            position_ids=None,
        )[0] == "out"

    assert "expand_dims" not in calls
    assert "tile" not in calls
    assert "mrope" not in calls


def test_native_mtp_qwen35_vlm_return_hidden_uses_gdn_sink_rollback_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mx = ModuleType("mlx.core")
    fake_mx.concatenate = lambda values, axis=0: ("concat", axis, values)
    fake_mx.zeros = lambda shape, dtype=None: ("zeros", shape, dtype)
    fake_mx.where = lambda mask, value, other: ("where", mask, value, other)
    fake_mx.split = lambda value, indices, axis: ("q", "k", "v")
    fake_mx.fast = SimpleNamespace(rms_norm=lambda value, _weight, _eps: ("rms", value))
    fake_mx.distributed = SimpleNamespace(all_sum=lambda value, group=None: ("all_sum", value, group))

    fake_nn = ModuleType("mlx.nn")
    fake_nn.Module = object
    fake_nn.RMSNorm = lambda *_args, **_kwargs: object()
    fake_nn.Linear = lambda *_args, **_kwargs: object()
    fake_nn.silu = lambda value: ("silu", value)
    fake_layers_distributed = ModuleType("mlx.nn.layers.distributed")
    fake_layers_distributed.sum_gradients = lambda _group: (lambda value: value)
    fake_gated_delta = ModuleType("mlx_lm.models.gated_delta")
    fake_gated_delta.gated_delta_update = lambda *args, **_kwargs: (("gdn-out", args), "ssm-final")
    fake_cache = ModuleType("mlx_lm.models.cache")
    fake_cache.KVCache = type("KVCache", (), {})
    _install_native_mtp_fake_mlx(monkeypatch, fake_mx, fake_nn)
    monkeypatch.setitem(sys.modules, "mlx.nn.layers.distributed", fake_layers_distributed)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.gated_delta", fake_gated_delta)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", fake_cache)

    import worker.runtime.native_mtp.qwen35_vlm_runtime as qwen35_runtime

    class FakeConfigModule:
        class TextConfig:
            @classmethod
            def from_dict(cls, params):
                return SimpleNamespace(**params)

    class FakeGatedDeltaNet:
        sharding_group = None
        conv_kernel_size = 3
        conv_dim = 4
        num_k_heads = 1
        num_v_heads = 1
        head_k_dim = 1
        head_v_dim = 1
        key_dim = 1
        A_log = "A"
        dt_bias = "dt"
        training = False

        def in_proj_qkv(self, inputs):
            return FakeTensor("qkv", (1, 2, 3))

        def in_proj_z(self, inputs):
            return FakeTensor("z", (1, 2, 1))

        def in_proj_b(self, inputs):
            return FakeTensor("b", (1, 2, 1))

        def in_proj_a(self, inputs):
            return FakeTensor("a", (1, 2, 1))

        def conv1d(self, value):
            return value

        def norm(self, out, z):
            return ("norm", out, z)

        def out_proj(self, value):
            return ("out", value)

    class FakeLayer:
        is_linear = True

        def __init__(self) -> None:
            self.linear_attn = FakeGatedDeltaNet()

        def __call__(self, x, mask=None, cache=None, position_ids=None, gdn_sink=None):
            return x

    model_calls: list[dict[str, object]] = []

    class FakeInnerModel:
        fa_idx = 0
        ssm_idx = 0

        def __init__(self) -> None:
            self.layers = [FakeLayer()]

        def __call__(
            self,
            inputs,
            cache=None,
            inputs_embeds=None,
            position_ids=None,
            capture_layer_ids=None,
            hidden_sink=None,
            gdn_sink=None,
            n_confirmed=0,
            return_pre_norm=False,
        ):
            _ = return_pre_norm
            model_calls.append(
                {
                    "capture_layer_ids": capture_layer_ids,
                    "hidden_sink": hidden_sink,
                    "gdn_sink": gdn_sink,
                    "n_confirmed": n_confirmed,
                }
            )
            if hidden_sink is not None:
                hidden_sink.append("heavy-hidden")
            if gdn_sink is not None:
                gdn_sink.append("heavy-gdn")
            return "normed"

        def norm(self, hidden):
            return ("norm", hidden)

    class FakeLanguageModel:
        def __init__(self, args=None, config=None) -> None:
            _ = config
            self._init_args = args or SimpleNamespace(mtp_num_hidden_layers=0)
            self.model = FakeInnerModel()
            self.args = SimpleNamespace(tie_word_embeddings=False, mtp_num_hidden_layers=0)
            self.lm_head = lambda value: ("logits", value)

    def original_language_call(
        self,
        inputs,
        inputs_embeds=None,
        mask=None,
        cache=None,
        **kwargs,
    ):
        hidden_sink = [] if kwargs.get("capture_layer_ids") is not None else None
        gdn_sink = [] if kwargs.get("capture_layer_ids") is not None else None
        out = self.model(
            inputs,
            cache=cache,
            inputs_embeds=inputs_embeds,
            position_ids=kwargs.get("position_ids"),
            capture_layer_ids=kwargs.get("capture_layer_ids"),
            hidden_sink=hidden_sink,
            gdn_sink=gdn_sink,
        )
        return SimpleNamespace(
            logits=("logits", out),
            hidden_states=hidden_sink,
            gdn_states=gdn_sink,
        )

    FakeLanguageModel.__call__ = original_language_call
    fake_language_module = SimpleNamespace(
        Qwen3_5GatedDeltaNet=FakeGatedDeltaNet,
        Qwen3_5DecoderLayer=type("Qwen3_5DecoderLayer", (), {}),
        Qwen3_5Model=type("Qwen3_5Model", (), {}),
        Qwen3_5Attention=type("Qwen3_5Attention", (), {}),
        Qwen3_5MLP=lambda *_args, **_kwargs: object(),
        create_attention_mask=lambda *_args, **_kwargs: "mask",
        LanguageModel=FakeLanguageModel,
    )
    fake_qwen_pkg = ModuleType("mlx_vlm.models.qwen3_5")
    fake_qwen_pkg.__path__ = []
    fake_qwen_pkg.config = FakeConfigModule
    fake_qwen_pkg.language = fake_language_module
    monkeypatch.setitem(sys.modules, "mlx_vlm.models.qwen3_5", fake_qwen_pkg)
    monkeypatch.setitem(sys.modules, "mlx_vlm.models.qwen3_5.config", FakeConfigModule)
    monkeypatch.setitem(sys.modules, "mlx_vlm.models.qwen3_5.language", fake_language_module)
    monkeypatch.setattr(qwen35_runtime, "_APPLIED", False)

    assert qwen35_runtime.apply() is True

    cache = [SimpleNamespace(offset=0)]
    model = FakeLanguageModel(SimpleNamespace(mtp_num_hidden_layers=0))
    result = model([101, 102], cache=cache, return_hidden=True, n_confirmed=1)

    assert result == (("logits", ("norm", "normed")), "normed", ["heavy-gdn"])
    assert model_calls == [
        {
            "capture_layer_ids": None,
            "hidden_sink": None,
            "gdn_sink": ["heavy-gdn"],
            "n_confirmed": 1,
        }
    ]


def test_native_mtp_qwen35_vlm_model_forwards_n_confirmed_to_linear_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mx = ModuleType("mlx.core")
    fake_mx.concatenate = lambda values, axis=0: ("concat", axis, values)
    fake_mx.zeros = lambda shape, dtype=None: ("zeros", shape, dtype)
    fake_mx.where = lambda mask, value, other: ("where", mask, value, other)
    fake_mx.split = lambda value, indices, axis: ("q", "k", "v")
    fake_mx.fast = SimpleNamespace(rms_norm=lambda value, _weight, _eps: ("rms", value))
    fake_mx.distributed = SimpleNamespace(
        all_sum=lambda value, group=None: ("all_sum", value, group)
    )
    fake_nn = ModuleType("mlx.nn")
    fake_nn.Module = object
    fake_nn.RMSNorm = lambda *_args, **_kwargs: object()
    fake_nn.Linear = lambda *_args, **_kwargs: object()
    fake_nn.silu = lambda value: ("silu", value)
    fake_layers_distributed = ModuleType("mlx.nn.layers.distributed")
    fake_layers_distributed.sum_gradients = lambda _group: (lambda value: value)
    fake_gated_delta = ModuleType("mlx_lm.models.gated_delta")
    fake_gated_delta.gated_delta_update = lambda *args, **_kwargs: (
        ("gdn-out", args),
        "ssm-final",
    )
    fake_cache = ModuleType("mlx_lm.models.cache")
    fake_cache.KVCache = type("KVCache", (), {})
    _install_native_mtp_fake_mlx(monkeypatch, fake_mx, fake_nn)
    monkeypatch.setitem(sys.modules, "mlx.nn.layers.distributed", fake_layers_distributed)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.gated_delta", fake_gated_delta)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", fake_cache)

    import worker.runtime.native_mtp.qwen35_vlm_runtime as qwen35_runtime

    calls: list[dict[str, object]] = []

    class FakeConfigModule:
        class TextConfig:
            @classmethod
            def from_dict(cls, params):
                return SimpleNamespace(**params)

    class FakeLinearAttn:
        def __call__(self, value, mask=None, cache=None, n_confirmed=0, gdn_sink=None):
            calls.append(
                {
                    "value": value,
                    "mask": mask,
                    "cache": cache,
                    "n_confirmed": n_confirmed,
                    "gdn_sink": gdn_sink,
                }
            )
            cache.rollback_state = ("conv-confirmed", "ssm-confirmed")
            return "linear-out"

    class FakeDecoderLayer:
        is_linear = True

        def __init__(self) -> None:
            self.linear_attn = FakeLinearAttn()
            self.input_layernorm = lambda value: ("ln", value)
            self.post_attention_layernorm = lambda value: ("post-ln", value)
            self.mlp = lambda value: ("mlp", value)

    class FakeModel:
        fa_idx = 0
        ssm_idx = 0

        def __init__(self) -> None:
            self.layers = [FakeDecoderLayer()]
            self.embed_tokens = lambda inputs: f"emb:{inputs!r}"
            self.norm = lambda hidden: ("norm", hidden)

    fake_language_module = SimpleNamespace(
        Qwen3_5GatedDeltaNet=type("Qwen3_5GatedDeltaNet", (), {}),
        Qwen3_5DecoderLayer=FakeDecoderLayer,
        Qwen3_5Model=FakeModel,
        Qwen3_5Attention=type("Qwen3_5Attention", (), {}),
        Qwen3_5MLP=lambda *_args, **_kwargs: object(),
        create_attention_mask=lambda *_args, **_kwargs: "fa-mask",
        create_ssm_mask=lambda *_args, **_kwargs: "ssm-mask",
        LanguageModel=type(
            "LanguageModel",
            (),
            {"__init__": lambda self, args, config=None: None, "__call__": lambda self: None},
        ),
    )
    fake_qwen_pkg = ModuleType("mlx_vlm.models.qwen3_5")
    fake_qwen_pkg.__path__ = []
    fake_qwen_pkg.config = FakeConfigModule
    fake_qwen_pkg.language = fake_language_module
    monkeypatch.setitem(sys.modules, "mlx_vlm.models.qwen3_5", fake_qwen_pkg)
    monkeypatch.setitem(sys.modules, "mlx_vlm.models.qwen3_5.config", FakeConfigModule)
    monkeypatch.setitem(sys.modules, "mlx_vlm.models.qwen3_5.language", fake_language_module)
    monkeypatch.setattr(qwen35_runtime, "_APPLIED", False)

    assert qwen35_runtime.apply() is True

    cache = SimpleNamespace(offset=0, rollback_state=None)
    model = FakeModel()
    model.layers[0].mlp = lambda value: f"mlp:{value}"
    model.layers[0].post_attention_layernorm = lambda value: f"post-ln:{value}"
    model.layers[0].input_layernorm = lambda value: f"ln:{value}"
    hidden = model(
        [101, 102],
        cache=[cache],
        n_confirmed=1,
        return_pre_norm=True,
    )

    assert calls == [
        {
            "value": "ln:emb:[101, 102]",
            "mask": "ssm-mask",
            "cache": cache,
            "n_confirmed": 1,
            "gdn_sink": None,
        }
    ]
    assert hidden == "emb:[101, 102]linear-outmlp:post-ln:emb:[101, 102]linear-out"
    assert cache.rollback_state == ("conv-confirmed", "ssm-confirmed")


def test_text_only_batch_generator_forwards_native_mtp_stats_to_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGenerationResponse:
        uid = 0
        token = 11
        logprobs = None
        finish_reason = "length"
        speculative_acceptance_rate = 0.75
        speculative_rollback_rate = 0.25
        speculative_accepted_tokens = 3
        speculative_rejected_tokens = 1
        speculative_num_draft_tokens = 1
        speculative_draft_model_configured = True

    class FakeBatchGenerator:
        def __init__(self, **_kwargs) -> None:
            self.next_calls = 0

        def insert(self, *_args, **_kwargs):
            return [0]

        def next(self):
            self.next_calls += 1
            return [], [FakeGenerationResponse()]

    class FakeDetokenizer:
        last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = f"tok-{token}"

        def finalize(self) -> None:
            self.last_segment = ""

    fake_generate = ModuleType("mlx_lm.generate")
    fake_generate.BatchGenerator = lambda *_args, **kwargs: FakeBatchGenerator(**kwargs)
    fake_sample_utils = ModuleType("mlx_lm.sample_utils")
    fake_sample_utils.make_sampler = lambda **_kwargs: object()
    monkeypatch.setitem(sys.modules, "mlx_lm.generate", fake_generate)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", fake_sample_utils)

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
    )
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=3,
    )

    events = list(scheduler.submit(request))
    scheduler.close()

    assert len(events) == 1
    assert events[0].text == "tok-11"
    assert events[0].speculative_acceptance_rate == 0.75
    assert events[0].speculative_rollback_rate == 0.25
    assert events[0].speculative_accepted_tokens == 3
    assert events[0].speculative_rejected_tokens == 1
    assert events[0].speculative_num_draft_tokens == 1
    assert events[0].speculative_draft_model_configured is True


def test_mlx_vlm_runtime_text_only_batch_generator_requires_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    batch_scheduler_calls = 0
    generate_step_calls = 0

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.text = ""
            self.last_segment = ""

        def __copy__(self):
            return FakeDetokenizer()

        def reset(self) -> None:
            self.text = ""
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = {101: "step"}.get(token, "")
            self.text += self.last_segment

        def finalize(self) -> None:
            self.last_segment = ""

    class FakeProcessor:
        chat_template = "{{ prompt }}"
        eos_token = "<eos>"
        pad_token = None

        def __init__(self) -> None:
            self.detokenizer = FakeDetokenizer()

        def __call__(self, prompts, **kwargs):
            import mlx.core as mx

            _ = prompts
            _ = kwargs
            return SimpleNamespace(
                input_ids=mx.array([[1, 2, 3]]),
                attention_mask=mx.array([[1, 1, 1]]),
            )

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), FakeProcessor()

    def fake_generate_step(*_args, **_kwargs):
        nonlocal generate_step_calls
        generate_step_calls += 1
        yield 101, [-0.1]

    class FakeBatchScheduler:
        def submit(self, request):
            request.detokenizer.add_token(202)
            yield mlx_vlm_runtime_module.RuntimeTokenEvent(
                text="batch",
                raw_text="batch",
                token_ids=(202,),
                prompt_tokens=request.prompt_tokens,
                completion_tokens=1,
                finish_reason="stop",
            )

    def fake_batch_scheduler(_loaded_model, **_kwargs):
        nonlocal batch_scheduler_calls
        batch_scheduler_calls += 1
        return FakeBatchScheduler()

    class FakeInputIDs:
        def __getitem__(self, _index):
            return self

        def tolist(self):
            return [1, 2, 3]

    def fake_prepare_inputs(*_args, **_kwargs):
        return {"input_ids": FakeInputIDs()}

    fake_mlx_vlm_module = ModuleType("mlx_vlm")
    fake_mlx_vlm_utils_module = ModuleType("mlx_vlm.utils")
    fake_mlx_vlm_utils_module.prepare_inputs = fake_prepare_inputs
    monkeypatch.setitem(sys.modules, "mlx_vlm", fake_mlx_vlm_module)
    monkeypatch.setitem(sys.modules, "mlx_vlm.utils", fake_mlx_vlm_utils_module)

    monkeypatch.setattr(mlx_vlm_runtime_module, "_installed_package_version", lambda name: f"{name}-version")
    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda *_args, **_kwargs: "formatted::prompt",
            generate_step_fn=fake_generate_step,
        )
    )
    monkeypatch.setattr(runtime, "_text_only_batch_generator_scheduler", fake_batch_scheduler)
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
    )

    assert (
        runtime._can_use_text_only_batch_generator(
            loaded_model=loaded_model,
            prepared_request=prepared,
            sampling=common_pb2.SamplingConfig(max_output_tokens=8),
            execution_ext=None,
        )
        is False
    )
    assert runtime._text_only_batch_generator_unsupported_reason(
        loaded_model=loaded_model,
        prepared_request=prepared,
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        execution_ext=None,
    ) == "text_only_batch_generator_not_enabled"
    assert (
        runtime._can_use_text_only_batch_generator(
            loaded_model=loaded_model,
            prepared_request=prepared,
            sampling=common_pb2.SamplingConfig(max_output_tokens=8, top_k=1),
            execution_ext={_TEXT_ONLY_BATCH_GENERATOR_EXT_KEY: "true"},
        )
        is True
    )
    opt_in_events = list(
        runtime._generate_text_only_batch_generator_events(
            loaded_model=loaded_model,
            prepared_request=prepared,
            sampling=common_pb2.SamplingConfig(max_output_tokens=8),
            cancel_event=Event(),
            prompt_tokens=3,
        )
    )

    assert [event.text for event in opt_in_events] == ["batch"]
    assert generate_step_calls == 0
    assert batch_scheduler_calls == 1
    assert runtime.last_probe_snapshot().multimodal_decode_mode == "text_only_batch_generator"
    assert runtime.last_probe_snapshot().text_batch_generator_submitted_request_count == 0


def test_text_only_batch_generator_prefers_tokenizer_chat_template_prompt() -> None:
    class FakeTokenizer:
        def __init__(self) -> None:
            self.messages = None

        def apply_chat_template(self, messages, **kwargs):
            self.messages = messages
            assert kwargs == {"tokenize": False, "add_generation_prompt": True}
            return "tokenizer::prompt"

    tokenizer = FakeTokenizer()
    prepared = PreparedVisionRequest(
        prompt_text="flattened prompt",
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        chat_messages=({"role": "user", "content": "Say hello."},),
    )

    prompt = MLXVLMRuntime._text_only_tokenizer_prompt(
        SimpleNamespace(tokenizer=tokenizer),
        prepared,
    )

    assert prompt == "tokenizer::prompt"
    assert tokenizer.messages == [{"role": "user", "content": "Say hello."}]


def test_gemma4_text_only_streaming_decoder_uses_tokenizer_decode() -> None:
    original_tokenizer_streaming_detokenizer = mlx_vlm_runtime_module._tokenizer_streaming_detokenizer

    class FakeTokenizer:
        chat_template = "{{ prompt }}"

        def __init__(self) -> None:
            self.detokenizer = None

        def decode(self, tokens):
            return {
                (101,): "1",
                (102,): ".",
                (103,): " The",
                (201,): "<|channel>",
                (202,): "thought\nhidden",
                (203,): "<channel|>",
            }.get(tuple(tokens), "")

    processor = SimpleNamespace(
        tokenizer=FakeTokenizer(),
        detokenizer=SimpleNamespace(),
    )
    loaded_model = {
        "processor": processor,
        "model": SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
        "metadata": {"vision_family_id": "gemma4-v1"},
        }

    try:
        mlx_vlm_runtime_module._tokenizer_streaming_detokenizer = lambda _tokenizer: None
        decoder = _text_only_streaming_decoder(processor, loaded_model)

        assert decoder is not None
        decoder.add_token(101)
        assert decoder.last_segment == "1"
        decoder.add_token(102)
        assert decoder.last_segment == "."
        decoder.add_token(103)
        assert decoder.last_segment == " The"
        decoder.add_token(201)
        assert decoder.last_segment == ""
        decoder.add_token(202)
        assert decoder.last_segment == "<think>\nhidden"
        decoder.add_token(203)
        assert decoder.last_segment == "</think>\n"
    finally:
        mlx_vlm_runtime_module._tokenizer_streaming_detokenizer = original_tokenizer_streaming_detokenizer


def test_mlx_vlm_runtime_reports_text_only_batch_generator_rejection_reason() -> None:
    runtime = MLXVLMRuntime()
    detokenizer = SimpleNamespace(
        reset=lambda: None,
        add_token=lambda _token: None,
        finalize=lambda: None,
    )
    loaded_model = {
        "processor": SimpleNamespace(detokenizer=detokenizer),
        "metadata": {},
    }
    prepared = PreparedVisionRequest(
        prompt_text="Say hello.",
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
    )

    assert runtime._text_only_batch_generator_unsupported_reason(
        loaded_model=loaded_model,
        prepared_request=prepared,
        sampling=common_pb2.SamplingConfig(temperature=0.7, top_p=0.95, top_k=40),
        execution_ext={_TEXT_ONLY_BATCH_GENERATOR_EXT_KEY: "true"},
    ) == "non_greedy_sampling"


def test_text_only_batch_generator_filters_special_stop_tokens() -> None:
    class FakeDetokenizer:
        def __init__(self) -> None:
            self.text = ""
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = {11: "Hello", 106: "<turn|>"}.get(token, "")
            self.text += self.last_segment

        def finalize(self) -> None:
            self.last_segment = ""

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1, all_special_ids=[1, 106]),
        executor=None,
        max_batch_size=1,
    )
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1, 106},
        cancel_event=Event(),
        prompt_tokens=1,
    )
    request.uid = 7
    scheduler._active_by_uid[7] = request
    scheduler._stats.active_batch_size = 1

    scheduler._emit_response(request, SimpleNamespace(token=11))
    scheduler._emit_response(request, SimpleNamespace(token=106))

    stats = scheduler.stats_snapshot()
    first = request.queue.get_nowait()
    done = request.queue.get_nowait()
    assert first.text == "Hello"
    assert done is _TEXT_ONLY_BATCH_DONE
    assert request.detokenizer.text == "Hello"
    assert stats.generated_token_count == 1
    assert stats.completed_request_count == 1
    assert stats.active_batch_size == 0


def test_text_only_batch_generator_records_scheduler_timings() -> None:
    class FakeResponse:
        def __init__(self, uid: int, token: int, finish_reason: str = "") -> None:
            self.uid = uid
            self.token = token
            self.finish_reason = finish_reason

    class FakeBatchGenerator:
        def __init__(self) -> None:
            self.next_calls = 0

        def insert(self, requests, *, max_tokens, caches=None, all_tokens=None):
            _ = requests
            _ = max_tokens
            _ = caches
            _ = all_tokens
            return [7]

        def next(self):
            self.next_calls += 1
            return [], [FakeResponse(uid=7, token=11, finish_reason="stop")]

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = f"tok-{token}"

        def finalize(self) -> None:
            self.last_segment = ""

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
    )
    scheduler._adapter._melix_batch_generator = FakeBatchGenerator()
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=3,
    )

    events = list(scheduler.submit(request))
    stats = scheduler.stats_snapshot()
    scheduler.close()

    assert [event.text for event in events] == ["tok-11"]
    assert stats.submitted_request_count == 1
    assert stats.completed_request_count == 1
    assert stats.step_count == 1
    assert stats.generated_token_count == 1
    assert stats.generated_response_count == 1
    assert stats.peak_active_batch_size == 1
    assert stats.active_batch_size == 0
    assert stats.queue_wait_ms_total >= 0
    assert stats.insert_ms_total >= 0
    assert stats.executor_step_ms_total >= 0
    assert stats.next_ms_total >= 0
    assert stats.emit_ms_total >= 0
    assert stats.first_response_ms_total >= stats.prepare_ms_total
    assert stats.first_visible_ms_total >= stats.first_response_ms_total
    assert stats.first_visible_token_index_total == 1
    assert stats.first_empty_segment_count == 0


def test_text_only_batch_generator_records_native_mtp_timing_deltas() -> None:
    class FakeResponse:
        def __init__(
            self,
            *,
            uid: int,
            token: int,
            finish_reason: str = "",
            speculative_cycle_count: int,
            speculative_accepted_tokens: int,
            speculative_rejected_tokens: int,
            speculative_backbone_ms: float,
            speculative_mtp_head_ms: float,
            speculative_sample_ms: float,
            speculative_cache_ops_ms: float,
        ) -> None:
            self.uid = uid
            self.token = token
            self.finish_reason = finish_reason
            self.speculative_cycle_count = speculative_cycle_count
            self.speculative_accepted_tokens = speculative_accepted_tokens
            self.speculative_rejected_tokens = speculative_rejected_tokens
            self.speculative_backbone_ms = speculative_backbone_ms
            self.speculative_mtp_head_ms = speculative_mtp_head_ms
            self.speculative_sample_ms = speculative_sample_ms
            self.speculative_cache_ops_ms = speculative_cache_ops_ms

    class FakeBatchGenerator:
        def __init__(self) -> None:
            self.next_calls = 0

        def insert(self, requests, *, max_tokens, caches=None, all_tokens=None):
            _ = requests
            _ = max_tokens
            _ = caches
            _ = all_tokens
            return [7]

        def next(self):
            self.next_calls += 1
            if self.next_calls == 1:
                return [], [
                    FakeResponse(
                        uid=7,
                        token=11,
                        speculative_cycle_count=1,
                        speculative_accepted_tokens=1,
                        speculative_rejected_tokens=0,
                        speculative_backbone_ms=100.0,
                        speculative_mtp_head_ms=10.0,
                        speculative_sample_ms=2.0,
                        speculative_cache_ops_ms=3.0,
                    )
                ]
            return [], [
                FakeResponse(
                    uid=7,
                    token=12,
                    finish_reason="length",
                    speculative_cycle_count=2,
                    speculative_accepted_tokens=1,
                    speculative_rejected_tokens=1,
                    speculative_backbone_ms=220.0,
                    speculative_mtp_head_ms=25.0,
                    speculative_sample_ms=5.0,
                    speculative_cache_ops_ms=8.0,
                )
            ]

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = f"tok-{token}"

        def finalize(self) -> None:
            self.last_segment = ""

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
    )
    scheduler._adapter._melix_batch_generator = FakeBatchGenerator()
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=3,
    )

    events = list(scheduler.submit(request))
    stats = scheduler.stats_snapshot()
    probe_kwargs = _text_batch_generator_probe_kwargs(stats)
    scheduler.close()

    assert [event.text for event in events] == ["tok-11", "tok-12"]
    assert stats.speculative_cycle_count_total == 2
    assert stats.speculative_accepted_count_total == 1
    assert stats.speculative_rejected_count_total == 1
    assert stats.speculative_backbone_ms_total == 220.0
    assert stats.speculative_mtp_head_ms_total == 25.0
    assert stats.speculative_sample_ms_total == 5.0
    assert stats.speculative_cache_ops_ms_total == 8.0
    assert probe_kwargs["text_batch_generator_speculative_cycle_count_total"] == 2
    assert probe_kwargs["text_batch_generator_speculative_backbone_ms_total"] == 220.0
    assert (
        mlx_vlm_runtime_module.VisionProbeSnapshot(
            0.0,
            0,
            0,
            0.0,
            **probe_kwargs,
        ).text_batch_generator_speculative_cycle_count_total
        == 2
    )


def test_text_only_batch_generator_uses_single_executor_handoff_per_tick() -> None:
    class FakeResponse:
        uid = 7
        token = 11
        finish_reason = "stop"

    class FakeBatchGenerator:
        def insert(self, requests, *, max_tokens, caches=None, all_tokens=None):
            _ = requests
            _ = max_tokens
            _ = caches
            _ = all_tokens
            return [7]

        def next(self):
            return [], [FakeResponse()]

    class FakeDetokenizer:
        last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = f"tok-{token}"

        def finalize(self) -> None:
            self.last_segment = ""

    class FakeExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, callback):
            self.calls += 1
            return callback()

    executor = FakeExecutor()
    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=executor,
        max_batch_size=1,
        wait_ms=0.0,
    )
    scheduler._adapter._melix_batch_generator = FakeBatchGenerator()
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=3,
    )

    events = list(scheduler.submit(request))
    scheduler.close()

    assert [event.text for event in events] == ["tok-11"]
    assert executor.calls == 1


def test_text_only_batch_generator_records_empty_segments_before_visible_text() -> None:
    class FakeDetokenizer:
        def __init__(self) -> None:
            self.last_segment = ""

        def add_token(self, token: int) -> None:
            self.last_segment = "" if token == 11 else "visible"

        def finalize(self) -> None:
            self.last_segment = ""

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
    )
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2, 3],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=3,
        started_at=time.perf_counter(),
        prepare_ms=1.5,
    )
    request.uid = 7
    scheduler._active_by_uid[7] = request
    scheduler._stats.submitted_request_count = 1
    scheduler._stats.prepare_ms_total = request.prepare_ms

    scheduler._emit_response(request, SimpleNamespace(uid=7, token=11))
    scheduler._emit_response(request, SimpleNamespace(uid=7, token=12))

    stats = scheduler.stats_snapshot()
    first = request.queue.get_nowait()
    scheduler.close()

    assert first.text == "visible"
    assert stats.prepare_ms_total == 1.5
    assert stats.first_response_ms_total >= 0
    assert stats.first_visible_ms_total >= stats.first_response_ms_total
    assert stats.first_visible_token_index_total == 2
    assert stats.first_empty_segment_count == 1


def test_text_only_batch_generator_insert_failure_notifies_popped_pending_request() -> None:
    class FakeBatchGenerator:
        def insert(self, requests, *, max_tokens, caches=None, all_tokens=None):
            _ = requests
            _ = max_tokens
            _ = caches
            _ = all_tokens
            raise RuntimeError("insert failed")

    class FakeDetokenizer:
        last_segment = ""

        def add_token(self, token: int) -> None:
            _ = token

        def finalize(self) -> None:
            self.last_segment = ""

    scheduler = _TextOnlyBatchGeneratorScheduler(
        model=SimpleNamespace(),
        adapter=SimpleNamespace(),
        processor=SimpleNamespace(eos_token_id=1),
        executor=None,
        max_batch_size=1,
        wait_ms=0.0,
    )
    scheduler._adapter._melix_batch_generator = FakeBatchGenerator()
    request = _TextOnlyBatchRequest(
        loaded_model={},
        input_ids=[1, 2],
        max_tokens=8,
        detokenizer=FakeDetokenizer(),
        stop_token_ids={1},
        cancel_event=Event(),
        prompt_tokens=2,
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        list(scheduler.submit(request))

    stats = scheduler.stats_snapshot()
    scheduler.close()
    assert stats.failed_request_count == 1


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
    runtime._record_fast_path_probe(loaded_model, prepared)
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


def test_mlx_vlm_runtime_prompt_text_and_media_presence_detects_media() -> None:
    image_prompt, has_image = MLXVLMRuntime._prompt_text_and_media_presence(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text=" describe "),
                    common_pb2.MessagePart(image_uri="file:///tmp/image.png"),
                ],
            )
        ]
    )
    video_prompt, has_video = MLXVLMRuntime._prompt_text_and_media_presence(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="watch"),
                    common_pb2.MessagePart(video_bytes=b"video"),
                ],
            )
        ]
    )

    assert image_prompt == "describe"
    assert has_image is True
    assert video_prompt == "watch"
    assert has_video is True


def test_mlx_vlm_runtime_prompt_only_request_falls_back_to_message_text() -> None:
    class IdentityFamilyConfig:
        def shape_request(self, prepared: PreparedVisionRequest) -> PreparedVisionRequest:
            return prepared

    prepared = MLXVLMRuntime._prompt_only_request(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="fallback prompt")])],
        family_config=IdentityFamilyConfig(),
        started_at=time.perf_counter(),
    )

    assert prepared.prompt_text == "fallback prompt"
    assert prepared.prompt_hash_hex == prepared.multimodal_hash_hex


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


def test_mlx_vlm_runtime_does_not_treat_variadic_kwargs_as_video_support(
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

    def fake_stream_generate(*args, **kwargs):
        _ = args
        stream_calls.append(dict(kwargs))
        yield SimpleNamespace(text="variadic fallback summary", generation_tokens=1)

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

    assert [event.text for event in events] == ["variadic fallback summary"]
    assert "video" not in stream_calls[0]
    assert stream_calls[0]["image"] is None
    assert runtime.last_probe_snapshot().multimodal_fallback_reason == "backend_video_kwarg_unsupported"
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
        (
            "language_model.model.layers.0.self_attn.q_proj.weight",
            "language_model.model.per_layer_model_projection.weight",
        )
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
    assert _gemma4_multimodal_weight_presence(
        {
            "embed_vision.proj.weight": object(),
            "embed_audio.proj.weight": object(),
        }.keys()
    ) == (True, True)
    assert _gemma4_multimodal_weight_presence(
        {
            "vision_tower.proj.weight": object(),
        }.keys()
    ) == (True, False)


def test_gemma4_scaled_linear_patch_accepts_newer_language_api(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mlx_core(monkeypatch)
    modules = _install_fake_mlx_vlm_modules(monkeypatch)

    class FakeScaledLinear:
        pass

    monkeypatch.setattr(mlx_vlm_runtime_module, "nn", None, raising=False)
    monkeypatch.setattr(
        modules["mlx_vlm.models.gemma4.language"],
        "ScaledLinear",
        FakeScaledLinear,
        raising=False,
    )

    _patch_gemma4_scaled_linear_quantization()

    assert hasattr(FakeScaledLinear, "to_quantized")


def test_callables_and_text_backed_shims_expose_upstream_compatible_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_vlm_modules(monkeypatch)
    import mlx.core as mx

    class FakeEmbedding:
        def __call__(self, input_ids):
            return mx.ones((*input_ids.shape, 2))

    class FakeInnerModel:
        embed_tokens = FakeEmbedding()
        embed_scale = 2.0
        hidden_size_per_layer_input = 1

        def get_per_layer_inputs(self, input_ids):
            return mx.ones((*input_ids.shape, 1, 1))

    language_model = SimpleNamespace(
        config=SimpleNamespace(model_type="gemma4_text", image_token_id=258880),
        model=FakeInnerModel(),
    )
    model = _Gemma4TextBackedModelShim(language_model)
    features = model.get_input_embeddings(mx.array([[1, 2]]), pixel_values=object(), ignored=True)

    assert model.language_model is language_model
    assert model.config.model_type == "gemma4"
    assert model.config.image_token_id == 258880
    assert model.config.audio_token_id == -2
    assert tuple(features.inputs_embeds.shape) == (1, 2, 2)
    assert tuple(features.per_layer_inputs.shape) == (1, 2, 1, 1)

    tokenizer_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeTokenizer:
        def __call__(self, *args, **kwargs):
            tokenizer_calls.append((args, kwargs))
            return "tokens"

    processor = _CallableTokenizerProcessor(
        SimpleNamespace(_tokenizer=FakeTokenizer(), detokenizer="detok")
    )

    assert processor.detokenizer == "detok"
    assert processor("prompt", padding=True) == "tokens"
    assert tokenizer_calls == [(("prompt",), {"padding": True})]


def test_callable_declares_kwarg_requires_explicit_parameter() -> None:
    def explicit(*, draft_model):
        _ = draft_model

    def variadic(**kwargs):
        _ = kwargs

    assert runtime_utils.callable_declares_kwarg(explicit, "draft_model") is True
    assert runtime_utils.callable_declares_kwarg(variadic, "draft_model") is False
    assert runtime_utils.callable_declares_kwarg(object(), "draft_model") is False
    assert runtime_utils.callable_accepts_kwarg(variadic, "draft_model") is True


def test_auto_mlx_vlm_backend_mtp_detection_requires_declared_draft_kwargs() -> None:
    drafter_calls: list[dict[str, object]] = []

    def fake_load_drafter(*args, **kwargs):
        drafter_calls.append({"args": args, "kwargs": kwargs})
        return {"draft_model_id": args[0]}

    backend = AutoMLXVLMBackend(
        load_fn=lambda model_path, revision="main": (object(), object()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        apply_chat_template_fn=lambda *args, **kwargs: "",
        batch_generate_fn=lambda *args, **kwargs: [],
        generate_step_fn=lambda *args, **kwargs: iter(()),
        load_drafter_fn=fake_load_drafter,
    )

    assert backend.supports_mtp_speculative() is False
    assert backend.load_drafter("draft-model", kind="mtp") == {"draft_model_id": "draft-model"}
    assert drafter_calls == [{"args": ("draft-model",), "kwargs": {}}]


def test_mlx_peak_memory_prefers_current_api() -> None:
    calls: list[str] = []

    current_api = SimpleNamespace(
        get_peak_memory=lambda: calls.append("current") or 2_000_000_000,
        metal=SimpleNamespace(get_peak_memory=lambda: calls.append("metal") or 1_000_000_000),
    )
    legacy_api = SimpleNamespace(
        metal=SimpleNamespace(get_peak_memory=lambda: calls.append("legacy-metal") or 3_000_000_000)
    )

    assert _mlx_peak_memory_gb(current_api) == 2.0
    assert _mlx_peak_memory_gb(legacy_api) == 3.0
    assert _mlx_peak_memory_gb(SimpleNamespace()) == 0.0
    assert calls == ["current", "legacy-metal"]


def test_gemma4_text_only_language_model_loader_wraps_and_sanitizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_vlm_modules(monkeypatch)
    import mlx.core as mx
    import mlx.nn as nn
    import mlx_vlm.models.gemma4.language as language

    calls: dict[str, object] = {}

    class FakeTextConfig:
        @classmethod
        def from_dict(cls, config):
            calls["config"] = dict(config)
            return SimpleNamespace(model_type="gemma4_text")

    class FakeLanguageModel:
        def __init__(self, config):
            self.config = config
            self.model = SimpleNamespace(hidden_size_per_layer_input=0)

        def sanitize(self, weights):
            calls["sanitize"] = dict(weights)
            return {"clean.scales": object(), "clean.weight": object()}

        def load_weights(self, weights):
            calls["load_weights"] = list(weights)

        def parameters(self):
            return []

        def eval(self):
            calls["eval"] = True

    def fake_quantize(model, *, group_size, bits, mode, class_predicate):
        calls["quantize"] = (model, group_size, bits, mode)
        assert class_predicate("custom", object()) == {"bits": 8}
        assert class_predicate("plain", object()) is False
        assert class_predicate(
            "odd",
            SimpleNamespace(to_quantized=lambda: None, weight=SimpleNamespace(size=63)),
        ) is False
        assert class_predicate(
            "clean",
            SimpleNamespace(to_quantized=lambda: None, weight=SimpleNamespace(size=64)),
        ) is True

    monkeypatch.setattr(language, "TextConfig", FakeTextConfig)
    monkeypatch.setattr(language, "LanguageModel", FakeLanguageModel)
    monkeypatch.setattr(nn, "quantize", fake_quantize)
    monkeypatch.setattr(mx, "eval", lambda parameters: calls.setdefault("mx_eval", parameters))

    model = AutoMLXVLMBackend._load_gemma4_text_only_language_model(
        config={
            "model_type": "gemma4_text",
            "quantization": {
                "group_size": 64,
                "bits": 4,
                "mode": "affine",
                "custom": {"bits": 8},
            },
        },
        weights={"clean.scales": object(), "unused": object()},
    )

    assert isinstance(model, _Gemma4TextBackedModelShim)
    assert calls["config"]["model_type"] == "gemma4_text"
    assert calls["sanitize"].keys() == {"clean.scales", "unused"}
    assert calls["eval"] is True
    assert calls["mx_eval"] == []
    assert [name for name, _value in calls["load_weights"]] == ["clean.scales", "clean.weight"]


def test_gemma4_text_backed_loader_uses_tokenizer_for_text_only_exports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    modules = _install_fake_mlx_vlm_modules(monkeypatch)
    import mlx.core as mx
    import mlx_vlm.utils as utils

    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "model.safetensors").write_bytes(b"")
    calls: dict[str, object] = {}

    modules["mlx_vlm.models.gemma4.language"].ScaledLinear = type(
        "ScaledLinear",
        (),
        {"to_quantized": lambda self: self},
    )
    monkeypatch.setattr(utils, "get_model_and_args", lambda *_args, **_kwargs: pytest.fail("unexpected model load"))
    monkeypatch.setattr(utils, "get_model_path", lambda *_args, **_kwargs: model_path)
    monkeypatch.setattr(utils, "load_config", lambda *_args, **_kwargs: {"model_type": "gemma4_text"})
    monkeypatch.setattr(utils, "load_processor", lambda *_args, **_kwargs: pytest.fail("unexpected processor load"))
    monkeypatch.setattr(utils, "update_module_configs", lambda *_args, **_kwargs: pytest.fail("unexpected config update"))

    def fake_load_text_only_language_model(*, config, weights):
        calls["model_args"] = (config, weights)
        return "text-model"

    monkeypatch.setattr(
        AutoMLXVLMBackend,
        "_load_gemma4_text_only_language_model",
        staticmethod(fake_load_text_only_language_model),
    )
    monkeypatch.setattr(
        utils,
        "load_tokenizer",
        lambda *_args, **_kwargs: SimpleNamespace(_tokenizer=lambda *a, **k: None),
    )
    monkeypatch.setattr(mx, "load", lambda path: {"model.layers.0.weight": path})

    model, processor, execution_mode = AutoMLXVLMBackend._load_gemma4_text_backed_model(
        model_spec=common_pb2.ModelSpec(model_path=str(model_path), revision="main"),
        original_error=RuntimeError("original"),
    )

    assert model == "text-model"
    assert calls["model_args"][0] == {"model_type": "gemma4_text"}
    assert list(calls["model_args"][1]) == ["model.layers.0.weight"]
    assert isinstance(processor, _CallableTokenizerProcessor)
    assert execution_mode == "text_backed"


def test_mtp_batch_response_helpers_read_current_upstream_shape() -> None:
    response = SimpleNamespace(
        texts=["hello"],
        stats=SimpleNamespace(prompt_tokens=3, generation_tokens=2),
    )

    assert MLXVLMRuntime._batch_response_text(response) == "hello"
    assert MLXVLMRuntime._response_number(response, "prompt_tokens") == 3
    assert MLXVLMRuntime._response_number(response, "generation_tokens") == 2


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


def test_mlx_vlm_runtime_uses_generate_step_for_mtp_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_vlm_prepare_inputs(monkeypatch)
    apply_calls: list[str] = []
    generate_step_calls: list[dict[str, object]] = []

    class FakeDetokenizer:
        def __init__(self) -> None:
            self.text = ""

        def reset(self) -> None:
            self.text = ""

        def add_token(self, token: int) -> None:
            self.text += {101: "MTP ", 102: "step"}.get(token, "")

        def finalize(self) -> None:
            pass

    class FakeProcessor:
        chat_template = "{{ prompt }}"
        eos_token = "<eos>"
        pad_token = None

        def __init__(self) -> None:
            self.detokenizer = FakeDetokenizer()

        def __call__(self, prompts, **kwargs):
            import mlx.core as mx

            _ = prompts
            _ = kwargs
            return SimpleNamespace(
                input_ids=mx.array([[1, 2, 3]]),
                attention_mask=mx.array([[1, 1, 1]]),
            )

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), FakeProcessor()

    drafter = SimpleNamespace(
        draft_model_id="draft-model",
        kind="mtp",
        model=SimpleNamespace(
            accept_lens=[2, 1],
            config=SimpleNamespace(block_size=6),
        ),
    )

    def fake_load_drafter(model_id: str, *, kind: str = "mtp"):
        _ = model_id
        _ = kind
        return drafter

    def fake_generate_step(
        input_ids,
        model,
        pixel_values,
        mask,
        *,
        max_tokens: int,
        draft_model,
        draft_kind: str,
        draft_block_size: int,
        prefill_step_size,
    ):
        generate_step_calls.append(
            {
                "input_ids_shape": tuple(input_ids.shape),
                "model": model,
                "pixel_values": pixel_values,
                "mask_shape": tuple(mask.shape),
                "max_tokens": max_tokens,
                "draft_model": draft_model,
                "draft_kind": draft_kind,
                "draft_block_size": draft_block_size,
                "prefill_step_size": prefill_step_size,
            }
        )
        yield 101, None
        yield 102, None

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=lambda _processor, _config, prompt, **kwargs: (
                apply_calls.append(prompt) or f"formatted::{prompt}"
            ),
            load_drafter_fn=fake_load_drafter,
            generate_step_fn=fake_generate_step,
        )
    )
    loaded_model = runtime.load_model(imported_gemma4_vlm_model())
    loaded_model["metadata"]["melix.vlm.execution_mode"] = "text_backed"
    prepared = runtime.render_prompt(
        [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text="Say hello.")])],
        loaded_model=loaded_model,
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
            acceleration_policy=common_pb2.AccelerationPolicy(
                mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
                draft_model_id="draft-model",
                num_draft_tokens=6,
                allow_baseline_fallback=False,
            ),
        )
    )

    assert apply_calls == ["Say hello."]
    assert events[-1].text == "MTP step"
    assert events[-1].prompt_tokens == 3
    assert events[-1].completion_tokens == 2
    assert events[-1].speculative_fallback_count == 0
    assert events[-1].speculative_num_draft_tokens == 6
    assert events[-1].speculative_draft_model_configured is True
    assert events[-1].speculative_acceptance_rate == 0.3
    assert events[-1].speculative_rollback_rate == 0.7
    assert events[-1].speculative_accepted_tokens == 3
    assert events[-1].speculative_rejected_tokens == 7
    assert generate_step_calls == [
        {
            "input_ids_shape": (1, 3),
            "model": loaded_model["model"],
            "pixel_values": None,
            "mask_shape": (1, 3),
            "max_tokens": 16,
            "draft_model": drafter,
            "draft_kind": "mtp",
            "draft_block_size": 6,
            "prefill_step_size": None,
        }
    ]


@pytest.mark.parametrize(
    ("drafter", "draft_block_size"),
    [
        (SimpleNamespace(model=SimpleNamespace()), 6),
        (SimpleNamespace(model=SimpleNamespace(accept_lens=["not-int"])), 6),
        (SimpleNamespace(model=SimpleNamespace(accept_lens=[])), 6),
        (SimpleNamespace(model=SimpleNamespace(accept_lens=[-1])), 6),
        (SimpleNamespace(model=SimpleNamespace(accept_lens=[0])), 1),
    ],
)
def test_mtp_drafter_acceptance_stats_ignore_unusable_accept_lens(
    drafter: SimpleNamespace,
    draft_block_size: int,
) -> None:
    assert MLXVLMRuntime._mtp_drafter_acceptance_stats(drafter, draft_block_size) is None


def test_auto_mlx_vlm_backend_detects_installed_optional_mtp_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlx_vlm = ModuleType("mlx_vlm")
    fake_mlx_vlm.__path__ = []
    fake_generate = ModuleType("mlx_vlm.generate")
    fake_speculative = ModuleType("mlx_vlm.speculative")
    fake_speculative.__path__ = []
    fake_drafters = ModuleType("mlx_vlm.speculative.drafters")

    def fake_load(model_path: str, *, revision: str = "main"):
        _ = model_path, revision
        return object(), object()

    def fake_stream_generate(*_args, **_kwargs):
        return iter(())

    def fake_apply_chat_template(*_args, **_kwargs):
        return ""

    def fake_generate_step(
        *_args,
        draft_model=None,
        draft_kind=None,
        draft_block_size=None,
        **_kwargs,
    ):
        _ = draft_model, draft_kind, draft_block_size
        return iter(())

    def fake_batch_generate(
        *_args,
        draft_model=None,
        draft_kind=None,
        draft_block_size=None,
        **_kwargs,
    ):
        _ = draft_model, draft_kind, draft_block_size
        return []

    def fake_load_drafter(model_id: str, *, kind: str = "mtp"):
        return {"model_id": model_id, "kind": kind}

    fake_mlx_vlm.load = fake_load
    fake_mlx_vlm.stream_generate = fake_stream_generate
    fake_mlx_vlm.apply_chat_template = fake_apply_chat_template
    fake_generate.generate_step = fake_generate_step
    fake_generate.batch_generate = fake_batch_generate
    fake_drafters.load_drafter = fake_load_drafter

    monkeypatch.setitem(sys.modules, "mlx_vlm", fake_mlx_vlm)
    monkeypatch.setitem(sys.modules, "mlx_vlm.generate", fake_generate)
    monkeypatch.setitem(sys.modules, "mlx_vlm.speculative", fake_speculative)
    monkeypatch.setitem(sys.modules, "mlx_vlm.speculative.drafters", fake_drafters)
    original_find_spec = mlx_vlm_runtime_module.importlib.util.find_spec
    monkeypatch.setattr(
        mlx_vlm_runtime_module.importlib.util,
        "find_spec",
        lambda name, *args, **kwargs: object()
        if name == "mlx_vlm"
        else original_find_spec(name, *args, **kwargs),
    )

    backend = AutoMLXVLMBackend()

    backend._ensure_runtime()

    assert backend.runtime_name == "mlx-vlm"
    assert backend.load_fn is fake_load
    assert backend.stream_generate_fn is fake_stream_generate
    assert backend.apply_chat_template_fn is fake_apply_chat_template
    assert backend.generate_step_fn is fake_generate_step
    assert backend.batch_generate_fn is fake_batch_generate
    assert backend.load_drafter_fn is fake_load_drafter
    generate_step_support = backend.generate_step_fn is not None and (
        runtime_utils.callable_declares_kwarg(backend.generate_step_fn, "draft_model")
        and runtime_utils.callable_declares_kwarg(backend.generate_step_fn, "draft_kind")
        and runtime_utils.callable_declares_kwarg(backend.generate_step_fn, "draft_block_size")
    )
    batch_generate_support = backend.batch_generate_fn is not None and (
        runtime_utils.callable_declares_kwarg(backend.batch_generate_fn, "draft_model")
        and runtime_utils.callable_declares_kwarg(backend.batch_generate_fn, "draft_kind")
        and runtime_utils.callable_declares_kwarg(backend.batch_generate_fn, "draft_block_size")
    )
    assert backend.supports_mtp_speculative() is (
        backend.load_drafter_fn is not None and (generate_step_support or batch_generate_support)
    )
    assert backend.supports_mtp_speculative() is True


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
    def fake_batch_generate(
        model,
        processor,
        *,
        prompts,
        draft_model,
        draft_kind,
        draft_block_size,
        **kwargs,
    ):
        _ = model
        _ = processor
        _ = prompts
        _ = draft_model
        _ = draft_kind
        _ = draft_block_size
        _ = kwargs
        return [SimpleNamespace(text="unexpected")]

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

    def fake_batch_generate(
        model,
        processor,
        *,
        prompts,
        draft_model,
        draft_kind,
        draft_block_size,
        **kwargs,
    ):
        _ = model
        _ = processor
        _ = prompts
        _ = draft_model
        _ = draft_kind
        _ = draft_block_size
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
    def fake_batch_generate(
        model,
        processor,
        *,
        prompts,
        draft_model,
        draft_kind,
        draft_block_size,
        **kwargs,
    ):
        _ = model
        _ = processor
        _ = prompts
        _ = draft_model
        _ = draft_kind
        _ = draft_block_size
        _ = kwargs
        return [SimpleNamespace(text="")]

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
