from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from functools import lru_cache, update_wrapper
import json
import math
from threading import RLock
from time import monotonic
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


_STRUCTURED_OUTPUT_MODE_KEY = "melix.structured_output.mode"
_STRUCTURED_OUTPUT_SCHEMA_JSON_KEY = "melix.structured_output.schema_json"
_TOKENIZER_EOS_CACHE_ATTR = "_melix_structured_output_eos_token_ids_cache"
_TOKENIZER_MASK_TEMPLATE_CACHE_ATTR = "_melix_structured_output_mask_template_cache"
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
        "description",
        "title",
        "default",
        "examples",
    )
)
_SUPPORTED_SCHEMA_TYPES = frozenset(
    ("object", "array", "string", "integer", "number", "boolean", "null")
)
_ANY_SCHEMA_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")
_MAX_SCHEMA_JSON_BYTES = 65_536
_MAX_SCHEMA_DEPTH = 32
_MAX_SCHEMA_NODES = 1_024
_MAX_SCHEMA_PROPERTIES = 256
_MAX_SCHEMA_REQUIRED = 256
_MAX_SCHEMA_ENUM_VALUES = 1_024
_MAX_SCHEMA_ENUM_TEXT_BYTES = 32_768
_MAX_SCHEMA_ARRAY_ITEMS = 1_024
_MAX_SCHEMA_NUMBER_CHARS = 128
_SCHEMA_COMPILE_DEADLINE_SECONDS = 0.050
_MAX_MASK_CACHE_ENTRIES = 64
_MAX_MASK_TEMPLATE_CACHE_ENTRIES = 64
_MAX_MASK_TEMPLATE_CACHE_ESTIMATED_BYTES = 64 * 1024 * 1024
_MAX_SCHEMA_CACHE_ENTRIES = 32
_MAX_SCHEMA_CACHE_ESTIMATED_BYTES = 16 * 1024 * 1024
_MAX_EXPONENT_MAGNITUDE = 1_024
_MAX_STATE_EXPLORATION_STATES = 4_096
_MAX_STATE_EXPLORATION_TRANSITIONS = 32_768
_MAX_STATE_EXPLORATION_SECONDS = 0.050


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


@runtime_checkable
class SamplerLogitsConstraint(Protocol):
    """Common receipt surface for request-owned sampler constraints."""

    @property
    def constraint_kind(self) -> str: ...

    @property
    def packed_allow_token_mask(self) -> tuple[int, ...]: ...

    @property
    def acceleration_receipt(self) -> dict[str, object]: ...


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


@dataclass(frozen=True, slots=True, eq=False)
class _FixedValueTrie:
    terminal: bool
    children: Mapping[str, "_FixedValueTrie"]


@dataclass(frozen=True, slots=True, eq=False)
class _SchemaNode:
    types: tuple[str, ...] = _ANY_SCHEMA_TYPES
    properties: tuple[_SchemaProperty, ...] = ()
    required: frozenset[str] = frozenset()
    additional: "_SchemaNode | None" = None
    items: "_SchemaNode | None" = None
    enum_json_values: frozenset[str] = frozenset()
    enum_trie: _FixedValueTrie | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
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
    unicode_digits: str = ""
    unicode_high_surrogate: int = 0
    number_state: str = ""
    number_text: str = ""
    literal_target: str = ""
    literal_index: int = 0
    value_node: _SchemaNode | None = None
    fixed_trie: _FixedValueTrie | None = None


@dataclass(slots=True)
class _SchemaCompileBudget:
    node_count: int = 0
    deadline: float | None = None
    clock: Callable[[], float] | None = None
    mode: str = "json_schema"


@dataclass(frozen=True, slots=True)
class _MaskTemplate:
    dense: Any
    packed: tuple[int, ...]
    estimated_bytes: int


@dataclass(slots=True)
class _MaskTemplateCache:
    entries: OrderedDict[object, _MaskTemplate] = field(default_factory=OrderedDict)
    estimated_bytes: int = 0


@dataclass(frozen=True, slots=True)
class _WeightedCacheInfo:
    hits: int
    misses: int
    maxsize: int
    currsize: int
    maxbytes: int
    currbytes: int


