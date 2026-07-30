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
            14: '"',
            15: "a",
            self.eos_token_id: "</s>",
        }
        for token_id in range(16, self.eos_token_id):
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
    if any(isinstance(value, list) for value in values):
        if len(values) > 1:
            raise ValueError(
                "GrammarConstraintProcessor only supports single-sequence inputs (batch size 1)."
            )
        values = values[0]
    return [int(value) for value in values]


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


def _schema_ext_for(schema: object) -> dict[str, str]:
    return {
        "melix.structured_output.mode": "json_schema",
        "melix.structured_output.schema_json": json.dumps(schema, separators=(",", ":")),
    }


def _schema_ext() -> dict[str, str]:
    return _schema_ext_for(
        {
            "type": "object",
            "required": ["answer"],
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string", "const": "ok"},
            },
        }
    )


def _schema_unavailable_metrics() -> dict[str, float]:
    return {
        "schema_available": 0.0,
        "schema_build_first_elapsed_ms": 0.0,
        "schema_build_second_elapsed_ms": 0.0,
        "schema_build_first_decode_calls": 0.0,
        "schema_build_second_decode_calls": 0.0,
        "schema_cached_mask_elapsed_ms": 0.0,
        "schema_peak_bytes": 0.0,
        "schema_initial_allowed_count": 0.0,
        "schema_complete_allowed_count": 0.0,
        "schema_compile_p95_ms": 0.0,
        "schema_complexity_refusal_elapsed_ms": 0.0,
        "schema_enum_mask_elapsed_ms": 0.0,
        "schema_free_text_mask_cache_entries": 0.0,
    }


def _schema_hardening_metrics(
    build_processors: Callable[[object, Any], list[Any]],
    *,
    tokenizer: ProbeTokenizer,
    prompt_token_id: int,
    logits: Any,
) -> dict[str, float]:
    from worker.runtime.structured_output_constraints import _compile_json_schema

    compile_schema_json = _schema_ext()["melix.structured_output.schema_json"]
    compile_samples: list[float] = []
    for _ in range(20):
        _compile_json_schema.cache_clear()
        compile_started = time.perf_counter()
        _compile_json_schema(compile_schema_json)
        compile_samples.append((time.perf_counter() - compile_started) * 1_000.0)
    compile_samples.sort()
    p95_index = max(0, math.ceil(len(compile_samples) * 0.95) - 1)
    compile_p95_ms = compile_samples[p95_index]
    if compile_p95_ms >= 50.0:
        raise RuntimeError(
            f"cold JSON schema compile p95 exceeded 50 ms: {compile_p95_ms:.3f} ms"
        )

    oversized_enum_ext = _schema_ext_for(
        {
            "type": "object",
            "properties": {
                "answer": {"type": "integer", "enum": list(range(1_025))},
            },
        }
    )
    refusal_started = time.perf_counter()
    try:
        build_processors(oversized_enum_ext, tokenizer)
    except Exception as exc:
        details = getattr(exc, "details", {})
        if details.get("reason") != "json_schema_too_complex":
            raise RuntimeError("oversized schema did not produce a typed complexity refusal") from exc
    else:
        raise RuntimeError("oversized schema was not rejected")
    complexity_refusal_elapsed_ms = (time.perf_counter() - refusal_started) * 1000.0
    if complexity_refusal_elapsed_ms >= 50.0:
        raise RuntimeError(
            "JSON schema complexity refusal exceeded 50 ms: "
            f"{complexity_refusal_elapsed_ms:.3f} ms"
        )

    enum_ext = _schema_ext_for(
        {
            "type": "object",
            "required": ["answer"],
            "additionalProperties": False,
            "properties": {
                "answer": {
                    "type": "string",
                    "enum": [f"enum-{index}" for index in range(512)],
                },
            },
        }
    )
    enum_processor = build_processors(enum_ext, tokenizer)[0]
    enum_processor(_mx().array([prompt_token_id]), logits)
    enum_processor(_mx().array([prompt_token_id, 0]), logits)
    enum_processor(_mx().array([prompt_token_id, 0, 2]), logits)
    enum_mask_started = time.perf_counter()
    enum_mask = enum_processor(_mx().array([prompt_token_id, 0, 2, 3]), logits)
    enum_mask_elapsed_ms = (time.perf_counter() - enum_mask_started) * 1000.0
    if not math.isfinite(float(enum_mask[0, 14])):
        raise RuntimeError("large-enum schema mask rejected the string-open token")

    free_text_ext = _schema_ext_for(
        {
            "type": "object",
            "required": ["answer"],
            "additionalProperties": False,
            "properties": {"answer": {"type": "string"}},
        }
    )
    free_text_processor = build_processors(free_text_ext, tokenizer)[0]
    generated = [0, 2, 3, 14]
    free_text_processor(_mx().array([prompt_token_id]), logits)
    for end in range(1, len(generated) + 1):
        free_text_processor(_mx().array([prompt_token_id, *generated[:end]]), logits)
    for _ in range(128):
        generated.append(15)
        free_text_processor(_mx().array([prompt_token_id, *generated]), logits)

    return {
        "schema_compile_p95_ms": compile_p95_ms,
        "schema_complexity_refusal_elapsed_ms": complexity_refusal_elapsed_ms,
        "schema_enum_mask_elapsed_ms": enum_mask_elapsed_ms,
        "schema_free_text_mask_cache_entries": float(len(free_text_processor._mask_cache)),
    }


