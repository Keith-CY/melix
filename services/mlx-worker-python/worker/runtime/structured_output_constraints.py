from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
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
_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    (
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
    )
)
_SUPPORTED_SCHEMA_TYPES = frozenset(
    ("object", "array", "string", "integer", "number", "boolean", "null")
)
_ANY_SCHEMA_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")


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


@dataclass(frozen=True, slots=True)
class _SchemaProperty:
    name: str
    node: "_SchemaNode"


@dataclass(frozen=True, slots=True)
class _SchemaNode:
    types: tuple[str, ...] = _ANY_SCHEMA_TYPES
    properties: tuple[_SchemaProperty, ...] = ()
    required: frozenset[str] = frozenset()
    additional: "_SchemaNode | None" = None
    items: "_SchemaNode | None" = None
    enum_json_values: frozenset[str] = frozenset()
    minimum: float | None = None
    maximum: float | None = None
    min_items: int = 0
    max_items: int | None = None


@dataclass(frozen=True, slots=True)
class _SchemaFrame:
    kind: str
    node: _SchemaNode
    expect: str
    seen: frozenset[str] = frozenset()
    pending_key: str = ""
    pending_value_node: _SchemaNode | None = None
    item_count: int = 0


@dataclass(frozen=True, slots=True)
class _SchemaPrefixState:
    root: str = "before"
    root_node: _SchemaNode | None = None
    stack: tuple[_SchemaFrame, ...] = ()
    mode: str = "normal"
    string_role: str = ""
    string_text: str = ""
    unicode_remaining: int = 0
    number_state: str = ""
    number_text: str = ""
    literal_target: str = ""
    literal_index: int = 0
    value_node: _SchemaNode | None = None
    fixed_candidates: frozenset[str] = frozenset()
    fixed_prefix: str = ""


_ANY_SCHEMA_NODE = _SchemaNode()
_INITIAL_JSON_OBJECT_STATE = _JSONPrefixState()


def normalize_structured_output_mode(execution_ext: object) -> str:
    raw_mode = _ext_get(execution_ext, _STRUCTURED_OUTPUT_MODE_KEY).strip().lower()
    if raw_mode in {"plain_text", "plaintext", "none"}:
        return "text"
    if raw_mode == "json":
        return "json_object"
    return raw_mode


def structured_output_requested(execution_ext: object) -> bool:
    mode = normalize_structured_output_mode(execution_ext)
    return bool(mode and mode != "text")


def schema_backed_json_schema_requested(execution_ext: object) -> bool:
    return (
        normalize_structured_output_mode(execution_ext) == "json_schema"
        and bool(_ext_get(execution_ext, _STRUCTURED_OUTPUT_SCHEMA_JSON_KEY).strip())
    )


def json_schema_constraint_error(execution_ext: object) -> StructuredOutputConstraintError | None:
    if not schema_backed_json_schema_requested(execution_ext):
        return None
    try:
        _compile_json_schema(_ext_get(execution_ext, _STRUCTURED_OUTPUT_SCHEMA_JSON_KEY))
    except StructuredOutputConstraintError as exc:
        return exc
    return None


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
        schema_json = _ext_get(execution_ext, _STRUCTURED_OUTPUT_SCHEMA_JSON_KEY)
        if not schema_json.strip():
            return []
        return [GrammarConstraintProcessor(tokenizer, schema=_compile_json_schema(schema_json))]
    raise StructuredOutputConstraintError(
        f"Unsupported structured output mode: {mode}.",
        details={
            "mode": mode,
            "enforcement": "sampler",
            "reason": "unsupported_mode",
        },
    )