class _WeightedLRUCache:
    def __init__(
        self,
        function: Callable[..., Any],
        *,
        maxsize: int,
        maxbytes: int,
        weight: Callable[[tuple[Any, ...], Mapping[str, Any], Any], int],
    ) -> None:
        self._function = function
        self._maxsize = maxsize
        self._maxbytes = maxbytes
        self._weight = weight
        self._entries: OrderedDict[object, tuple[Any, int]] = OrderedDict()
        self._estimated_bytes = 0
        self._hits = 0
        self._misses = 0
        self._lock = RLock()
        update_wrapper(self, function)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        key = self._key(args, kwargs)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._hits += 1
                self._entries.move_to_end(key)
                return cached[0]
            self._misses += 1

        value = self._function(*args, **kwargs)
        estimated_bytes = max(1, int(self._weight(args, kwargs, value)))
        if estimated_bytes > self._maxbytes:
            return value

        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached[0]
            self._entries[key] = (value, estimated_bytes)
            self._estimated_bytes += estimated_bytes
            while (
                len(self._entries) > self._maxsize
                or self._estimated_bytes > self._maxbytes
            ):
                _, (_, evicted_bytes) = self._entries.popitem(last=False)
                self._estimated_bytes -= evicted_bytes
        return value

    def cache_clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._estimated_bytes = 0
            self._hits = 0
            self._misses = 0

    def cache_info(self) -> _WeightedCacheInfo:
        with self._lock:
            return _WeightedCacheInfo(
                hits=self._hits,
                misses=self._misses,
                maxsize=self._maxsize,
                currsize=len(self._entries),
                maxbytes=self._maxbytes,
                currbytes=self._estimated_bytes,
            )

    @staticmethod
    def _key(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> object:
        if not kwargs:
            return args
        return args, tuple(sorted(kwargs.items()))


def _weighted_lru_cache(
    *,
    maxsize: int,
    maxbytes: int,
    weight: Callable[[tuple[Any, ...], Mapping[str, Any], Any], int],
) -> Callable[[Callable[..., Any]], _WeightedLRUCache]:
    def decorate(function: Callable[..., Any]) -> _WeightedLRUCache:
        return _WeightedLRUCache(
            function,
            maxsize=maxsize,
            maxbytes=maxbytes,
            weight=weight,
        )

    return decorate


def _schema_graph_estimated_bytes(root: _SchemaNode) -> int:
    estimated_bytes = 0
    schema_stack = [root]
    trie_stack: list[_FixedValueTrie] = []
    seen_schema: set[int] = set()
    seen_trie: set[int] = set()
    while schema_stack:
        node = schema_stack.pop()
        identity = id(node)
        if identity in seen_schema:
            continue
        seen_schema.add(identity)
        estimated_bytes += 512
        estimated_bytes += sum(_utf8_estimated_size(item) + 32 for item in node.types)
        estimated_bytes += sum(_utf8_estimated_size(item) + 64 for item in node.required)
        estimated_bytes += sum(
            _utf8_estimated_size(item) + 64 for item in node.enum_json_values
        )
        for prop in node.properties:
            estimated_bytes += _utf8_estimated_size(prop.name) + 128
            schema_stack.append(prop.node)
        if node.additional is not None:
            schema_stack.append(node.additional)
        if node.items is not None:
            schema_stack.append(node.items)
        if node.enum_trie is not None:
            trie_stack.append(node.enum_trie)

    while trie_stack:
        trie = trie_stack.pop()
        identity = id(trie)
        if identity in seen_trie:
            continue
        seen_trie.add(identity)
        estimated_bytes += 192 + len(trie.children) * 96
        for char, child in trie.children.items():
            estimated_bytes += _utf8_estimated_size(char)
            trie_stack.append(child)
    return estimated_bytes


def _utf8_estimated_size(value: str) -> int:
    return len(value.encode("utf-8", errors="surrogatepass"))


def _schema_cache_weight(
    args: tuple[Any, ...],
    _kwargs: Mapping[str, Any],
    root: _SchemaNode,
) -> int:
    schema_json = args[0]
    return _utf8_estimated_size(schema_json) + _schema_graph_estimated_bytes(root)


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


def sampler_constraint_requested(execution_ext: object) -> bool:
    if execution_ext is None or (isinstance(execution_ext, Mapping) and not execution_ext):
        return False
    mode = normalize_structured_output_mode(execution_ext)
    structured_constraint_requested = (
        schema_backed_json_schema_requested(execution_ext)
        if mode == "json_schema"
        else bool(mode and mode != "text")
    )
    if structured_constraint_requested:
        return True
    from worker.runtime.tool_wire_constraints import tool_constraint_requested

    return tool_constraint_requested(execution_ext)


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


def sampler_constraint_preflight_error(
    execution_ext: object,
) -> StructuredOutputConstraintError | None:
    schema_error = json_schema_constraint_error(execution_ext)
    if schema_error is not None:
        return schema_error
    from worker.runtime.tool_wire_constraints import tool_constraint_preflight_error

    return tool_constraint_preflight_error(execution_ext)


def build_structured_output_logits_processors(
    execution_ext: object,
    tokenizer: Any,
) -> list[Any]:
    from worker.runtime.tool_wire_constraints import (
        build_tool_choice_logits_processors,
        tool_constraint_requested,
    )

    if tool_constraint_requested(execution_ext):
        processors = build_tool_choice_logits_processors(execution_ext, tokenizer)
        _attach_acceleration_receipt(execution_ext, processors)
        return processors
    mode = normalize_structured_output_mode(execution_ext)
    if not mode or mode == "text":
        return []
    if mode == "json_object":
        processors = [GrammarConstraintProcessor(tokenizer)]
        _attach_acceleration_receipt(execution_ext, processors)
        return processors
    if mode == "json_schema":
        schema_json = _ext_get(execution_ext, _STRUCTURED_OUTPUT_SCHEMA_JSON_KEY)
        if not schema_json.strip():
            return []
        processors = [GrammarConstraintProcessor(tokenizer, schema=_compile_json_schema(schema_json))]
        _attach_acceleration_receipt(execution_ext, processors)
        return processors
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
                    "mode": "json_schema" if schema is not None else "json_object",
                    "enforcement": "sampler",
                    "reason": "tokenizer_vocab_unavailable",
                },
        )
        self._id_to_text = vocabulary
        vocab_size = max(_tokenizer_vocab_size(tokenizer), max(vocabulary) + 1)
        self._mask_vocab_words = math.ceil(vocab_size / 64)
        self._eos_token_ids = _tokenizer_eos_token_ids(tokenizer, vocabulary)
        self._constraint_kind = "json_schema" if schema is not None else "json_object"
        self._base_token_count: int | None = None
        self._applied_generated_count = 0
        self._state: _JSONPrefixState | _SchemaPrefixState | None = (
            _SchemaPrefixState(root_node=schema)
            if schema is not None
            else _INITIAL_JSON_OBJECT_STATE
        )
        self._mask_cache: OrderedDict[
            tuple[_JSONPrefixState | _SchemaPrefixState | None, int, bool],
            _MaskTemplate,
        ] = OrderedDict()
        template_cache = getattr(tokenizer, _TOKENIZER_MASK_TEMPLATE_CACHE_ATTR, None)
        if not isinstance(template_cache, _MaskTemplateCache):
            template_cache = _MaskTemplateCache()
            try:
                setattr(tokenizer, _TOKENIZER_MASK_TEMPLATE_CACHE_ATTR, template_cache)
            except Exception:
                pass
        self._mask_template_cache = template_cache
        self._mask_templates: OrderedDict[object, _MaskTemplate] = template_cache.entries
        self._packed_allow_token_mask: tuple[int, ...] = ()

    @property
    def constraint_kind(self) -> str:
        return self._constraint_kind

    @property
    def packed_allow_token_mask(self) -> tuple[int, ...]:
        return self._packed_allow_token_mask

    @property
    def acceleration_receipt(self) -> dict[str, object]:
        return {
            "constraint_kind": self.constraint_kind,
            "mask_vocab_words": self._mask_vocab_words,
            "fast_path_used": False,
            "fallback_reason": "structured_output_acceleration_unsupported",
        }

    def __call__(self, tokens: Any, logits: Any) -> Any:
        if self._base_token_count is None:
            self._base_token_count = _single_sequence_token_count(tokens)
        generated_count, unapplied_ids = _unapplied_token_ids(
            tokens,
            base_token_count=self._base_token_count,
            applied_generated_count=self._applied_generated_count,
        )
        if unapplied_ids:
            self._advance_state(unapplied_ids)
            self._applied_generated_count = generated_count
        vocab_size = int(logits.shape[-1])
        mask = self._mask_for_state(self._state, vocab_size, logits)
        return logits + mask

    def _advance_state(self, token_ids: list[int]) -> None:
        state = self._state
        if state is None:
            return
        for token_id in token_ids:
            if token_id in self._eos_token_ids and self._is_complete(state):
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
        cache_key = (state, vocab_size, len(logits.shape) > 1)
        cached = self._mask_cache.get(cache_key)
        if cached is not None:
            self._packed_allow_token_mask = cached.packed
            return cached.dense

        template = self._mask_templates.get(cache_key)
        if template is not None:
            self._packed_allow_token_mask = template.packed
            self._remember_request_mask(cache_key, template)
            return template.dense

        import mlx.core as mx

        allowed = [
            state is not None and self._token_allowed(state, token_id)
            for token_id in range(vocab_size)
        ]
        values = [0.0 if item else -math.inf for item in allowed]
        packed = _pack_allowed_tokens(allowed)
        self._packed_allow_token_mask = packed
        mask = mx.array(values)
        if len(logits.shape) > 1:
            mask = mask.reshape((1, vocab_size))
        template = _MaskTemplate(
            dense=mask,
            packed=packed,
            estimated_bytes=_mask_template_estimated_bytes(vocab_size),
        )
        self._remember_shared_mask(cache_key, template)
        self._remember_request_mask(cache_key, template)
        return mask

    def _remember_shared_mask(
        self,
        cache_key: tuple[_JSONPrefixState | _SchemaPrefixState | None, int, bool],
        template: _MaskTemplate,
    ) -> None:
        cache = self._mask_template_cache
        existing = cache.entries.pop(cache_key, None)
        if existing is not None:
            cache.estimated_bytes -= existing.estimated_bytes
        while cache.entries and (
            len(cache.entries) >= _MAX_MASK_TEMPLATE_CACHE_ENTRIES
            or cache.estimated_bytes + template.estimated_bytes
            > _MAX_MASK_TEMPLATE_CACHE_ESTIMATED_BYTES
        ):
            _, evicted = cache.entries.popitem(last=False)
            cache.estimated_bytes -= evicted.estimated_bytes
        if template.estimated_bytes <= _MAX_MASK_TEMPLATE_CACHE_ESTIMATED_BYTES:
            cache.entries[cache_key] = template
            cache.estimated_bytes += template.estimated_bytes

    def _remember_request_mask(
        self,
        cache_key: tuple[_JSONPrefixState | _SchemaPrefixState | None, int, bool],
        template: _MaskTemplate,
    ) -> None:
        self._mask_cache[cache_key] = template
        if len(self._mask_cache) > _MAX_MASK_CACHE_ENTRIES:
            self._mask_cache.popitem(last=False)

    def _token_allowed(
        self,
        state: _JSONPrefixState | _SchemaPrefixState,
        token_id: int,
    ) -> bool:
        if self._is_complete(state) and self._eos_token_ids:
            return token_id in self._eos_token_ids
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


