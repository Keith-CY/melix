#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
import types
from typing import Any


def _repo_root() -> Path:
    raw = os.environ.get("MELIX_STRUCTURED_OUTPUT_CONSTRAINT_REPO_ROOT", "").strip()
    return Path(raw).resolve() if raw else Path.cwd().resolve()


ROOT = _repo_root()
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))  # pragma: no cover - script bootstrap


class _FakeMLXScalar:
    def __init__(self, value: float) -> None:
        self._value = float(value)

    def item(self) -> float:
        return self._value


class _FakeMLXArray:
    def __init__(self, values: Any) -> None:
        if isinstance(values, _FakeMLXArray):
            values = values.tolist()
        self._values = self._copy_values(values)
        self.shape = self._shape(self._values)

    def __getitem__(self, item: Any) -> Any:
        value = self._values
        if isinstance(item, tuple):
            for part in item:
                value = value[part]
        else:
            value = value[item]
        if isinstance(value, list):
            return _FakeMLXArray(value)
        return value

    def __add__(self, other: Any) -> "_FakeMLXArray":
        other_values = other.tolist() if hasattr(other, "tolist") else other
        return _FakeMLXArray(self._add_values(self._values, other_values))

    def __radd__(self, other: Any) -> "_FakeMLXArray":
        other_values = other.tolist() if hasattr(other, "tolist") else other
        return _FakeMLXArray(self._add_values(other_values, self._values))

    def reshape(self, shape: tuple[int, ...]) -> "_FakeMLXArray":
        flat = self._flatten(self._values)
        if len(shape) == 2 and shape[0] == 1 and shape[1] == len(flat):
            return _FakeMLXArray([flat])
        if len(shape) == 1 and shape[0] == len(flat):
            return _FakeMLXArray(flat)
        raise ValueError(f"unsupported fake MLX reshape: {shape!r}")

    def tolist(self) -> Any:
        return self._copy_values(self._values)

    @classmethod
    def _copy_values(cls, values: Any) -> Any:
        if isinstance(values, list):
            return [cls._copy_values(value) for value in values]
        return values

    @classmethod
    def _shape(cls, values: Any) -> tuple[int, ...]:
        if not isinstance(values, list):
            return ()
        if not values:
            return (0,)
        return (len(values),) + cls._shape(values[0])

    @classmethod
    def _flatten(cls, values: Any) -> list[Any]:
        if isinstance(values, list):
            flattened: list[Any] = []
            for value in values:
                flattened.extend(cls._flatten(value))
            return flattened
        return [values]

    @classmethod
    def _add_values(cls, left: Any, right: Any) -> Any:
        if isinstance(left, list) and isinstance(right, list):
            return [
                cls._add_values(left_value, right_value)
                for left_value, right_value in zip(left, right, strict=True)
            ]
        if isinstance(left, list):
            return [cls._add_values(value, right) for value in left]
        if isinstance(right, list):
            return [cls._add_values(left, value) for value in right]
        return float(left) + float(right)


def _fake_zeros(shape: tuple[int, ...]) -> _FakeMLXArray:
    if len(shape) == 1:
        return _FakeMLXArray([0.0 for _ in range(shape[0])])
    if len(shape) == 2:
        return _FakeMLXArray([[0.0 for _ in range(shape[1])] for _ in range(shape[0])])
    raise ValueError(f"unsupported fake MLX zeros shape: {shape!r}")


def _fake_isfinite(values: Any) -> _FakeMLXArray:
    raw = values.tolist() if hasattr(values, "tolist") else values

    def convert(value: Any) -> Any:
        if isinstance(value, list):
            return [convert(item) for item in value]
        return 1.0 if math.isfinite(float(value)) else 0.0

    return _FakeMLXArray(convert(raw))


def _fake_sum(values: Any) -> _FakeMLXScalar:
    raw = values.tolist() if hasattr(values, "tolist") else values
    return _FakeMLXScalar(sum(float(value) for value in _FakeMLXArray._flatten(raw)))


def _install_fake_mlx_core() -> types.ModuleType:
    fake_mlx = types.ModuleType("mlx")
    fake_core = types.ModuleType("mlx.core")
    fake_core.array = lambda values, *args, **kwargs: _FakeMLXArray(values)
    fake_core.zeros = lambda shape, *args, **kwargs: _fake_zeros(tuple(shape))
    fake_core.isfinite = _fake_isfinite
    fake_core.sum = _fake_sum
    fake_mlx.core = fake_core
    sys.modules["mlx"] = fake_mlx
    sys.modules["mlx.core"] = fake_core
    return fake_core


def _mx() -> types.ModuleType:
    try:
        import mlx.core as mx

        return mx
    except ImportError:
        return _install_fake_mlx_core()