class GrammarConstraintProcessor:
    """JSON-object or schema-aware grammar logits processor for mlx-lm generation."""

    def __init__(self, tokenizer: Any, *, schema: _SchemaNode | None = None) -> None:
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
        self._schema = schema
        self._base_token_count: int | None = None
        self._applied_generated_count = 0
        self._state: _JSONPrefixState | _SchemaPrefixState | None = (
            _SchemaPrefixState(root_node=schema)
            if schema is not None
            else _INITIAL_JSON_OBJECT_STATE
        )
        self._mask_cache: dict[
            tuple[_JSONPrefixState | _SchemaPrefixState | None, int],
            Any,
        ] = {}

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
            next_state = self._transition_text(state, text)
            if next_state is None:
                self._state = None
                return
            state = next_state
        self._state = state

    def _mask_for_state(
        self,
        state: _JSONPrefixState | _SchemaPrefixState | None,
        vocab_size: int,
        logits: Any,
    ) -> Any:
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

    def _token_allowed(
        self,
        state: _JSONPrefixState | _SchemaPrefixState,
        token_id: int,
    ) -> bool:
        if token_id in self._eos_token_ids and self._is_complete(state):
            return True
        text = self._id_to_text.get(token_id, "")
        return self._transition_text(state, text) is not None

    def _transition_text(
        self,
        state: _JSONPrefixState | _SchemaPrefixState,
        text: str,
    ) -> _JSONPrefixState | _SchemaPrefixState | None:
        if isinstance(state, _SchemaPrefixState):
            return _schema_transition_text(state, text)
        return _transition_text(state, text)

    def _is_complete(self, state: _JSONPrefixState | _SchemaPrefixState) -> bool:
        if isinstance(state, _SchemaPrefixState):
            return _schema_is_complete(state)
        return _is_complete(state)


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


@lru_cache(maxsize=128)
def _compile_json_schema(schema_json: str) -> _SchemaNode:
    try:
        raw_schema = json.loads(schema_json)
    except json.JSONDecodeError as exc:
        raise StructuredOutputConstraintError(
            "response_format json_schema contains malformed JSON.",
            details={
                "mode": "json_schema",
                "enforcement": "sampler",
                "reason": "json_schema_invalid",
                "message": exc.msg,
            },
        ) from exc
    node = _compile_schema_node(raw_schema, pointer="")
    if "object" not in node.types:
        raise StructuredOutputConstraintError(
            "response_format json_schema root must be an object schema.",
            details={
                "mode": "json_schema",
                "enforcement": "sampler",
                "reason": "json_schema_root_not_object",
            },
        )
    return node


def _compile_schema_node(raw_schema: object, *, pointer: str) -> _SchemaNode:
    if raw_schema is True:
        return _ANY_SCHEMA_NODE
    if raw_schema is False:
        raise _schema_error(
            "response_format json_schema false schemas are not supported.",
            reason="json_schema_unsupported_keyword",
            keyword="false_schema",
            pointer=pointer,
        )
    if not isinstance(raw_schema, dict):
        raise _schema_error(
            "response_format json_schema nodes must be JSON objects.",
            reason="json_schema_invalid",
            pointer=pointer,
        )

    for keyword in raw_schema:
        if keyword not in _SUPPORTED_SCHEMA_KEYWORDS:
            raise _schema_error(
                f"response_format json_schema keyword is not supported: {keyword}.",
                reason="json_schema_unsupported_keyword",
                keyword=keyword,
                pointer=pointer,
            )

    enum_json_values = _schema_enum_json_values(raw_schema, pointer=pointer)
    types = _schema_types(raw_schema, enum_json_values, pointer=pointer)
    enum_json_values = _schema_enum_json_values_matching_types(
        enum_json_values,
        types,
        pointer=pointer,
    )
    properties = _schema_properties(raw_schema, pointer=pointer)
    required = _schema_required(raw_schema, pointer=pointer)
    additional = _schema_additional(raw_schema, pointer=pointer)
    items = _schema_items(raw_schema, pointer=pointer)
    minimum = _schema_number_bound(raw_schema, "minimum", pointer=pointer)
    maximum = _schema_number_bound(raw_schema, "maximum", pointer=pointer)
    min_items = _schema_non_negative_int(raw_schema, "minItems", default=0, pointer=pointer)
    max_items = (
        _schema_non_negative_int(raw_schema, "maxItems", default=0, pointer=pointer)
        if "maxItems" in raw_schema
        else None
    )
    if max_items is not None and max_items < min_items:
        raise _schema_error(
            "response_format json_schema maxItems must be greater than or equal to minItems.",
            reason="json_schema_invalid",
            pointer=pointer,
        )
    if required and "object" not in types:
        raise _schema_error(
            "response_format json_schema required is only supported for object schemas.",
            reason="json_schema_invalid",
            pointer=pointer,
        )
    property_names = frozenset(prop.name for prop in properties)
    unknown_required = required - property_names
    if unknown_required and additional is None:
        raise _schema_error(
            "response_format json_schema required properties must be declared when additionalProperties is false.",
            reason="json_schema_invalid",
            keyword=sorted(unknown_required)[0],
            pointer=pointer,
        )
    if items is not None and "array" not in types:
        raise _schema_error(
            "response_format json_schema items is only supported for array schemas.",
            reason="json_schema_invalid",
            pointer=pointer,
        )
    if (min_items or max_items is not None) and "array" not in types:
        raise _schema_error(
            "response_format json_schema minItems/maxItems are only supported for array schemas.",
            reason="json_schema_invalid",
            pointer=pointer,
        )
    if (minimum is not None or maximum is not None) and not ({"number", "integer"} & set(types)):
        raise _schema_error(
            "response_format json_schema minimum/maximum are only supported for numeric schemas.",
            reason="json_schema_invalid",
            pointer=pointer,
        )

    return _SchemaNode(
        types=types,
        properties=properties,
        required=required,
        additional=additional,
        items=items,
        enum_json_values=enum_json_values,
        minimum=minimum,
        maximum=maximum,
        min_items=min_items,
        max_items=max_items,
    )


