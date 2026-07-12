from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any


_STRUCTURED_OUTPUT_MODE_KEY = "melix.structured_output.mode"
_STRUCTURED_OUTPUT_SCHEMA_JSON_KEY = "melix.structured_output.schema_json"
_TOKENIZER_EOS_CACHE_ATTR = "_melix_structured_output_eos_token_ids_cache"
_TOKENIZER_VOCAB_CACHE_ATTR = "_melix_structured_output_vocab_cache"
_JSON_WHITESPACE = frozenset((" ", "\t", "\n", "\r"))
_JSON_HEX = frozenset("0123456789abcdefABCDEF")
_JSON_NUMBER_DELIMITERS = _JSON_WHITESPACE | frozenset((",", "]", "}"))
_JSON_NUMBER_FINAL_STATES = frozenset(("zero", "int", "frac", "exp"))


class StructuredOutputConstraintError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "unsupported_structured_output",
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class _Frame:
    kind: str
    expect: str


@dataclass(frozen=True, slots=True)
class _JSONPrefixState:
    root: str = "before"
    stack: tuple[_Frame, ...] = ()
    mode: str = "normal"
    string_role: str = ""
    unicode_remaining: int = 0
    number_state: str = ""
    literal_target: str = ""
    literal_index: int = 0


_INITIAL_JSON_OBJECT_STATE = _JSONPrefixState()


def normalize_structured_output_mode(execution_ext: object) -> str:
    raw_mode = _ext_get(execution_ext, _STRUCTURED_OUTPUT_MODE_KEY).strip().lower()
    if raw_mode in {"plain_text", "plaintext", "none"}:
        return "text"
    if raw_mode == "json":
        return "json_object"
    return raw_mode


def schema_backed_json_schema_requested(execution_ext: object) -> bool:
    return (
        normalize_structured_output_mode(execution_ext) == "json_schema"
        and bool(_ext_get(execution_ext, _STRUCTURED_OUTPUT_SCHEMA_JSON_KEY).strip())
    )


def json_schema_constraint_error(execution_ext: object) -> StructuredOutputConstraintError | None:
    if not schema_backed_json_schema_requested(execution_ext):
        return None
    return StructuredOutputConstraintError(
        "response_format json_schema requires sampler grammar support, "
        "but this worker only supports json_object constraints.",
        details={
            "mode": "json_schema",
            "enforcement": "sampler",
            "reason": "json_schema_grammar_unavailable",
        },
    )


def build_structured_output_logits_processors(
    execution_ext: object,
    tokenizer: Any,
) -> list[Any]:
    mode = normalize_structured_output_mode(execution_ext)
    if not mode or mode == "text":
        return []
    if mode == "json_object":
        return [GrammarConstraintProcessor(tokenizer)]
    if mode == "json_schema":
        error = json_schema_constraint_error(execution_ext)
        if error is not None:
            raise error
        return []
    raise StructuredOutputConstraintError(
        f"Unsupported structured output mode: {mode}.",
        details={
            "mode": mode,
            "enforcement": "sampler",
            "reason": "unsupported_mode",
        },
    )


