from __future__ import annotations

import json
from threading import Event
from threading import get_ident
from pathlib import Path
import types
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime import mlx_text_runtime as mlx_text_runtime_module
from worker.runtime import runtime_utils
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.mlx_text_runtime import AutoMLXBackend, MLXTextRuntime, RuntimeTokenEvent, RuntimeToolCallEvent
from worker.runtime.mlx_text_runtime import RuntimeUnavailableError, resolve_text_stop_contract


def _install_fake_mlx_core(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    fake_mlx = types.ModuleType("mlx")
    fake_core = types.ModuleType("mlx.core")
    fake_core.metal = types.SimpleNamespace(get_peak_memory=lambda: 0)
    fake_mlx.core = fake_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_core)
    return fake_core


class FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []
        self.eos_token = "</s>"
        self.eos_token_id = 2

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
    assert [chunk.raw_text for chunk in chunks] == ["Hel", "Hello"]
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].prompt_tokens == 12
    assert chunks[-1].completion_tokens == 2
    assert chunks[-1].generation_tps == 123.0
    assert chunks[-1].speculative_acceptance_rate == 0.8
    assert chunks[-1].speculative_rejected_tokens == 3
    assert chunks[-1].speculative_draft_model_configured is True
    assert chunks[-1].dflash_enabled is True
    assert chunks[-1].dflash_rollback_count == 2


def test_auto_backend_uses_batch_generator_for_native_mtp_text_models(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mlx_core(monkeypatch)
    seen: dict[str, object] = {
        "closed": 0,
        "detokenizer_access_count": 0,
        "detokenizer_copy_count": 0,
        "init_count": 0,
        "insert_calls": [],
        "prefill_calls": [],
        "removed_calls": [],
        "request_detokenizers": [],
        "request_detokenizer_ids": [],
    }

    class FakeDetokenizer:
        def __copy__(self):
            seen["detokenizer_copy_count"] = int(seen["detokenizer_copy_count"]) + 1
            clone = FakeDetokenizer()
            seen["request_detokenizers"].append(clone)
            seen["request_detokenizer_ids"].append(id(clone))
            return clone

        def __init__(self) -> None:
            self._text = ""
            self._last_offset = 0
            self.tokens: list[int] = []

        def reset(self) -> None:
            self._text = ""
            self._last_offset = 0
            self.tokens = []

        def add_token(self, token: int) -> None:
            self.tokens.append(token)
            self._text += {101: "A", 102: "B"}.get(token, "")

        @property
        def last_segment(self) -> str:
            segment = self._text[self._last_offset :]
            self._last_offset = len(self._text)
            return segment

        def finalize(self) -> None:
            self._text += "!"

    class FakeTokenizer:
        eos_token = "</s>"
        eos_token_id = 2

        @property
        def detokenizer(self) -> FakeDetokenizer:
            seen["detokenizer_access_count"] = int(seen["detokenizer_access_count"]) + 1
            return FakeDetokenizer()

        def encode(self, prompt: str, add_special_tokens: bool = True):
            seen["encoded"] = (prompt, add_special_tokens)
            return [11, 12, 13]

    logprob_index_calls = {"count": 0}

    class UnrequestedLogprobs:
        def __getitem__(self, _token_id: int):
            logprob_index_calls["count"] += 1
            raise AssertionError("native MTP text should not materialize unrequested logprobs")

    class FakeBatchGenerator:
        def __init__(
            self,
            model,
            *,
            max_tokens: int,
            stop_tokens,
            sampler,
            prefill_batch_size: int,
            completion_batch_size: int,
            prefill_step_size: int,
        ) -> None:
            seen["init_count"] = int(seen["init_count"]) + 1
            seen["batch_generator_init"] = {
                "model": model,
                "max_tokens": max_tokens,
                "stop_tokens": stop_tokens,
                "sampler": sampler,
                "prefill_batch_size": prefill_batch_size,
                "completion_batch_size": completion_batch_size,
                "prefill_step_size": prefill_step_size,
            }
            self._step = 0

        def insert(self, prompts, max_tokens=None, caches=None, all_tokens=None, samplers=None):
            seen["insert_calls"].append(
                {
                    "prompts": prompts,
                    "max_tokens": max_tokens,
                    "caches": caches,
                    "all_tokens": all_tokens,
                    "samplers": samplers,
                }
            )
            seen["insert"] = {
                "prompts": prompts,
                "max_tokens": max_tokens,
                "caches": caches,
                "all_tokens": all_tokens,
                "samplers": samplers,
            }
            self._step = 0
            return [77]

        def next_generated(self):
            self._step += 1
            if self._step == 1:
                return [
                    SimpleNamespace(
                        uid=77,
                        token=101,
                        logprobs=UnrequestedLogprobs(),
                        finish_reason=None,
                        speculative_acceptance_rate=0.5,
                        speculative_accepted_tokens=1,
                        speculative_rejected_tokens=1,
                        speculative_num_draft_tokens=1,
                        speculative_draft_model_configured=True,
                    )
                ]
            return [
                SimpleNamespace(
                    uid=77,
                    token=102,
                    logprobs=UnrequestedLogprobs(),
                    finish_reason="length",
                    speculative_acceptance_rate=0.75,
                    speculative_rollback_rate=0.25,
                    speculative_accepted_tokens=3,
                    speculative_rejected_tokens=1,
                    speculative_num_draft_tokens=1,
                    speculative_draft_model_configured=True,
                    speculative_backbone_ms=12.5,
                )
            ]

        def remove(self, uids):
            seen["removed_calls"].append(list(uids))
            seen["removed"] = list(uids)

        def close(self):
            seen["closed"] = int(seen["closed"]) + 1

    monkeypatch.setattr(
        mlx_text_runtime_module,
        "_load_mlx_batch_generator_class",
        lambda: FakeBatchGenerator,
    )

    def fake_prefill(model, prompt_tokens, *, prefill_step_size: int, stream):
        seen["prefill_calls"].append(
            {
                "model": model,
                "prompt_tokens": list(prompt_tokens),
                "prefill_step_size": prefill_step_size,
                "stream": stream,
            }
        )
        return ["prompt-cache"], [13], [11, 12]

    monkeypatch.setattr(
        mlx_text_runtime_module,
        "_native_mtp_prefill_prompt_cache",
        fake_prefill,
    )
    monkeypatch.setattr(
        mlx_text_runtime_module,
        "maybe_apply_native_mtp_text_preload_patches",
        lambda _model_path, *, metadata: {
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.compatible": "true",
            "melix.native_mtp.weights_present": "true",
            "melix.native_mtp.weight_count": "15",
            "melix.native_mtp.patch_applied": "true",
            "melix.native_mtp.active": "true",
            "melix.native_mtp.reason": "",
        },
    )

    model = SimpleNamespace(
        mtp=object(),
        mtp_forward=lambda *_args, **_kwargs: None,
        _melix_native_mtp_active=True,
    )

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        return model, FakeTokenizer()

    def fake_stream_generate(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("native MTP text path should not call stream_generate")

    def fake_sampler_factory(**kwargs):
        seen["sampler"] = dict(kwargs)
        return "sampler"

    peak_memory_calls = {"count": 0}

    def fake_peak_memory(_mx):
        peak_memory_calls["count"] += 1
        return 42.0

    monkeypatch.setattr(mlx_text_runtime_module, "_mlx_peak_memory_gb", fake_peak_memory)

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=fake_sampler_factory,
    )
    model_spec = WorkerModelCatalog.dev_text_model(
        environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"}
    )
    model_spec.ext["melix.native_mtp.enabled"] = "true"
    model_spec.ext["melix.native_mtp.active"] = "true"
    model_spec.ext["melix.native_mtp.patch_applied"] = "true"
    model_spec.ext["melix.native_mtp.compatible"] = "true"
    loaded_model = backend.load_model(model_spec)

    events = list(
        backend.generate_tokens(
            loaded_model,
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=2),
            Event(),
        )
    )
    events_again = list(
        backend.generate_tokens(
            loaded_model,
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=2),
            Event(),
        )
    )

    assert seen["encoded"] == ("prompt", True)
    assert seen["init_count"] == 1
    assert seen["batch_generator_init"] == {
        "model": model,
        "max_tokens": 2,
        "stop_tokens": [[2]],
        "sampler": "sampler",
        "prefill_batch_size": 1,
        "completion_batch_size": 1,
        "prefill_step_size": 2048,
    }
    assert seen["prefill_calls"] == [
        {
            "model": model,
            "prompt_tokens": [11, 12, 13],
            "prefill_step_size": 2048,
            "stream": None,
        },
        {
            "model": model,
            "prompt_tokens": [11, 12, 13],
            "prefill_step_size": 2048,
            "stream": None,
        },
    ]
    assert seen["insert_calls"] == [
        {
            "prompts": [[13]],
            "max_tokens": [2],
            "caches": [["prompt-cache"]],
            "all_tokens": [[11, 12]],
            "samplers": ["sampler"],
        },
        {
            "prompts": [[13]],
            "max_tokens": [2],
            "caches": [["prompt-cache"]],
            "all_tokens": [[11, 12]],
            "samplers": ["sampler"],
        },
    ]
    assert seen["removed_calls"] == [[77], [77]]
    assert seen["closed"] == 0
    assert [event.text for event in events] == ["A", "B!"]
    assert [event.raw_text for event in events] == ["A", "AB!"]
    assert [event.text for event in events_again] == ["A", "B!"]
    assert [event.raw_text for event in events_again] == ["A", "AB!"]
    assert seen["detokenizer_access_count"] == 1
    assert seen["detokenizer_copy_count"] == 2
    assert len(set(seen["request_detokenizer_ids"])) == 2
    assert [event.token_logprobs for event in events] == [(), ()]
    assert [event.token_logprobs for event in events_again] == [(), ()]
    assert logprob_index_calls["count"] == 0
    assert events[0].peak_memory is None
    assert events[-1].peak_memory == 42.0
    assert events_again[0].peak_memory is None
    assert events_again[-1].peak_memory == 42.0
    assert peak_memory_calls["count"] == 2
    assert events[0].generation_tps is None
    assert events[-1].generation_tps is not None
    assert events[-1].generation_tps > 0.0
    assert events_again[0].generation_tps is None
    assert events_again[-1].generation_tps is not None
    assert events_again[-1].generation_tps > 0.0
    assert events[-1].finish_reason == "length"
    assert events[-1].completion_tokens == 2
    assert events[-1].speculative_acceptance_rate == 0.75
    assert events[-1].speculative_rollback_rate == 0.25
    assert events[-1].speculative_accepted_tokens == 3
    assert events[-1].speculative_rejected_tokens == 1
    assert events[-1].speculative_num_draft_tokens == 1
    assert events[-1].speculative_draft_model_configured is True
    assert events[-1].speculative_target_verify_ms == 12.5
    assert events[0].native_mtp_timings is None
    assert events[-1].native_mtp_timings is not None
    assert events[-1].native_mtp_timings.insert_ms is not None
    assert events[-1].native_mtp_timings.prepare_ms is not None
    assert events[-1].native_mtp_timings.prompt_encode_ms is not None
    assert events[-1].native_mtp_timings.prefill_ms is not None
    assert events[-1].native_mtp_timings.batch_insert_ms is not None
    assert events[-1].native_mtp_timings.first_response_ms is not None
    assert events[-1].native_mtp_timings.first_visible_ms is not None

    backend.close_loaded_model(loaded_model)
    assert seen["closed"] == 1