def _schema_enum_json_values(raw_schema: dict[str, object], *, pointer: str) -> frozenset[str]:
    const_json: str | None = None
    if "const" in raw_schema:
        const_json = json.dumps(raw_schema["const"], ensure_ascii=False, separators=(",", ":"))
    enum_json_values: frozenset[str] = frozenset()
    if "enum" in raw_schema:
        raw_enum = raw_schema["enum"]
        if not isinstance(raw_enum, list) or not raw_enum:
            raise _schema_error(
                "response_format json_schema enum must be a non-empty array.",
                reason="json_schema_invalid",
                keyword="enum",
                pointer=pointer,
            )
        enum_json_values = frozenset(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) for value in raw_enum
        )
    if const_json is not None and enum_json_values:
        if const_json not in enum_json_values:
            raise _schema_error(
                "response_format json_schema const must be one of the enum values.",
                reason="json_schema_unsatisfiable",
                keyword="const",
                pointer=pointer,
            )
        return frozenset((const_json,))
    if const_json is not None:
        return frozenset((const_json,))
    if enum_json_values:
        return enum_json_values
    return frozenset()


def _schema_enum_json_values_matching_types(
    enum_json_values: frozenset[str],
    types: tuple[str, ...],
    *,
    pointer: str,
) -> frozenset[str]:
    if not enum_json_values:
        return frozenset()
    matching = frozenset(
        value
        for value in enum_json_values
        if any(_schema_json_value_matches_type(value, schema_type) for schema_type in types)
    )
    if not matching:
        raise _schema_error(
            "response_format json_schema enum/const values do not match the declared type.",
            reason="json_schema_unsatisfiable",
            keyword="enum",
            pointer=pointer,
        )
    return matching


def _schema_types(
    raw_schema: dict[str, object],
    enum_json_values: frozenset[str],
    *,
    pointer: str,
) -> tuple[str, ...]:
    raw_type = raw_schema.get("type")
    if raw_type is None:
        if "properties" in raw_schema or "required" in raw_schema or "additionalProperties" in raw_schema:
            return ("object",)
        if "items" in raw_schema or "minItems" in raw_schema or "maxItems" in raw_schema:
            return ("array",)
        if enum_json_values:
            return tuple(
                item
                for item in _ANY_SCHEMA_TYPES
                if any(_schema_json_value_matches_type(value, item) for value in enum_json_values)
            )
        return _ANY_SCHEMA_TYPES
    values = raw_type if isinstance(raw_type, list) else [raw_type]
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or value not in _SUPPORTED_SCHEMA_TYPES:
            raise _schema_error(
                "response_format json_schema type is not supported.",
                reason="json_schema_unsupported_type",
                keyword=str(value),
                pointer=f"{pointer}/type" if pointer else "/type",
            )
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _schema_json_value_matches_type(value_json: str, schema_type: str) -> bool:
    value = json.loads(value_json)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return False


