from __future__ import annotations

import json
from threading import Event
from threading import get_ident
from pathlib import Path
import types
import sys

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.mlx_text_runtime import AutoMLXBackend, MLXTextRuntime, RuntimeUnavailableError


class FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
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
            {
                "tokenize": False,
                "add_generation_prompt": True,
            },
        )
    ]


def test_runtime_merges_chat_template_kwargs_into_tokenizer_calls() -> None:
    runtime = MLXTextRuntime(backend=object())
    tokenizer = FakeTokenizer()

    prompt = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Hello")],
            )
        ],
        loaded_model={"tokenizer": tokenizer},
        template_kwargs={
            "add_generation_prompt": False,
            "continue_final_message": True,
        },
    )

    assert prompt == "<prompt-from-template>"
    assert tokenizer.calls == [
        (
            [
                {"role": "user", "content": "Hello"},
            ],
            {
                "tokenize": False,
                "add_generation_prompt": False,
                "continue_final_message": True,
            },
        )
    ]


def test_runtime_passes_message_names_into_tokenizer_calls() -> None:
    runtime = MLXTextRuntime(backend=object())
    tokenizer = FakeTokenizer()

    prompt = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="assistant",
                name="planner",
                parts=[common_pb2.MessagePart(text="Draft reply")],
            )
        ],
        loaded_model={"tokenizer": tokenizer},
        template_kwargs={
            "add_generation_prompt": False,
            "continue_final_message": True,
        },
    )

    assert prompt == "<prompt-from-template>"
    assert tokenizer.calls == [
        (
            [
                {"role": "assistant", "name": "planner", "content": "Draft reply"},
            ],
            {
                "tokenize": False,
                "add_generation_prompt": False,
                "continue_final_message": True,
            },
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
        tail = FakeGenerationResponse(
            text="lo",
            prompt_tokens=12,
            generation_tokens=2,
            finish_reason="stop",
            prompt_tps=321.0,
            generation_tps=123.0,
            peak_memory=1.5,
        )
        tail.speculative_acceptance_rate = 0.8
        tail.speculative_rejected_tokens = 3
        tail.speculative_draft_model_configured = True
        tail.dflash_enabled = True
        tail.dflash_rollback_count = 2
        yield tail

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
    assert chunks[-1].speculative_acceptance_rate == 0.8
    assert chunks[-1].speculative_rejected_tokens == 3
    assert chunks[-1].speculative_draft_model_configured is True
    assert chunks[-1].dflash_enabled is True
    assert chunks[-1].dflash_rollback_count == 2


def test_text_runtime_load_and_generation_run_on_mlx_executor_thread() -> None:
    main_thread_id = get_ident()
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load_thread_id"] = get_ident()
        seen["load"] = (model_source, kwargs)
        return object(), FakeTokenizer()

    def fake_sampler_factory(*, temp: float, top_p: float, top_k: int):
        _ = temp
        _ = top_p
        _ = top_k
        return "sampler"

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler):
        _ = model
        _ = tokenizer
        _ = prompt
        _ = max_tokens
        _ = sampler
        seen["stream_thread_id"] = get_ident()
        yield FakeGenerationResponse(text="owned", prompt_tokens=4, generation_tokens=1, finish_reason="stop")

    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    runtime = MLXTextRuntime(
        backend=AutoMLXBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            sampler_factory=fake_sampler_factory,
        ),
        executor=executor,
    )
    try:
        model_spec = WorkerModelCatalog.dev_text_model(
            environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"}
        )
        loaded_model = runtime.load_model(model_spec)
        chunks = list(
            runtime.generate_tokens(
                loaded_model,
                "prompt",
                common_pb2.SamplingConfig(max_output_tokens=4),
                Event(),
            )
        )
        executor_thread_id = executor.run(get_ident)
    finally:
        executor.shutdown()

    assert [chunk.text for chunk in chunks] == ["owned"]
    assert seen["load_thread_id"] == executor_thread_id
    assert seen["stream_thread_id"] == executor_thread_id
    assert executor_thread_id != main_thread_id