def test_native_mtp_text_patch_adds_qwen35_methods() -> None:
    import worker.runtime.native_mtp.qwen35_model as qwen35_model

    if not qwen35_model.apply():
        pytest.skip("mlx-lm Qwen3.5 model patch is unavailable")

    from mlx_lm.models.qwen3_5 import Model, TextModel, TextModelArgs

    args = TextModelArgs.from_dict(
        {
            "model_type": "qwen3_5_text",
            "hidden_size": 64,
            "intermediate_size": 128,
            "num_hidden_layers": 4,
            "num_attention_heads": 4,
            "num_key_value_heads": 2,
            "vocab_size": 256,
            "linear_num_value_heads": 2,
            "linear_num_key_heads": 2,
            "linear_key_head_dim": 16,
            "linear_value_head_dim": 16,
            "linear_conv_kernel_dim": 3,
            "full_attention_interval": 2,
            "tie_word_embeddings": True,
            "rms_norm_eps": 1e-5,
            "head_dim": 32,
            "rope_theta": 1000.0,
            "partial_rotary_factor": 0.5,
            "max_position_embeddings": 128,
            "mtp_num_hidden_layers": 1,
        }
    )

    assert getattr(args, "mtp_num_hidden_layers", None) == 1
    assert hasattr(TextModel, "mtp_forward")
    assert hasattr(TextModel, "make_mtp_cache")
    assert hasattr(TextModel, "_melix_mtp_patched")
    assert hasattr(Model, "mtp_forward")
    assert hasattr(Model, "make_mtp_cache")


def test_native_mtp_text_sanitize_allows_non_mtp_weight_shards() -> None:
    import worker.runtime.native_mtp as native_mtp
    import worker.runtime.native_mtp.qwen35_model as qwen35_model

    native_mtp.set_mtp_active(True)
    if not qwen35_model.apply():
        pytest.skip("mlx-lm Qwen3.5 model patch is unavailable")

    from mlx_lm.models.qwen3_5 import TextModel

    class FakeTextModel(TextModel):
        pass

    fake_model = FakeTextModel.__new__(FakeTextModel)
    fake_model.args = SimpleNamespace(tie_word_embeddings=False)
    fake_model.mtp = object()
    weights = {
        "language_model.model.embed_tokens.weight": SimpleNamespace(
            shape=(4, 4),
            ndim=2,
            moveaxis=lambda *_args: None,
        )
    }

    assert fake_model.sanitize(weights) == weights


def test_native_mtp_loader_discovers_extra_index_mtp_shards(tmp_path: Path) -> None:
    from worker.runtime.native_mtp.mlx_lm_loader import extra_mtp_safetensor_files

    (tmp_path / "model-00001-of-00001.safetensors").write_bytes(b"base")
    (tmp_path / "mtp-extra.safetensors").write_bytes(b"mtp")
    (tmp_path / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "weight_map": {
                    "language_model.model.embed_tokens.weight": "model-00001-of-00001.safetensors",
                    "language_model.mtp.fc.weight": "mtp-extra.safetensors",
                }
            }
        ),
        encoding="utf-8",
    )

    assert [path.name for path in extra_mtp_safetensor_files(tmp_path)] == [
        "mtp-extra.safetensors"
    ]


def test_native_mtp_batch_generator_eligibility_uses_text_model_melix_flag() -> None:
    from worker.runtime.native_mtp import batch_generator

    if not batch_generator.apply():
        pytest.skip("mlx-lm BatchGenerator patch is unavailable")

    class MtpTextModel:
        def __init__(self) -> None:
            self.mtp = object()
            self._melix_native_mtp_active = True

        def mtp_forward(self, *_args):
            return None

    gen_batch = SimpleNamespace(
        model=MtpTextModel(),
        uids=[1],
        logits_processors=[],
    )

    assert batch_generator._is_mtp_eligible(gen_batch) is True


def test_native_mtp_response_stats_are_terminal_only() -> None:
    from worker.runtime.native_mtp import batch_generator

    stats = batch_generator._MtpStats(
        cycles=2,
        accepts=1,
        rejects=1,
        backbone_ms=10.0,
        mtp_head_ms=2.0,
        sample_ms=1.0,
        cache_ops_ms=0.5,
    )

    nonterminal = SimpleNamespace()
    terminal = SimpleNamespace()

    batch_generator._attach_mtp_response_stats(
        nonterminal,
        stats,
        terminal=False,
    )
    batch_generator._attach_mtp_response_stats(
        terminal,
        stats,
        terminal=True,
    )

    assert not hasattr(nonterminal, "speculative_cycle_count")
    assert terminal.speculative_cycle_count == 2
    assert terminal.speculative_accepted_tokens == 1
    assert terminal.speculative_rejected_tokens == 1
    assert terminal.speculative_backbone_ms == 10.0
    assert terminal.speculative_mtp_head_ms == 2.0
    assert terminal.speculative_sample_ms == 1.0
    assert terminal.speculative_cache_ops_ms == 0.5


def test_auto_backend_forwards_trust_remote_code_when_loader_supports_it() -> None:
    seen: dict[str, object] = {}

    def fake_load(
        model_source: str,
        *,
        lazy: bool = False,
        trust_remote_code: bool = False,
    ):
        seen["load"] = (model_source, lazy, trust_remote_code)
        return object(), FakeTokenizer()

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "sampler",
    )

    backend.load_model(WorkerModelCatalog.dev_text_model(), trust_remote_code=True)

    assert seen["load"] == ("models/melix-dev-text", False, True)


def test_auto_backend_rejects_trust_when_loader_cannot_accept_kwarg() -> None:
    def fake_load(model_source: str, *, lazy: bool = False):  # pragma: no cover - must be blocked.
        _ = model_source, lazy
        return object(), FakeTokenizer()

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "sampler",
    )

    with pytest.raises(RuntimeError, match="trust_remote_code"):
        backend.load_model(WorkerModelCatalog.dev_text_model(), trust_remote_code=True)


def test_mlx_text_runtime_rejects_trust_when_backend_cannot_accept_kwarg() -> None:
    class LegacyBackend:
        runtime_name = "mlx-lm"

        def load_model(self, model_spec):  # pragma: no cover - must be blocked before invocation.
            return {"model_id": model_spec.model_id}

        def estimate_resident_bytes(self, model_spec) -> int:  # pragma: no cover - not used by this test.
            _ = model_spec
            return 0

    runtime = MLXTextRuntime(backend=LegacyBackend())

    with pytest.raises(RuntimeError, match="trust_remote_code"):
        runtime.load_model(WorkerModelCatalog.dev_text_model(), trust_remote_code=True)


def test_mlx_text_runtime_uses_explicit_trust_support_override() -> None:
    class BackendWithExplicitSupport:
        runtime_name = "wrapped-runtime"
        supports_trust_policy = True

        def load_model(self, model_spec):  # pragma: no cover - property checks only.
            return {"model_id": model_spec.model_id}

    class BackendWithExplicitOptOut:
        runtime_name = "mlx-lm"
        supports_trust_policy = False

        def load_model(self, model_spec):  # pragma: no cover - property checks only.
            return {"model_id": model_spec.model_id}

    assert MLXTextRuntime(backend=BackendWithExplicitSupport()).supports_trust_policy is True
    assert MLXTextRuntime(backend=BackendWithExplicitOptOut()).supports_trust_policy is False


