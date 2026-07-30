from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
import json
import math
from time import monotonic
from types import MappingProxyType
from typing import Any

from worker.runtime import structured_output_constraints as structured
from worker.runtime import tool_call_rescue


_TOOL_CHOICE_KEYS = (
    "melix.compat.tool_choice_resolved",
    "melix.tool_config.tool_choice",
)
_TOOLS_JSON_KEY = "melix.tool_config.tools_json"
_PARSER_MODE_KEY = "melix.tool_parser.mode"
_MAX_TOOL_COUNT = 32
_MAX_TOOL_NAME_BYTES = 256
_MAX_XML_PARAMETER_NAME_BYTES = 256
_MAX_SENTINEL_TOKEN_COUNT = 16
_MAX_SENTINEL_TOKEN_BYTES = 256
_TOOL_COMPILE_DEADLINE_SECONDS = 0.050
_MAX_TOOL_CACHE_ENTRIES = 32
_MAX_TOOL_CACHE_ESTIMATED_BYTES = 16 * 1024 * 1024
_MAX_TOOL_TRIE_CACHE_ENTRIES = 32
_MAX_TOOL_TRIE_CACHE_ESTIMATED_BYTES = 16 * 1024 * 1024
_MAX_XML_STATE_CACHE_ENTRIES = 64
_MAX_XML_STATE_CACHE_ESTIMATED_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ToolWireGrammarDescriptor:
    dialect: str
    begin: str
    end: str
    trigger: str
    sentinel_tokens: tuple[str, ...]
    argument_style: str


JSON_OBJECT_TOOL_WIRE = ToolWireGrammarDescriptor(
    dialect="json_object_arguments",
    begin="<tool_call>",
    end="</tool_call>",
    trigger="<tool_call>",
    sentinel_tokens=("<tool_call>", "</tool_call>"),
    argument_style="json_object",
)
XML_PARAMETER_TOOL_WIRE = ToolWireGrammarDescriptor(
    dialect="xml_parameter_blocks",
    begin="<tool_call>",
    end="</tool_call>",
    trigger="<tool_call>",
    sentinel_tokens=("<tool_call>", "</tool_call>", "</parameter>", "</function>"),
    argument_style="xml_parameters",
)


@dataclass(frozen=True, slots=True, eq=False)
class _CompiledTool:
    name: str
    arguments: structured._SchemaNode


@dataclass(frozen=True, slots=True, eq=False)
class _ChoiceTrie:
    terminal: object | None
    children: Mapping[str, "_ChoiceTrie"]


@dataclass(frozen=True, slots=True)
class _XMLChoice:
    kind: str
    property: structured._SchemaProperty | None = None


@dataclass(frozen=True, slots=True)
class _ToolPrefixState:
    phase: str
    trie: _ChoiceTrie | None = None
    tool: _CompiledTool | None = None
    schema_state: structured._SchemaPrefixState | None = None
    suffix: str = ""
    suffix_index: int = 0
    seen: frozenset[str] = frozenset()


def tool_constraint_requested(execution_ext: object) -> bool:
    choice = _resolved_tool_choice(execution_ext)
    return choice == "required" or bool(_named_tool_choice(choice))


def tool_constraint_preflight_error(
    execution_ext: object,
) -> structured.StructuredOutputConstraintError | None:
    if not tool_constraint_requested(execution_ext):
        return None
    try:
        _compile_tool_constraint(execution_ext)
    except structured.StructuredOutputConstraintError as exc:
        return exc
    return None


def build_tool_choice_logits_processors(
    execution_ext: object,
    tokenizer: Any,
) -> list[Any]:
    if not tool_constraint_requested(execution_ext):
        return []
    compiled_tools, selected_name, descriptor, parallel = _compile_tool_constraint(execution_ext)
    return [
        ToolGrammarConstraintProcessor(
            tokenizer,
            tools=compiled_tools,
            selected_name=selected_name,
            descriptor=descriptor,
            parallel=parallel,
        )
    ]