class ProbeTokenizer:
    def __init__(self, vocab_size: int) -> None:
        self.vocab_size = vocab_size
        self.eos_token_id = vocab_size - 1
        self.decode_calls = 0
        self._id_to_text = {
            0: "{",
            1: "}",
            2: '"answer"',
            3: ":",
            4: '"ok"',
            5: ",",
            6: "[",
            7: "]",
            8: "0",
            9: "true",
            10: "false",
            11: "null",
            12: " ",
            13: "\n",
            self.eos_token_id: "</s>",
        }
        for token_id in range(14, self.eos_token_id):
            self._id_to_text[token_id] = f"tok{token_id}"

    def get_vocab(self) -> dict[str, int]:
        return {text: token_id for token_id, text in self._id_to_text.items()}

    def decode(self, token_ids, skip_special_tokens: bool = False) -> str:
        _ = skip_special_tokens
        self.decode_calls += 1
        return "".join(self._id_to_text[int(token_id)] for token_id in token_ids)


class _FallbackGrammarConstraintProcessor:
    """Uncached pre-implementation probe path for base-repo comparison."""

    def __init__(self, tokenizer: Any) -> None:
        self._id_to_text = _uncached_tokenizer_vocabulary(tokenizer)
        self._eos_token_id = int(getattr(tokenizer, "eos_token_id", -1))
        self._state = "initial"
        self._base_token_count: int | None = None
        self._applied_generated_count = 0
        self._mask_cache: dict[tuple[str, int], Any] = {}

    def __call__(self, tokens: Any, logits: Any) -> Any:
        token_ids = _token_ids(tokens)
        if self._base_token_count is None:
            self._base_token_count = len(token_ids)
        generated_ids = token_ids[self._base_token_count :]
        unapplied_ids = generated_ids[self._applied_generated_count :]
        if unapplied_ids:
            self._advance_state(unapplied_ids)
            self._applied_generated_count = len(generated_ids)
        vocab_size = int(logits.shape[-1])
        return logits + self._mask_for_state(self._state, vocab_size, logits)

    def _advance_state(self, token_ids: list[int]) -> None:
        for token_id in token_ids:
            if self._state == "initial" and self._id_to_text.get(token_id) == "{":
                self._state = "object_open"
            elif self._state == "object_open" and self._id_to_text.get(token_id) == "}":
                self._state = "complete"
            elif self._state == "complete" and token_id == self._eos_token_id:
                continue
            else:
                self._state = "invalid"

    def _mask_for_state(self, state: str, vocab_size: int, logits: Any) -> Any:
        cached = self._mask_cache.get((state, vocab_size))
        if cached is not None:
            return cached

        mx = _mx()
        values = [
            0.0 if self._token_allowed(state, token_id) else -math.inf
            for token_id in range(vocab_size)
        ]
        mask = mx.array(values)
        if len(logits.shape) > 1:
            mask = mask.reshape((1, vocab_size))
        self._mask_cache[(state, vocab_size)] = mask
        return mask

    def _token_allowed(self, state: str, token_id: int) -> bool:
        text = self._id_to_text.get(token_id, "")
        if state == "initial":
            return text == "{"
        if state == "object_open":
            return text in {'"', '"answer"', "}", " "}
        if state == "complete":
            return token_id == self._eos_token_id or text in {" ", "\n"}
        return False


def _token_ids(tokens: Any) -> list[int]:
    if hasattr(tokens, "tolist"):
        values = tokens.tolist()
    else:
        try:
            values = list(tokens)
        except TypeError:
            return [int(tokens)]
    if not isinstance(values, list):
        return [int(values)]
    flattened: list[int] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(int(item) for item in value)
        else:
            flattened.append(int(value))
    return flattened


def _uncached_tokenizer_vocabulary(tokenizer: Any) -> dict[int, str]:
    decode = getattr(tokenizer, "decode", None)
    vocab_size = int(getattr(tokenizer, "vocab_size", 0) or 0)
    if vocab_size <= 0 or not callable(decode):
        return {}
    vocabulary: dict[int, str] = {}
    for token_id in range(vocab_size):
        text = decode([token_id], skip_special_tokens=False)
        if isinstance(text, str) and text:
            vocabulary[token_id] = text
    return vocabulary


def _fallback_builder(execution_ext: object, tokenizer: Any) -> list[Any]:
    getter = getattr(execution_ext, "get", None)
    mode = str(getter("melix.structured_output.mode", "") if callable(getter) else "").strip()
    if mode == "json_object":
        return [_FallbackGrammarConstraintProcessor(tokenizer)]
    return []