def test_auto_backend_reuses_cached_stop_kwarg_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()
    signature_calls: dict[str, int] = {}
    stop_contract_calls = 0
    original_signature = runtime_utils.inspect.signature
    original_resolve_stop_contract = mlx_text_runtime_module.resolve_text_stop_contract

    def tracked_signature(callable_obj):
        name = getattr(callable_obj, "__name__", repr(callable_obj))
        signature_calls[name] = signature_calls.get(name, 0) + 1
        return original_signature(callable_obj)

    def tracked_resolve_stop_contract(loaded_model, sampling, execution_ext=None):
        nonlocal stop_contract_calls
        stop_contract_calls += 1
        return original_resolve_stop_contract(loaded_model, sampling, execution_ext)

    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)
    monkeypatch.setattr(mlx_text_runtime_module, "resolve_text_stop_contract", tracked_resolve_stop_contract)

    def fake_load(model_source: str, **kwargs):
        _ = (model_source, kwargs)
        return object(), FakeTokenizer()

    seen_sampler_kwargs: list[dict[str, float | int]] = []

    def fake_sampler_factory(
        *,
        temp: float,
        top_p: float,
        top_k: int,
        frequency_penalty: float,
        presence_penalty: float,
    ):
        seen_sampler_kwargs.append(
            {
                "temp": temp,
                "top_p": top_p,
                "top_k": top_k,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
            }
        )
        return "fake-sampler"

    seen_stop_values: list[list[str] | None] = []

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler, *, stop=None):
        _ = (model, tokenizer, prompt, max_tokens, sampler)
        seen_stop_values.append(stop)
        yield FakeGenerationResponse(text="ok", prompt_tokens=1, generation_tokens=1)

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=fake_sampler_factory,
    )
    loaded_model = backend.load_model(
        WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    )
    sampling = common_pb2.SamplingConfig(
        max_output_tokens=8,
        stop=["</turn>"],
        frequency_penalty=0.25,
        presence_penalty=0.5,
    )

    for _ in range(2):
        chunks = list(backend.generate_tokens(loaded_model, "prompt", sampling, Event()))
        assert [chunk.text for chunk in chunks] == ["ok"]

    assert seen_stop_values == [["</turn>", "</s>"], ["</turn>", "</s>"]]
    assert seen_sampler_kwargs == [
        {
            "temp": 0.0,
            "top_p": 0.0,
            "top_k": 0,
            "frequency_penalty": 0.25,
            "presence_penalty": 0.5,
        },
        {
            "temp": 0.0,
            "top_p": 0.0,
            "top_k": 0,
            "frequency_penalty": 0.25,
            "presence_penalty": 0.5,
        },
    ]
    assert signature_calls.get("fake_stream_generate") == 1
    assert signature_calls.get("fake_sampler_factory") == 1
    assert stop_contract_calls == 1

    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_sample_utils = types.ModuleType("mlx_lm.sample_utils")
    fake_mlx_lm.load = fake_load
    fake_mlx_lm.stream_generate = fake_stream_generate
    fake_mlx_lm.sample_utils = fake_sample_utils
    fake_sample_utils.make_sampler = fake_sampler_factory
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", fake_sample_utils)
    monkeypatch.setattr(
        mlx_text_runtime_module.importlib.util,
        "find_spec",
        lambda name: object() if name == "mlx_lm" else None,
    )
    runtime_utils.clear_callable_kwarg_signature_cache()
    signature_calls.clear()
    seen_stop_values.clear()
    seen_sampler_kwargs.clear()
    stop_contract_calls = 0

    live_backend = AutoMLXBackend()
    live_loaded_model = live_backend.load_model(
        WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    )
    chunks = list(live_backend.generate_tokens(live_loaded_model, "prompt", sampling, Event()))

    assert [chunk.text for chunk in chunks] == ["ok"]
    assert seen_stop_values == [["</turn>", "</s>"]]
    assert seen_sampler_kwargs == [
        {
            "temp": 0.0,
            "top_p": 0.0,
            "top_k": 0,
            "frequency_penalty": 0.25,
            "presence_penalty": 0.5,
        }
    ]
    assert signature_calls.get("fake_stream_generate") == 1
    assert signature_calls.get("fake_sampler_factory") == 1
    assert stop_contract_calls == 1
    runtime_utils.clear_callable_kwarg_signature_cache()


def test_cached_stream_stop_kwargs_covers_empty_fallback_and_cached_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sampling = common_pb2.SamplingConfig(max_output_tokens=8, stop=["</turn>"])
    loaded_model = {"tokenizer": FakeTokenizer()}

    assert mlx_text_runtime_module._cached_stream_stop_kwargs(
        loaded_model,
        sampling,
        None,
        "",
    ) == {}

    resolve_calls = 0
    original_resolve_stop_contract = mlx_text_runtime_module.resolve_text_stop_contract

    def tracked_resolve_stop_contract(loaded_model, sampling, execution_ext=None):
        nonlocal resolve_calls
        resolve_calls += 1
        return original_resolve_stop_contract(loaded_model, sampling, execution_ext)

    monkeypatch.setattr(
        mlx_text_runtime_module,
        "resolve_text_stop_contract",
        tracked_resolve_stop_contract,
    )

    fallback_kwargs = mlx_text_runtime_module._cached_stream_stop_kwargs(
        object(),
        sampling,
        None,
        "stop",
    )
    assert fallback_kwargs == {"stop": ["</turn>"]}
    assert resolve_calls == 1

    first_kwargs = mlx_text_runtime_module._cached_stream_stop_kwargs(
        loaded_model,
        sampling,
        None,
        "stop",
    )
    second_kwargs = mlx_text_runtime_module._cached_stream_stop_kwargs(
        loaded_model,
        sampling,
        None,
        "stop",
    )
    assert first_kwargs == {"stop": ["</turn>", "</s>"]}
    assert second_kwargs is first_kwargs
    assert resolve_calls == 2


def test_auto_backend_scores_reward_responses_with_mlx_generation() -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        return object(), FakeTokenizer()

    def fake_sampler_factory(*, temp: float, top_p: float, top_k: int):
        seen["sampler"] = {"temp": temp, "top_p": top_p, "top_k": top_k}
        return "score-sampler"

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler):
        seen["stream"] = {
            "model": model,
            "tokenizer": tokenizer,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "sampler": sampler,
        }
        yield FakeGenerationResponse(text="Score: ", prompt_tokens=8, generation_tokens=1)
        yield FakeGenerationResponse(text="87", prompt_tokens=8, generation_tokens=2)

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=fake_sampler_factory,
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/reward"})
    model_spec.ext["melix.reward_model.score_prompt_template"] = (
        "Prompt={prompt}\nResponse={response}\nReturn score:"
    )
    model_spec.ext["melix.reward_model.score_max_tokens"] = "12"
    loaded_model = backend.load_model(model_spec)

    score = backend.score_response(loaded_model, "Explain safely.", "Helpful answer.")

    assert score == pytest.approx(0.87)
    assert seen["load"] == ("mlx-community/reward", {"lazy": False})
    assert seen["sampler"] == {"temp": 0.0, "top_p": 1.0, "top_k": 1}
    assert seen["stream"] == {
        "model": loaded_model["model"],
        "tokenizer": loaded_model["tokenizer"],
        "prompt": "Prompt=Explain safely.\nResponse=Helpful answer.\nReturn score:",
        "max_tokens": 12,
        "sampler": "score-sampler",
    }


def test_reward_score_prompt_and_parser_cover_fallbacks() -> None:
    prompt = mlx_text_runtime_module._reward_score_prompt(
        {"metadata": {"melix.reward_model.scoring_prompt_template": "Metadata {prompt} {response}"}},
        prompt="Prompt",
        response="Response",
        execution_ext={
            "melix.reward_model.score_prompt_template": "Override {prompt} => {response}",
        },
    )
    assert prompt == "Override Prompt => Response"

    default_prompt = mlx_text_runtime_module._reward_score_prompt(
        object(),
        prompt="Explain safely.",
        response="Helpful answer.",
        execution_ext=None,
    )
    assert "Explain safely." in default_prompt
    assert "Helpful answer." in default_prompt
    assert mlx_text_runtime_module._reward_score_max_tokens(
        {"metadata": {"melix.reward_model.max_tokens": "12"}},
        execution_ext={"melix.reward_model.score_max_tokens": "18"},
    ) == 18
    assert mlx_text_runtime_module._reward_score_max_tokens(
        {"metadata": {"melix.reward_model.score_max_tokens": "not-an-int"}},
        execution_ext=None,
    ) == 8
    assert mlx_text_runtime_module._parse_reward_score_text("0.42") == pytest.approx(0.42)

    with pytest.raises(RuntimeUnavailableError):
        mlx_text_runtime_module._parse_reward_score_text("no numeric score")
    with pytest.raises(RuntimeUnavailableError):
        mlx_text_runtime_module._parse_reward_score_text("-0.5")


def test_auto_backend_score_response_reports_unavailable_runtime() -> None:
    backend = AutoMLXBackend(
        load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    backend._available = False
    backend._error = ModuleNotFoundError("mlx-lm is not installed")

    with pytest.raises(RuntimeUnavailableError, match="mlx-lm is not installed"):
        backend.score_response({}, "Prompt", "Response")


def test_text_stop_contract_merges_request_metadata_and_tokenizer_eos() -> None:
    contract = resolve_text_stop_contract(
        {
            "tokenizer": FakeTokenizer(),
            "metadata": {"melix.stop_sequences": '["</model>", "</request>"]'},
            "model_ext": {"melix.turn_boundary.stop_sequences": "</turn>"},
        },
        common_pb2.SamplingConfig(stop=["</request>"]),
        {"melix.stop_sequences": "</ext>"},
    )

    assert contract.sequences == ("</request>", "</model>", "</turn>", "</ext>", "</s>")
    assert contract.resolved_stop_token_count == 6
    assert contract.source == "request+model_metadata+tokenizer_eos"


def test_text_stop_contract_handles_metadata_and_tokenizer_edge_cases() -> None:
    class EosIdOnlyTokenizer:
        eos_token = ""
        eos_token_id = [2, 3, ""]

    assert mlx_text_runtime_module._split_stop_sequence_value(" ") == []
    assert mlx_text_runtime_module._split_stop_sequence_value("[not-json") == ["[not-json"]
    assert mlx_text_runtime_module._split_stop_sequence_value(["</list>", " "]) == ["</list>"]
    assert mlx_text_runtime_module._split_stop_sequence_value(42) == ["42"]

    request_only_contract = resolve_text_stop_contract(
        object(),
        common_pb2.SamplingConfig(stop=["</request>"]),
    )
    assert request_only_contract.sequences == ("</request>",)
    assert request_only_contract.resolved_stop_token_count == 1
    assert request_only_contract.source == "request"

    eos_id_contract = resolve_text_stop_contract(
        {"tokenizer": EosIdOnlyTokenizer()},
        common_pb2.SamplingConfig(),
    )
    assert eos_id_contract.sequences == ()
    assert eos_id_contract.resolved_stop_token_count == 2
    assert eos_id_contract.source == "tokenizer_eos"


def test_auto_backend_passes_resolved_stop_sequences_when_supported() -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        _ = kwargs
        return object(), FakeTokenizer()

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler, stop):
        seen["stop"] = stop
        yield FakeGenerationResponse(
            text="done",
            prompt_tokens=1,
            generation_tokens=1,
            finish_reason="stop",
        )

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=lambda **kwargs: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.ext["melix.stop_sequences"] = "</model>"
    loaded_model = backend.load_model(model_spec)

    chunks = list(
        backend.generate_tokens(
            loaded_model,
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=4, stop=["</request>"]),
            Event(),
        )
    )

    assert seen["stop"] == ["</request>", "</model>", "</s>"]
    assert [chunk.text for chunk in chunks] == ["done"]