def tool_wire_descriptor(execution_ext: object) -> ToolWireGrammarDescriptor:
    raw_style = _ext_get(execution_ext, "melix.tool_wire.argument_style").strip().lower()
    raw_dialect = _ext_get(execution_ext, "melix.tool_wire.dialect").strip().lower()
    parser_mode = _ext_get(execution_ext, _PARSER_MODE_KEY).strip().lower()
    if parser_mode:
        if parser_mode == "qwen":
            base = JSON_OBJECT_TOOL_WIRE
        elif parser_mode == "xml":
            base = XML_PARAMETER_TOOL_WIRE
        else:
            raise _tool_error(
                "The selected tool parser has no sampler-enforced wire dialect.",
                "tool_wire_parser_mode_unsupported",
                details={"parser_mode": parser_mode},
            )
    else:
        base = (
            XML_PARAMETER_TOOL_WIRE
            if raw_style == "xml_parameters" or raw_dialect == "xml_parameter_blocks"
            else JSON_OBJECT_TOOL_WIRE
        )
    if raw_style and raw_style != base.argument_style:
        raise _tool_error(
            "Tool wire argument style does not match the selected dialect.",
            "tool_wire_descriptor_mismatch",
        )
    if raw_dialect and raw_dialect != base.dialect:
        raise _tool_error(
            "Tool wire dialect does not match the selected argument style.",
            "tool_wire_descriptor_mismatch",
        )
    begin = _validated_wire_marker(execution_ext, "melix.tool_wire.begin", base.begin)
    end = _validated_wire_marker(execution_ext, "melix.tool_wire.end", base.end)
    trigger = _validated_wire_marker(execution_ext, "melix.tool_wire.trigger", base.trigger)
    sentinel_tokens = _sentinel_tokens(execution_ext, base.sentinel_tokens)
    return ToolWireGrammarDescriptor(
        dialect=base.dialect,
        begin=begin,
        end=end,
        trigger=trigger,
        sentinel_tokens=sentinel_tokens,
        argument_style=base.argument_style,
    )


def tool_wire_accepts_text(execution_ext: object, text: str) -> bool:
    tools, _, descriptor, parallel = _compile_tool_constraint(execution_ext)
    trie = _tool_prefix_trie(tools, descriptor)
    state = _tool_transition_text(
        _ToolPrefixState(phase="prefix", trie=trie),
        text,
        descriptor=descriptor,
        tools=tools,
        choice_trie=trie,
        parallel=parallel,
    )
    return state is not None and _tool_state_complete(state)