def _mask_template_estimated_bytes(vocab_size: int) -> int:
    dense_upper_bound = vocab_size * 8
    packed_tuple_upper_bound = 40 + math.ceil(vocab_size / 64) * 36
    return 4_096 + dense_upper_bound + packed_tuple_upper_bound


def _single_sequence_token_count(tokens: Any) -> int:
    shape = getattr(tokens, "shape", None)
    if isinstance(shape, tuple):
        if len(shape) == 1:
            return int(shape[0])
        if len(shape) == 2:
            if int(shape[0]) != 1:
                raise ValueError(
                    "GrammarConstraintProcessor only supports single-sequence inputs (batch size 1)."
                )
            return int(shape[1])
    return len(_token_ids(tokens))


def _unapplied_token_ids(
    tokens: Any,
    *,
    base_token_count: int,
    applied_generated_count: int,
) -> tuple[int, list[int]]:
    token_count = _single_sequence_token_count(tokens)
    generated_count = max(0, token_count - base_token_count)
    if generated_count <= applied_generated_count:
        return generated_count, []
    start = base_token_count + applied_generated_count
    shape = getattr(tokens, "shape", None)
    if isinstance(shape, tuple) and len(shape) == 1:
        return generated_count, _token_ids(tokens[start:])
    return generated_count, _token_ids(tokens)[start:]


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


