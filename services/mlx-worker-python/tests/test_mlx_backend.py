from __future__ import annotations

from threading import Event
import types
import sys

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime.mlx_text_runtime import AutoMLXBackend, MLXTextRuntime, RuntimeUnavailableError


class FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], bool, bool]] = []

    def apply_chat_template(self, messages, tokenize: bool, add_generation_prompt: bool):
        self.calls.append((messages, tokenize, add_generation_prompt))
        return "<prompt-from-template>"


class FakeGenerationResponse:
    def __init__(
        self,
        *,
        text: str,
        prompt_tokens: int,
        generation_tokens: int,
        prompt_tps: float = 0.0,
        generation_tps: float = 0.0,
        peak_memory: float = 0.0,
        finish_reason: str | None = None,
    ) -> None:
        self.text = text
        self.token = 1
        self.logprobs = None
        self.from_draft = False
        self.prompt_tokens = prompt_tokens
        self.prompt_tps = prompt_tps
        self.generation_tokens = generation_tokens
        self.generation_tps = generation_tps
        self.peak_memory = peak_memory
        self.finish_reason = finish_reason


def test_runtime_uses_chat_template_when_runtime_model_exposes_tokenizer() -> None:
    runtime = MLXTextRuntime(backend=object())
    tokenizer = FakeTokenizer()

    prompt = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="system",
                parts=[common_pb2.MessagePart(text="You are helpful.")],
            ),
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Hello")],
            ),
        ],
        loaded_model={"tokenizer": tokenizer},
    )

    assert prompt == "<prompt-from-template>"
    assert tokenizer.calls == [
        (
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
            False,
            True,
        )
    ]


def test_auto_backend_uses_mlx_load_stream_and_sampler_hooks() -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        return object(), FakeTokenizer()

    def fake_sampler_factory(*, temp: float, top_p: float, top_k: int):
        seen["sampler"] = {"temp": temp, "top_p": top_p, "top_k": top_k}
        return "fake-sampler"

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler):
        seen["stream"] = {
            "model": model,
            "tokenizer": tokenizer,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "sampler": sampler,
        }
        yield FakeGenerationResponse(text="Hel", prompt_tokens=12, generation_tokens=1)
        yield FakeGenerationResponse(
            text="lo",
            prompt_tokens=12,
            generation_tokens=2,
            finish_reason="stop",
            prompt_tps=321.0,
            generation_tps=123.0,
            peak_memory=1.5,
        )

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=fake_sampler_factory,
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    loaded_model = backend.load_model(model_spec)

    chunks = list(
        backend.generate_tokens(
            loaded_model,
            "<prompt-from-template>",
            common_pb2.SamplingConfig(
                temperature=0.7,
                top_p=0.9,
                top_k=32,
                max_output_tokens=24,
            ),
            Event(),
        )
    )

    assert seen["load"] == ("mlx-community/test-model", {"lazy": False})
    assert seen["sampler"]["temp"] == pytest.approx(0.7)
    assert seen["sampler"]["top_p"] == pytest.approx(0.9)
    assert seen["sampler"]["top_k"] == 32
    assert seen["stream"] == {
        "model": loaded_model["model"],
        "tokenizer": loaded_model["tokenizer"],
        "prompt": "<prompt-from-template>",
        "max_tokens": 24,
        "sampler": "fake-sampler",
    }
    assert [chunk.text for chunk in chunks] == ["Hel", "lo"]
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].prompt_tokens == 12
    assert chunks[-1].completion_tokens == 2
    assert chunks[-1].generation_tps == 123.0


def test_auto_backend_lazy_import_wires_runtime_modules(monkeypatch) -> None:
    seen: dict[str, object] = {}

    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.__path__ = []

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        return object(), FakeTokenizer()

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler):
        seen["stream"] = {"prompt": prompt, "max_tokens": max_tokens, "sampler": sampler}
        yield FakeGenerationResponse(text="token", prompt_tokens=3, generation_tokens=1, finish_reason="stop")

    fake_mlx_lm.load = fake_load
    fake_mlx_lm.stream_generate = fake_stream_generate

    fake_sample_utils = types.ModuleType("mlx_lm.sample_utils")

    def fake_make_sampler(*, temp: float, top_p: float, top_k: int):
        seen["sampler"] = {"temp": temp, "top_p": top_p, "top_k": top_k}
        return "lazy-sampler"

    fake_sample_utils.make_sampler = fake_make_sampler

    monkeypatch.setattr("importlib.util.find_spec", lambda name: object() if name == "mlx_lm" else None)
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", fake_sample_utils)

    backend = AutoMLXBackend()
    loaded_model = backend.load_model(WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/lazy-model"}))
    chunks = list(
        backend.generate_tokens(
            loaded_model,
            "lazy prompt",
            common_pb2.SamplingConfig(max_output_tokens=8),
            Event(),
        )
    )

    assert backend.runtime_name == "mlx-lm"
    assert seen["load"] == ("mlx-community/lazy-model", {"lazy": False})
    assert seen["stream"] == {"prompt": "lazy prompt", "max_tokens": 8, "sampler": "lazy-sampler"}
    assert [chunk.text for chunk in chunks] == ["token"]


def test_auto_backend_handles_unavailable_runtime_and_skips_empty_segments(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    backend = AutoMLXBackend()

    with pytest.raises(RuntimeUnavailableError):
        backend.load_model(WorkerModelCatalog.dev_text_model())

    with pytest.raises(RuntimeUnavailableError):
        list(backend.generate_tokens({}, "prompt", common_pb2.SamplingConfig(), Event()))

    visible_chunks = list(
        AutoMLXBackend(
            load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
            stream_generate_fn=lambda *args, **kwargs: iter(
                [
                    FakeGenerationResponse(text="", prompt_tokens=4, generation_tokens=0),
                    FakeGenerationResponse(text="tail", prompt_tokens=4, generation_tokens=1, finish_reason="stop"),
                ]
            ),
            sampler_factory=lambda **kwargs: "sampler",
        ).generate_tokens(
            {"model": object(), "tokenizer": FakeTokenizer()},
            "prompt",
            common_pb2.SamplingConfig(),
            Event(),
        )
    )

    cancelled = Event()
    cancelled.set()
    cancelled_chunks = list(
        AutoMLXBackend(
            load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
            stream_generate_fn=lambda *args, **kwargs: iter(
                [FakeGenerationResponse(text="cancelled", prompt_tokens=1, generation_tokens=1)]
            ),
            sampler_factory=lambda **kwargs: "sampler",
        ).generate_tokens(
            {"model": object(), "tokenizer": FakeTokenizer()},
            "prompt",
            common_pb2.SamplingConfig(),
            cancelled,
        )
    )

    assert [chunk.text for chunk in visible_chunks] == ["tail"]
    assert cancelled_chunks == []


def test_worker_model_catalog_uses_environment_override_for_dev_text_model() -> None:
    model = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    assert model.model_path == "mlx-community/test-model"