def _run_schema_sample(
    build_processors: Callable[[object, Any], list[Any]],
    *,
    vocab_size: int,
    mask_iterations: int,
) -> dict[str, float]:
    mx = _mx()
    tokenizer = ProbeTokenizer(vocab_size)
    ext = _schema_ext()
    prompt_token_id = vocab_size - 2
    logits = mx.zeros((1, vocab_size))

    tracemalloc.start()
    first_started = time.perf_counter()
    try:
        first_processors = build_processors(ext, tokenizer)
    except Exception:
        tracemalloc.stop()
        return _schema_unavailable_metrics()
    first_build_elapsed_ms = (time.perf_counter() - first_started) * 1000.0
    first_decode_calls = tokenizer.decode_calls

    second_started = time.perf_counter()
    try:
        second_processors = build_processors(ext, tokenizer)
    except Exception:
        tracemalloc.stop()
        return _schema_unavailable_metrics()
    second_build_elapsed_ms = (time.perf_counter() - second_started) * 1000.0
    second_decode_calls = tokenizer.decode_calls - first_decode_calls

    if len(first_processors) != 1 or len(second_processors) != 1:
        tracemalloc.stop()
        return _schema_unavailable_metrics()

    processor = second_processors[0]
    initial = processor(mx.array([prompt_token_id]), logits)
    after_open_object = processor(mx.array([prompt_token_id, 0]), logits)
    after_value = processor(mx.array([prompt_token_id, 0, 2, 3, 4]), logits)
    after_complete_object = processor(mx.array([prompt_token_id, 0, 2, 3, 4, 1]), logits)
    if not math.isfinite(float(initial[0, 0])):
        raise RuntimeError("initial JSON-schema mask rejected the object-open token")
    if math.isfinite(float(initial[0, 2])):
        raise RuntimeError("initial JSON-schema mask allowed a property key before object-open")
    if not math.isfinite(float(after_open_object[0, 2])):
        raise RuntimeError("object-open JSON-schema mask rejected required property key")
    if math.isfinite(float(after_open_object[0, 1])):
        raise RuntimeError("object-open JSON-schema mask allowed close before required key")
    if not math.isfinite(float(after_value[0, 1])):
        raise RuntimeError("post-value JSON-schema mask rejected object close")
    if not math.isfinite(float(after_complete_object[0, vocab_size - 1])):
        raise RuntimeError("complete JSON-schema mask rejected EOS")

    mask_started = time.perf_counter()
    for _ in range(mask_iterations):
        processor(mx.array([prompt_token_id, 0, 2, 3, 4, 1]), logits)
    cached_mask_elapsed_ms = (time.perf_counter() - mask_started) * 1000.0

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    metrics = {
        "schema_available": 1.0,
        "schema_build_first_elapsed_ms": first_build_elapsed_ms,
        "schema_build_second_elapsed_ms": second_build_elapsed_ms,
        "schema_build_first_decode_calls": float(first_decode_calls),
        "schema_build_second_decode_calls": float(second_decode_calls),
        "schema_cached_mask_elapsed_ms": cached_mask_elapsed_ms,
        "schema_peak_bytes": float(peak_bytes),
        "schema_initial_allowed_count": float(_finite_count(initial)),
        "schema_complete_allowed_count": float(_finite_count(after_complete_object)),
    }
    metrics.update(
        _schema_hardening_metrics(
            build_processors,
            tokenizer=tokenizer,
            prompt_token_id=prompt_token_id,
            logits=logits,
        )
    )
    return metrics