def test_auto_backend_does_not_pass_stop_to_variadic_stream_generate() -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        _ = model_source, kwargs
        return object(), FakeTokenizer()

    def fake_stream_generate(*args, **kwargs):
        seen["kwargs"] = dict(kwargs)
        yield FakeGenerationResponse(text="done", prompt_tokens=1, generation_tokens=1, finish_reason="stop")

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=lambda **kwargs: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.ext["melix.stop_sequences"] = "</model>"
    loaded_model = backend.load_model(model_spec)

    chunks = list(
        backend.generate_tokens(
            loaded_model,
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=4, stop=["</request>"]),
            Event(),
        )
    )

    assert "stop" not in seen["kwargs"]
    assert "stop_words" not in seen["kwargs"]
    assert "stop_sequences" not in seen["kwargs"]
    assert runtime_utils.callable_declares_kwarg(42, "stop") is False
    assert [chunk.text for chunk in chunks] == ["done"]


def test_runtime_enforces_stop_sequences_across_backend_chunk_boundaries() -> None:
    class ChunkedStopBackend:
        runtime_name = "fake-stop-runtime"

        def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
            yield RuntimeTokenEvent(text="alpha<sto", prompt_tokens=1, completion_tokens=1)
            yield RuntimeTokenEvent(
                text="p>leaked",
                prompt_tokens=1,
                completion_tokens=2,
                finish_reason="length",
            )

    runtime = MLXTextRuntime(backend=ChunkedStopBackend())
    events = list(
        runtime.generate_tokens(
            {"tokenizer": FakeTokenizer()},
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=8, stop=["<stop>"]),
            Event(),
        )
    )

    assert [event.text for event in events] == ["alpha", ""]
    assert events[-1].finish_reason == "stop_sequence"


def test_runtime_stop_sequence_filter_flushes_pending_text_around_non_text_events() -> None:
    runtime = MLXTextRuntime(backend=object())

    events = list(
        runtime._apply_stop_sequences(
            [
                RuntimeTokenEvent(text="<sto", prompt_tokens=1, completion_tokens=1),
                RuntimeToolCallEvent(call_id="call-1", tool_name="lookup", arguments_json_fragment="{}"),
                RuntimeTokenEvent(text="", prompt_tokens=1, completion_tokens=2, finish_reason="length"),
            ],
            ("<stop>",),
        )
    )

    assert [type(event) for event in events] == [RuntimeTokenEvent, RuntimeToolCallEvent, RuntimeTokenEvent]
    assert events[0].text == "<sto"
    assert events[2].finish_reason == "length"


def test_runtime_stop_sequence_filter_flushes_trailing_viable_prefix() -> None:
    runtime = MLXTextRuntime(backend=object())

    events = list(
        runtime._apply_stop_sequences(
            [RuntimeTokenEvent(text="<sto", prompt_tokens=1, completion_tokens=1)],
            ("<stop>",),
        )
    )

    assert [event.text for event in events] == ["<sto"]


def test_stop_sequence_filter_reuses_max_prefix_length(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MLXTextRuntime(backend=object())
    original = mlx_text_runtime_module._stop_sequence_max_prefix_length
    calls = 0

    def counted_max_prefix_length(stop_sequences: tuple[str, ...]) -> int:
        nonlocal calls
        calls += 1
        return original(stop_sequences)

    monkeypatch.setattr(mlx_text_runtime_module, "_stop_sequence_max_prefix_length", counted_max_prefix_length)

    events = list(
        runtime._apply_stop_sequences(
            [RuntimeTokenEvent(text="chunk", prompt_tokens=1, completion_tokens=index) for index in range(25)],
            ("<stop>", "</turn>", "END"),
        )
    )

    assert calls == 1
    assert "".join(event.text for event in events) == "chunk" * 25

    assert mlx_text_runtime_module._native_mtp_text_model_active(object()) is False
    assert mlx_text_runtime_module._cached_native_mtp_text_model_active(object()) is False
    active_model = SimpleNamespace(mtp=object(), mtp_forward=lambda *_args, **_kwargs: None)
    assert mlx_text_runtime_module._native_mtp_text_model_active(
        {"metadata": {"melix.native_mtp.active": "true"}, "model": active_model}
    ) is True
    uncached_loaded_model = {"metadata": {"melix.native_mtp.active": "false"}, "model": object()}
    assert mlx_text_runtime_module._cached_native_mtp_text_model_active(uncached_loaded_model) is False
    assert uncached_loaded_model[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] is False

    def fake_load(model_source: str, **kwargs):
        _ = (model_source, kwargs)
        return object(), FakeTokenizer()

    def fake_sampler_factory(*, temp: float, top_p: float, top_k: int):
        _ = (temp, top_p, top_k)
        return "fake-sampler"

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler, *, stop=None):
        _ = (model, tokenizer, prompt, max_tokens, sampler, stop)
        yield FakeGenerationResponse(text="ok", prompt_tokens=1, generation_tokens=1)

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=fake_sampler_factory,
    )
    loaded_model = backend.load_model(
        WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    )
    assert loaded_model[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] is False

    native_mtp_active_check = Mock(side_effect=AssertionError("native MTP active state should be cached at load"))
    monkeypatch.setattr(
        mlx_text_runtime_module,
        "_native_mtp_text_model_active",
        native_mtp_active_check,
    )
    chunks = list(
        backend.generate_tokens(
            loaded_model,
            "prompt",
            common_pb2.SamplingConfig(max_output_tokens=1),
            Event(),
        )
    )
    assert [chunk.text for chunk in chunks] == ["ok"]
    native_mtp_active_check.assert_not_called()


def test_stop_sequence_filter_reuses_unmodified_token_events() -> None:
    runtime = MLXTextRuntime(backend=object())
    event = RuntimeTokenEvent(text="chunk", prompt_tokens=1, completion_tokens=1)

    events = list(runtime._apply_stop_sequences([event], ("<stop>", "</turn>")))

    assert events == [event]
    assert events[0] is event


def test_stop_sequence_filter_preserves_cumulative_raw_text_when_visible_is_unmodified() -> None:
    runtime = MLXTextRuntime(backend=object())
    first = RuntimeTokenEvent(text="Hel", raw_text="Hel", prompt_tokens=1, completion_tokens=1)
    second = RuntimeTokenEvent(
        text="lo",
        raw_text="Hello",
        prompt_tokens=1,
        completion_tokens=2,
        finish_reason="length",
    )

    events = list(runtime._apply_stop_sequences([first, second], ("<stop>", "</turn>")))

    assert [event.text for event in events] == ["Hel", "lo"]
    assert [event.raw_text for event in events] == ["Hel", "Hello"]


def test_stop_sequence_helpers_preserve_earliest_match_and_viable_suffix() -> None:
    assert mlx_text_runtime_module._first_stop_sequence_index("abcEND<stop>", ("<stop>", "END")) == 3
    assert mlx_text_runtime_module._first_stop_sequence_index("<stop>END", ("END", "<stop>")) == 0
    assert mlx_text_runtime_module._first_stop_sequence_index("no marker", ("END", "<stop>")) is None

    stop_sequences = ("<stop>", "</turn>")
    max_prefix_length = mlx_text_runtime_module._stop_sequence_max_prefix_length(stop_sequences)
    prefixes = mlx_text_runtime_module._stop_sequence_prefixes(stop_sequences, max_prefix_length)
    assert "<sto" in prefixes
    assert mlx_text_runtime_module._viable_stop_prefix_suffix("hello <sto", stop_sequences, max_prefix_length) == "<sto"
    assert (
        mlx_text_runtime_module._viable_stop_prefix_suffix(
            "hello <sto",
            stop_sequences,
            max_prefix_length,
            prefixes,
        )
        == "<sto"
    )
    assert mlx_text_runtime_module._viable_stop_prefix_suffix("hello <sto", stop_sequences) == "<sto"
    assert mlx_text_runtime_module._viable_stop_prefix_suffix("hello", stop_sequences, max_prefix_length) == ""
    assert mlx_text_runtime_module._stop_sequence_prefixes(stop_sequences, 0) == frozenset()


def test_auto_backend_records_installed_mlx_package_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(package_name: str) -> str:
        return {
            "mlx": "0.31.2",
            "mlx-lm": "0.31.3",
        }[package_name]

    monkeypatch.setattr(mlx_text_runtime_module, "_installed_package_version", fake_version)
    backend = AutoMLXBackend(
        load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )

    loaded_model = backend.load_model(WorkerModelCatalog.dev_text_model())

    assert loaded_model["mlx_version"] == "0.31.2"
    assert loaded_model["mlx_lm_version"] == "0.31.3"


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