class ToolGrammarConstraintProcessor:
    """Sampler-enforced required or named tool call grammar."""

    def __init__(
        self,
        tokenizer: Any,
        *,
        tools: tuple[_CompiledTool, ...],
        selected_name: str,
        descriptor: ToolWireGrammarDescriptor,
        parallel: bool,
    ) -> None:
        vocabulary = structured._tokenizer_vocabulary(tokenizer)
        if not vocabulary:
            raise structured.StructuredOutputConstraintError(
                "The tokenizer does not expose a decodable vocabulary for tool constraints.",
                details={
                    "mode": "tool_choice",
                    "enforcement": "sampler",
                    "reason": "tokenizer_vocab_unavailable",
                },
        )
        self._id_to_text = vocabulary
        vocab_size = max(structured._tokenizer_vocab_size(tokenizer), max(vocabulary) + 1)
        self._mask_vocab_words = math.ceil(vocab_size / 64)
        self._eos_token_ids = structured._tokenizer_eos_token_ids(tokenizer, vocabulary)
        self._descriptor = descriptor
        self._tools = tools
        self._selected_name = selected_name
        self._parallel = parallel
        self._choice_trie = _tool_prefix_trie(tools, descriptor)
        self._state: _ToolPrefixState | None = _ToolPrefixState(
            phase="prefix",
            trie=self._choice_trie,
        )
        self._base_token_count: int | None = None
        self._applied_generated_count = 0
        self._mask_cache: OrderedDict[
            object,
            structured._MaskTemplate,
        ] = OrderedDict()
        template_cache = structured._tokenizer_mask_template_cache(tokenizer)
        self._mask_template_cache = template_cache
        self._packed_allow_token_mask: tuple[int, ...] = ()

    @property
    def constraint_kind(self) -> str:
        return "tool_choice_named" if self._selected_name else "tool_choice_required"

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
            self._base_token_count = structured._single_sequence_token_count(tokens)
        generated_count, unapplied_ids = structured._unapplied_token_ids(
            tokens,
            base_token_count=self._base_token_count,
            applied_generated_count=self._applied_generated_count,
        )
        if unapplied_ids:
            self._advance_state(unapplied_ids)
            self._applied_generated_count = generated_count
        return logits + self._mask_for_state(self._state, int(logits.shape[-1]), logits)

    def _advance_state(self, token_ids: list[int]) -> None:
        state = self._state
        if state is None:
            return
        for token_id in token_ids:
            if token_id in self._eos_token_ids and _tool_state_complete(state):
                continue
            next_state = _tool_transition_text(
                state,
                self._id_to_text.get(token_id, ""),
                descriptor=self._descriptor,
                tools=self._tools,
                choice_trie=self._choice_trie,
                parallel=self._parallel,
            )
            if next_state is None:
                self._state = None
                return
            state = next_state
        self._state = state

    def _mask_for_state(self, state: _ToolPrefixState | None, vocab_size: int, logits: Any) -> Any:
        cache_key = (
            self._choice_trie,
            self._descriptor,
            self._parallel,
            state,
            vocab_size,
            len(logits.shape) > 1,
        )
        cached = self._mask_cache.get(cache_key)
        if cached is not None:
            self._mask_cache.move_to_end(cache_key)
            self._packed_allow_token_mask = cached.packed
            return cached.dense

        template = self._mask_template_cache.get(cache_key)
        if template is not None:
            self._packed_allow_token_mask = template.packed
            self._remember_request_mask(cache_key, template)
            return template.dense

        allowed = [
            state is not None and self._token_allowed(state, token_id)
            for token_id in range(vocab_size)
        ]
        packed = _pack_allowed_tokens(allowed)
        self._packed_allow_token_mask = packed
        import mlx.core as mx

        mask = mx.array([0.0 if item else -math.inf for item in allowed])
        if len(logits.shape) > 1:
            mask = mask.reshape((1, vocab_size))
        template = structured._MaskTemplate(
            dense=mask,
            packed=packed,
            estimated_bytes=structured._mask_template_estimated_bytes(vocab_size),
        )
        template = self._remember_shared_mask(cache_key, template)
        self._packed_allow_token_mask = template.packed
        self._remember_request_mask(cache_key, template)
        return template.dense

    def _token_allowed(self, state: _ToolPrefixState, token_id: int) -> bool:
        complete = _tool_state_complete(state)
        if complete and self._eos_token_ids and not self._parallel:
            return token_id in self._eos_token_ids
        if token_id in self._eos_token_ids and complete:
            return True
        return (
            _tool_transition_text(
                state,
                self._id_to_text.get(token_id, ""),
                descriptor=self._descriptor,
                tools=self._tools,
                choice_trie=self._choice_trie,
                parallel=self._parallel,
            )
            is not None
        )

    def _remember_shared_mask(
        self,
        cache_key: object,
        template: structured._MaskTemplate,
    ) -> structured._MaskTemplate:
        return self._mask_template_cache.remember(cache_key, template)

    def _remember_request_mask(
        self,
        cache_key: object,
        template: structured._MaskTemplate,
    ) -> None:
        self._mask_cache[cache_key] = template
        if len(self._mask_cache) > structured._MAX_MASK_CACHE_ENTRIES:
            self._mask_cache.popitem(last=False)