def _tool_ext(*, parser_mode: str) -> dict[str, str]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Read weather",
                "parameters": {
                    "type": "object",
                    "required": ["count", "unit"],
                    "additionalProperties": False,
                    "properties": {
                        "count": {"type": "integer", "minimum": 1, "maximum": 5},
                        "note": {"type": "string"},
                        "unit": {"type": "string", "enum": ["c", "f"]},
                    },
                },
            },
        }
    ]
    return {
        "melix.compat.tool_choice_resolved": "required",
        "melix.compat.reasoning_mode": "disabled",
        "melix.tool_parser.mode": parser_mode,
        "melix.tool_config.tools_json": json.dumps(tools, separators=(",", ":")),
    }


def _tool_unavailable_metrics() -> dict[str, float]:
    return {
        "tool_available": 0.0,
        "tool_compile_p95_ms": 0.0,
        "tool_roundtrip_mismatch_count": 0.0,
        "tool_mask_vocab_words": 0.0,
        "schema_state_budget_refusal_elapsed_ms": 0.0,
    }


def _tool_metrics(
    build_processors: Callable[[object, Any], list[Any]],
    *,
    implementation_available: bool,
    vocab_size: int,
) -> dict[str, float]:
    if not implementation_available:
        return _tool_unavailable_metrics()
    try:
        from worker.runtime.structured_output_constraints import (
            StructuredOutputConstraintError,
            audit_schema_state_space,
        )
        from worker.runtime.tool_call_rescue import parse_tool_body
        from worker.runtime.tool_wire_constraints import (
            _compile_tool_definitions,
            tool_constraint_preflight_error,
            tool_wire_accepts_text,
        )
    except ImportError:
        return _tool_unavailable_metrics()

    json_ext = _tool_ext(parser_mode="qwen")
    xml_ext = _tool_ext(parser_mode="xml")
    compile_samples: list[float] = []
    for _ in range(20):
        _compile_tool_definitions.cache_clear()
        started = time.perf_counter()
        error = tool_constraint_preflight_error(json_ext)
        compile_samples.append((time.perf_counter() - started) * 1_000.0)
        if error is not None:
            raise RuntimeError("supported tool grammar failed bounded preflight") from error
    compile_samples.sort()
    p95_index = max(0, math.ceil(len(compile_samples) * 0.95) - 1)
    compile_p95_ms = compile_samples[p95_index]
    if compile_p95_ms >= 50.0:
        raise RuntimeError(
            f"cold tool grammar compile p95 exceeded 50 ms: {compile_p95_ms:.3f} ms"
        )

    json_wire = '<tool_call>{"name":"weather","arguments":{"count":2,"unit":"c"}}</tool_call>'
    xml_wire = (
        "<tool_call><function=weather>"
        '<parameter=count>2</parameter>'
        '<parameter=note>"a<z and </parameter> text"</parameter>'
        '<parameter=unit>"c"</parameter>'
        "</function></tool_call>"
    )
    mismatches = 0
    for ext, wire in ((json_ext, json_wire), (xml_ext, xml_wire)):
        if not tool_wire_accepts_text(ext, wire):
            mismatches += 1
            continue
        parsed = parse_tool_body(wire)
        if not isinstance(parsed, dict) or parsed.get("name") != "weather":
            mismatches += 1

    tokenizer = ProbeTokenizer(vocab_size)
    processor = build_processors(json_ext, tokenizer)[0]
    receipt = getattr(processor, "acceleration_receipt", {})
    if receipt.get("fallback_reason") != "structured_output_acceleration_unsupported":
        raise RuntimeError("tool constraint did not expose typed acceleration fallback")

    numeric_schema = json.dumps(
        {
            "type": "object",
            "required": ["n"],
            "additionalProperties": False,
            "properties": {
                "n": {"type": "integer", "minimum": 0, "maximum": 10**30},
            },
        },
        separators=(",", ":"),
    )
    budget_started = time.perf_counter()
    try:
        audit_schema_state_space(
            numeric_schema,
            alphabet='{"n":0123456789}',
            max_depth=40,
            max_states=64,
            max_transitions=512,
            deadline_seconds=0.050,
        )
    except StructuredOutputConstraintError as exc:
        if exc.details.get("limit") != "state_space_exploration":
            raise RuntimeError("state audit returned the wrong typed budget receipt") from exc
    else:
        raise RuntimeError("numeric state audit did not stop at its hard budget")
    budget_elapsed_ms = (time.perf_counter() - budget_started) * 1_000.0
    if budget_elapsed_ms >= 50.0:
        raise RuntimeError(
            f"schema state-budget refusal exceeded 50 ms: {budget_elapsed_ms:.3f} ms"
        )

    return {
        "tool_available": 1.0,
        "tool_compile_p95_ms": compile_p95_ms,
        "tool_roundtrip_mismatch_count": float(mismatches),
        "tool_mask_vocab_words": float(receipt.get("mask_vocab_words", 0)),
        "schema_state_budget_refusal_elapsed_ms": budget_elapsed_ms,
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
    schema_samples = [
        _run_schema_sample(
            build_processors,
            vocab_size=vocab_size,
            mask_iterations=mask_iterations,
        )
        for _ in range(sample_count)
    ]
    tool_metrics = _tool_metrics(
        build_processors,
        implementation_available=implementation_available,
        vocab_size=vocab_size,
    )

    def mean(key: str) -> float:
        return statistics.fmean(sample[key] for sample in samples)

    def schema_mean(key: str) -> float:
        return statistics.fmean(sample[key] for sample in schema_samples)

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
                "schema_available": schema_mean("schema_available"),
                "schema_build_first_elapsed_ms_mean": schema_mean(
                    "schema_build_first_elapsed_ms"
                ),
                "schema_build_second_elapsed_ms_mean": schema_mean(
                    "schema_build_second_elapsed_ms"
                ),
                "schema_build_first_decode_calls_mean": schema_mean(
                    "schema_build_first_decode_calls"
                ),
                "schema_build_second_decode_calls_mean": schema_mean(
                    "schema_build_second_decode_calls"
                ),
                "schema_cached_mask_elapsed_ms_mean": schema_mean(
                    "schema_cached_mask_elapsed_ms"
                ),
                "schema_peak_bytes_mean": schema_mean("schema_peak_bytes"),
                "schema_initial_allowed_count_mean": schema_mean(
                    "schema_initial_allowed_count"
                ),
                "schema_complete_allowed_count_mean": schema_mean(
                    "schema_complete_allowed_count"
                ),
                "schema_compile_p95_ms_mean": schema_mean("schema_compile_p95_ms"),
                "schema_complexity_refusal_elapsed_ms_mean": schema_mean(
                    "schema_complexity_refusal_elapsed_ms"
                ),
                "schema_enum_mask_elapsed_ms_mean": schema_mean(
                    "schema_enum_mask_elapsed_ms"
                ),
                "schema_free_text_mask_cache_entries_mean": schema_mean(
                    "schema_free_text_mask_cache_entries"
                ),
                "vocab_size": float(vocab_size),
                "mask_iterations": float(mask_iterations),
                "sample_count": float(sample_count),
                **tool_metrics,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