@_weighted_lru_cache(
    maxsize=_MAX_SCHEMA_CACHE_ENTRIES,
    maxbytes=_MAX_SCHEMA_CACHE_ESTIMATED_BYTES,
    weight=_schema_cache_weight,
)
def _compile_json_schema(schema_json: str) -> _SchemaNode:
    clock = monotonic
    budget = _SchemaCompileBudget(
        deadline=clock() + _SCHEMA_COMPILE_DEADLINE_SECONDS,
        clock=clock,
    )
    try:
        schema_size = len(schema_json.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise StructuredOutputConstraintError(
            "response_format json_schema is not valid UTF-8 text.",
            details={
                "mode": "json_schema",
                "enforcement": "sampler",
                "reason": "json_schema_invalid",
            },
        ) from exc
    if schema_size > _MAX_SCHEMA_JSON_BYTES:
        raise _schema_complexity_error(
            "response_format json_schema exceeds the supported byte limit.",
            limit="max_schema_bytes",
        )
    try:
        raw_schema = _schema_json_loads(schema_json)
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise StructuredOutputConstraintError(
            "response_format json_schema contains malformed JSON.",
            details={
                "mode": "json_schema",
                "enforcement": "sampler",
                "reason": "json_schema_invalid",
                "message": getattr(exc, "msg", str(exc)),
            },
        ) from exc
    _check_schema_compile_budget(budget, pointer="")
    try:
        node = _compile_schema_node(
            raw_schema,
            pointer="",
            depth=0,
            budget=budget,
        )
    except RecursionError as exc:
        raise _schema_complexity_error(
            "response_format json_schema exceeds the supported nesting depth.",
            limit="max_depth",
        ) from exc
    if node.types != ("object",):
        raise StructuredOutputConstraintError(
            "response_format json_schema root must be an object schema.",
            details={
                "mode": "json_schema",
                "enforcement": "sampler",
                "reason": "json_schema_root_not_object",
            },
        )
    return node


def _reject_nonfinite_json_number(value: str) -> object:
    raise ValueError(f"non-finite JSON number: {value}")


def _schema_json_loads(value: str) -> object:
    return json.loads(
        value,
        parse_float=Decimal,
        parse_int=Decimal,
        parse_constant=_reject_nonfinite_json_number,
    )


def _compile_schema_node(
    raw_schema: object,
    *,
    pointer: str,
    depth: int = 0,
    budget: _SchemaCompileBudget | None = None,
) -> _SchemaNode:
    if depth > _MAX_SCHEMA_DEPTH:
        raise _schema_complexity_error(
            "response_format json_schema exceeds the supported nesting depth.",
            limit="max_depth",
            pointer=pointer,
        )
    if budget is None:
        budget = _SchemaCompileBudget()
    _check_schema_compile_budget(budget, pointer=pointer)
    budget.node_count += 1
    if budget.node_count > _MAX_SCHEMA_NODES:
        raise _schema_complexity_error(
            "response_format json_schema exceeds the supported node count.",
            limit="max_nodes",
            pointer=pointer,
        )
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
        _check_schema_compile_budget(budget, pointer=pointer)
        if keyword not in _SUPPORTED_SCHEMA_KEYWORDS:
            raise _schema_error(
                f"response_format json_schema keyword is not supported: {keyword}.",
                reason="json_schema_unsupported_keyword",
                keyword=keyword,
                pointer=pointer,
            )

    enum_json_values = _schema_enum_json_values(raw_schema, pointer=pointer, budget=budget)
    types = _schema_types(raw_schema, enum_json_values, pointer=pointer, budget=budget)
    minimum = _schema_number_bound(raw_schema, "minimum", pointer=pointer)
    maximum = _schema_number_bound(raw_schema, "maximum", pointer=pointer)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise _schema_error(
            "response_format json_schema minimum must be less than or equal to maximum.",
            reason="json_schema_unsatisfiable",
            keyword="minimum",
            pointer=pointer,
        )
    enum_json_values = _schema_enum_json_values_matching_types(
        enum_json_values,
        types,
        pointer=pointer,
        budget=budget,
    )
    enum_json_values = _schema_enum_json_values_matching_bounds(
        enum_json_values,
        types=types,
        minimum=minimum,
        maximum=maximum,
        pointer=pointer,
        budget=budget,
    )
    properties = _schema_properties(
        raw_schema,
        pointer=pointer,
        depth=depth,
        budget=budget,
    )
    required = _schema_required(raw_schema, pointer=pointer, budget=budget)
    additional = _schema_additional(
        raw_schema,
        pointer=pointer,
        depth=depth,
        budget=budget,
    )
    items = _schema_items(
        raw_schema,
        pointer=pointer,
        depth=depth,
        budget=budget,
    )
    min_items = _schema_non_negative_int(
        raw_schema,
        "minItems",
        default=0,
        pointer=pointer,
        budget=budget,
    )
    max_items = (
        _schema_non_negative_int(
            raw_schema,
            "maxItems",
            default=0,
            pointer=pointer,
            budget=budget,
        )
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

    structural_node = _SchemaNode(
        types=types,
        properties=properties,
        required=required,
        additional=additional,
        items=items,
        minimum=minimum,
        maximum=maximum,
        min_items=min_items,
        max_items=max_items,
    )
    enum_json_values = _schema_enum_json_values_matching_node(
        enum_json_values,
        structural_node,
        pointer=pointer,
        budget=budget,
    )
    return _SchemaNode(
        types=structural_node.types,
        properties=structural_node.properties,
        required=structural_node.required,
        additional=structural_node.additional,
        items=structural_node.items,
        enum_json_values=enum_json_values,
        enum_trie=_schema_fixed_value_trie(
            enum_json_values,
            budget=budget,
            pointer=pointer,
        ),
        minimum=structural_node.minimum,
        maximum=structural_node.maximum,
        min_items=structural_node.min_items,
        max_items=structural_node.max_items,
    )


def _schema_enum_json_values(
    raw_schema: dict[str, object],
    *,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> frozenset[str]:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    has_const = "const" in raw_schema
    const_value = raw_schema.get("const")
    const_json: str | None = None
    if has_const:
        try:
            _validate_json_text_utf8(const_value, budget=budget, pointer=pointer)
        except UnicodeEncodeError as exc:
            raise _schema_error(
                "response_format json_schema const value must be valid UTF-8 text.",
                reason="json_schema_invalid",
                keyword="const",
                pointer=pointer,
            ) from exc
        const_json = _schema_json_dumps(const_value, budget=budget, pointer=pointer)
    enum_json_values: frozenset[str] = frozenset()
    raw_enum: list[object] = []
    if "enum" in raw_schema:
        raw_enum_value = raw_schema["enum"]
        if not isinstance(raw_enum_value, list) or not raw_enum_value:
            raise _schema_error(
                "response_format json_schema enum must be a non-empty array.",
                reason="json_schema_invalid",
                keyword="enum",
                pointer=pointer,
            )
        raw_enum = raw_enum_value
        if len(raw_enum) > _MAX_SCHEMA_ENUM_VALUES:
            raise _schema_complexity_error(
                "response_format json_schema enum exceeds the supported value count.",
                limit="max_enum_values",
                pointer=pointer,
            )
        encoded_values: set[str] = set()
        for value in raw_enum:
            if budget is not None:
                _check_schema_compile_budget(budget, pointer=pointer)
            try:
                _validate_json_text_utf8(value, budget=budget, pointer=pointer)
            except UnicodeEncodeError as exc:
                raise _schema_error(
                    "response_format json_schema enum values must be valid UTF-8 text.",
                    reason="json_schema_invalid",
                    keyword="enum",
                    pointer=pointer,
                ) from exc
            encoded_values.add(_schema_json_dumps(value, budget=budget, pointer=pointer))
        enum_json_values = frozenset(encoded_values)
        try:
            enum_text_bytes = 0
            for value in enum_json_values:
                if budget is not None:
                    _check_schema_compile_budget(budget, pointer=pointer)
                enum_text_bytes += len(value.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise _schema_error(
                "response_format json_schema enum values must be valid UTF-8 text.",
                reason="json_schema_invalid",
                keyword="enum",
                pointer=pointer,
            ) from exc
        if enum_text_bytes > _MAX_SCHEMA_ENUM_TEXT_BYTES:
            raise _schema_complexity_error(
                "response_format json_schema enum exceeds the supported text size.",
                limit="max_enum_text_bytes",
                pointer=pointer,
            )
    if has_const and enum_json_values:
        if not any(
            _schema_json_values_equal(const_value, value, budget=budget, pointer=pointer)
            for value in raw_enum
        ):
            raise _schema_error(
                "response_format json_schema const must be one of the enum values.",
                reason="json_schema_unsatisfiable",
                keyword="const",
                pointer=pointer,
            )
        return frozenset((const_json,))
    if const_json is not None:
        try:
            const_json.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _schema_error(
                "response_format json_schema const value must be valid UTF-8 text.",
                reason="json_schema_invalid",
                keyword="const",
                pointer=pointer,
            ) from exc
        return frozenset((const_json,))
    if enum_json_values:
        return enum_json_values
    return frozenset()


def _schema_json_dumps(
    value: object,
    *,
    budget: _SchemaCompileBudget | None = None,
    pointer: str = "",
) -> str:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("schema JSON numbers must be finite")
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(
            _schema_json_dumps(item, budget=budget, pointer=pointer) for item in value
        ) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=True, separators=(',', ':'))}:"
            f"{_schema_json_dumps(item, budget=budget, pointer=pointer)}"
            for key, item in value.items()
        ) + "}"
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _validate_json_text_utf8(
    value: object,
    *,
    budget: _SchemaCompileBudget | None = None,
    pointer: str = "",
) -> None:
    stack = [value]
    while stack:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        item = stack.pop()
        if isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            for key, child in item.items():
                key.encode("utf-8")
                stack.append(child)


def _schema_enum_json_values_matching_types(
    enum_json_values: frozenset[str],
    types: tuple[str, ...],
    *,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> frozenset[str]:
    if not enum_json_values:
        return frozenset()
    matching_values: set[str] = set()
    for value in enum_json_values:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        if any(_schema_json_value_matches_type(value, schema_type) for schema_type in types):
            matching_values.add(value)
    matching = frozenset(matching_values)
    if not matching:
        raise _schema_error(
            "response_format json_schema enum/const values do not match the declared type.",
            reason="json_schema_unsatisfiable",
            keyword="enum",
            pointer=pointer,
        )
    return matching


def _schema_enum_json_values_matching_bounds(
    enum_json_values: frozenset[str],
    *,
    types: tuple[str, ...],
    minimum: Decimal | None,
    maximum: Decimal | None,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> frozenset[str]:
    if not enum_json_values or (minimum is None and maximum is None):
        return enum_json_values
    numeric_node = _SchemaNode(types=types, minimum=minimum, maximum=maximum)
    matching_values: set[str] = set()
    for value in enum_json_values:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        if (
            not any(
                _schema_json_value_matches_type(value, item)
                for item in ("integer", "number")
            )
            or _schema_number_satisfies_node(numeric_node, value)
        ):
            matching_values.add(value)
    matching = frozenset(matching_values)
    if not matching:
        raise _schema_error(
            "response_format json_schema enum/const values do not satisfy numeric bounds.",
            reason="json_schema_unsatisfiable",
            keyword="enum",
            pointer=pointer,
        )
    return matching


def _schema_enum_json_values_matching_node(
    enum_json_values: frozenset[str],
    node: _SchemaNode,
    *,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> frozenset[str]:
    if not enum_json_values:
        return frozenset()
    matching_values: set[str] = set()
    for value in enum_json_values:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        if _schema_json_value_satisfies_node(
            value,
            node,
            budget=budget,
            pointer=pointer,
        ):
            matching_values.add(value)
    matching = frozenset(matching_values)
    if not matching:
        raise _schema_error(
            "response_format json_schema enum/const values do not satisfy the structural constraints.",
            reason="json_schema_unsatisfiable",
            keyword="enum",
            pointer=pointer,
        )
    return matching


def _schema_json_value_satisfies_node(
    value_json: str,
    node: _SchemaNode,
    *,
    budget: _SchemaCompileBudget | None = None,
    pointer: str = "",
) -> bool:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    try:
        value = _schema_json_loads(value_json)
    except (json.JSONDecodeError, ValueError, RecursionError):
        return False
    return _schema_value_satisfies_node(value, node, budget=budget, pointer=pointer)


def _schema_value_satisfies_node(
    value: object,
    node: _SchemaNode,
    *,
    budget: _SchemaCompileBudget | None = None,
    pointer: str = "",
) -> bool:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    if node is _ANY_SCHEMA_NODE:
        return True
    if not any(_schema_value_matches_type(value, schema_type) for schema_type in node.types):
        return False
    if node.enum_json_values and not any(
        _schema_json_values_equal(
            value,
            _schema_json_loads(candidate),
            budget=budget,
            pointer=pointer,
        )
        for candidate in node.enum_json_values
    ):
        return False
    if isinstance(value, Decimal):
        if node.minimum is not None and value < node.minimum:
            return False
        if node.maximum is not None and value > node.maximum:
            return False
    if isinstance(value, dict):
        if not node.required.issubset(value):
            return False
        properties = {prop.name: prop.node for prop in node.properties}
        for key, child_value in value.items():
            if budget is not None:
                _check_schema_compile_budget(budget, pointer=pointer)
            child_node = properties.get(key, node.additional)
            if child_node is None or not _schema_value_satisfies_node(
                child_value,
                child_node,
                budget=budget,
                pointer=pointer,
            ):
                return False
    if isinstance(value, list):
        if len(value) < node.min_items:
            return False
        if node.max_items is not None and len(value) > node.max_items:
            return False
        item_node = node.items or _ANY_SCHEMA_NODE
        for item in value:
            if not _schema_value_satisfies_node(
                item,
                item_node,
                budget=budget,
                pointer=pointer,
            ):
                return False
    return True


def _schema_value_matches_type(value: object, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value()
    if schema_type == "number":
        return isinstance(value, Decimal) and value.is_finite()
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return False


def _schema_fixed_value_trie(
    values: frozenset[str],
    *,
    budget: _SchemaCompileBudget | None = None,
    pointer: str = "",
) -> _FixedValueTrie | None:
    if not values:
        return None
    mutable_root: dict[str, object] = {"terminal": False, "children": {}}
    for value in values:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        current = mutable_root
        for char in value:
            if budget is not None:
                _check_schema_compile_budget(budget, pointer=pointer)
            children = current["children"]
            assert isinstance(children, dict)
            current = children.setdefault(char, {"terminal": False, "children": {}})
            assert isinstance(current, dict)
        current["terminal"] = True

    frozen_nodes: dict[int, _FixedValueTrie] = {}
    pending: list[tuple[dict[str, object], bool]] = [(mutable_root, False)]
    while pending:
        raw, children_ready = pending.pop()
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        raw_children = raw["children"]
        assert isinstance(raw_children, dict)
        if not children_ready:
            pending.append((raw, True))
            pending.extend(
                (child, False)
                for child in raw_children.values()
                if isinstance(child, dict)
            )
            continue
        children = MappingProxyType(
            {
                str(char): frozen_nodes[id(child)]
                for char, child in raw_children.items()
                if isinstance(child, dict)
            }
        )
        frozen_nodes[id(raw)] = _FixedValueTrie(
            terminal=bool(raw["terminal"]),
            children=children,
        )

    return frozen_nodes[id(mutable_root)]


def _schema_types(
    raw_schema: dict[str, object],
    enum_json_values: frozenset[str],
    *,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> tuple[str, ...]:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    if "type" not in raw_schema:
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
    raw_type = raw_schema["type"]
    values = raw_type if isinstance(raw_type, list) else [raw_type]
    if not values:
        raise _schema_error(
            "response_format json_schema type must not be an empty array.",
            reason="json_schema_invalid",
            keyword="type",
            pointer=f"{pointer}/type" if pointer else "/type",
        )
    normalized: list[str] = []
    for value in values:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
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
    return _schema_value_matches_type(_schema_json_loads(value_json), schema_type)


def _schema_json_values_equal(
    left: object,
    right: object,
    *,
    budget: _SchemaCompileBudget | None = None,
    pointer: str = "",
) -> bool:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    numeric_types = (Decimal, int, float)
    if isinstance(left, numeric_types) and isinstance(right, numeric_types):
        left_number = left if isinstance(left, Decimal) else Decimal(str(left))
        right_number = right if isinstance(right, Decimal) else Decimal(str(right))
        return left_number.is_finite() and right_number.is_finite() and left_number == right_number
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _schema_json_values_equal(
                left_item,
                right_item,
                budget=budget,
                pointer=pointer,
            )
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _schema_json_values_equal(
                left[key],
                right[key],
                budget=budget,
                pointer=pointer,
            )
            for key in left
        )
    return type(left) is type(right) and left == right


def _schema_properties(
    raw_schema: dict[str, object],
    *,
    pointer: str,
    depth: int = 0,
    budget: _SchemaCompileBudget | None = None,
) -> tuple[_SchemaProperty, ...]:
    raw_properties = raw_schema.get("properties", {})
    if not isinstance(raw_properties, dict):
        raise _schema_error(
            "response_format json_schema properties must be an object.",
            reason="json_schema_invalid",
            keyword="properties",
            pointer=pointer,
        )
    if len(raw_properties) > _MAX_SCHEMA_PROPERTIES:
        raise _schema_complexity_error(
            "response_format json_schema properties exceeds the supported count.",
            limit="max_properties",
            pointer=pointer,
        )
    for name in raw_properties:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        if not isinstance(name, str):
            raise _schema_error(
                "response_format json_schema property names must be strings.",
                reason="json_schema_invalid",
                keyword="properties",
                pointer=pointer,
            )
        try:
            name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _schema_error(
                "response_format json_schema property names must be valid UTF-8 text.",
                reason="json_schema_invalid",
                keyword="properties",
                pointer=pointer,
            ) from exc
    properties: list[_SchemaProperty] = []
    for name, child_schema in sorted(raw_properties.items()):
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        properties.append(
            _SchemaProperty(
                name=name,
                node=_compile_schema_node(
                    child_schema,
                    pointer=f"{pointer}/properties/{name}",
                    depth=depth + 1,
                    budget=budget,
                ),
            )
        )
    return tuple(properties)


def _schema_required(
    raw_schema: dict[str, object],
    *,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> frozenset[str]:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    raw_required = raw_schema.get("required", [])
    if not isinstance(raw_required, list) or any(not isinstance(item, str) for item in raw_required):
        raise _schema_error(
            "response_format json_schema required must be an array of property names.",
            reason="json_schema_invalid",
            keyword="required",
            pointer=pointer,
        )
    if len(raw_required) > _MAX_SCHEMA_REQUIRED:
        raise _schema_complexity_error(
            "response_format json_schema required exceeds the supported count.",
            limit="max_required",
            pointer=pointer,
        )
    required: set[str] = set()
    for item in raw_required:
        if budget is not None:
            _check_schema_compile_budget(budget, pointer=pointer)
        try:
            item.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _schema_error(
                "response_format json_schema required names must be valid UTF-8 text.",
                reason="json_schema_invalid",
                keyword="required",
                pointer=pointer,
            ) from exc
        required.add(item)
    return frozenset(required)


def _schema_additional(
    raw_schema: dict[str, object],
    *,
    pointer: str,
    depth: int = 0,
    budget: _SchemaCompileBudget | None = None,
) -> _SchemaNode | None:
    raw_additional = raw_schema.get("additionalProperties", True)
    if raw_additional is False:
        return None
    if raw_additional is True:
        return _ANY_SCHEMA_NODE
    if isinstance(raw_additional, dict):
        return _compile_schema_node(
            raw_additional,
            pointer=f"{pointer}/additionalProperties",
            depth=depth + 1,
            budget=budget,
        )
    raise _schema_error(
        "response_format json_schema additionalProperties must be a boolean or schema object.",
        reason="json_schema_invalid",
        keyword="additionalProperties",
        pointer=pointer,
    )


def _schema_items(
    raw_schema: dict[str, object],
    *,
    pointer: str,
    depth: int = 0,
    budget: _SchemaCompileBudget | None = None,
) -> _SchemaNode | None:
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
    return _compile_schema_node(
        raw_items,
        pointer=f"{pointer}/items",
        depth=depth + 1,
        budget=budget,
    )


def _schema_number_bound(
    raw_schema: dict[str, object],
    keyword: str,
    *,
    pointer: str,
) -> Decimal | None:
    if keyword not in raw_schema:
        return None
    value = raw_schema[keyword]
    if not isinstance(value, (Decimal, int, float)) or isinstance(value, bool):
        raise _schema_error(
            f"response_format json_schema {keyword} must be numeric.",
            reason="json_schema_invalid",
            keyword=keyword,
            pointer=pointer,
        )
    value_text = str(value)
    if len(value_text) > _MAX_SCHEMA_NUMBER_CHARS:
        raise _schema_complexity_error(
            f"response_format json_schema {keyword} exceeds the supported numeric size.",
            limit="max_number_chars",
            pointer=pointer,
        )
    normalized = Decimal(value_text)
    if not normalized.is_finite():
        raise _schema_error(
            f"response_format json_schema {keyword} must be finite.",
            reason="json_schema_invalid",
            keyword=keyword,
            pointer=pointer,
        )
    if normalized and abs(normalized.adjusted()) > _MAX_EXPONENT_MAGNITUDE:
        raise _schema_complexity_error(
            f"response_format json_schema {keyword} exponent exceeds the supported magnitude.",
            limit="max_exponent_magnitude",
            pointer=pointer,
        )
    return normalized


def _schema_non_negative_int(
    raw_schema: dict[str, object],
    keyword: str,
    *,
    default: int,
    pointer: str,
    budget: _SchemaCompileBudget | None = None,
) -> int:
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    if keyword not in raw_schema:
        return default
    value = raw_schema[keyword]
    if not isinstance(value, (Decimal, int)) or isinstance(value, bool):
        raise _schema_error(
            f"response_format json_schema {keyword} must be a non-negative integer.",
            reason="json_schema_invalid",
            keyword=keyword,
            pointer=pointer,
        )
    normalized = value if isinstance(value, Decimal) else Decimal(value)
    if normalized < 0 or normalized != normalized.to_integral_value():
        raise _schema_error(
            f"response_format json_schema {keyword} must be a non-negative integer.",
            reason="json_schema_invalid",
            keyword=keyword,
            pointer=pointer,
        )
    if normalized > _MAX_SCHEMA_ARRAY_ITEMS:
        raise _schema_complexity_error(
            f"response_format json_schema {keyword} exceeds the supported item count.",
            limit="max_array_items",
            pointer=pointer,
        )
    if budget is not None:
        _check_schema_compile_budget(budget, pointer=pointer)
    return int(normalized)


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


def _check_schema_compile_budget(
    budget: _SchemaCompileBudget,
    *,
    pointer: str,
) -> None:
    if budget.clock is None or budget.deadline is None or budget.clock() <= budget.deadline:
        return
    if budget.mode == "tool_choice":
        details = {
            "mode": "tool_choice",
            "enforcement": "sampler",
            "reason": "tool_schema_too_complex",
            "limit": "compile_deadline_ms",
        }
        if pointer:
            details["schema_pointer"] = pointer
        raise StructuredOutputConstraintError(
            "Tool grammar compilation exceeded its deadline.",
            details=details,
        )
    raise _schema_complexity_error(
        "response_format json_schema compilation exceeded its deadline.",
        limit="compile_deadline_ms",
        pointer=pointer,
    )


def _schema_complexity_error(
    message: str,
    *,
    limit: str,
    pointer: str = "",
) -> StructuredOutputConstraintError:
    error = _schema_error(
        message,
        reason="json_schema_too_complex",
        pointer=pointer,
    )
    error.details["limit"] = limit
    return error


def _schema_is_complete(state: _SchemaPrefixState) -> bool:
    return state.mode == "normal" and state.root == "done" and not state.stack


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
    if state.mode == "surrogate_backslash":
        return _schema_replace_mode(state, mode="surrogate_u") if char == "\\" else None
    if state.mode == "surrogate_u":
        return (
            _schema_replace_mode(
                state,
                mode="unicode",
                unicode_remaining=4,
                unicode_digits="",
            )
            if char == "u"
            else None
        )
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
        if char == '"' and _schema_object_available_keys(frame):
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
    trie = node.enum_trie
    if trie is None:
        return None
    child = trie.children.get(char)
    if child is None:
        return None
    next_state = _schema_replace_mode(
        state,
        mode="fixed",
        value_node=node,
        fixed_trie=child,
    )
    return _schema_complete_fixed_if_unambiguous(next_state)


def _schema_consume_fixed_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    trie = state.fixed_trie
    if trie is None:
        return None
    child = trie.children.get(char)
    if child is not None:
        return _schema_complete_fixed_if_unambiguous(
            _schema_replace_mode(state, fixed_trie=child)
        )
    if trie.terminal:
        completed = _schema_complete_value(_schema_reset_scalar_mode(state))
        return _schema_transition_char(completed, char) if completed is not None else None
    return None


def _schema_complete_fixed_if_unambiguous(state: _SchemaPrefixState) -> _SchemaPrefixState:
    trie = state.fixed_trie
    if trie is not None and trie.terminal and not trie.children:
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
    if state.string_role != "key":
        return state
    next_text = f"{state.string_text}{char}"
    if not _schema_key_prefix_allowed(state, next_text):
        return None
    return _schema_replace_mode(state, string_text=next_text)


def _schema_consume_escape_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    if char == "u":
        return _schema_replace_mode(
            state,
            mode="unicode",
            unicode_remaining=4,
            unicode_digits="",
        )
    escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    if char not in escapes:
        return None
    if state.string_role != "key":
        return _schema_replace_mode(state, mode="string")
    next_text = f"{state.string_text}{escapes[char]}"
    if not _schema_key_prefix_allowed(state, next_text):
        return None
    return _schema_replace_mode(state, mode="string", string_text=next_text)


def _schema_consume_unicode_char(
    state: _SchemaPrefixState,
    char: str,
) -> _SchemaPrefixState | None:
    if char not in _JSON_HEX:
        return None
    remaining = state.unicode_remaining - 1
    digits = f"{state.unicode_digits}{char}"
    if remaining <= 0:
        code_unit = int(digits, 16)
        if state.unicode_high_surrogate:
            if not 0xDC00 <= code_unit <= 0xDFFF:
                return None
            decoded_char = chr(
                0x10000
                + (state.unicode_high_surrogate - 0xD800) * 0x400
                + (code_unit - 0xDC00)
            )
        elif 0xD800 <= code_unit <= 0xDBFF:
            return _schema_replace_mode(
                state,
                mode="surrogate_backslash",
                unicode_remaining=0,
                unicode_digits="",
                unicode_high_surrogate=code_unit,
            )
        elif 0xDC00 <= code_unit <= 0xDFFF:
            return None
        else:
            decoded_char = chr(code_unit)
        decoded_text = (
            f"{state.string_text}{decoded_char}"
            if state.string_role == "key"
            else state.string_text
        )
        if state.string_role == "key" and not _schema_key_prefix_allowed(state, decoded_text):
            return None
        return _schema_replace_mode(
            state,
            mode="string",
            string_text=decoded_text,
            unicode_remaining=0,
            unicode_digits="",
            unicode_high_surrogate=0,
        )
    return _schema_replace_mode(
        state,
        unicode_remaining=remaining,
        unicode_digits=digits,
    )


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
            return _schema_append_number_char(state, char, number_state="zero")
        if "1" <= char <= "9":
            return _schema_append_number_char(state, char, number_state="int")
        return None
    if number_state == "zero":
        if char == ".":
            return _schema_append_number_char(state, char, number_state="frac_start")
        if char in {"e", "E"}:
            return _schema_append_number_char(state, char, number_state="exp_start")
        return None
    if number_state == "int":
        if "0" <= char <= "9":
            return _schema_append_number_char(state, char)
        if char == ".":
            return _schema_append_number_char(state, char, number_state="frac_start")
        if char in {"e", "E"}:
            return _schema_append_number_char(state, char, number_state="exp_start")
        return None
    if number_state == "frac_start":
        return (
            _schema_append_number_char(state, char, number_state="frac")
            if "0" <= char <= "9"
            else None
        )
    if number_state == "frac":
        if "0" <= char <= "9":
            return _schema_append_number_char(state, char)
        if char in {"e", "E"}:
            return _schema_append_number_char(state, char, number_state="exp_start")
        return None
    if number_state == "exp_start":
        if char in {"+", "-"}:
            return _schema_append_number_char(state, char, number_state="exp_sign")
        if "0" <= char <= "9":
            return _schema_append_number_char(state, char, number_state="exp")
        return None
    if number_state == "exp_sign":
        return (
            _schema_append_number_char(state, char, number_state="exp")
            if "0" <= char <= "9"
            else None
        )
    if number_state == "exp":
        return _schema_append_number_char(state, char) if "0" <= char <= "9" else None
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
) -> _SchemaPrefixState | None:
    tracks_text = _schema_tracks_number_text(node)
    next_state = _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack,
        mode="number",
        number_state=number_state,
        number_text=char if tracks_text else "",
        value_node=node,
    )
    if tracks_text and not _schema_number_prefix_viable(node, next_state.number_text, number_state):
        return None
    return next_state


def _schema_append_number_char(
    state: _SchemaPrefixState,
    char: str,
    *,
    number_state: str | None = None,
) -> _SchemaPrefixState | None:
    node = state.value_node
    tracks_text = _schema_tracks_number_text(node)
    next_text = f"{state.number_text}{char}" if tracks_text else ""
    next_number_state = state.number_state if number_state is None else number_state
    if tracks_text and not _schema_number_prefix_viable(node, next_text, next_number_state):
        return None
    return _schema_replace_mode(
        state,
        number_state=next_number_state,
        number_text=next_text,
    )


def _schema_replace_mode(
    state: _SchemaPrefixState,
    *,
    mode: str | None = None,
    string_text: str | None = None,
    unicode_remaining: int | None = None,
    unicode_digits: str | None = None,
    unicode_high_surrogate: int | None = None,
    number_state: str | None = None,
    number_text: str | None = None,
    literal_index: int | None = None,
    value_node: _SchemaNode | None = None,
    fixed_trie: _FixedValueTrie | None = None,
) -> _SchemaPrefixState:
    return _SchemaPrefixState(
        root=state.root,
        root_node=state.root_node,
        stack=state.stack,
        mode=state.mode if mode is None else mode,
        string_role=state.string_role,
        string_text=state.string_text if string_text is None else string_text,
        unicode_remaining=state.unicode_remaining if unicode_remaining is None else unicode_remaining,
        unicode_digits=state.unicode_digits if unicode_digits is None else unicode_digits,
        unicode_high_surrogate=(
            state.unicode_high_surrogate
            if unicode_high_surrogate is None
            else unicode_high_surrogate
        ),
        number_state=state.number_state if number_state is None else number_state,
        number_text=state.number_text if number_text is None else number_text,
        literal_target=state.literal_target,
        literal_index=state.literal_index if literal_index is None else literal_index,
        value_node=state.value_node if value_node is None else value_node,
        fixed_trie=state.fixed_trie if fixed_trie is None else fixed_trie,
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
    value_node = (
        property_node
        if property_node is not None
        else _schema_additional_node(frame.node)
    )
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
    if _schema_additional_node(frame.node) is not None:
        return True
    return any(
        prop.name not in frame.seen and prop.name.startswith(prefix)
        for prop in frame.node.properties
    )


def _schema_object_available_keys(frame: _SchemaFrame) -> bool:
    if _schema_additional_node(frame.node) is not None:
        return True
    return any(prop.name not in frame.seen for prop in frame.node.properties)


def _schema_additional_node(node: _SchemaNode) -> _SchemaNode | None:
    return _ANY_SCHEMA_NODE if node is _ANY_SCHEMA_NODE else node.additional


def _schema_array_can_accept_value(frame: _SchemaFrame) -> bool:
    return frame.node.max_items is None or frame.item_count < frame.node.max_items


def _schema_node_allows_type(node: _SchemaNode | None, schema_type: str) -> bool:
    return node is None or schema_type in node.types


def _schema_number_satisfies_node(node: _SchemaNode | None, text: str) -> bool:
    if node is None:
        return True
    if not text and not _schema_tracks_number_text(node):
        return True
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return False
    if not value.is_finite():
        return False
    if _schema_requires_integer(node) and value != value.to_integral_value():
        return False
    if node.minimum is not None and value < node.minimum:
        return False
    if node.maximum is not None and value > node.maximum:
        return False
    return True


def _schema_requires_integer(node: _SchemaNode | None) -> bool:
    return node is not None and "integer" in node.types and "number" not in node.types


def _schema_tracks_number_text(node: _SchemaNode | None) -> bool:
    return bool(
        node is not None
        and (
            _schema_requires_integer(node)
            or node.minimum is not None
            or node.maximum is not None
        )
    )


def _schema_number_prefix_viable(
    node: _SchemaNode | None,
    text: str,
    number_state: str,
) -> bool:
    if node is None or not _schema_tracks_number_text(node):
        return True
    if len(text) > _MAX_SCHEMA_NUMBER_CHARS:
        return False
    if len(text) == _MAX_SCHEMA_NUMBER_CHARS:
        return (
            number_state in _JSON_NUMBER_FINAL_STATES
            and _schema_number_satisfies_node(node, text)
        )
    if number_state == "after_minus":
        return _schema_range_intersects(node, None, Decimal(0))
    if number_state in {"exp_start", "exp_sign", "exp"}:
        return _schema_exponent_prefix_viable(node, text, number_state)
    if number_state == "frac_start":
        return any(
            _schema_number_prefix_viable(node, f"{text}{digit}", "frac")
            for digit in "0123456789"
        )
    if number_state not in _JSON_NUMBER_FINAL_STATES:
        return True
    if _schema_number_satisfies_node(node, text):
        return True
    try:
        value = Decimal(text)
    except InvalidOperation:
        return False
    exponent_range = _schema_allowed_exponent_range(node, value)
    if exponent_range is not None:
        return True
    return _schema_direct_decimal_prefix_intersects(node, text, number_state)


def _schema_exponent_prefix_viable(
    node: _SchemaNode,
    text: str,
    number_state: str,
) -> bool:
    marker_index = max(text.rfind("e"), text.rfind("E"))
    if marker_index < 0:
        return False
    try:
        mantissa = Decimal(text[:marker_index])
    except InvalidOperation:
        return False
    allowed = _schema_allowed_exponent_range(node, mantissa)
    if allowed is None:
        return False
    allowed_min, allowed_max = allowed
    exponent_text = text[marker_index + 1 :]
    if number_state == "exp_start":
        return allowed_min <= allowed_max
    sign = ""
    if exponent_text[:1] in {"+", "-"}:
        sign = exponent_text[0]
        exponent_text = exponent_text[1:]
    if number_state == "exp_sign":
        if sign == "-":
            return allowed_min <= min(allowed_max, 0)
        return max(allowed_min, 0) <= allowed_max
    if sign == "-":
        magnitude_min = max(0, -allowed_max)
        magnitude_max = max(0, -allowed_min)
        return _unsigned_integer_prefix_intersects(
            exponent_text,
            magnitude_min,
            magnitude_max,
        )
    return _unsigned_integer_prefix_intersects(
        exponent_text,
        max(0, allowed_min),
        allowed_max,
    )


def _schema_allowed_exponent_range(
    node: _SchemaNode,
    mantissa: Decimal,
) -> tuple[int, int] | None:
    if not mantissa.is_finite():
        return None
    if mantissa == 0:
        return (
            (-_MAX_EXPONENT_MAGNITUDE, _MAX_EXPONENT_MAGNITUDE)
            if _schema_number_satisfies_node(node, "0")
            else None
        )

    magnitude = abs(mantissa)
    if mantissa > 0:
        if node.maximum is not None and node.maximum <= 0:
            return None
        lower = node.minimum if node.minimum is not None and node.minimum > 0 else None
        upper = node.maximum
    else:
        if node.minimum is not None and node.minimum >= 0:
            return None
        lower = -node.maximum if node.maximum is not None and node.maximum < 0 else None
        upper = -node.minimum if node.minimum is not None else None

    exponent_min = -_MAX_EXPONENT_MAGNITUDE
    exponent_max = _MAX_EXPONENT_MAGNITUDE
    if lower is not None and lower > 0:
        exponent_min = max(exponent_min, _decimal_scale_ceiling(magnitude, lower))
    if upper is not None:
        exponent_max = min(exponent_max, _decimal_scale_floor(magnitude, upper))
    if _schema_requires_integer(node):
        normalized_exponent = int(magnitude.normalize().as_tuple().exponent)
        exponent_min = max(exponent_min, -normalized_exponent)
    if exponent_min > exponent_max:
        return None
    return exponent_min, exponent_max


def _decimal_scale_ceiling(magnitude: Decimal, target: Decimal) -> int:
    exponent = target.adjusted() - magnitude.adjusted()
    while magnitude.scaleb(exponent) < target:
        exponent += 1
    return exponent


def _decimal_scale_floor(magnitude: Decimal, target: Decimal) -> int:
    exponent = target.adjusted() - magnitude.adjusted()
    while magnitude.scaleb(exponent) > target:
        exponent -= 1
    return exponent


def _unsigned_integer_prefix_intersects(prefix: str, lower: int, upper: int) -> bool:
    if upper < lower or upper < 0:
        return False
    lower = max(0, lower)
    significant = prefix.lstrip("0")
    if not significant:
        return lower <= upper
    prefix_value = int(significant)
    scale = 1
    while prefix_value * scale <= upper:
        interval_lower = prefix_value * scale
        interval_upper = (prefix_value + 1) * scale - 1
        if interval_upper >= lower and interval_lower <= upper:
            return True
        scale *= 10
    return False


def _schema_direct_decimal_prefix_intersects(
    node: _SchemaNode,
    text: str,
    number_state: str,
) -> bool:
    try:
        value = Decimal(text)
    except InvalidOperation:
        return False
    if number_state in {"zero", "int"}:
        if value == 0:
            if text.startswith("-"):
                return _schema_range_intersects(
                    node,
                    Decimal(-1),
                    Decimal(0),
                    lower_open=True,
                )
            return _schema_range_intersects(
                node,
                Decimal(0),
                Decimal(1),
                upper_open=True,
            )
        if _schema_integer_digit_prefix_intersects(node, text):
            return True
        if value > 0:
            return _schema_range_intersects(node, value, value + 1, upper_open=True)
        return _schema_range_intersects(node, value - 1, value, lower_open=True)
    if number_state == "frac":
        fraction_digits = len(text.split(".", 1)[1])
        unit = Decimal(1).scaleb(-fraction_digits)
        if value >= 0:
            return _schema_range_intersects(node, value, value + unit, upper_open=True)
        return _schema_range_intersects(node, value - unit, value, lower_open=True)
    return False


def _schema_integer_digit_prefix_intersects(node: _SchemaNode, text: str) -> bool:
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    if not digits or digits == "0":
        return False
    prefix = Decimal(digits)
    scale = Decimal(10)
    for _ in range(_MAX_SCHEMA_NUMBER_CHARS - len(digits)):
        if negative:
            lower = -(prefix * scale + scale - 1)
            upper = -(prefix * scale)
        else:
            lower = prefix * scale
            upper = prefix * scale + scale - 1
        if _schema_range_intersects(node, lower, upper):
            return True
        if not negative and node.maximum is not None and lower > node.maximum:
            return False
        if negative and node.minimum is not None and upper < node.minimum:
            return False
        scale *= 10
    return False


def _schema_range_intersects(
    node: _SchemaNode,
    lower: Decimal | None,
    upper: Decimal | None,
    *,
    lower_open: bool = False,
    upper_open: bool = False,
) -> bool:
    effective_lower = lower
    effective_upper = upper
    effective_lower_open = lower_open
    effective_upper_open = upper_open
    if node.minimum is not None:
        if effective_upper is not None and (
            effective_upper < node.minimum
            or (effective_upper == node.minimum and effective_upper_open)
        ):
            return False
        if effective_lower is None or effective_lower < node.minimum:
            effective_lower = node.minimum
            effective_lower_open = False
    if node.maximum is not None:
        if effective_lower is not None and (
            effective_lower > node.maximum
            or (effective_lower == node.maximum and effective_lower_open)
        ):
            return False
        if effective_upper is None or effective_upper > node.maximum:
            effective_upper = node.maximum
            effective_upper_open = False
    if effective_lower is not None and effective_upper is not None:
        if effective_lower > effective_upper or (
            effective_lower == effective_upper
            and (effective_lower_open or effective_upper_open)
        ):
            return False
    if not _schema_requires_integer(node):
        return True
    integer_lower = (
        int(effective_lower.to_integral_value(rounding=ROUND_FLOOR)) + 1
        if effective_lower is not None
        and (effective_lower_open or effective_lower != effective_lower.to_integral_value())
        else int(effective_lower)
        if effective_lower is not None
        else -(10**_MAX_SCHEMA_NUMBER_CHARS)
    )
    integer_upper = (
        int(effective_upper.to_integral_value(rounding=ROUND_CEILING)) - 1
        if effective_upper is not None
        and (effective_upper_open or effective_upper != effective_upper.to_integral_value())
        else int(effective_upper)
        if effective_upper is not None
        else 10**_MAX_SCHEMA_NUMBER_CHARS
    )
    return integer_lower <= integer_upper


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
        if "0" <= char <= "9":
            return state
        if char == ".":
            return _replace_mode(state, number_state="frac_start")
        if char in {"e", "E"}:
            return _replace_mode(state, number_state="exp_start")
        return None
    if number_state == "frac_start":
        return _replace_mode(state, number_state="frac") if "0" <= char <= "9" else None
    if number_state == "frac":
        if "0" <= char <= "9":
            return state
        if char in {"e", "E"}:
            return _replace_mode(state, number_state="exp_start")
        return None
    if number_state == "exp_start":
        if char in {"+", "-"}:
            return _replace_mode(state, number_state="exp_sign")
        if "0" <= char <= "9":
            return _replace_mode(state, number_state="exp")
        return None
    if number_state == "exp_sign":
        return _replace_mode(state, number_state="exp") if "0" <= char <= "9" else None
    if number_state == "exp":
        return state if "0" <= char <= "9" else None
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


def audit_schema_state_space(
    schema_json: str,
    *,
    alphabet: str,
    max_depth: int,
    max_states: int = _MAX_STATE_EXPLORATION_STATES,
    max_transitions: int = _MAX_STATE_EXPLORATION_TRANSITIONS,
    deadline_seconds: float = _MAX_STATE_EXPLORATION_SECONDS,
) -> dict[str, int | bool]:
    """Explore a schema grammar only under hard cardinality and time budgets."""

    if max_depth < 0 or max_states <= 0 or max_transitions <= 0 or deadline_seconds <= 0:
        raise ValueError("Schema state-space audit budgets must be positive.")
    node = _compile_json_schema(schema_json)
    frontier = {_SchemaPrefixState(root_node=node)}
    seen = set(frontier)
    transitions = 0
    deadline = monotonic() + deadline_seconds
    for _ in range(max_depth):
        next_frontier: set[_SchemaPrefixState] = set()
        for state in frontier:
            for char in alphabet:
                transitions += 1
                if transitions > max_transitions or monotonic() > deadline:
                    raise _state_space_budget_error(len(seen), transitions)
                next_state = _schema_transition_char(state, char)
                if next_state is None or next_state in seen:
                    continue
                next_frontier.add(next_state)
                seen.add(next_state)
                if len(seen) > max_states:
                    raise _state_space_budget_error(len(seen), transitions)
        frontier = next_frontier
        if not frontier:
            break
    return {
        "state_count": len(seen),
        "transition_count": transitions,
        "frontier_count": len(frontier),
        "complete_state_seen": any(_schema_is_complete(state) for state in seen),
    }


def _state_space_budget_error(
    state_count: int,
    transition_count: int,
) -> StructuredOutputConstraintError:
    error = _schema_complexity_error(
        "Schema state-space audit exceeded its bounded exploration budget.",
        limit="state_space_exploration",
    )
    error.details["state_count"] = str(state_count)
    error.details["transition_count"] = str(transition_count)
    return error


def _pack_allowed_tokens(allowed: list[bool]) -> tuple[int, ...]:
    words = [0] * math.ceil(len(allowed) / 64)
    for token_id, is_allowed in enumerate(allowed):
        if is_allowed:
            words[token_id // 64] |= 1 << (token_id % 64)
    return tuple(words)


def _attach_acceleration_receipt(execution_ext: object, processors: list[Any]) -> None:
    if not processors:
        return
    receipt = getattr(processors[0], "acceleration_receipt", None)
    if not isinstance(receipt, dict):
        return
    _ext_set(execution_ext, "melix.constraint.constraint_kind", receipt.get("constraint_kind", ""))
    _ext_set(execution_ext, "melix.constraint.mask_vocab_words", receipt.get("mask_vocab_words", 0))
    _ext_set(
        execution_ext,
        "melix.constraint.fast_path_used",
        "true" if receipt.get("fast_path_used") else "false",
    )
    _ext_set(
        execution_ext,
        "melix.constraint.fallback_reason",
        receipt.get("fallback_reason", ""),
    )


def _ext_set(execution_ext: object, key: str, value: object) -> None:
    try:
        execution_ext[key] = str(value)  # type: ignore[index]
    except (KeyError, TypeError, AttributeError):
        return