def _compile_tool_constraint(
    execution_ext: object,
) -> tuple[tuple[_CompiledTool, ...], str, ToolWireGrammarDescriptor, bool]:
    reasoning_mode = (
        _ext_get(execution_ext, "melix.compat.reasoning_mode")
        or _ext_get(execution_ext, "melix.reasoning.mode")
    ).strip().lower()
    if reasoning_mode not in {"", "none", "off", "disabled", "false"}:
        raise structured.StructuredOutputConstraintError(
            "Reasoning-enabled required tool constraints need a bounded prefix policy.",
            code="tool_constraint_reasoning_unsupported",
            details={
                "mode": "tool_choice",
                "enforcement": "sampler",
                "reason": "tool_constraint_reasoning_unsupported",
            },
        )
    raw_tools = _ext_get(execution_ext, _TOOLS_JSON_KEY)
    if not raw_tools:
        raise _tool_error("Required tool choice has no tool definitions.", "tool_schema_missing")
    compiled_tools = _compile_tool_definitions(raw_tools)
    names = {tool.name for tool in compiled_tools}

    choice = _resolved_tool_choice(execution_ext)
    selected_name = _named_tool_choice(choice)
    if selected_name and selected_name not in names:
        raise _tool_error("Named tool choice does not match a declared tool.", "named_tool_not_found")
    selected = (
        tuple(tool for tool in compiled_tools if tool.name == selected_name)
        if selected_name
        else compiled_tools
    )
    descriptor = tool_wire_descriptor(execution_ext)
    if descriptor.argument_style == "xml_parameters":
        for tool in selected:
            if tool_call_rescue.XML_PARAMETER_FUNCTION_OPEN_RE.fullmatch(
                f"<function={tool.name}>"
            ) is None:
                raise _tool_error(
                    "XML parameter grammar cannot round-trip the function name through its parser.",
                    "tool_xml_function_name_invalid",
                )
            declared = {prop.name for prop in tool.arguments.properties}
            if not tool.arguments.required.issubset(declared):
                raise _tool_error(
                    "XML parameter grammar cannot represent undeclared required properties.",
                    "tool_schema_unsupported",
                )
            for prop in tool.arguments.properties:
                if len(prop.name.encode("utf-8")) > _MAX_XML_PARAMETER_NAME_BYTES:
                    raise _tool_complexity_error(
                        "XML parameter name exceeds the supported byte limit.",
                        "max_xml_parameter_name_bytes",
                    )
                if tool_call_rescue.XML_PARAMETER_OPEN_RE.fullmatch(
                    f"<parameter={prop.name}>"
                ) is None:
                    raise _tool_error(
                        "XML parameter grammar cannot round-trip a property name through its parser.",
                        "tool_xml_parameter_name_invalid",
                    )
    parallel = _ext_get(execution_ext, "melix.tool_config.parallel_policy").strip().lower() == "enabled"
    return selected, selected_name, descriptor, parallel


@structured._weighted_lru_cache(
    maxsize=_MAX_TOOL_CACHE_ENTRIES,
    maxbytes=_MAX_TOOL_CACHE_ESTIMATED_BYTES,
    weight=lambda args, _kwargs, tools: len(args[0].encode("utf-8"))
    + _compiled_tools_estimated_bytes(tools),
)
def _compile_tool_definitions(raw_tools: str) -> tuple[_CompiledTool, ...]:
    clock = monotonic
    budget = structured._SchemaCompileBudget(
        deadline=clock() + _TOOL_COMPILE_DEADLINE_SECONDS,
        clock=clock,
        mode="tool_choice",
    )
    try:
        if len(raw_tools.encode("utf-8")) > structured._MAX_SCHEMA_JSON_BYTES:
            raise _tool_complexity_error("Tool schemas exceed the supported byte limit.", "max_schema_bytes")
        payload = json.loads(
            raw_tools,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=structured._reject_nonfinite_json_number,
        )
    except UnicodeEncodeError as exc:
        raise _tool_error("Tool schemas are not valid UTF-8 text.", "tool_schema_invalid") from exc
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise _tool_error("Tool schemas contain malformed JSON.", "tool_schema_invalid") from exc
    if not isinstance(payload, list) or not payload:
        raise _tool_error("Tool schemas must be a non-empty array.", "tool_schema_invalid")
    if len(payload) > _MAX_TOOL_COUNT:
        raise _tool_complexity_error("Tool count exceeds the supported limit.", "max_tool_count")

    structured._check_schema_compile_budget(budget, pointer="")
    compiled: list[_CompiledTool] = []
    names: set[str] = set()
    for index, item in enumerate(payload):
        structured._check_schema_compile_budget(
            budget,
            pointer=f"/tools/{index}",
        )
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict):
            raise _tool_error("Tool definitions must use OpenAI function objects.", "tool_schema_invalid")
        raw_name = function.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        try:
            name_bytes = len(name.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise _tool_error("Tool name must be valid UTF-8 text.", "tool_name_invalid") from exc
        if not name or name_bytes > _MAX_TOOL_NAME_BYTES or any(
            char in name for char in "<>{}\""
        ):
            raise _tool_error("Tool name is empty or cannot be represented by the wire grammar.", "tool_name_invalid")
        if name in names:
            raise _tool_error("Tool names must be unique.", "tool_name_duplicate")
        names.add(name)
        parameters = function.get("parameters") if "parameters" in function else {}
        if parameters == {}:
            parameters = {"type": "object", "additionalProperties": False}
        try:
            node = structured._compile_schema_node(
                parameters,
                pointer=f"/tools/{index}/function/parameters",
                depth=0,
                budget=budget,
            )
        except structured.StructuredOutputConstraintError as exc:
            raise _tool_schema_error(exc) from exc
        if node.types != ("object",):
            raise _tool_error("Tool parameter schemas must resolve to an object.", "tool_schema_root_not_object")
        compiled.append(_CompiledTool(name=name, arguments=node))

    return tuple(compiled)


def _resolved_tool_choice(execution_ext: object) -> str:
    for key in _TOOL_CHOICE_KEYS:
        value = _ext_get(execution_ext, key).strip()
        if value:
            return value
    return ""


def _named_tool_choice(choice: str) -> str:
    normalized = choice.strip()
    if normalized.lower() in {"", "auto", "none", "required"}:
        return ""
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    if not isinstance(payload, dict):
        return ""
    function = payload.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "").strip()
    return str(payload.get("name") or "").strip()