def _schema_properties(raw_schema: dict[str, object], *, pointer: str) -> tuple[_SchemaProperty, ...]:
    raw_properties = raw_schema.get("properties", {})
    if raw_properties is None:
        raw_properties = {}
    if not isinstance(raw_properties, dict):
        raise _schema_error(
            "response_format json_schema properties must be an object.",
            reason="json_schema_invalid",
            keyword="properties",
            pointer=pointer,
        )
    properties: list[_SchemaProperty] = []
    for name, child_schema in sorted(raw_properties.items()):
        if not isinstance(name, str):
            raise _schema_error(
                "response_format json_schema property names must be strings.",
                reason="json_schema_invalid",
                keyword="properties",
                pointer=pointer,
            )
        properties.append(
            _SchemaProperty(
                name=name,
                node=_compile_schema_node(child_schema, pointer=f"{pointer}/properties/{name}"),
            )
        )
    return tuple(properties)


def _schema_required(raw_schema: dict[str, object], *, pointer: str) -> frozenset[str]:
    raw_required = raw_schema.get("required", [])
    if raw_required is None:
        raw_required = []
    if not isinstance(raw_required, list) or any(not isinstance(item, str) for item in raw_required):
        raise _schema_error(
            "response_format json_schema required must be an array of property names.",
            reason="json_schema_invalid",
            keyword="required",
            pointer=pointer,
        )
    return frozenset(raw_required)


def _schema_additional(raw_schema: dict[str, object], *, pointer: str) -> _SchemaNode | None:
    raw_additional = raw_schema.get("additionalProperties", True)
    if raw_additional is False:
        return None
    if raw_additional is True:
        return _ANY_SCHEMA_NODE
    if isinstance(raw_additional, dict):
        return _compile_schema_node(raw_additional, pointer=f"{pointer}/additionalProperties")
    raise _schema_error(
        "response_format json_schema additionalProperties must be a boolean or schema object.",
        reason="json_schema_invalid",
        keyword="additionalProperties",
        pointer=pointer,
    )


def _schema_items(raw_schema: dict[str, object], *, pointer: str) -> _SchemaNode | None:
    if "items" not in raw_schema:
        return None
    raw_items = raw_schema["items"]
    if isinstance(raw_items, list):
        raise _schema_error(
            "response_format json_schema tuple-style items are not supported.",
            reason="json_schema_unsupported_keyword",
            keyword="items[]",
            pointer=pointer,
        )
    return _compile_schema_node(raw_items, pointer=f"{pointer}/items")


def _schema_number_bound(
    raw_schema: dict[str, object],
    keyword: str,
    *,
    pointer: str,
) -> float | None:
    if keyword not in raw_schema:
        return None
    value = raw_schema[keyword]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _schema_error(
            f"response_format json_schema {keyword} must be numeric.",
            reason="json_schema_invalid",
            keyword=keyword,
            pointer=pointer,
        )
    return float(value)


def _schema_non_negative_int(
    raw_schema: dict[str, object],
    keyword: str,
    *,
    default: int,
    pointer: str,
) -> int:
    if keyword not in raw_schema:
        return default
    value = raw_schema[keyword]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _schema_error(
            f"response_format json_schema {keyword} must be a non-negative integer.",
            reason="json_schema_invalid",
            keyword=keyword,
            pointer=pointer,
        )
    return value


def _schema_error(
    message: str,
    *,
    reason: str,
    keyword: str = "",
    pointer: str = "",
) -> StructuredOutputConstraintError:
    details = {
        "mode": "json_schema",
        "enforcement": "sampler",
        "reason": reason,
    }
    if keyword:
        details["keyword"] = keyword
    if pointer:
        details["schema_pointer"] = pointer
    return StructuredOutputConstraintError(message, details=details)


def _schema_is_complete(state: _SchemaPrefixState) -> bool:
    return state.mode == "normal" and state.root == "done" and not state.stack