def test_auto_backend_retries_adapter_backed_quantized_load_without_strict(
    monkeypatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        raise ValueError("Received 126 parameters not in model: language_model.layer.weight")

    fake_utils = types.ModuleType("mlx_lm.utils")

    def fake_download(model_source: str, **kwargs):
        seen["download"] = (model_source, kwargs)
        return "/tmp/downloaded-model"

    def fake_load_model(model_source: str, **kwargs):
        seen["load_model"] = (model_source, kwargs)
        return object(), {"eos_token_id": 2}

    def fake_load_adapters(model, adapter_path: str):
        seen["load_adapters"] = (model, adapter_path)

        class AdapterModel:
            def eval(self) -> None:
                seen["adapter_eval"] = True

        return AdapterModel()

    def fake_load_tokenizer(model_source: str, tokenizer_config=None, eos_token_ids=None):
        seen["load_tokenizer"] = (model_source, tokenizer_config, eos_token_ids)
        return FakeTokenizer()

    fake_utils._download = fake_download
    fake_utils.load_adapters = fake_load_adapters
    fake_utils.load_model = fake_load_model
    fake_utils.load_tokenizer = fake_load_tokenizer
    monkeypatch.setitem(sys.modules, "mlx_lm.utils", fake_utils)

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
    model_spec.ext["melix.adapter_manifest_path"] = "/tmp/melix-train/train_lora.adapter.json"
    model_spec.ext["melix.adapter_weights_path"] = "/tmp/melix-train/weights/adapters.safetensors"

    loaded_model = backend.load_model(model_spec)

    assert seen["load"] == (
        "mlx-community/test-model",
        {
            "lazy": False,
            "adapter_path": str(Path("/tmp/melix-train/weights").resolve()),
        },
    )
    assert seen["download"] == ("mlx-community/test-model", {"revision": "dev"})
    assert seen["load_model"] == (
        "/tmp/downloaded-model",
        {
            "lazy": False,
            "strict": False,
        },
    )
    assert seen["load_adapters"][1] == str(Path("/tmp/melix-train/weights").resolve())
    assert seen["adapter_eval"] is True
    assert seen["load_tokenizer"] == ("/tmp/downloaded-model", None, 2)
    assert loaded_model["activation_mode"] == "adapter_backed_runtime"


def test_auto_backend_retries_adapter_backed_quantized_load_with_supported_trust_remote_code(
    monkeypatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_load(model_source: str, **kwargs):
        seen["load"] = (model_source, kwargs)
        raise ValueError("Received 3 parameters not in model: language_model.layer.weight")

    fake_utils = types.ModuleType("mlx_lm.utils")

    def fake_download(model_source: str, *, revision=None, trust_remote_code=False):
        seen["download"] = (model_source, revision, trust_remote_code)
        return "/tmp/downloaded-trust-model"

    def fake_load_model(model_source: str, *, lazy: bool, strict: bool, trust_remote_code=False):
        seen["load_model"] = (model_source, lazy, strict, trust_remote_code)
        return object(), {"eos_token_id": 7}

    def fake_load_adapters(model, adapter_path: str):
        seen["load_adapters"] = (model, adapter_path)

        class AdapterModel:
            def eval(self) -> None:
                seen["adapter_eval"] = True

        return AdapterModel()

    def fake_load_tokenizer(model_source: str, tokenizer_config=None, eos_token_ids=None):
        seen["load_tokenizer"] = (model_source, tokenizer_config, eos_token_ids)
        return FakeTokenizer()

    fake_utils._download = fake_download
    fake_utils.load_adapters = fake_load_adapters
    fake_utils.load_model = fake_load_model
    fake_utils.load_tokenizer = fake_load_tokenizer
    monkeypatch.setitem(sys.modules, "mlx_lm.utils", fake_utils)

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})
    model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
    model_spec.ext["melix.adapter_manifest_path"] = "/tmp/melix-train/train_lora.adapter.json"
    model_spec.ext["melix.adapter_weights_path"] = "/tmp/melix-train/weights/adapters.safetensors"

    backend.load_model(model_spec, trust_remote_code=True)

    assert seen["load"] == (
        "mlx-community/test-model",
        {
            "lazy": False,
            "trust_remote_code": True,
            "adapter_path": str(Path("/tmp/melix-train/weights").resolve()),
        },
    )
    assert seen["download"] == ("mlx-community/test-model", "dev", True)
    assert seen["load_model"] == ("/tmp/downloaded-trust-model", False, False, True)
    assert seen["adapter_eval"] is True
    assert seen["load_tokenizer"] == ("/tmp/downloaded-trust-model", None, 7)


def test_auto_backend_reraises_non_adapter_unmatched_load_error() -> None:
    def fake_load(model_source: str, **kwargs):
        _ = model_source
        _ = kwargs
        raise ValueError("Received 3 parameters not in model: language_model.layer.weight")

    backend = AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "unused",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/test-model"})

    with pytest.raises(ValueError, match="parameters not in model"):
        backend.load_model(model_spec)


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


def test_auto_backend_passes_sampling_penalties_when_sampler_accepts_them() -> None:
    seen: dict[str, object] = {}

    def fake_make_sampler(
        *,
        temp: float,
        top_p: float,
        top_k: int,
        frequency_penalty: float,
        presence_penalty: float,
    ):
        seen["sampler"] = {
            "temp": temp,
            "top_p": top_p,
            "top_k": top_k,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }
        return "penalty-aware-sampler"

    def fake_stream_generate(model, tokenizer, prompt: str, max_tokens: int, sampler):
        seen["stream"] = {"sampler": sampler, "max_tokens": max_tokens}
        yield FakeGenerationResponse(text="token", prompt_tokens=3, generation_tokens=1, finish_reason="stop")

    backend = AutoMLXBackend(
        load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=fake_stream_generate,
        sampler_factory=fake_make_sampler,
    )
    loaded_model = backend.load_model(WorkerModelCatalog.dev_text_model())

    list(
        backend.generate_tokens(
            loaded_model,
            "prompt",
            common_pb2.SamplingConfig(
                temperature=0.25,
                top_p=0.75,
                top_k=5,
                frequency_penalty=0.4,
                presence_penalty=0.6,
                max_output_tokens=9,
            ),
            Event(),
        )
    )

    assert seen["sampler"]["temp"] == pytest.approx(0.25)
    assert seen["sampler"]["top_p"] == pytest.approx(0.75)
    assert seen["sampler"]["top_k"] == 5
    assert seen["sampler"]["frequency_penalty"] == pytest.approx(0.4)
    assert seen["sampler"]["presence_penalty"] == pytest.approx(0.6)
    assert seen["stream"] == {"sampler": "penalty-aware-sampler", "max_tokens": 9}


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