@structured._weighted_lru_cache(
    maxsize=_MAX_TOOL_TRIE_CACHE_ENTRIES,
    maxbytes=_MAX_TOOL_TRIE_CACHE_ESTIMATED_BYTES,
    weight=lambda args, _kwargs, trie: _compiled_tools_estimated_bytes(args[0])
    + _descriptor_estimated_bytes(args[1])
    + _choice_trie_estimated_bytes(trie),
)
def _tool_prefix_trie(
    tools: tuple[_CompiledTool, ...],
    descriptor: ToolWireGrammarDescriptor,
) -> _ChoiceTrie:
    entries: list[tuple[str, object]] = []
    for tool in tools:
        if descriptor.argument_style == "xml_parameters":
            prefix = f"{descriptor.trigger}<function={tool.name}>"
        else:
            encoded_name = json.dumps(tool.name, ensure_ascii=True, separators=(",", ":"))
            prefix = f'{descriptor.trigger}{{"name":{encoded_name},"arguments":'
        entries.append((prefix, tool))
    return _choice_trie(entries)


def _choice_trie(entries: list[tuple[str, object]]) -> _ChoiceTrie:
    root: dict[str, object] = {"terminal": None, "children": {}}
    for text, terminal in entries:
        cursor = root
        for char in text:
            children = cursor["children"]
            assert isinstance(children, dict)
            cursor = children.setdefault(char, {"terminal": None, "children": {}})
            assert isinstance(cursor, dict)
        cursor["terminal"] = terminal

    def freeze(raw: dict[str, object]) -> _ChoiceTrie:
        children = raw["children"]
        assert isinstance(children, dict)
        return _ChoiceTrie(
            terminal=raw["terminal"],
            children=MappingProxyType(
                {str(char): freeze(child) for char, child in children.items() if isinstance(child, dict)}
            ),
        )

    return freeze(root)


def _compiled_tools_estimated_bytes(tools: tuple[_CompiledTool, ...]) -> int:
    estimated_bytes = 0
    seen_schema: set[int] = set()
    for tool in tools:
        estimated_bytes += len(tool.name.encode("utf-8")) + 256
        identity = id(tool.arguments)
        if identity not in seen_schema:
            seen_schema.add(identity)
            estimated_bytes += structured._schema_graph_estimated_bytes(tool.arguments)
    return estimated_bytes


def _descriptor_estimated_bytes(descriptor: ToolWireGrammarDescriptor) -> int:
    return 256 + sum(
        structured._utf8_estimated_size(value)
        for value in (
            descriptor.dialect,
            descriptor.begin,
            descriptor.end,
            descriptor.trigger,
            descriptor.argument_style,
            *descriptor.sentinel_tokens,
        )
    )


def _choice_trie_estimated_bytes(root: _ChoiceTrie) -> int:
    estimated_bytes = 0
    stack = [root]
    seen: set[int] = set()
    while stack:
        trie = stack.pop()
        identity = id(trie)
        if identity in seen:
            continue
        seen.add(identity)
        estimated_bytes += 192 + len(trie.children) * 96
        for char, child in trie.children.items():
            estimated_bytes += structured._utf8_estimated_size(char)
            stack.append(child)
    return estimated_bytes


def _tool_transition_text(
    state: _ToolPrefixState,
    text: str,
    *,
    descriptor: ToolWireGrammarDescriptor,
    tools: tuple[_CompiledTool, ...],
    choice_trie: _ChoiceTrie,
    parallel: bool,
) -> _ToolPrefixState | None:
    if not text:
        return None
    next_state: _ToolPrefixState | None = state
    for char in text:
        if next_state is None:
            return None
        next_state = _tool_transition_char(
            next_state,
            char,
            descriptor=descriptor,
            tools=tools,
            choice_trie=choice_trie,
            parallel=parallel,
        )
    return next_state