@lru_cache(maxsize=8192)
def _schema_transition_text(
    state: _SchemaPrefixState,
    text: str,
) -> _SchemaPrefixState | None:
    if not text:
        return None
    next_state: _SchemaPrefixState | None = state
    for char in text:
        if next_state is None:
            return None
        next_state = _schema_transition_char(next_state, char)
    return next_state


def _schema_transition_char(state: _SchemaPrefixState, char: str) -> _SchemaPrefixState | None:
    if state.mode == "string":
        return _schema_consume_string_char(state, char)
    if state.mode == "escape":
        return _schema_consume_escape_char(state, char)
    if state.mode == "unicode":
        return _schema_consume_unicode_char(state, char)
    if state.mode == "number":
        return _schema_consume_number_char(state, char)
    if state.mode == "literal":
        return _schema_consume_literal_char(state, char)
    if state.mode == "fixed":
        return _schema_consume_fixed_char(state, char)
    return _schema_consume_normal_char(state, char)


def _schema_consume_normal_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    if state.root == "done":
        return state if char in _JSON_WHITESPACE else None
    if not state.stack:
        if char in _JSON_WHITESPACE:
            return state
        return _schema_start_value(state, state.root_node or _ANY_SCHEMA_NODE, char)
    frame = state.stack[-1]
    if frame.kind == "object":
        return _schema_consume_object_char(state, frame, char)
    if frame.kind == "array":
        return _schema_consume_array_char(state, frame, char)
    return None


def _schema_consume_object_char(
    state: _SchemaPrefixState,
    frame: _SchemaFrame,
    char: str,
) -> _SchemaPrefixState | None:
    if char in _JSON_WHITESPACE:
        return state
    if frame.expect == "key_or_end":
        if char == "}" and frame.node.required.issubset(frame.seen):
            return _schema_close_container(state)
        if char == '"':
            return _schema_enter_string(state, role="key")
        return None
    if frame.expect == "key":
        return _schema_enter_string(state, role="key") if char == '"' else None
    if frame.expect == "colon":
        return _schema_replace_top(state, "value") if char == ":" else None
    if frame.expect == "value" and frame.pending_value_node is not None:
        return _schema_start_value(state, frame.pending_value_node, char)
    if frame.expect == "comma_or_end":
        if char == "," and _schema_object_available_keys(frame):
            return _schema_replace_top(
                state,
                "key",
                pending_key="",
                pending_value_node=None,
            )
        if char == "}" and frame.node.required.issubset(frame.seen):
            return _schema_close_container(state)
    return None


def _schema_consume_array_char(
    state: _SchemaPrefixState,
    frame: _SchemaFrame,
    char: str,
) -> _SchemaPrefixState | None:
    if char in _JSON_WHITESPACE:
        return state
    items = frame.node.items or _ANY_SCHEMA_NODE
    if frame.expect == "value_or_end":
        if char == "]" and frame.item_count >= frame.node.min_items:
            return _schema_close_container(state)
        if _schema_array_can_accept_value(frame):
            return _schema_start_value(state, items, char)
        return None
    if frame.expect == "value":
        return _schema_start_value(state, items, char) if _schema_array_can_accept_value(frame) else None
    if frame.expect == "comma_or_end":
        if char == "," and _schema_array_can_accept_value(frame):
            return _schema_replace_top(state, "value")
        if char == "]" and frame.item_count >= frame.node.min_items:
            return _schema_close_container(state)
    return None


def _schema_start_value(
    state: _SchemaPrefixState,
    node: _SchemaNode,
    char: str,
) -> _SchemaPrefixState | None:
    if char in _JSON_WHITESPACE:
        return state
    if node.enum_json_values:
        return _schema_enter_fixed_value(state, node, char)
    allowed = set(node.types)
    if char == "{" and "object" in allowed:
        return _schema_push(
            state,
            _SchemaFrame(kind="object", node=node, expect="key_or_end"),
        )
    if char == "[" and "array" in allowed:
        return _schema_push(
            state,
            _SchemaFrame(kind="array", node=node, expect="value_or_end"),
        )
    if char == '"' and "string" in allowed:
        return _schema_enter_string(state, role="value", value_node=node)
    if char == "t" and "boolean" in allowed:
        return _schema_enter_literal(state, node, "true")
    if char == "f" and "boolean" in allowed:
        return _schema_enter_literal(state, node, "false")
    if char == "n" and "null" in allowed:
        return _schema_enter_literal(state, node, "null")
    if {"number", "integer"} & allowed:
        if char == "-":
            return _schema_enter_number(state, node, "after_minus", char)
        if char == "0":
            return _schema_enter_number(state, node, "zero", char)
        if "1" <= char <= "9":
            return _schema_enter_number(state, node, "int", char)
    return None