def test_adapter_backed_contract_exposes_typed_fields_from_ext_metadata() -> None:
    """Typed contract resolves all required fields from ext + manifest."""
    from worker.runtime.mlx_text_runtime import (
        AdapterBackedLoadContract,
        _resolve_adapter_backed_contract,
    )

    model_spec = WorkerModelCatalog.dev_text_model(
        environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"}
    )
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
    model_spec.ext["melix.adapter_manifest_path"] = "/tmp/melix-train/train_lora.adapter.json"
    model_spec.ext["melix.adapter_weights_path"] = "/tmp/melix-train/weights/adapters.safetensors"
    model_spec.ext["melix.adapter_set_hash"] = "hash-1234"
    model_spec.ext["melix.derived_from_model_id"] = "melix-dev-text"

    contract = _resolve_adapter_backed_contract(model_spec)

    assert isinstance(contract, AdapterBackedLoadContract)
    assert contract.adapter_manifest_path == "/tmp/melix-train/train_lora.adapter.json"
    assert contract.adapter_weights_path == "/tmp/melix-train/weights/adapters.safetensors"
    assert contract.adapter_dir == str(Path("/tmp/melix-train/weights").resolve())
    assert contract.adapter_set_hash == "hash-1234"
    assert contract.derived_from_model_id == "melix-dev-text"


def test_adapter_backed_contract_returns_none_for_fused_models() -> None:
    from worker.runtime.mlx_text_runtime import _resolve_adapter_backed_contract

    model_spec = WorkerModelCatalog.dev_text_model()
    # Fused and base models produce no contract.
    assert _resolve_adapter_backed_contract(model_spec) is None


def test_adapter_backed_contract_honors_runtime_mode_enum_over_ext_string() -> None:
    """Proto RuntimeMode enum is authoritative when set."""
    from worker.runtime.mlx_text_runtime import _resolve_adapter_backed_contract
    from packages.protocol.python.worker.v1 import common_pb2

    # Spec with the typed enum but NO ext string — contract still resolves.
    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.runtime_mode = common_pb2.RUNTIME_MODE_ADAPTER_BACKED
    model_spec.ext["melix.adapter_manifest_path"] = "/tmp/melix/manifest.json"
    model_spec.ext["melix.adapter_weights_path"] = "/tmp/melix/weights/adapters.safetensors"

    contract = _resolve_adapter_backed_contract(model_spec)
    assert contract is not None
    assert contract.adapter_manifest_path == "/tmp/melix/manifest.json"


def test_adapter_backed_contract_ignores_ext_string_when_enum_says_fused() -> None:
    """When runtime_mode is FUSED, stale ext strings don't drag us back into adapter-backed."""
    from worker.runtime.mlx_text_runtime import _resolve_adapter_backed_contract
    from packages.protocol.python.worker.v1 import common_pb2

    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.runtime_mode = common_pb2.RUNTIME_MODE_FUSED_DERIVED_MODEL
    # Stale ext values left over from an earlier run.
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"

    assert _resolve_adapter_backed_contract(model_spec) is None


def test_adapter_backed_contract_rejects_missing_manifest_when_enum_set() -> None:
    from worker.runtime.mlx_text_runtime import _resolve_adapter_backed_contract
    from packages.protocol.python.worker.v1 import common_pb2

    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.runtime_mode = common_pb2.RUNTIME_MODE_ADAPTER_BACKED

    with pytest.raises(RuntimeError, match="adapter_manifest_path"):
        _resolve_adapter_backed_contract(model_spec)


def test_auto_backend_loads_adapter_backed_runtime_with_adapter_path() -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        return object(), FakeTokenizer()

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    model_spec.model_id = "melix-dev-text-lora-runtime"
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
    model_spec.ext["melix.adapter_manifest_path"] = "/tmp/melix-train/train_lora.adapter.json"
    model_spec.ext["melix.adapter_weights_path"] = "/tmp/melix-train/weights/adapters.safetensors"
    model_spec.ext["melix.derived_from_adapter"] = "true"
    model_spec.ext["melix.derived_from_model_id"] = "melix-dev-text"

    loaded_model = backend.load_model(model_spec)

    assert seen["load"] == (
        "mlx-community/test-model",
        {
            "lazy": False,
            "adapter_path": str(Path("/tmp/melix-train/weights").resolve()),
        },
    )
    assert loaded_model["activation_mode"] == "adapter_backed_runtime"
    assert loaded_model["adapter_manifest_path"] == "/tmp/melix-train/train_lora.adapter.json"
    assert loaded_model["adapter_weights_path"] == "/tmp/melix-train/weights/adapters.safetensors"
    assert loaded_model["derived_from_model_id"] == "melix-dev-text"


def test_auto_backend_resolves_adapter_weights_from_manifest_when_ext_omits_them(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        return object(), FakeTokenizer()

    manifest_path = tmp_path / "train_lora.adapter.json"
    weights_path = tmp_path / "artifacts" / "adapters.safetensors"
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    weights_path.write_text("adapter", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"weights_path": str(weights_path)}) + "\n",
        encoding="utf-8",
    )

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
    model_spec.ext["melix.adapter_manifest_path"] = str(manifest_path)

    loaded_model = backend.load_model(model_spec)

    assert seen["load"] == (
        "mlx-community/test-model",
        {
            "lazy": False,
            "adapter_path": str(weights_path.parent.resolve()),
        },
    )
    assert loaded_model["adapter_weights_path"] == str(weights_path)