def test_auto_backend_estimates_resident_bytes_from_model_weights(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"weights")
    backend = AutoMLXBackend(
        load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model()
    model_spec.model_path = str(model_dir)

    assert backend.estimate_resident_bytes(model_spec) == len(b"weights")


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


# ---------------------------------------------------------------------------
# _estimate_cache_bytes
# ---------------------------------------------------------------------------


def test_estimate_cache_bytes_returns_zero_for_empty_and_none() -> None:
    from worker.runtime.mlx_text_runtime import _estimate_cache_bytes

    assert _estimate_cache_bytes([]) == 0
    assert _estimate_cache_bytes(None) == 0  # type: ignore[arg-type]
    assert _estimate_cache_bytes("not-a-list") == 0  # type: ignore[arg-type]


def test_estimate_cache_bytes_sums_nbytes_from_layered_state() -> None:
    from worker.runtime.mlx_text_runtime import _estimate_cache_bytes

    class FakeTensor:
        def __init__(self, n: int) -> None:
            self.nbytes = n

    class FakeLayerCache:
        def __init__(self, tensors) -> None:
            self.state = tensors

    cache = [
        FakeLayerCache([FakeTensor(100), FakeTensor(200)]),
        FakeLayerCache([FakeTensor(50)]),
    ]
    assert _estimate_cache_bytes(cache) == 350


def test_estimate_cache_bytes_handles_size_itemsize_fallback() -> None:
    from worker.runtime.mlx_text_runtime import _estimate_cache_bytes

    class FakeTensorNoNbytes:
        size = 10
        itemsize = 4

    class FakeLayerCache:
        state = [FakeTensorNoNbytes()]

    assert _estimate_cache_bytes([FakeLayerCache()]) == 40


def test_estimate_cache_bytes_handles_scalar_state_with_nbytes() -> None:
    from worker.runtime.mlx_text_runtime import _estimate_cache_bytes

    class FakeScalarState:
        nbytes = 512

    class FakeLayerCache:
        state = FakeScalarState()

    assert _estimate_cache_bytes([FakeLayerCache()]) == 512


def _install_fake_trim(monkeypatch, *, returns):
    """Install a fake mlx_lm.models.cache.trim_prompt_cache returning `returns`."""
    import types as _types
    calls = []

    def fake_trim(cache, n):
        calls.append((cache, n))
        if isinstance(returns, Exception):
            raise returns
        return returns

    mod = sys.modules.get("mlx_lm.models.cache") or _types.ModuleType("mlx_lm.models.cache")
    mod.trim_prompt_cache = fake_trim  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", mod)
    return calls


def test_trim_restored_cache_noop_for_zero_or_negative() -> None:
    from worker.runtime.mlx_text_runtime import _trim_restored_cache

    assert _trim_restored_cache([SimpleNamespace()], 0) is True
    assert _trim_restored_cache([SimpleNamespace()], -3) is True


def test_trim_restored_cache_exact_trim_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from worker.runtime.mlx_text_runtime import _trim_restored_cache

    calls = _install_fake_trim(monkeypatch, returns=4)
    cache = [SimpleNamespace(state=[])]
    assert _trim_restored_cache(cache, 4) is True
    assert calls == [(cache, 4)]


def test_trim_restored_cache_partial_trim_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from worker.runtime.mlx_text_runtime import _trim_restored_cache

    # trim_prompt_cache could only trim 2 of the requested 4 (e.g. rotating cache).
    _install_fake_trim(monkeypatch, returns=2)
    assert _trim_restored_cache([SimpleNamespace()], 4) is False


def test_trim_restored_cache_exception_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from worker.runtime.mlx_text_runtime import _trim_restored_cache

    _install_fake_trim(monkeypatch, returns=RuntimeError("cannot trim"))
    assert _trim_restored_cache([SimpleNamespace()], 4) is False


def test_estimate_cache_bytes_skips_layer_with_none_state() -> None:
    from worker.runtime.mlx_text_runtime import _estimate_cache_bytes

    class FakeLayerNoState:
        pass

    assert _estimate_cache_bytes([FakeLayerNoState()]) == 0


def test_generate_native_mtp_invalid_block_size_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers except (ValueError, TypeError) in block_size parsing (line ~1287)."""
    fake_core = _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_lm_cache(monkeypatch, fake_core)

    from worker.runtime import prefix_block_store as _pbs
    mock_store = _pbs.PrefixBlockStore()
    monkeypatch.setattr(_pbs, "get_store", lambda *a, **kw: mock_store)
    monkeypatch.setattr(mlx_text_runtime_module, "_get_prefix_store", lambda *a, **kw: mock_store)
    monkeypatch.setattr(mlx_text_runtime_module, "_clone_cache_snapshot", lambda cache: None)
    monkeypatch.setattr(mlx_text_runtime_module, "_estimate_cache_bytes", lambda cache: 0)

    def fake_prefill(model, tokens, *, prefill_step_size, stream, restore_cache=None, restore_token_count=0):
        return [SimpleNamespace(state=[])], [int(tokens[-1])], list(tokens[:-1])

    monkeypatch.setattr(mlx_text_runtime_module, "_native_mtp_prefill_prompt_cache", fake_prefill)

    class FakeBatchGenerator:
        stream = None
        def __init__(self, model, **kwargs) -> None: pass  # pragma: no cover
        def insert(self, tokens, max_tokens, caches, all_tokens, samplers): return [77]
        def next_generated(self):
            return [SimpleNamespace(uid=77, token=1, finish_reason="stop",
                speculative_acceptance_rate=None, speculative_rollback_rate=None,
                speculative_accepted_tokens=None, speculative_rejected_tokens=None,
                speculative_num_draft_tokens=None, speculative_draft_model_configured=None,
                speculative_backbone_ms=None, speculative_cycle_count=None,
                speculative_mtp_head_ms=None, speculative_sample_ms=None,
                speculative_cache_ops_ms=None)]
        def remove(self, uids) -> None: pass  # pragma: no cover

    monkeypatch.setattr(mlx_text_runtime_module, "_load_mlx_batch_generator_class", lambda: FakeBatchGenerator)
    monkeypatch.setattr(mlx_text_runtime_module, "maybe_apply_native_mtp_text_preload_patches",
        lambda _path, *, metadata: {"melix.native_mtp.enabled": "true", "melix.native_mtp.compatible": "true",
            "melix.native_mtp.weights_present": "true", "melix.native_mtp.weight_count": "1",
            "melix.native_mtp.patch_applied": "true", "melix.native_mtp.active": "true", "melix.native_mtp.reason": ""})

    class FakeTokenizer:
        eos_token = "</s>"
        eos_token_id = 2
        detokenizer = SimpleNamespace(tokens=[], reset=lambda: None,
            add_token=lambda t: None, last_segment="x", finalize=lambda: None)
        def encode(self, prompt, add_special_tokens=True): return [1, 2, 3, 4]

    def fake_load(s, **kw): return SimpleNamespace(), FakeTokenizer()

    backend = mlx_text_runtime_module.AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *a, **kw: iter([]),  # pragma: no cover
        sampler_factory=lambda **kw: "s",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "x"})
    for k in ["melix.native_mtp.enabled", "melix.native_mtp.active",
              "melix.native_mtp.patch_applied", "melix.native_mtp.compatible"]:
        model_spec.ext[k] = "true"
    loaded = backend.load_model(model_spec)
    loaded[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] = True

    import threading
    # Non-integer value hits the except branch.
    events = list(backend.generate_tokens(
        loaded, "hi", common_pb2.SamplingConfig(max_output_tokens=1), threading.Event(),
        execution_ext={"_melix.session_id": "s", "_melix.block_size": "not-an-int"},
    ))
    assert len(events) > 0
    # Negative value parses as an int but trips the < 1 guard → default.
    events = list(backend.generate_tokens(
        loaded, "hi", common_pb2.SamplingConfig(max_output_tokens=1), threading.Event(),
        execution_ext={"_melix.session_id": "s2", "_melix.block_size": "-5"},
    ))
    assert len(events) > 0


# ---------------------------------------------------------------------------
# _native_mtp_prefill_prompt_cache — restore_cache path
# ---------------------------------------------------------------------------


def _install_fake_mlx_lm_cache(monkeypatch: pytest.MonkeyPatch, fake_core: types.ModuleType) -> None:
    import types as _types

    mlx_lm_models_cache = _types.ModuleType("mlx_lm.models.cache")

    def fake_make_prompt_cache(_model):  # pragma: no cover
        return [SimpleNamespace(state=[])]

    mlx_lm_models_cache.make_prompt_cache = fake_make_prompt_cache  # type: ignore[attr-defined]
    mlx_lm = sys.modules.get("mlx_lm") or _types.ModuleType("mlx_lm")
    mlx_lm_models = getattr(mlx_lm, "models", None) or _types.ModuleType("mlx_lm.models")
    monkeypatch.setitem(sys.modules, "mlx_lm", mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.models", mlx_lm_models)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", mlx_lm_models_cache)


def test_native_mtp_prefill_prompt_cache_restore_early_return_for_single_token_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_core = _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_lm_cache(monkeypatch, fake_core)
    from worker.runtime.mlx_text_runtime import _native_mtp_prefill_prompt_cache

    restore_cache = [SimpleNamespace(state=[])]
    model_calls: list[object] = []

    def fake_model(arr, cache=None):  # pragma: no cover
        model_calls.append(arr)

    result_cache, last_token, cached_tokens = _native_mtp_prefill_prompt_cache(
        fake_model,
        [1, 2, 3, 4, 5],
        prefill_step_size=4,
        stream=None,
        restore_cache=restore_cache,
        restore_token_count=4,
    )

    assert result_cache is restore_cache
    assert last_token == [5]
    assert cached_tokens == [1, 2, 3, 4]
    assert model_calls == []


def test_native_mtp_prefill_prompt_cache_restore_runs_suffix_prefill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_core = _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_lm_cache(monkeypatch, fake_core)

    eval_calls: list[object] = []

    class FakeArray:
        def __init__(self, tokens: list[int]) -> None:
            self._tokens = list(tokens)

        def __getitem__(self, idx):
            if isinstance(idx, tuple) and len(idx) == 2:
                col_idx = idx[1]
                if isinstance(col_idx, slice) and col_idx.start is not None:
                    return FakeArray(self._tokens[col_idx.start:])
            return FakeArray(self._tokens)

        @property
        def shape(self):
            return (1, len(self._tokens))

    fake_core.array = lambda data, *a, **kw: FakeArray(list(data))  # type: ignore[attr-defined]
    fake_core.eval = lambda items: eval_calls.append(items)  # type: ignore[attr-defined]

    from worker.runtime.mlx_text_runtime import _native_mtp_prefill_prompt_cache

    restore_cache = [SimpleNamespace(state=[])]
    model_calls: list[object] = []

    def fake_model(arr, cache=None):
        model_calls.append(arr)

    result_cache, last_token, cached_tokens = _native_mtp_prefill_prompt_cache(
        fake_model,
        [1, 2, 3, 4, 5, 6, 7, 8],
        prefill_step_size=4,
        stream=None,
        restore_cache=restore_cache,
        restore_token_count=4,
    )

    assert result_cache is restore_cache
    assert last_token == [8]
    assert cached_tokens[:4] == [1, 2, 3, 4]
    assert len(model_calls) > 0


# ---------------------------------------------------------------------------
# _generate_native_mtp_batch_tokens — LCP store integration
# ---------------------------------------------------------------------------


def test_generate_native_mtp_lcp_store_consulted_with_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers LCP ext-extraction and store query code paths."""
    fake_core = _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_lm_cache(monkeypatch, fake_core)

    from worker.runtime import prefix_block_store as _pbs

    mock_store = _pbs.PrefixBlockStore()
    monkeypatch.setattr(_pbs, "get_store", lambda *a, **kw: mock_store)
    monkeypatch.setattr(mlx_text_runtime_module, "_get_prefix_store", lambda *a, **kw: mock_store)
    monkeypatch.setattr(mlx_text_runtime_module, "_clone_cache_snapshot", lambda cache: None)
    monkeypatch.setattr(mlx_text_runtime_module, "_estimate_cache_bytes", lambda cache: 0)

    def fake_prefill(model, tokens, *, prefill_step_size, stream, restore_cache=None, restore_token_count=0):
        cache = restore_cache if restore_cache is not None else [SimpleNamespace(state=[])]
        return cache, [int(tokens[-1])], list(tokens[:-1])

    monkeypatch.setattr(mlx_text_runtime_module, "_native_mtp_prefill_prompt_cache", fake_prefill)

    class FakeResponse:
        uid = 77
        token = 101
        finish_reason = "stop"
        speculative_acceptance_rate = None
        speculative_rollback_rate = None
        speculative_accepted_tokens = None
        speculative_rejected_tokens = None
        speculative_num_draft_tokens = None
        speculative_draft_model_configured = None
        speculative_backbone_ms = None
        speculative_cycle_count = None
        speculative_mtp_head_ms = None
        speculative_sample_ms = None
        speculative_cache_ops_ms = None

    class FakeBatchGenerator:
        stream = None

        def __init__(self, model, **kwargs) -> None:  # pragma: no cover
            pass

        def insert(self, tokens, max_tokens, caches, all_tokens, samplers):
            return [77]

        def next_generated(self):
            return [FakeResponse()]

        def remove(self, uids) -> None:  # pragma: no cover
            pass

    monkeypatch.setattr(mlx_text_runtime_module, "_load_mlx_batch_generator_class", lambda: FakeBatchGenerator)
    monkeypatch.setattr(
        mlx_text_runtime_module,
        "maybe_apply_native_mtp_text_preload_patches",
        lambda _path, *, metadata: {
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.compatible": "true",
            "melix.native_mtp.weights_present": "true",
            "melix.native_mtp.weight_count": "1",
            "melix.native_mtp.patch_applied": "true",
            "melix.native_mtp.active": "true",
            "melix.native_mtp.reason": "",
        },
    )

    class FakeDetokenizer:
        tokens: list[int] = []

        def reset(self) -> None:
            self.tokens = []

        def add_token(self, token: int) -> None:
            self.tokens.append(token)

        @property
        def last_segment(self) -> str:  # pragma: no cover
            return "x"

        def finalize(self) -> None:  # pragma: no cover
            pass

    class FakeTokenizer:
        eos_token = "</s>"
        eos_token_id = 2
        detokenizer = FakeDetokenizer()

        def encode(self, prompt: str, add_special_tokens: bool = True):
            return [10, 20, 30, 40, 50, 60, 70, 80]

    def fake_load(model_source: str, **kwargs):
        return SimpleNamespace(_melix_native_mtp_active=True), FakeTokenizer()

    def fake_stream_generate(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("LCP test should not call stream_generate")

    backend = mlx_text_runtime_module.AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=lambda **kw: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model(
        environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/lcp-test"}
    )
    model_spec.ext["melix.native_mtp.enabled"] = "true"
    model_spec.ext["melix.native_mtp.active"] = "true"
    model_spec.ext["melix.native_mtp.patch_applied"] = "true"
    model_spec.ext["melix.native_mtp.compatible"] = "true"
    loaded_model = backend.load_model(model_spec)
    loaded_model[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] = True

    import threading

    events = list(
        backend.generate_tokens(
            loaded_model,
            "hello world",
            common_pb2.SamplingConfig(max_output_tokens=2),
            threading.Event(),
            execution_ext={
                "_melix.session_id": "lcp-session-99",
                "_melix.model_id": "test-model",
                "_melix.model_revision": "v1",
                "_melix.block_size": "4",
                "_melix.acceleration_mode": "",
            },
        )
    )

    assert len(events) > 0
    final = events[-1]
    assert final.cache_hit_mode == "none"
    assert final.recovered_prefix_tokens == 0


def test_generate_native_mtp_lcp_warm_path_uses_restored_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers the _use_lcp=True code path (lines ~1308-1344, 1449-1453)."""
    fake_core = _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_lm_cache(monkeypatch, fake_core)

    from worker.runtime import prefix_block_store as _pbs
    from worker.runtime.prefix_block_store import PrefixBlockStore

    mock_store = PrefixBlockStore()
    mock_store.put(
        session_id="warm-session",
        token_ids=[10, 20, 30, 40, 50, 60, 70, 80],
        cache_snapshot={"data": "warm-cache"},
        cache_mode="CACHE_MODE_TIERED",
        model_id="test-model",
        model_revision="v1",
        block_size=4,
        total_bytes=512,
    )

    monkeypatch.setattr(_pbs, "get_store", lambda *a, **kw: mock_store)
    monkeypatch.setattr(mlx_text_runtime_module, "_get_prefix_store", lambda *a, **kw: mock_store)
    monkeypatch.setattr(
        mlx_text_runtime_module,
        "_clone_cache_snapshot",
        lambda cache: [SimpleNamespace(state=[])] if cache is not None else None,
    )
    monkeypatch.setattr(mlx_text_runtime_module, "_estimate_cache_bytes", lambda cache: 0)

    def fake_prefill(model, tokens, *, prefill_step_size, stream, restore_cache=None, restore_token_count=0):
        cache = restore_cache if restore_cache is not None else [SimpleNamespace(state=[])]
        return cache, [int(tokens[-1])], list(tokens[:-1])

    monkeypatch.setattr(mlx_text_runtime_module, "_native_mtp_prefill_prompt_cache", fake_prefill)

    class FakeResponse:
        uid = 77
        token = 101
        finish_reason = "stop"
        speculative_acceptance_rate = None
        speculative_rollback_rate = None
        speculative_accepted_tokens = None
        speculative_rejected_tokens = None
        speculative_num_draft_tokens = None
        speculative_draft_model_configured = None
        speculative_backbone_ms = None
        speculative_cycle_count = None
        speculative_mtp_head_ms = None
        speculative_sample_ms = None
        speculative_cache_ops_ms = None

    class FakeBatchGenerator:
        stream = None

        def __init__(self, model, **kwargs) -> None:  # pragma: no cover
            pass

        def insert(self, tokens, max_tokens, caches, all_tokens, samplers):
            return [77]

        def next_generated(self):
            return [FakeResponse()]

        def remove(self, uids) -> None:  # pragma: no cover
            pass

    monkeypatch.setattr(mlx_text_runtime_module, "_load_mlx_batch_generator_class", lambda: FakeBatchGenerator)
    monkeypatch.setattr(
        mlx_text_runtime_module,
        "maybe_apply_native_mtp_text_preload_patches",
        lambda _path, *, metadata: {
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.compatible": "true",
            "melix.native_mtp.weights_present": "true",
            "melix.native_mtp.weight_count": "1",
            "melix.native_mtp.patch_applied": "true",
            "melix.native_mtp.active": "true",
            "melix.native_mtp.reason": "",
        },
    )

    class FakeDetokenizer:
        tokens: list[int] = []

        def reset(self) -> None:
            self.tokens = []

        def add_token(self, token: int) -> None:
            self.tokens.append(token)

        @property
        def last_segment(self) -> str:  # pragma: no cover
            return "x"

        def finalize(self) -> None:  # pragma: no cover
            pass

    class FakeTokenizer:
        eos_token = "</s>"
        eos_token_id = 2
        detokenizer = FakeDetokenizer()

        def encode(self, prompt: str, add_special_tokens: bool = True):
            return [10, 20, 30, 40, 50, 60, 70, 80]

    def fake_load(model_source: str, **kwargs):
        return SimpleNamespace(_melix_native_mtp_active=True), FakeTokenizer()

    def fake_stream_generate(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("warm path test should not call stream_generate")

    backend = mlx_text_runtime_module.AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=fake_stream_generate,
        sampler_factory=lambda **kw: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model(
        environment={"MELIX_DEV_TEXT_MODEL_PATH": "mlx-community/lcp-warm-test"}
    )
    model_spec.ext["melix.native_mtp.enabled"] = "true"
    model_spec.ext["melix.native_mtp.active"] = "true"
    model_spec.ext["melix.native_mtp.patch_applied"] = "true"
    model_spec.ext["melix.native_mtp.compatible"] = "true"
    loaded_model = backend.load_model(model_spec)
    loaded_model[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] = True

    import threading

    events = list(
        backend.generate_tokens(
            loaded_model,
            "hello world",
            common_pb2.SamplingConfig(max_output_tokens=2),
            threading.Event(),
            execution_ext={
                "_melix.session_id": "warm-session",
                "_melix.model_id": "test-model",
                "_melix.model_revision": "v1",
                "_melix.block_size": "4",
                "_melix.acceleration_mode": "",
            },
        )
    )

    assert len(events) > 0
    final = events[-1]
    assert final.cache_hit_mode in ("partial", "exact")


def _build_lcp_backend(monkeypatch, *, store, clone_fn, responses, encode_tokens=None,
                       trim_returns=None, prefill_calls=None):
    """Build an MTP-active backend wired to a mock prefix store for LCP tests."""
    fake_core = _install_fake_mlx_core(monkeypatch)
    _install_fake_mlx_lm_cache(monkeypatch, fake_core)

    from worker.runtime import prefix_block_store as _pbs

    monkeypatch.setattr(_pbs, "get_store", lambda *a, **kw: store)
    monkeypatch.setattr(mlx_text_runtime_module, "_get_prefix_store", lambda *a, **kw: store)
    monkeypatch.setattr(mlx_text_runtime_module, "_clone_cache_snapshot", clone_fn)
    monkeypatch.setattr(mlx_text_runtime_module, "_estimate_cache_bytes", lambda cache: 0)
    if trim_returns is not None:
        _install_fake_trim(monkeypatch, returns=trim_returns)

    tokens_to_encode = encode_tokens or [10, 20, 30, 40, 50, 60, 70, 80]

    def fake_prefill(model, tokens, *, prefill_step_size, stream, restore_cache=None, restore_token_count=0):
        if prefill_calls is not None:
            prefill_calls.append({"restore_cache": restore_cache, "restore_token_count": restore_token_count})
        cache = restore_cache if restore_cache is not None else [SimpleNamespace(state=[])]
        return cache, [int(tokens[-1])], list(tokens[:-1])

    monkeypatch.setattr(mlx_text_runtime_module, "_native_mtp_prefill_prompt_cache", fake_prefill)

    class FakeBatchGenerator:
        stream = None
        def __init__(self, model, **kwargs) -> None: pass  # pragma: no cover
        def insert(self, tokens, max_tokens, caches, all_tokens, samplers): return [77]
        def next_generated(self): return responses
        def remove(self, uids) -> None: pass  # pragma: no cover

    monkeypatch.setattr(mlx_text_runtime_module, "_load_mlx_batch_generator_class", lambda: FakeBatchGenerator)
    monkeypatch.setattr(mlx_text_runtime_module, "maybe_apply_native_mtp_text_preload_patches",
        lambda _path, *, metadata: {"melix.native_mtp.enabled": "true", "melix.native_mtp.compatible": "true",
            "melix.native_mtp.weights_present": "true", "melix.native_mtp.weight_count": "1",
            "melix.native_mtp.patch_applied": "true", "melix.native_mtp.active": "true", "melix.native_mtp.reason": ""})

    class FakeDetokenizer:
        tokens: list[int] = []
        def reset(self) -> None: self.tokens = []
        def add_token(self, token: int) -> None: self.tokens.append(token)
        @property
        def last_segment(self) -> str: return "x"
        def finalize(self) -> None: pass

    class FakeTokenizer:
        eos_token = "</s>"
        eos_token_id = 2
        detokenizer = FakeDetokenizer()
        def encode(self, prompt, add_special_tokens=True): return list(tokens_to_encode)

    def fake_load(s, **kw): return SimpleNamespace(_melix_native_mtp_active=True), FakeTokenizer()

    backend = mlx_text_runtime_module.AutoMLXBackend(
        load_fn=fake_load,
        stream_generate_fn=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no stream_generate")),  # pragma: no cover
        sampler_factory=lambda **kw: "sampler",
    )
    model_spec = WorkerModelCatalog.dev_text_model(environment={"MELIX_DEV_TEXT_MODEL_PATH": "x"})
    for k in ("melix.native_mtp.enabled", "melix.native_mtp.active",
              "melix.native_mtp.patch_applied", "melix.native_mtp.compatible"):
        model_spec.ext[k] = "true"
    loaded = backend.load_model(model_spec)
    loaded[mlx_text_runtime_module._NATIVE_MTP_TEXT_ACTIVE_FIELD] = True
    return backend, loaded


def _mtp_response(**overrides):
    base = dict(uid=77, token=101, finish_reason="stop",
        speculative_acceptance_rate=None, speculative_rollback_rate=None,
        speculative_accepted_tokens=None, speculative_rejected_tokens=None,
        speculative_num_draft_tokens=None, speculative_draft_model_configured=None,
        speculative_backbone_ms=None, speculative_cycle_count=None,
        speculative_mtp_head_ms=None, speculative_sample_ms=None, speculative_cache_ops_ms=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_generate_native_mtp_lcp_clone_failure_releases_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers the failed-clone branch that releases the ref and falls back to cold prefill."""
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    store.put(
        session_id="clone-fail-session",
        token_ids=[10, 20, 30, 40, 50, 60, 70, 80],
        cache_snapshot=[SimpleNamespace(state=[])],
        cache_mode="CACHE_MODE_TIERED",
        model_id="test-model",
        model_revision="v1",
        block_size=4,
        total_bytes=512,
    )

    # Clone returns None on the warm hit (forcing the fallback+release branch),
    # but the post-prefill store update also calls clone — return None there too.
    clone_calls = {"n": 0}

    def clone_fn(cache):
        clone_calls["n"] += 1
        return None

    backend, loaded = _build_lcp_backend(
        monkeypatch, store=store, clone_fn=clone_fn, responses=[_mtp_response()]
    )

    import threading
    events = list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=2), threading.Event(),
        execution_ext={"_melix.session_id": "clone-fail-session", "_melix.model_id": "test-model",
            "_melix.model_revision": "v1", "_melix.block_size": "4"},
    ))

    assert len(events) > 0
    # Clone was attempted (warm hit) and failed → fell back; ref released cleanly.
    assert clone_calls["n"] >= 1
    # No active refs leaked.
    entry = store.acquire("clone-fail-session")
    assert entry is not None
    assert entry._active_refs == 1
    store.release(entry)


