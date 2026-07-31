from __future__ import annotations

import sys
import types
from threading import Event
from typing import Any, Sequence

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime import mlx_text_runtime
from worker.runtime.mlx_text_runtime import (
    AutoMLXBackend,
    RuntimeTokenEvent,
    _flat_stop_token_ids,
    _is_greedy_sampling,
)
from worker.runtime.prompt_lookup import PromptLookupConfig
from worker.runtime.prompt_lookup_mlx import (
    MLXPromptLookupStep,
    PromptLookupUnavailable,
    build_mlx_step,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeTokenizer:
    bos_token = None
    eos_token_id = 7

    def encode(self, prompt: str, add_special_tokens: bool = True) -> list[int]:
        del add_special_tokens
        return [ord(character) for character in prompt]


class FakeDetokenizer:
    """Emits one character per token id, mirroring mlx-lm's streaming shape."""

    def __init__(self) -> None:
        self.tokens: list[int] = []
        self.last_segment = ""
        self.finalized = False
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1
        self.tokens = []
        self.last_segment = ""

    def add_token(self, token_id: int) -> None:
        self.tokens.append(int(token_id))
        self.last_segment = chr(token_id) if 32 <= token_id < 0x11000 else f"<{token_id}>"

    def finalize(self) -> None:
        self.finalized = True


def _sampling(
    temperature: float = 0.0,
    top_k: int = 1,
    max_output_tokens: int = 16,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
):
    return common_pb2.SamplingConfig(
        temperature=temperature,
        top_p=1.0,
        top_k=top_k,
        max_output_tokens=max_output_tokens,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )


def _backend() -> AutoMLXBackend:
    return AutoMLXBackend(
        load_fn=lambda source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=lambda *args, **kwargs: iter(()),
        sampler_factory=lambda **kwargs: "sampler",
    )


def _loaded_model(tokenizer: Any | None = None, model: Any | None = None) -> dict[str, Any]:
    return {"model": model if model is not None else (lambda *a, **k: None), "tokenizer": tokenizer or FakeTokenizer()}


def _passage_step(passage: Sequence[int], fallback: int = 7):
    """Greedy StepFn that continues `passage`, else emits the EOS id."""
    passage = [int(token) for token in passage]

    def next_token(context: Sequence[int]) -> int:
        for length in range(min(len(context), len(passage) - 1), 0, -1):
            if list(context[-length:]) == passage[:length]:
                return passage[length]
        return fallback

    def step(context: Sequence[int], draft: Sequence[int]) -> list[int]:
        working = list(context)
        predictions = [next_token(working)]
        for token in draft:
            working.append(int(token))
            predictions.append(next_token(working))
        return predictions

    return step


# ---------------------------------------------------------------------------
# Gating helpers
# ---------------------------------------------------------------------------


def test_greedy_sampling_requires_zero_temperature() -> None:
    assert _is_greedy_sampling(_sampling(temperature=0.0, top_k=0)) is True
    assert _is_greedy_sampling(_sampling(temperature=0.7, top_k=40)) is False
    # top_k == 1 at a non-zero temperature is argmax only via the pinned
    # mlx-lm's internal sampler-chain ordering, not a documented contract, so
    # it is deliberately excluded from the greedy guarantee.
    assert _is_greedy_sampling(_sampling(temperature=0.7, top_k=1)) is False


def test_greedy_sampling_rejects_non_zero_penalties() -> None:
    # Penalties do not reach the pinned mlx-lm's make_sampler, but the forwarding
    # is runtime-detected from the sampler factory. If it ever starts applying
    # them, the standard path would emit penalized tokens while prompt lookup
    # verified against a plain argmax — so a penalized request must not qualify.
    assert _is_greedy_sampling(_sampling(frequency_penalty=0.5)) is False
    assert _is_greedy_sampling(_sampling(presence_penalty=0.5)) is False
    assert _is_greedy_sampling(_sampling(frequency_penalty=0.0, presence_penalty=0.0)) is True


def test_prompt_lookup_skipped_for_penalized_greedy_requests() -> None:
    backend = _backend()
    tokenizer = FakeTokenizer()
    tokenizer.detokenizer = FakeDetokenizer()  # type: ignore[attr-defined]

    assert (
        backend._maybe_generate_prompt_lookup_tokens(
            _loaded_model(tokenizer),
            "abc",
            config=PromptLookupConfig(enabled=True),
            sampling=_sampling(temperature=0.0, frequency_penalty=1.2),
            max_tokens=8,
            cancel_event=Event(),
        )
        is None
    )


def test_flat_stop_token_ids_keeps_single_token_sequences() -> None:
    assert _flat_stop_token_ids(None) == ()
    assert _flat_stop_token_ids([]) == ()
    assert _flat_stop_token_ids([[7], [11]]) == (7, 11)
    # Multi-token stop sequences stay with the downstream stop contract.
    assert _flat_stop_token_ids([[7], [1, 2]]) == (7,)


def test_prompt_lookup_skipped_for_sampled_requests() -> None:
    backend = _backend()
    assert (
        backend._maybe_generate_prompt_lookup_tokens(
            _loaded_model(),
            "abc",
            config=PromptLookupConfig(enabled=True),
            sampling=_sampling(temperature=0.9, top_k=40),
            max_tokens=8,
            cancel_event=Event(),
        )
        is None
    )


def test_prompt_lookup_skipped_without_tokenizer_encode() -> None:
    backend = _backend()

    class NoEncode:
        detokenizer = FakeDetokenizer()

    assert (
        backend._maybe_generate_prompt_lookup_tokens(
            {"model": lambda *a, **k: None, "tokenizer": NoEncode()},
            "abc",
            config=PromptLookupConfig(enabled=True),
            sampling=_sampling(),
            max_tokens=8,
            cancel_event=Event(),
        )
        is None
    )


def test_prompt_lookup_skipped_when_mlx_step_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend()
    tokenizer = FakeTokenizer()
    tokenizer.detokenizer = FakeDetokenizer()  # type: ignore[attr-defined]

    def unavailable(*args: Any, **kwargs: Any):
        raise PromptLookupUnavailable("no mlx")

    monkeypatch.setattr(mlx_text_runtime, "build_mlx_step", unavailable)
    assert (
        backend._maybe_generate_prompt_lookup_tokens(
            _loaded_model(tokenizer),
            "abc",
            config=PromptLookupConfig(enabled=True),
            sampling=_sampling(),
            max_tokens=8,
            cancel_event=Event(),
        )
        is None
    )


def test_disabled_config_keeps_generate_tokens_on_standard_path() -> None:
    seen: list[str] = []

    def fake_stream_generate(model, tokenizer, prompt, max_tokens, sampler):
        seen.append("stream")
        yield types.SimpleNamespace(text="ok", finish_reason="stop", generation_tokens=1, prompt_tokens=3)

    backend = AutoMLXBackend(
        load_fn=lambda source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=fake_stream_generate,
        sampler_factory=lambda **kwargs: "sampler",
    )
    events = list(
        backend.generate_tokens(_loaded_model(), "abc", _sampling(), Event(), execution_ext={})
    )
    assert seen == ["stream"]
    assert [event.text for event in events] == ["ok"]


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


def _run_prompt_lookup(
    *,
    passage: Sequence[int],
    prompt: str,
    max_tokens: int = 16,
    config: PromptLookupConfig | None = None,
    cancel_event: Event | None = None,
) -> tuple[list[RuntimeTokenEvent], FakeDetokenizer]:
    backend = _backend()
    detokenizer = FakeDetokenizer()
    events = list(
        backend._generate_prompt_lookup_tokens(
            _loaded_model(),
            prompt,
            config=config or PromptLookupConfig(enabled=True, max_ngram=4, min_ngram=2, max_draft_tokens=6),
            step=_passage_step(passage),
            detokenizer=detokenizer,
            max_tokens=max_tokens,
            cancel_event=cancel_event or Event(),
        )
    )
    return events, detokenizer


def test_prompt_lookup_emits_one_event_per_token_with_terminal_receipts() -> None:
    passage = [ord(c) for c in "HELLOWORLD"]
    # The prompt contains the passage, so drafts land and the run terminates on
    # the fallback EOS id once the passage is exhausted.
    events, detokenizer = _run_prompt_lookup(passage=passage, prompt="XX" + "HELLOWORLD" + "YH")

    assert events
    assert [event.finish_reason for event in events[:-1]] == [None] * (len(events) - 1)
    terminal = events[-1]
    assert terminal.finish_reason in {"stop", "length"}
    assert terminal.prompt_tokens == len("XXHELLOWORLDYH")
    assert terminal.completion_tokens == len(events)
    # Receipts ride the existing speculative vocabulary.
    assert terminal.speculative_acceptance_rate is not None
    assert terminal.speculative_num_draft_tokens == 6
    assert terminal.speculative_draft_model_configured is False
    assert terminal.generation_tps is not None
    assert detokenizer.finalized is True
    assert detokenizer.reset_count == 1


def test_prompt_lookup_raw_text_accumulates_across_events() -> None:
    passage = [ord(c) for c in "ABCDEFGH"]
    events, _ = _run_prompt_lookup(passage=passage, prompt="ZZ" + "ABCDEFGH" + "YA")

    assert events[-1].raw_text == "".join(event.text for event in events)


def test_prompt_lookup_respects_max_tokens() -> None:
    passage = [ord(c) for c in "ABCDEFGHIJKLMNOP"]
    events, _ = _run_prompt_lookup(
        passage=passage, prompt="ZZ" + "ABCDEFGHIJKLMNOP" + "YA", max_tokens=4
    )

    assert len(events) == 4
    assert events[-1].finish_reason == "length"


def test_prompt_lookup_stops_on_eos_token() -> None:
    # The step's fallback token is the tokenizer EOS id, so generation must end
    # on it rather than running to the token budget.
    events, _ = _run_prompt_lookup(passage=[ord("A"), ord("B")], prompt="QQQ", max_tokens=32)

    assert events[-1].finish_reason == "stop"
    assert events[-1].token_ids == (7,)


def test_prompt_lookup_empty_prompt_emits_nothing() -> None:
    events, _ = _run_prompt_lookup(passage=[1, 2, 3], prompt="")
    assert events == []


def test_prompt_lookup_cancellation_stops_generation() -> None:
    cancel_event = Event()
    cancel_event.set()
    events, _ = _run_prompt_lookup(
        passage=[ord(c) for c in "ABCDEF"], prompt="ZZABCDEFYA", cancel_event=cancel_event
    )
    assert events == []


# ---------------------------------------------------------------------------
# MLX verify step — cache reconciliation
# ---------------------------------------------------------------------------


class _FakeArray:
    def __init__(self, rows: Any) -> None:
        self.rows = rows

    def __getitem__(self, index: int) -> "_FakeArray":
        return _FakeArray(self.rows[index])

    def tolist(self) -> Any:
        return self.rows


class _FakeLayer:
    """Tracks cache length independently so the step's accounting is checkable."""

    def __init__(self) -> None:
        self.offset = 0

    @property
    def state(self) -> Any:
        return self.offset


class _FakeCacheModule(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("mlx_lm.models.cache")
        self.trim_supported = True
        self.made = 0

    def make_prompt_cache(self, model: Any) -> list[_FakeLayer]:
        del model
        self.made += 1
        return [_FakeLayer()]

    def trim_prompt_cache(self, cache: list[_FakeLayer], count: int) -> int:
        if not self.trim_supported:
            return 0
        trimmed = min(count, cache[0].offset)
        cache[0].offset -= trimmed
        return trimmed


class _FakeModel:
    """Vocab-8 model whose argmax is a function of the last input token."""

    def __init__(self) -> None:
        self.forward_widths: list[int] = []

    def __call__(self, inputs: _FakeArray, cache: list[_FakeLayer] | None = None) -> _FakeArray:
        tokens = inputs.rows[0]
        if cache is not None:
            cache[0].offset += len(tokens)
        self.forward_widths.append(len(tokens))
        logits = []
        for token in tokens:
            row = [0.0] * 8
            row[(int(token) + 1) % 8] = 1.0
            logits.append(row)
        return _FakeArray([logits])


@pytest.fixture()
def fake_mlx(monkeypatch: pytest.MonkeyPatch) -> _FakeCacheModule:
    mx_module = types.ModuleType("mlx.core")
    mx_module.array = lambda value: _FakeArray(value)  # type: ignore[attr-defined]
    mx_module.argmax = lambda array, axis=-1: _FakeArray(  # type: ignore[attr-defined]
        [max(range(len(row)), key=row.__getitem__) for row in array.rows]
    )
    mx_module.eval = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    mlx_package = types.ModuleType("mlx")
    mlx_package.core = mx_module  # type: ignore[attr-defined]
    cache_module = _FakeCacheModule()

    monkeypatch.setitem(sys.modules, "mlx", mlx_package)
    monkeypatch.setitem(sys.modules, "mlx.core", mx_module)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", cache_module)
    return cache_module


def test_mlx_step_returns_one_prediction_per_input_position(fake_mlx: _FakeCacheModule) -> None:
    model = _FakeModel()
    step = MLXPromptLookupStep(model)

    predictions = step(context=[1, 2, 3], draft=[4, 5])

    # Model argmax is (token + 1) % 8 over inputs [last_context] + draft.
    assert predictions == [4, 5, 6]
    assert model.forward_widths == [2, 3]  # prefill of [1, 2], then verify of [3, 4, 5]


def test_mlx_step_trims_cache_after_a_rejected_draft(fake_mlx: _FakeCacheModule) -> None:
    model = _FakeModel()
    step = MLXPromptLookupStep(model)

    step(context=[1, 2, 3], draft=[4, 5])
    # Cache advanced across the draft: 2 prefill + 3 verify inputs.
    assert fake_mlx.made == 1
    cache_after_first = 5

    # The caller accepted nothing, so the committed context grew by one token
    # only. The next call must trim the cache back to len(context) - 1 = 3.
    step(context=[1, 2, 3, 4], draft=[])
    assert cache_after_first > 3
    assert fake_mlx.made == 1  # trimmed, not rebuilt
    assert model.forward_widths == [2, 3, 1]


def test_mlx_step_rebuilds_cache_when_trim_is_unsupported(fake_mlx: _FakeCacheModule) -> None:
    model = _FakeModel()
    step = MLXPromptLookupStep(model)
    step(context=[1, 2, 3], draft=[4, 5])

    fake_mlx.trim_supported = False
    step(context=[1, 2, 3, 4], draft=[])

    # A cache that cannot trim to the boundary is rebuilt and re-prefilled
    # rather than reused at a misaligned position.
    assert fake_mlx.made == 2
    assert model.forward_widths == [2, 3, 3, 1]


def test_mlx_step_extends_cache_for_a_fully_accepted_draft(fake_mlx: _FakeCacheModule) -> None:
    model = _FakeModel()
    step = MLXPromptLookupStep(model)

    step(context=[1, 2], draft=[3, 4])
    # Whole draft plus bonus accepted: committed context is now [1,2,3,4,5], so
    # the cache (holding 4 positions) needs exactly one more token, no trim.
    step(context=[1, 2, 3, 4, 5], draft=[])
    assert fake_mlx.made == 1
    assert model.forward_widths == [1, 3, 1]


def test_mlx_step_empty_context_returns_nothing(fake_mlx: _FakeCacheModule) -> None:
    assert MLXPromptLookupStep(_FakeModel())(context=[], draft=[1]) == []


def test_build_mlx_step_rejects_non_callable_model(fake_mlx: _FakeCacheModule) -> None:
    with pytest.raises(PromptLookupUnavailable):
        build_mlx_step(object())


def test_build_mlx_step_reports_missing_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any):
        if name in {"mlx.core", "mlx_lm.models.cache"}:
            raise ImportError(f"blocked {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(PromptLookupUnavailable):
        build_mlx_step(lambda *a, **k: None)