def test_auto_backend_rejects_adapter_backed_runtime_without_manifest_metadata() -> None:
    backend = AutoMLXBackend(
        load_fn=lambda *args, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"

    with pytest.raises(RuntimeError, match="adapter_manifest_path"):
        backend.load_model(model_spec)


def test_auto_backend_rejects_adapter_backed_runtime_without_weights_metadata() -> None:
    backend = AutoMLXBackend(
        load_fn=lambda *args, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
    model_spec.ext["melix.adapter_manifest_path"] = "/tmp/melix-train/train_lora.adapter.json"

    with pytest.raises(RuntimeError, match="adapter_weights_path"):
        backend.load_model(model_spec)


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


def test_auto_backend_surfaces_import_failure_during_lazy_runtime_resolution(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object() if name == "mlx_lm" else None)
    monkeypatch.setitem(sys.modules, "mlx_lm", None)
    monkeypatch.delitem(sys.modules, "mlx_lm.sample_utils", raising=False)

    backend = AutoMLXBackend()
    backend._load_fn = None
    backend._stream_generate_fn = None
    backend._sampler_factory = None
    backend._available = True

    with pytest.raises(RuntimeUnavailableError):
        backend._ensure_runtime()

    assert backend.runtime_name == "mlx-unavailable"


def test_auto_backend_reports_zero_resident_bytes_estimate() -> None:
    backend = AutoMLXBackend(
        load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "sampler",
    )

    assert backend.estimate_resident_bytes(WorkerModelCatalog.dev_text_model()) == 0


def test_runtime_name_falls_back_when_backend_has_no_runtime_name() -> None:
    runtime = MLXTextRuntime(backend=object())

    assert runtime.runtime_name == "unknown-runtime"


def test_runtime_wraps_plain_string_backend_tokens() -> None:
    class PlainStringBackend:
        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id}

        def estimate_resident_bytes(self, model_spec):
            return 1

        def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
            yield "plain-token"

    runtime = MLXTextRuntime(backend=PlainStringBackend())
    events = list(
        runtime.generate_tokens(
            {},
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=4),
            Event(),
        )
    )

    assert [event.text for event in events] == ["plain-token"]


def test_worker_model_catalog_uses_environment_override_for_dev_text_model() -> None:
    model = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    assert model.model_path == "mlx-community/test-model"


def test_worker_model_catalog_dev_text_model_preserves_explicit_route_override() -> None:
    model = WorkerModelCatalog.dev_text_model(
        environment={
            "MELIX_DEV_TEXT_FAMILY_ID": "qwen3moe",
            "MELIX_DEV_TEXT_ROUTE_KIND": "custom_text_route",
        }
    )

    assert model.ext["melix.capability.route_kind"] == "custom_text_route"


def test_worker_model_catalog_and_runtime_expose_text_family_metadata() -> None:
    model = WorkerModelCatalog.dev_text_model(
        environment={
            "MELIX_DEV_TEXT_FAMILY_ID": "qwen3moe",
            "MELIX_DEV_TEXT_MODEL_PATH": "models/qwen3-moe-128e",
        }
    )
    runtime = MLXTextRuntime(
        backend=AutoMLXBackend(
            load_fn=lambda *_args, **_kwargs: (object(), FakeTokenizer()),
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            sampler_factory=lambda **kwargs: "unused",
        )
    )

    loaded = runtime.load_model(model)

    assert model.ext["text_backend_id"] == "mlx_lm"
    assert model.ext["text_family_id"] == "qwen3moe"
    assert model.ext["melix.capability.route_kind"] == "python_text_compatibility"
    assert model.ext["melix.capability.supported_parsers"] == "text,qwen"
    assert model.ext["tool_parser_mode"] == "qwen"
    assert loaded["text_backend_id"] == "mlx_lm"
    assert loaded["text_family_id"] == "qwen3moe"
    assert loaded["model_architecture"] == "qwen3_moe"
    assert loaded["text_attention_profile"] == "gqa"
    assert loaded["text_rope_profile"] == "yarn_interleaved"
    assert loaded["text_moe_enabled"] == "true"
    assert loaded["text_moe_expert_count"] == "128"
    assert loaded["text_moe_gate_dequant"] == "true"