def _tool_transition_char(
    state: _ToolPrefixState,
    char: str,
    *,
    descriptor: ToolWireGrammarDescriptor,
    tools: tuple[_CompiledTool, ...],
    choice_trie: _ChoiceTrie,
    parallel: bool,
) -> _ToolPrefixState | None:
    if state.phase in {"prefix", "xml_choice"}:
        trie = state.trie
        if trie is None:
            return None
        child = trie.children.get(char)
        if child is None:
            return None
        next_state = _ToolPrefixState(
            phase=state.phase,
            trie=child,
            tool=state.tool,
            seen=state.seen,
        )
        if child.terminal is None or child.children:
            return next_state
        if state.phase == "prefix" and isinstance(child.terminal, _CompiledTool):
            tool = child.terminal
            if descriptor.argument_style == "xml_parameters":
                return _xml_between_state(tool, state.seen)
            return _ToolPrefixState(
                phase="json_args",
                tool=tool,
                schema_state=structured._SchemaPrefixState(root_node=tool.arguments),
            )
        if state.phase == "xml_choice" and isinstance(child.terminal, _XMLChoice):
            choice = child.terminal
            if choice.kind == "close":
                return _ToolPrefixState(
                    phase="suffix",
                    tool=state.tool,
                    suffix=descriptor.end,
                    seen=state.seen,
                )
            prop = choice.property
            if prop is None:
                return None
            return _ToolPrefixState(
                phase="xml_value",
                tool=state.tool,
                schema_state=structured._SchemaPrefixState(root_node=prop.node),
                seen=state.seen | frozenset((prop.name,)),
            )
        return None

    if state.phase in {"json_args", "xml_value"}:
        schema_state = state.schema_state
        if schema_state is None:
            return None
        if structured._schema_is_complete(schema_state):
            suffix = "}" + descriptor.end if state.phase == "json_args" else "</parameter>"
            return _consume_suffix_char(state, char, suffix=suffix)
        next_schema = structured._schema_transition_char(schema_state, char)
        if next_schema is not None:
            return _ToolPrefixState(
                phase=state.phase,
                tool=state.tool,
                schema_state=next_schema,
                seen=state.seen,
            )
        if state.phase == "xml_value" and char == "<":
            delimited = structured._schema_transition_char(schema_state, " ")
            if delimited is not None and structured._schema_is_complete(delimited):
                return _consume_suffix_char(state, char, suffix="</parameter>")
        return None

    if state.phase == "suffix":
        return _consume_suffix_char(state, char, suffix=state.suffix)
    if state.phase in {"complete", "separator"}:
        if char.isspace():
            return _ToolPrefixState(phase="separator", seen=state.seen)
        if not parallel:
            return None
        child = choice_trie.children.get(char)
        if child is None:
            return None
        restart = _ToolPrefixState(phase="prefix", trie=child)
        if child.terminal is not None and not child.children:
            return _tool_transition_char(
                _ToolPrefixState(phase="prefix", trie=choice_trie),
                char,
                descriptor=descriptor,
                tools=tools,
                choice_trie=choice_trie,
                parallel=parallel,
            )
        return restart
    return None


def _consume_suffix_char(
    state: _ToolPrefixState,
    char: str,
    *,
    suffix: str,
) -> _ToolPrefixState | None:
    index = state.suffix_index if state.phase == "suffix" and state.suffix == suffix else 0
    if index >= len(suffix) or suffix[index] != char:
        return None
    index += 1
    if index < len(suffix):
        return _ToolPrefixState(
            phase="suffix",
            tool=state.tool,
            suffix=suffix,
            suffix_index=index,
            seen=state.seen,
        )
    if suffix == "</parameter>":
        if state.tool is None:
            return None
        return _xml_between_state(state.tool, state.seen)
    return _ToolPrefixState(phase="complete")


@structured._weighted_lru_cache(
    maxsize=_MAX_XML_STATE_CACHE_ENTRIES,
    maxbytes=_MAX_XML_STATE_CACHE_ESTIMATED_BYTES,
    weight=lambda args, _kwargs, state: _compiled_tools_estimated_bytes((args[0],))
    + sum(structured._utf8_estimated_size(item) + 64 for item in args[1])
    + (_choice_trie_estimated_bytes(state.trie) if state.trie is not None else 1),
)
def _xml_between_state(tool: _CompiledTool, seen: frozenset[str]) -> _ToolPrefixState:
    entries: list[tuple[str, object]] = []
    for prop in tool.arguments.properties:
        if prop.name not in seen:
            entries.append((f"<parameter={prop.name}>", _XMLChoice("property", prop)))
    if tool.arguments.required.issubset(seen):
        entries.append(("</function>", _XMLChoice("close")))
    return _ToolPrefixState(
        phase="xml_choice",
        trie=_choice_trie(entries),
        tool=tool,
        seen=seen,
    )