def test_generate_native_mtp_emits_nonterminal_then_terminal_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers the non-terminal event branch (cache metrics omitted until finish)."""
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    backend, loaded = _build_lcp_backend(
        monkeypatch,
        store=store,
        clone_fn=lambda cache: None,
        responses=[_mtp_response(finish_reason=None, token=55), _mtp_response(token=66)],
    )

    import threading
    events = list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=4), threading.Event(),
        execution_ext={"_melix.session_id": "nonterminal-session", "_melix.model_id": "test-model",
            "_melix.model_revision": "v1", "_melix.block_size": "4"},
    ))

    assert len(events) >= 2
    # First (non-terminal) event carries no cache metrics.
    assert events[0].cache_hit_mode is None
    assert events[0].recovered_prefix_tokens is None
    # Terminal event carries them.
    assert events[-1].cache_hit_mode == "none"


def test_generate_native_mtp_partial_hit_trims_stale_tail_before_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial hit must trim the stored tail (stored_len - recovered) before replay."""
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    # Stored prompt is 8 tokens; new prompt shares only the first block of 4.
    store.put(
        session_id="partial-session",
        token_ids=[10, 20, 30, 40, 50, 60, 70, 80],
        cache_snapshot=[SimpleNamespace(state=[])],
        cache_mode="CACHE_MODE_TIERED",
        model_id="test-model",
        model_revision="v1",
        block_size=4,
        total_bytes=512,
    )

    prefill_calls: list[dict] = []
    backend, loaded = _build_lcp_backend(
        monkeypatch,
        store=store,
        clone_fn=lambda cache: [SimpleNamespace(state=[])] if cache is not None else None,
        responses=[_mtp_response()],
        encode_tokens=[10, 20, 30, 40, 99, 99, 99, 99],  # shares block 1, diverges in block 2
        trim_returns=4,  # stored_len(8) - recovered(4) = 4 trimmed successfully
        prefill_calls=prefill_calls,
    )

    import threading
    events = list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=2), threading.Event(),
        execution_ext={"_melix.session_id": "partial-session", "_melix.model_id": "test-model",
            "_melix.model_revision": "v1", "_melix.block_size": "4"},
    ))

    assert len(events) > 0
    assert events[-1].cache_hit_mode == "partial"
    assert events[-1].recovered_prefix_tokens == 4
    # Suffix prefill ran with the trimmed restored cache at the recovered boundary.
    warm_calls = [c for c in prefill_calls if c["restore_cache"] is not None]
    assert warm_calls and warm_calls[0]["restore_token_count"] == 4