def _schema_enter_fixed_value(
    state: _SchemaPrefixState,
    node: _SchemaNode,
    char: str,
) -> _SchemaPrefixState | None:
    prefix = char
    if not any(candidate.startswith(prefix) for candidate in node.enum_json_values):
        return None
    next_state = _schema_replace_mode(
        state,
        mode="fixed",
        value_node=node,
        fixed_candidates=node.enum_json_values,
        fixed_prefix=prefix,
    )
    return _schema_complete_fixed_if_unambiguous(next_state)


def _schema_consume_fixed_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    prefix = f"{state.fixed_prefix}{char}"
    if any(candidate.startswith(prefix) for candidate in state.fixed_candidates):
        return _schema_complete_fixed_if_unambiguous(
            _schema_replace_mode(state, fixed_prefix=prefix)
        )
    if state.fixed_prefix in state.fixed_candidates:
        completed = _schema_complete_value(_schema_reset_scalar_mode(state))
        return _schema_transition_char(completed, char) if completed is not None else None
    return None


def _schema_complete_fixed_if_unambiguous(state: _SchemaPrefixState) -> _SchemaPrefixState:
    if state.fixed_prefix in state.fixed_candidates and not any(
        candidate != state.fixed_prefix and candidate.startswith(state.fixed_prefix)
        for candidate in state.fixed_candidates
    ):
        completed = _schema_complete_value(_schema_reset_scalar_mode(state))
        return completed if completed is not None else state
    return state


def _schema_consume_string_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    if char == '"':
        if state.string_role == "key":
            return _schema_complete_key_string(state)
        if state.string_role == "value" and _schema_node_allows_type(state.value_node, "string"):
            return _schema_complete_value(_schema_reset_scalar_mode(state))
        return None
    if char == "\\":
        return _schema_replace_mode(state, mode="escape")
    if ord(char) < 0x20:
        return None
    next_text = f"{state.string_text}{char}"
    if state.string_role == "key" and not _schema_key_prefix_allowed(state, next_text):
        return None
    return _schema_replace_mode(state, string_text=next_text)


def _schema_consume_escape_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    if char == "u":
        return _schema_replace_mode(state, mode="unicode", unicode_remaining=4)
    escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    if char not in escapes:
        return None
    next_text = f"{state.string_text}{escapes[char]}"
    if state.string_role == "key" and not _schema_key_prefix_allowed(state, next_text):
        return None
    return _schema_replace_mode(state, mode="string", string_text=next_text)


def _schema_consume_unicode_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    if char not in _JSON_HEX:
        return None
    remaining = state.unicode_remaining - 1
    if remaining <= 0:
        # Keep escaped unicode key/value text broad. Supported property names in Melix schemas
        # are emitted directly by the gateway, so escaped-key matching is intentionally refused
        # unless the object allows additional properties.
        if state.string_role == "key" and not _schema_top_frame(state).node.additional:
            return None
        return _schema_replace_mode(state, mode="string", unicode_remaining=0)
    return _schema_replace_mode(state, unicode_remaining=remaining)


def _schema_consume_literal_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    target = state.literal_target
    index = state.literal_index
    if index >= len(target) or char != target[index]:
        return None
    index += 1
    if index == len(target):
        return _schema_complete_value(_schema_reset_scalar_mode(state))
    return _schema_replace_mode(state, literal_index=index)


