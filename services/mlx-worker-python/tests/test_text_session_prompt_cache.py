from __future__ import annotations

from threading import Event
from typing import Any

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime import mlx_text_runtime
from worker.runtime.mlx_text_runtime import AutoMLXBackend
from worker.runtime.prefix_block_store import get_store, reset_store


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeTokenizer:
    bos_token = None

    def encode(self, prompt: str, add_special_tokens: bool = True) -> list[int]:
        _ = add_special_tokens
        return [ord(ch) for ch in prompt]


class FakeCacheLayer:
    """Prompt-cache layer whose shallow copy detaches token history, mirroring
    the MLX copy-on-write contract clone_cache_snapshot relies on."""

    def __init__(self, tokens: list[int] | None = None) -> None:
        self.tokens = list(tokens or [])

    def __copy__(self) -> "FakeCacheLayer":
        return FakeCacheLayer(self.tokens)


class FakeResponse:
    def __init__(self, text: str, finish_reason: str | None = None, generation_tokens: int = 1) -> None:
        self.text = text
        self.finish_reason = finish_reason
        self.generation_tokens = generation_tokens
        self.prompt_tokens = 0


def _make_cached_stream(calls: list[dict[str, Any]]):
    def fake_stream_generate(model, tokenizer, prompt, max_tokens, sampler, prompt_cache=None):
        calls.append({"prompt": prompt, "prompt_cache": prompt_cache})
        if prompt_cache is not None and isinstance(prompt, list):
            prompt_cache[0].tokens.extend(int(token) for token in prompt)
        yield FakeResponse(text="Hel")
        yield FakeResponse(text="lo", finish_reason="stop", generation_tokens=2)

    return fake_stream_generate


def _make_plain_stream(calls: list[dict[str, Any]]):
    def fake_stream_generate(model, tokenizer, prompt, max_tokens, sampler):
        calls.append({"prompt": prompt})
        yield FakeResponse(text="Hel")
        yield FakeResponse(text="lo", finish_reason="stop", generation_tokens=2)

    return fake_stream_generate


def _make_backend(stream_fn) -> AutoMLXBackend:
    return AutoMLXBackend(
        load_fn=lambda model_source, **kwargs: (object(), FakeTokenizer()),
        stream_generate_fn=stream_fn,
        sampler_factory=lambda **kwargs: "sampler",
        prompt_cache_factory=lambda model: [FakeCacheLayer()],
    )


def _loaded_model() -> dict[str, Any]:
    return {"model": object(), "tokenizer": FakeTokenizer()}


def _sampling(max_tokens: int = 8) -> common_pb2.SamplingConfig:
    return common_pb2.SamplingConfig(
        temperature=0.0,
        top_p=1.0,
        top_k=1,
        max_output_tokens=max_tokens,
    )


def _ext(session_id: str = "sess-1", block_size: int = 4) -> dict[str, str]:
    return {
        "_melix.session_id": session_id,
        "_melix.model_id": "m1",
        "_melix.model_revision": "r1",
        "_melix.block_size": str(block_size),
    }


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MELIX_PREFIX_CACHE_COLD_DIR", raising=False)
    reset_store()
    yield
    reset_store()


# ---------------------------------------------------------------------------
# Path selection
# ---------------------------------------------------------------------------


def test_no_session_id_keeps_plain_string_path() -> None:
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    events = list(
        backend.generate_tokens(_loaded_model(), "abcdefgh", _sampling(), Event(), execution_ext={})
    )
    assert [event.text for event in events] == ["Hel", "lo"]
    assert calls[0]["prompt"] == "abcdefgh"
    assert calls[0]["prompt_cache"] is None
    assert get_store().session_count() == 0


def test_stream_without_prompt_cache_kwarg_stays_uncached() -> None:
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_plain_stream(calls))
    events = list(
        backend.generate_tokens(_loaded_model(), "abcdefgh", _sampling(), Event(), execution_ext=_ext())
    )
    assert [event.text for event in events] == ["Hel", "lo"]
    assert calls[0]["prompt"] == "abcdefgh"
    assert get_store().session_count() == 0


# ---------------------------------------------------------------------------
# Session-cached decode
# ---------------------------------------------------------------------------


def test_first_turn_miss_prefills_full_prompt_and_stores_state() -> None:
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    prompt = "abcdefgh"
    events = list(
        backend.generate_tokens(_loaded_model(), prompt, _sampling(), Event(), execution_ext=_ext())
    )

    assert calls[0]["prompt"] == [ord(ch) for ch in prompt]
    assert calls[0]["prompt_cache"] is not None

    store = get_store()
    assert store.session_count() == 1
    entry = store.acquire("sess-1")
    assert entry is not None
    assert entry.token_ids == [ord(ch) for ch in prompt]
    assert entry.cache_snapshot[0].tokens == [ord(ch) for ch in prompt]
    store.release(entry)

    terminal = events[-1]
    assert terminal.finish_reason == "stop"
    assert terminal.cache_hit_mode == "none"
    assert terminal.recovered_prefix_tokens == 0
    assert terminal.cache_fallback_reason == "no_reusable_prefix"
    assert terminal.prompt_tokens == len(prompt)


