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
from worker.runtime import mlx_text_runtime as mlx_text_runtime_module
from worker.runtime import runtime_utils
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.mlx_text_runtime import AutoMLXBackend, MLXTextRuntime, RuntimeTokenEvent, RuntimeToolCallEvent
from worker.runtime.mlx_text_runtime import RuntimeUnavailableError, resolve_text_stop_contract


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
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].prompt_tokens == 12
    assert chunks[-1].completion_tokens == 2
    assert chunks[-1].generation_tps == 123.0
    assert chunks[-1].speculative_acceptance_rate == 0.8
    assert chunks[-1].speculative_rejected_tokens == 3
    assert chunks[-1].speculative_draft_model_configured is True
    assert chunks[-1].dflash_enabled is True
    assert chunks[-1].dflash_rollback_count == 2


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


def test_stop_sequence_filter_reuses_unmodified_token_events() -> None:
    runtime = MLXTextRuntime(backend=object())
    event = RuntimeTokenEvent(text="chunk", prompt_tokens=1, completion_tokens=1)

    events = list(runtime._apply_stop_sequences([event], ("<stop>", "</turn>")))

    assert events == [event]
    assert events[0] is event


def test_stop_sequence_helpers_preserve_earliest_match_and_viable_suffix() -> None:
    assert mlx_text_runtime_module._first_stop_sequence_index("abcEND<stop>", ("<stop>", "END")) == 3
    assert mlx_text_runtime_module._first_stop_sequence_index("<stop>END", ("END", "<stop>")) == 0
    assert mlx_text_runtime_module._first_stop_sequence_index("no marker", ("END", "<stop>")) is None

    stop_sequences = ("<stop>", "</turn>")
    max_prefix_length = mlx_text_runtime_module._stop_sequence_max_prefix_length(stop_sequences)
    assert mlx_text_runtime_module._viable_stop_prefix_suffix("hello <sto", stop_sequences, max_prefix_length) == "<sto"
    assert mlx_text_runtime_module._viable_stop_prefix_suffix("hello <sto", stop_sequences) == "<sto"
    assert mlx_text_runtime_module._viable_stop_prefix_suffix("hello", stop_sequences, max_prefix_length) == ""


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