def _schema_consume_number_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    number_state = state.number_state
    if char in _JSON_NUMBER_DELIMITERS and number_state in _JSON_NUMBER_FINAL_STATES:
        if not _schema_number_satisfies_node(state.value_node, state.number_text):
            return None
        completed = _schema_complete_value(_schema_reset_scalar_mode(state))
        return _schema_transition_char(completed, char) if completed is not None else None
    if number_state == "after_minus":
        if char == "0":
            return _schema_replace_mode(state, number_state="zero", number_text=f"{state.number_text}{char}")
        if "1" <= char <= "9":
            return _schema_replace_mode(state, number_state="int", number_text=f"{state.number_text}{char}")
        return None
    if number_state == "zero":
        if char == "." and _schema_node_allows_type(state.value_node, "number"):
            return _schema_replace_mode(state, number_state="frac_start", number_text=f"{state.number_text}{char}")
        if char in {"e", "E"} and _schema_node_allows_type(state.value_node, "number"):
            return _schema_replace_mode(state, number_state="exp_start", number_text=f"{state.number_text}{char}")
        return None
    if number_state == "int":
        if char.isdigit():
            return _schema_replace_mode(state, number_text=f"{state.number_text}{char}")
        if char == "." and _schema_node_allows_type(state.value_node, "number"):
            return _schema_replace_mode(state, number_state="frac_start", number_text=f"{state.number_text}{char}")
        if char in {"e", "E"} and _schema_node_allows_type(state.value_node, "number"):
            return _schema_replace_mode(state, number_state="exp_start", number_text=f"{state.number_text}{char}")
        return None
    if number_state == "frac_start":
        return (
            _schema_replace_mode(state, number_state="frac", number_text=f"{state.number_text}{char}")
            if char.isdigit()
            else None
        )
    if number_state == "frac":
        if char.isdigit():
            return _schema_replace_mode(state, number_text=f"{state.number_text}{char}")
        if char in {"e", "E"}:
            return _schema_replace_mode(state, number_state="exp_start", number_text=f"{state.number_text}{char}")
        return None
    if number_state == "exp_start":
        if char in {"+", "-"}:
            return _schema_replace_mode(state, number_state="exp_sign", number_text=f"{state.number_text}{char}")
        if char.isdigit():
            return _schema_replace_mode(state, number_state="exp", number_text=f"{state.number_text}{char}")
        return None
    if number_state == "exp_sign":
        return (
            _schema_replace_mode(state, number_state="exp", number_text=f"{state.number_text}{char}")
            if char.isdigit()
            else None
        )
    if number_state == "exp":
        return _schema_replace_mode(state, number_text=f"{state.number_text}{char}") if char.isdigit() else None
    return None


def _schema_enter_string(
    state: _SchemaPrefixState,
    *,
    role: str,
    value_node: _SchemaNode | None = None,
) -> _SchemaPrefixState:
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack,
        mode="string",
        string_role=role,
        value_node=value_node,
    )


def _schema_enter_literal(
    state: _SchemaPrefixState,
    node: _SchemaNode,
    target: str,
) -> _SchemaPrefixState:
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack,
        mode="literal",
        literal_target=target,
        literal_index=1,
        value_node=node,
    )


def _schema_enter_number(
    state: _SchemaPrefixState,
    node: _SchemaNode,
    number_state: str,
    char: str,
) -> _SchemaPrefixState:
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack,
        mode="number",
        number_state=number_state,
        number_text=char,
        value_node=node,
    )


def _schema_replace_mode(
    state: _SchemaPrefixState,
    *,
    mode: str | None = None,
    string_text: str | None = None,
    unicode_remaining: int | None = None,
    number_state: str | None = None,
    number_text: str | None = None,
    literal_index: int | None = None,
    value_node: _SchemaNode | None = None,
    fixed_candidates: frozenset[str] | None = None,
    fixed_prefix: str | None = None,
) -> _SchemaPrefixState:
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack,
        mode=state.mode if mode is None else mode,
        string_role=state.string_role,
        string_text=state.string_text if string_text is None else string_text,
        unicode_remaining=state.unicode_remaining if unicode_remaining is None else unicode_remaining,
        number_state=state.number_state if number_state is None else number_state,
        number_text=state.number_text if number_text is None else number_text,
        literal_target=state.literal_target,
        literal_index=state.literal_index if literal_index is None else literal_index,
        value_node=state.value_node if value_node is None else value_node,
        fixed_candidates=state.fixed_candidates if fixed_candidates is None else fixed_candidates,
        fixed_prefix=state.fixed_prefix if fixed_prefix is None else fixed_prefix,
    )