class GrammarConstraintProcessor:
    """JSON-object grammar logits processor for mlx-lm generation."""

    def __init__(self, tokenizer: Any) -> None:
        vocabulary = _tokenizer_vocabulary(tokenizer)
        if not vocabulary:
            raise StructuredOutputConstraintError(
                "The tokenizer does not expose a decodable vocabulary for structured output.",
                details={
                    "mode": "json_object",
                    "enforcement": "sampler",
                    "reason": "tokenizer_vocab_unavailable",
                },
        )
        self._id_to_text = vocabulary
        self._eos_token_ids = _tokenizer_eos_token_ids(tokenizer, vocabulary)
        self._base_token_count: int | None = None
        self._applied_generated_count = 0
        self._state: _JSONPrefixState | None = _INITIAL_JSON_OBJECT_STATE
        self._mask_cache: dict[tuple[_JSONPrefixState | None, int], Any] = {}

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
        mask = self._mask_for_state(self._state, vocab_size, logits)
        return logits + mask

    def _advance_state(self, token_ids: list[int]) -> None:
        state = self._state
        if state is None:
            return
        for token_id in token_ids:
            if token_id in self._eos_token_ids and _is_complete(state):
                continue
            text = self._id_to_text.get(token_id, "")
            next_state = _transition_text(state, text)
            if next_state is None:
                self._state = None
                return
            state = next_state
        self._state = state

    def _mask_for_state(self, state: _JSONPrefixState | None, vocab_size: int, logits: Any) -> Any:
        cache_key = (state, vocab_size)
        cached = self._mask_cache.get(cache_key)
        if cached is not None:
            return cached

        import mlx.core as mx

        if state is None:
            values = [-math.inf] * vocab_size
        else:
            values = [
                0.0 if self._token_allowed(state, token_id) else -math.inf
                for token_id in range(vocab_size)
            ]
        mask = mx.array(values)
        if len(logits.shape) > 1:
            mask = mask.reshape((1, vocab_size))
        self._mask_cache[cache_key] = mask
        return mask

    def _token_allowed(self, state: _JSONPrefixState, token_id: int) -> bool:
        if token_id in self._eos_token_ids and _is_complete(state):
            return True
        text = self._id_to_text.get(token_id, "")
        return _transition_text(state, text) is not None


def _ext_get(execution_ext: object, key: str) -> str:
    if not execution_ext:
        return ""
    getter = getattr(execution_ext, "get", None)
    if not callable(getter):
        return ""
    return str(getter(key, "") or "")


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


def _tokenizer_eos_token_ids(tokenizer: Any, vocabulary: dict[int, str]) -> frozenset[int]:
    cached = getattr(tokenizer, _TOKENIZER_EOS_CACHE_ATTR, None)
    if isinstance(cached, frozenset):
        return cached

    values: list[int] = []
    for attr in ("eos_token_id", "eos_token_ids"):
        raw = getattr(tokenizer, attr, None)
        if raw is None:
            continue
        if isinstance(raw, int):
            values.append(raw)
            continue
        if isinstance(raw, (list, tuple, set, frozenset)):
            for item in raw:
                if isinstance(item, int):
                    values.append(item)
    if not values:
        eos_token = getattr(tokenizer, "eos_token", None)
        if isinstance(eos_token, str):
            values.extend(
                token_id for token_id, text in vocabulary.items() if text == eos_token
            )
    eos_token_ids = frozenset(values)
    try:
        setattr(tokenizer, _TOKENIZER_EOS_CACHE_ATTR, eos_token_ids)
    except Exception:
        pass
    return eos_token_ids


def _tokenizer_vocabulary(tokenizer: Any) -> dict[int, str]:
    cached = getattr(tokenizer, _TOKENIZER_VOCAB_CACHE_ATTR, None)
    if isinstance(cached, dict) and cached:
        return cached

    vocab_size = _tokenizer_vocab_size(tokenizer)
    decode = getattr(tokenizer, "decode", None)
    if vocab_size <= 0 or not callable(decode):
        return {}
    vocabulary: dict[int, str] = {}
    for token_id in range(vocab_size):
        try:
            text = decode([token_id], skip_special_tokens=False)
        except TypeError:
            try:
                text = decode([token_id])
            except Exception:
                continue
        except Exception:
            continue
        if isinstance(text, str) and text:
            vocabulary[token_id] = text
    if vocabulary:
        try:
            setattr(tokenizer, _TOKENIZER_VOCAB_CACHE_ATTR, vocabulary)
        except Exception:
            pass
    return vocabulary


def _tokenizer_vocab_size(tokenizer: Any) -> int:
    raw_size = getattr(tokenizer, "vocab_size", None)
    if isinstance(raw_size, int) and raw_size > 0:
        return raw_size
    get_vocab = getattr(tokenizer, "get_vocab", None)
    if callable(get_vocab):
        try:
            vocab = get_vocab()
        except Exception:
            vocab = None
        if isinstance(vocab, dict) and vocab:
            token_ids = [value for value in vocab.values() if isinstance(value, int) and value >= 0]
            if token_ids:
                return max(token_ids) + 1
    try:
        size = len(tokenizer)
    except Exception:
        return 0
    return int(size) if size > 0 else 0


def _is_complete(state: _JSONPrefixState) -> bool:
    return state.mode == "normal" and state.root == "done" and not state.stack