def test_generate_native_mtp_partial_hit_falls_back_when_trim_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the stale tail cannot be fully trimmed, fall back to a cold prefill (no reuse)."""
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    store.put(
        session_id="trim-fail-session",
        token_ids=[10, 20, 30, 40, 50, 60, 70, 80],
        cache_snapshot=[SimpleNamespace(state=[])],
        cache_mode="CACHE_MODE_TIERED",
        model_id="test-model",
        model_revision="v1",
        block_size=4,
        total_bytes=512,
    )

    prefill_calls: list[dict] = []
    backend, loaded = _build_lcp_backend(
        monkeypatch,
        store=store,
        clone_fn=lambda cache: [SimpleNamespace(state=[])] if cache is not None else None,
        responses=[_mtp_response()],
        encode_tokens=[10, 20, 30, 40, 99, 99, 99, 99],
        trim_returns=2,  # only 2 of the required 4 trimmed → unsafe → fall back
        prefill_calls=prefill_calls,
    )

    import threading
    events = list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=2), threading.Event(),
        execution_ext={"_melix.session_id": "trim-fail-session", "_melix.model_id": "test-model",
            "_melix.model_revision": "v1", "_melix.block_size": "4"},
    ))

    assert len(events) > 0
    # Cold-prefill fallback: no restore_cache passed to prefill, and the entry ref
    # was released cleanly (re-acquire sees only our own ref).
    assert all(c["restore_cache"] is None for c in prefill_calls)
    entry = store.acquire("trim-fail-session")
    assert entry is not None
    assert entry._active_refs == 1
    store.release(entry)


def test_generate_native_mtp_unset_block_size_defaults_not_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset/"0" block size must default to 64, not degenerate to 1-token blocks."""
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    captured: dict[str, int] = {}
    orig_find = store.find_lcp

    def spy_find(token_ids, model_id, model_revision, block_size, **kw):
        captured["block_size"] = block_size
        return orig_find(token_ids, model_id, model_revision, block_size, **kw)

    store.find_lcp = spy_find  # type: ignore[method-assign]

    backend, loaded = _build_lcp_backend(
        monkeypatch, store=store, clone_fn=lambda cache: None, responses=[_mtp_response()]
    )

    import threading
    list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=2), threading.Event(),
        # Mirrors engine_core for an unset preferred_block_size: "0".
        execution_ext={"_melix.session_id": "bs0", "_melix.model_id": "test-model",
            "_melix.model_revision": "v1", "_melix.block_size": "0"},
    ))

    assert captured.get("block_size") == 64


def test_generate_native_mtp_test_fallback_hook_ignored_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The _test.force_cache_fallback request field is inert unless the env gate is set."""
    monkeypatch.delenv("MELIX_ENABLE_TEST_CACHE_HOOKS", raising=False)
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    store.put(
        session_id="hook-session",
        token_ids=[10, 20, 30, 40, 50, 60, 70, 80],
        cache_snapshot=[SimpleNamespace(state=[])],
        cache_mode="CACHE_MODE_TIERED",
        model_id="test-model",
        model_revision="v1",
        block_size=4,
        total_bytes=512,
    )
    backend, loaded = _build_lcp_backend(
        monkeypatch,
        store=store,
        clone_fn=lambda cache: [SimpleNamespace(state=[])] if cache is not None else None,
        responses=[_mtp_response()],
    )

    import threading
    events = list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=2), threading.Event(),
        execution_ext={"_melix.session_id": "hook-session", "_melix.model_id": "test-model",
            "_melix.model_revision": "v1", "_melix.block_size": "4",
            "_test.force_cache_fallback": "true"},
    ))
    # Without the env gate the hook is ignored, so the exact match is still reused.
    assert events[-1].cache_hit_mode == "exact"


def test_generate_native_mtp_no_session_reports_no_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no session id the cache is bypassed and the reason is observable."""
    from worker.runtime.prefix_block_store import PrefixBlockStore

    store = PrefixBlockStore()
    backend, loaded = _build_lcp_backend(
        monkeypatch, store=store, clone_fn=lambda cache: None, responses=[_mtp_response()]
    )

    import threading
    events = list(backend.generate_tokens(
        loaded, "hello world", common_pb2.SamplingConfig(max_output_tokens=2), threading.Event(),
        execution_ext={"_melix.model_id": "test-model", "_melix.model_revision": "v1"},
    ))
    assert events[-1].cache_hit_mode == "none"
    assert events[-1].cache_fallback_reason == "no_session_id"