def _builder() -> tuple[Callable[[object, Any], list[Any]], bool]:
    if os.environ.get("MELIX_STRUCTURED_OUTPUT_CONSTRAINT_FORCE_FALLBACK", "").strip():
        return _fallback_builder, False
    try:
        from worker.runtime.structured_output_constraints import build_structured_output_logits_processors
    except Exception:
        return _fallback_builder, False
    return build_structured_output_logits_processors, True


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def _finite_count(values: Any) -> int:
    mx = _mx()
    return int(mx.sum(mx.isfinite(values)).item())


def _run_sample(
    build_processors: Callable[[object, Any], list[Any]],
    *,
    vocab_size: int,
    mask_iterations: int,
) -> dict[str, float]:
    mx = _mx()
    tokenizer = ProbeTokenizer(vocab_size)
    ext = {"melix.structured_output.mode": "json_object"}
    prompt_token_id = vocab_size - 2
    logits = mx.zeros((1, vocab_size))

    tracemalloc.start()
    first_started = time.perf_counter()
    first_processors = build_processors(ext, tokenizer)
    first_build_elapsed_ms = (time.perf_counter() - first_started) * 1000.0
    first_decode_calls = tokenizer.decode_calls

    second_started = time.perf_counter()
    second_processors = build_processors(ext, tokenizer)
    second_build_elapsed_ms = (time.perf_counter() - second_started) * 1000.0
    second_decode_calls = tokenizer.decode_calls - first_decode_calls

    if len(first_processors) != 1 or len(second_processors) != 1:
        raise RuntimeError("structured output builder did not produce one logits processor")

    processor = second_processors[0]
    initial = processor(mx.array([prompt_token_id]), logits)
    after_open_object = processor(mx.array([prompt_token_id, 0]), logits)
    after_complete_object = processor(mx.array([prompt_token_id, 0, 1]), logits)
    if not math.isfinite(float(initial[0, 0])):
        raise RuntimeError("initial JSON-object mask rejected the object-open token")
    if math.isfinite(float(initial[0, 2])):
        raise RuntimeError("initial JSON-object mask allowed a key token before object-open")
    if not math.isfinite(float(after_open_object[0, 1])):
        raise RuntimeError("object-open mask rejected object close")
    if not math.isfinite(float(after_complete_object[0, vocab_size - 1])):
        raise RuntimeError("complete object mask rejected EOS")

    mask_started = time.perf_counter()
    for _ in range(mask_iterations):
        processor(mx.array([prompt_token_id, 0, 1]), logits)
    cached_mask_elapsed_ms = (time.perf_counter() - mask_started) * 1000.0

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "first_build_elapsed_ms": first_build_elapsed_ms,
        "second_build_elapsed_ms": second_build_elapsed_ms,
        "first_decode_calls": float(first_decode_calls),
        "second_decode_calls": float(second_decode_calls),
        "cached_mask_elapsed_ms": cached_mask_elapsed_ms,
        "peak_bytes": float(peak_bytes),
        "initial_allowed_count": float(_finite_count(initial)),
        "complete_allowed_count": float(_finite_count(after_complete_object)),
    }


def main() -> int:
    vocab_size = _env_int("MELIX_STRUCTURED_OUTPUT_CONSTRAINT_VOCAB_SIZE", 2048, 32)
    mask_iterations = _env_int("MELIX_STRUCTURED_OUTPUT_CONSTRAINT_MASK_ITERATIONS", 5000, 1)
    sample_count = _env_int("MELIX_STRUCTURED_OUTPUT_CONSTRAINT_SAMPLES", 5, 1)
    build_processors, implementation_available = _builder()

    samples = [
        _run_sample(
            build_processors,
            vocab_size=vocab_size,
            mask_iterations=mask_iterations,
        )
        for _ in range(sample_count)
    ]

    def mean(key: str) -> float:
        return statistics.fmean(sample[key] for sample in samples)

    print(
        json.dumps(
            {
                "implementation_available": 1.0 if implementation_available else 0.0,
                "build_first_elapsed_ms_mean": mean("first_build_elapsed_ms"),
                "build_second_elapsed_ms_mean": mean("second_build_elapsed_ms"),
                "build_first_decode_calls_mean": mean("first_decode_calls"),
                "build_second_decode_calls_mean": mean("second_decode_calls"),
                "cached_mask_elapsed_ms_mean": mean("cached_mask_elapsed_ms"),
                "peak_bytes_mean": mean("peak_bytes"),
                "initial_allowed_count_mean": mean("initial_allowed_count"),
                "complete_allowed_count_mean": mean("complete_allowed_count"),
                "vocab_size": float(vocab_size),
                "mask_iterations": float(mask_iterations),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