@lru_cache(maxsize=8192)
def _transition_text(state: _JSONPrefixState, text: str) -> _JSONPrefixState | None:
    if not text:
        return None
    next_state: _JSONPrefixState | None = state
    for char in text:
        if next_state is None:
            return None
        next_state = _transition_char(next_state, char)
    return next_state


def _transition_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    if state.mode == "string":
        return _consume_string_char(state, char)
    if state.mode == "escape":
        return _consume_escape_char(state, char)
    if state.mode == "unicode":
        return _consume_unicode_char(state, char)
    if state.mode == "number":
        return _consume_number_char(state, char)
    if state.mode == "literal":
        return _consume_literal_char(state, char)
    return _consume_normal_char(state, char)


def _consume_normal_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    if state.root == "done":
        return state if char in _JSON_WHITESPACE else None
    if not state.stack:
        if char in _JSON_WHITESPACE:
            return state
        if char == "{":
            return _JSONPrefixState(root="in_progress", stack=(_Frame("object", "key_or_end"),))
        return None

    frame = state.stack[-1]
    if frame.kind == "object":
        return _consume_object_char(state, frame.expect, char)
    if frame.kind == "array":
        return _consume_array_char(state, frame.expect, char)
    return None


def _consume_object_char(
    state: _JSONPrefixState,
    expect: str,
    char: str,
) -> _JSONPrefixState | None:
    if char in _JSON_WHITESPACE:
        return state
    if expect == "key_or_end":
        if char == "}":
            return _close_container(state)
        if char == '"':
            return _enter_string(state, "key")
        return None
    if expect == "key":
        return _enter_string(state, "key") if char == '"' else None
    if expect == "colon":
        return _replace_top(state, "value") if char == ":" else None
    if expect == "value":
        return _start_value(state, char)
    if expect == "comma_or_end":
        if char == ",":
            return _replace_top(state, "key")
        if char == "}":
            return _close_container(state)
    return None


def _consume_array_char(
    state: _JSONPrefixState,
    expect: str,
    char: str,
) -> _JSONPrefixState | None:
    if char in _JSON_WHITESPACE:
        return state
    if expect == "value_or_end":
        if char == "]":
            return _close_container(state)
        return _start_value(state, char)
    if expect == "value":
        return _start_value(state, char)
    if expect == "comma_or_end":
        if char == ",":
            return _replace_top(state, "value")
        if char == "]":
            return _close_container(state)
    return None