def _tool_state_complete(state: _ToolPrefixState) -> bool:
    return state.phase in {"complete", "separator"}


def _pack_allowed_tokens(allowed: list[bool]) -> tuple[int, ...]:
    words = [0] * math.ceil(len(allowed) / 64)
    for token_id, is_allowed in enumerate(allowed):
        if is_allowed:
            words[token_id // 64] |= 1 << (token_id % 64)
    return tuple(words)


def _sentinel_tokens(
    execution_ext: object,
    expected: tuple[str, ...],
) -> tuple[str, ...]:
    raw_tokens = _ext_get(execution_ext, "melix.tool_wire.sentinel_tokens").strip()
    if not raw_tokens:
        return expected
    try:
        payload = json.loads(raw_tokens)
        if (
            not isinstance(payload, list)
            or not payload
            or len(payload) > _MAX_SENTINEL_TOKEN_COUNT
            or any(not isinstance(token, str) or not token for token in payload)
            or len(set(payload)) != len(payload)
            or any(
                len(token.encode("utf-8")) > _MAX_SENTINEL_TOKEN_BYTES
                for token in payload
            )
        ):
            raise ValueError("invalid sentinel token list")
    except (json.JSONDecodeError, UnicodeEncodeError, ValueError) as exc:
        raise _tool_error(
            "Tool wire sentinel tokens are malformed.",
            "tool_wire_descriptor_invalid",
        ) from exc
    sentinel_tokens = tuple(payload)
    if sentinel_tokens != expected:
        raise _tool_error(
            "Tool wire sentinel tokens do not match the selected dialect.",
            "tool_wire_descriptor_mismatch",
        )
    return sentinel_tokens


def _validated_wire_marker(execution_ext: object, key: str, expected: str) -> str:
    marker = _ext_get(execution_ext, key).strip()
    if not marker:
        return expected
    try:
        marker_bytes = len(marker.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise _tool_error(
            "Tool wire marker must be valid UTF-8 text.",
            "tool_wire_descriptor_invalid",
        ) from exc
    if marker_bytes > 256:
        raise _tool_complexity_error("Tool wire marker exceeds the supported limit.", "max_wire_marker_bytes")
    if marker != expected:
        raise _tool_error(
            "Tool wire marker does not match the selected dialect.",
            "tool_wire_descriptor_mismatch",
        )
    return expected


def _ext_get(execution_ext: object, key: str) -> str:
    if not execution_ext:
        return ""
    getter = getattr(execution_ext, "get", None)
    if not callable(getter):
        return ""
    return str(getter(key, "") or "")


def _tool_error(
    message: str,
    reason: str,
    *,
    details: Mapping[str, str] | None = None,
) -> structured.StructuredOutputConstraintError:
    error_details = {
        "mode": "tool_choice",
        "enforcement": "sampler",
        "reason": reason,
    }
    if details:
        error_details.update(details)
    return structured.StructuredOutputConstraintError(
        message,
        details=error_details,
    )


def _tool_schema_error(
    error: structured.StructuredOutputConstraintError,
) -> structured.StructuredOutputConstraintError:
    reason = error.details.get("reason", "")
    if reason.startswith("tool_"):
        return error
    if reason == "json_schema_too_complex":
        mapped_reason = "tool_schema_too_complex"
    elif reason in {"json_schema_unsupported_keyword", "json_schema_unsupported_type"}:
        mapped_reason = "tool_schema_unsupported"
    else:
        mapped_reason = "tool_schema_invalid"
    details = dict(error.details)
    details["mode"] = "tool_choice"
    details["reason"] = mapped_reason
    return structured.StructuredOutputConstraintError(
        str(error),
        code=error.code,
        details=details,
    )


def _tool_complexity_error(message: str, limit: str) -> structured.StructuredOutputConstraintError:
    error = _tool_error(message, "tool_schema_too_complex")
    error.details["limit"] = limit
    return error