def _schema_reset_scalar_mode(state: _SchemaPrefixState) -> _SchemaPrefixState:
    return _SchemaPrefixState(root=state.root, root_node=state.root_node, stack=state.stack)


def _schema_push(state: _SchemaPrefixState, frame: _SchemaFrame) -> _SchemaPrefixState:
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack + (frame,),
    )


def _schema_replace_top(
    state: _SchemaPrefixState,
    expect: str,
    *,
    seen: frozenset[str] | None = None,
    pending_key: str | None = None,
    pending_value_node: _SchemaNode | None = None,
    item_count: int | None = None,
) -> _SchemaPrefixState | None:
    if not state.stack:
        return None
    top = state.stack[-1]
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack[:-1]
        + (
            _SchemaFrame(
                kind=top.kind,
                node=top.node,
                expect=expect,
                seen=top.seen if seen is None else seen,
                pending_key=top.pending_key if pending_key is None else pending_key,
                pending_value_node=(
                    top.pending_value_node
                    if pending_value_node is None and pending_key is None
                    else pending_value_node
                ),
                item_count=top.item_count if item_count is None else item_count,
            ),
        ),
    )


def _schema_close_container(state: _SchemaPrefixState) -> _SchemaPrefixState | None:
    if not state.stack:
        return None
    return _schema_complete_value(
        _SchemaPrefixState(root=state.root, root_node=state.root_node, stack=state.stack[:-1])
    )


def _schema_complete_value(state: _SchemaPrefixState) -> _SchemaPrefixState | None:
    if not state.stack:
        return _SchemaPrefixState(root="done", root_node=state.root_node)
    top = state.stack[-1]
    if top.kind == "object" and top.expect == "value":
        return _schema_replace_top(
            state,
            "comma_or_end",
            seen=top.seen | frozenset((top.pending_key,)),
            pending_key="",
            pending_value_node=None,
        )
    if top.kind == "array" and top.expect in {"value", "value_or_end"}:
        return _schema_replace_top(
            state,
            "comma_or_end",
            item_count=top.item_count + 1,
        )
    return None


def _schema_complete_key_string(state: _SchemaPrefixState) -> _SchemaPrefixState | None:
    frame = _schema_top_frame(state)
    key = state.string_text
    if key in frame.seen:
        return None
    property_node = _schema_property_node(frame.node, key)
    value_node = property_node if property_node is not None else frame.node.additional
    if value_node is None:
        return None
    return _schema_replace_top(
        _schema_reset_scalar_mode(state),
        "colon",
        pending_key=key,
        pending_value_node=value_node,
    )


def _schema_top_frame(state: _SchemaPrefixState) -> _SchemaFrame:
    return state.stack[-1]


def _schema_property_node(node: _SchemaNode, key: str) -> _SchemaNode | None:
    for prop in node.properties:
        if prop.name == key:
            return prop.node
    return None


def _schema_key_prefix_allowed(state: _SchemaPrefixState, prefix: str) -> bool:
    frame = _schema_top_frame(state)
    if frame.node.additional is not None:
        return True
    return any(
        prop.name not in frame.seen and prop.name.startswith(prefix)
        for prop in frame.node.properties
    )


def _schema_object_available_keys(frame: _SchemaFrame) -> bool:
    if frame.node.additional is not None:
        return True
    return any(prop.name not in frame.seen for prop in frame.node.properties)


def _schema_array_can_accept_value(frame: _SchemaFrame) -> bool:
    return frame.node.max_items is None or frame.item_count < frame.node.max_items


def _schema_node_allows_type(node: _SchemaNode | None, schema_type: str) -> bool:
    return node is None or schema_type in node.types


def _schema_number_satisfies_node(node: _SchemaNode | None, text: str) -> bool:
    if node is None:
        return True
    try:
        value = float(text)
    except ValueError:
        return False
    if "integer" in node.types and "number" not in node.types and not value.is_integer():
        return False
    if node.minimum is not None and value < node.minimum:
        return False
    if node.maximum is not None and value > node.maximum:
        return False
    return True


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