def test_second_turn_partial_hit_replays_suffix_only() -> None:
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    turn_one = "abcdefgh"  # 8 tokens — two full blocks of 4
    turn_two = turn_one + "wxyz"

    list(backend.generate_tokens(_loaded_model(), turn_one, _sampling(), Event(), execution_ext=_ext()))
    events = list(
        backend.generate_tokens(_loaded_model(), turn_two, _sampling(), Event(), execution_ext=_ext())
    )

    # Second call only replays the 4-token suffix onto the restored state.
    assert calls[1]["prompt"] == [ord(ch) for ch in "wxyz"]
    restored_cache = calls[1]["prompt_cache"]
    assert restored_cache[0].tokens == [ord(ch) for ch in turn_two]

    terminal = events[-1]
    assert terminal.cache_hit_mode == "partial"
    assert terminal.cache_hit_tier == "hot"
    assert terminal.recovered_prefix_tokens == len(turn_one)
    assert terminal.cache_fallback_reason == ""
    assert terminal.prompt_tokens == len(turn_two)

    # The store now holds the full turn-two prompt for the next turn.
    store = get_store()
    entry = store.acquire("sess-1")
    assert entry is not None
    assert entry.token_ids == [ord(ch) for ch in turn_two]
    store.release(entry)


def test_exact_hit_replays_last_token(monkeypatch: pytest.MonkeyPatch) -> None:
    trims: list[int] = []

    def fake_trim_impl(prompt_cache: Any, trim_tokens: int) -> bool:
        trims.append(trim_tokens)
        layer = prompt_cache[0]
        if trim_tokens > 0:
            layer.tokens = layer.tokens[:-trim_tokens]
        return True

    monkeypatch.setattr(mlx_text_runtime, "_trim_restored_cache", fake_trim_impl)
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    prompt = "abcdefgh"

    list(backend.generate_tokens(_loaded_model(), prompt, _sampling(), Event(), execution_ext=_ext()))
    events = list(
        backend.generate_tokens(_loaded_model(), prompt, _sampling(), Event(), execution_ext=_ext())
    )

    # Exact hit: one token is held out of the reused state and replayed.
    assert trims == [1]
    assert calls[1]["prompt"] == [ord(prompt[-1])]
    assert calls[1]["prompt_cache"][0].tokens == [ord(ch) for ch in prompt]

    terminal = events[-1]
    assert terminal.cache_hit_mode == "exact"
    assert terminal.cache_hit_tier == "hot"
    assert terminal.recovered_prefix_tokens == len(prompt) - 1
    assert terminal.prompt_tokens == len(prompt)


def test_trim_failure_falls_back_to_full_prefill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mlx_text_runtime, "_trim_restored_cache", lambda cache, n: False)
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    turn_one = "abcdefghij"  # 10 tokens — stored tail is not block aligned
    turn_two = turn_one + "wxyz"

    list(backend.generate_tokens(_loaded_model(), turn_one, _sampling(), Event(), execution_ext=_ext()))
    events = list(
        backend.generate_tokens(_loaded_model(), turn_two, _sampling(), Event(), execution_ext=_ext())
    )

    # The partial hit needs a 2-token trim; the failed trim falls back to a
    # full prefill instead of reusing misaligned state.
    assert calls[1]["prompt"] == [ord(ch) for ch in turn_two]
    terminal = events[-1]
    assert terminal.cache_hit_mode == "none"
    assert terminal.cache_fallback_reason == "cache_reuse_unavailable"
    assert terminal.recovered_prefix_tokens == 0


def test_cancel_event_stops_stream() -> None:
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    cancel = Event()
    cancel.set()
    events = list(
        backend.generate_tokens(_loaded_model(), "abcdefgh", _sampling(), cancel, execution_ext=_ext())
    )
    assert events == []


def test_multi_session_isolation() -> None:
    calls: list[dict[str, Any]] = []
    backend = _make_backend(_make_cached_stream(calls))
    list(
        backend.generate_tokens(
            _loaded_model(), "abcdefgh", _sampling(), Event(), execution_ext=_ext(session_id="sess-a")
        )
    )
    list(
        backend.generate_tokens(
            _loaded_model(), "ABCDEFGH", _sampling(), Event(), execution_ext=_ext(session_id="sess-b")
        )
    )
    store = get_store()
    assert store.session_count() == 2