def _start_value(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    if char in _JSON_WHITESPACE:
        return state
    if char == "{":
        return _push(state, _Frame("object", "key_or_end"))
    if char == "[":
        return _push(state, _Frame("array", "value_or_end"))
    if char == '"':
        return _enter_string(state, "value")
    if char == "t":
        return _enter_literal(state, "true")
    if char == "f":
        return _enter_literal(state, "false")
    if char == "n":
        return _enter_literal(state, "null")
    if char == "-":
        return _enter_number(state, "after_minus")
    if char == "0":
        return _enter_number(state, "zero")
    if "1" <= char <= "9":
        return _enter_number(state, "int")
    return None


def _consume_string_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    if char == '"':
        if state.string_role == "key":
            return _replace_top(_reset_scalar_mode(state), "colon")
        if state.string_role == "value":
            return _complete_value(_reset_scalar_mode(state))
        return None
    if char == "\\":
        return _replace_mode(state, mode="escape")
    if ord(char) < 0x20:
        return None
    return state


def _consume_escape_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    if char == "u":
        return _replace_mode(state, mode="unicode", unicode_remaining=4)
    if char in {'"', "\\", "/", "b", "f", "n", "r", "t"}:
        return _replace_mode(state, mode="string")
    return None


def _consume_unicode_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    if char not in _JSON_HEX:
        return None
    remaining = state.unicode_remaining - 1
    if remaining <= 0:
        return _replace_mode(state, mode="string", unicode_remaining=0)
    return _replace_mode(state, unicode_remaining=remaining)


def _consume_literal_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    target = state.literal_target
    index = state.literal_index
    if index >= len(target) or char != target[index]:
        return None
    index += 1
    if index == len(target):
        return _complete_value(_reset_scalar_mode(state))
    return _replace_mode(state, literal_index=index)


def _consume_number_char(state: _JSONPrefixState, char: str) -> _JSONPrefixState | None:
    number_state = state.number_state
    if char in _JSON_NUMBER_DELIMITERS and number_state in _JSON_NUMBER_FINAL_STATES:
        completed = _complete_value(_reset_scalar_mode(state))
        return _transition_char(completed, char) if completed is not None else None
    if number_state == "after_minus":
        if char == "0":
            return _replace_mode(state, number_state="zero")
        if "1" <= char <= "9":
            return _replace_mode(state, number_state="int")
        return None
    if number_state == "zero":
        if char == ".":
            return _replace_mode(state, number_state="frac_start")
        if char in {"e", "E"}:
            return _replace_mode(state, number_state="exp_start")
        return None
    if number_state == "int":
        if char.isdigit():
            return state
        if char == ".":
            return _replace_mode(state, number_state="frac_start")
        if char in {"e", "E"}:
            return _replace_mode(state, number_state="exp_start")
        return None
    if number_state == "frac_start":
        return _replace_mode(state, number_state="frac") if char.isdigit() else None
    if number_state == "frac":
        if char.isdigit():
            return state
        if char in {"e", "E"}:
            return _replace_mode(state, number_state="exp_start")
        return None
    if number_state == "exp_start":
        if char in {"+", "-"}:
            return _replace_mode(state, number_state="exp_sign")
        if char.isdigit():
            return _replace_mode(state, number_state="exp")
        return None
    if number_state == "exp_sign":
        return _replace_mode(state, number_state="exp") if char.isdigit() else None
    if number_state == "exp":
        return state if char.isdigit() else None
    return None


def _enter_string(state: _JSONPrefixState, role: str) -> _JSONPrefixState:
    return _JSONPrefixState(
        root=state.root,
        stack=state.stack,
        mode="string",
        string_role=role,
    )


def _enter_literal(state: _JSONPrefixState, target: str) -> _JSONPrefixState:
    return _JSONPrefixState(
        root=state.root,
        stack=state.stack,
        mode="literal",
        literal_target=target,
        literal_index=1,
    )


def _enter_number(state: _JSONPrefixState, number_state: str) -> _JSONPrefixState:
    return _JSONPrefixState(
        root=state.root,
        stack=state.stack,
        mode="number",
        number_state=number_state,
    )


def _replace_mode(
    state: _JSONPrefixState,
    *,
    mode: str | None = None,
    unicode_remaining: int | None = None,
    number_state: str | None = None,
    literal_index: int | None = None,
) -> _JSONPrefixState:
    return _JSONPrefixState(
        root=state.root,
        stack=state.stack,
        mode=state.mode if mode is None else mode,
        string_role=state.string_role,
        unicode_remaining=state.unicode_remaining if unicode_remaining is None else unicode_remaining,
        number_state=state.number_state if number_state is None else number_state,
        literal_target=state.literal_target,
        literal_index=state.literal_index if literal_index is None else literal_index,
    )


def _reset_scalar_mode(state: _JSONPrefixState) -> _JSONPrefixState:
    return _JSONPrefixState(root=state.root, stack=state.stack)


def _push(state: _JSONPrefixState, frame: _Frame) -> _JSONPrefixState:
    return _JSONPrefixState(root=state.root, stack=state.stack + (frame,))


def _replace_top(state: _JSONPrefixState, expect: str) -> _JSONPrefixState | None:
    if not state.stack:
        return None
    top = state.stack[-1]
    return _JSONPrefixState(
        root=state.root,
        stack=state.stack[:-1] + (_Frame(top.kind, expect),),
    )


def _close_container(state: _JSONPrefixState) -> _JSONPrefixState | None:
    if not state.stack:
        return None
    return _complete_value(_JSONPrefixState(root=state.root, stack=state.stack[:-1]))


def _complete_value(state: _JSONPrefixState) -> _JSONPrefixState | None:
    if not state.stack:
        return _JSONPrefixState(root="done")
    top = state.stack[-1]
    if top.kind == "object" and top.expect == "value":
        return _replace_top(state, "comma_or_end")
    if top.kind == "array" and top.expect in {"value", "value_or_end"}:
        return _replace_top(state, "comma_or_end")
    return None
