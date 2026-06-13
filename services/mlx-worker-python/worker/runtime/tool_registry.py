from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, cast

from packages.protocol.python.worker.v1 import common_pb2


_TOOL_CONFIG = common_pb2.ToolConfig
_TOOL_CONFIG_FROM_BYTES = _TOOL_CONFIG.FromString
_COMPACT_SORTED_JSON_ENCODER = json.JSONEncoder(separators=(",", ":"), sort_keys=True)
_COPY_DICT = dict.copy
_COPY_LIST = list.copy
_MISSING_TOOL_SENTINEL = object()


def _copy_tool_config(template: common_pb2.ToolConfig) -> common_pb2.ToolConfig:
    config = _TOOL_CONFIG()
    config.CopyFrom(template)
    return config


_OpenAIToolTemplate = tuple[
    str,
    str,
    str,
    str,
    tuple[tuple[str, dict[str, Any]], ...],
    list[str],
]


_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SELECTION_CACHE_MAX_SIZE = 32
_KEYWORD_LITERAL_HINT_CHARACTERS = ":/_"
_KEYWORD_TOKEN_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_KEYWORD_BOUNDARY_TRANSLATION = str.maketrans(
    {
        chr(codepoint): " "
        for codepoint in range(128)
        if chr(codepoint) not in _KEYWORD_TOKEN_CHARACTERS
    }
)
_KeywordHintRule = tuple[str, bool]

TOOL_REGISTRY_SCHEMA_VERSION = "melix.agentic_tool_registry.v1"
BUILTIN_TOOLSET_VERSION = "melix.agentic_tools.builtin.v1"
DEFAULT_TOOL_PARSER = "qwen"
DEFAULT_TOOL_PARSER_CONTRACT_VERSION = "melix.tool_parser.qwen.v1"
BUILTIN_AGENTIC_TOOL_NAMES = (
    "image_crop",
    "layout_parse",
    "text_search",
    "image_search",
    "visit",
    "local_compute",
)
_BUILTIN_AGENTIC_TOOL_NAME_SET = frozenset(BUILTIN_AGENTIC_TOOL_NAMES)
ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES = ("local_compute",)
_KEYWORD_MATCHABLE_TOOL_NAMES = tuple(
    tool_name
    for tool_name in BUILTIN_AGENTIC_TOOL_NAMES
    if tool_name not in ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES
)


class ToolRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolArgumentDescriptor:
    name: str
    json_type: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not _TOOL_NAME_RE.fullmatch(normalized_name):
            raise ToolRegistryError(f"Invalid tool argument name: {self.name}")
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "json_type", self.json_type.strip())
        object.__setattr__(self, "description", self.description.strip())
        if not self.json_type:
            raise ToolRegistryError(f"Tool argument {self.name} must declare a JSON type.")
        if not self.description:
            raise ToolRegistryError(f"Tool argument {self.name} must include a description.")

    def json_schema(self) -> dict[str, Any]:
        return {
            "type": self.json_type,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    tool_kind: str
    observation_kind: str
    arguments: tuple[ToolArgumentDescriptor, ...]
    _cached_required_arguments: tuple[str, ...] = field(default=(), init=False, repr=False)
    _cached_required_arguments_list: list[str] = field(
        default_factory=list, init=False, repr=False
    )
    _cached_schema_properties: tuple[tuple[str, dict[str, Any]], ...] = field(
        default=(), init=False, repr=False
    )
    _cached_schema: str = field(default="", init=False, repr=False)
    _cached_schema_bytes: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not _TOOL_NAME_RE.fullmatch(normalized_name):
            raise ToolRegistryError(f"Invalid tool registry name: {self.name}")
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "tool_kind", self.tool_kind.strip())
        object.__setattr__(self, "observation_kind", self.observation_kind.strip())
        if not self.description:
            raise ToolRegistryError(f"Tool {normalized_name} must include a description.")
        if not self.tool_kind:
            raise ToolRegistryError(f"Tool {normalized_name} must include a tool kind.")
        if not self.observation_kind:
            raise ToolRegistryError(f"Tool {normalized_name} must include an observation kind.")
        if not self.arguments:
            raise ToolRegistryError(f"Tool {normalized_name} must define at least one argument.")
        argument_names: set[str] = set()
        for argument in self.arguments:
            if argument.name in argument_names:
                raise ToolRegistryError(
                    f"Duplicate argument {argument.name} in tool registry entry {normalized_name}."
                )
            argument_names.add(argument.name)
        required_arguments = tuple(argument.name for argument in self.arguments if argument.required)
        object.__setattr__(self, "_cached_required_arguments", required_arguments)
        object.__setattr__(self, "_cached_required_arguments_list", list(required_arguments))
        schema_properties = tuple(
            (argument.name, argument.json_schema()) for argument in self.arguments
        )
        object.__setattr__(self, "_cached_schema_properties", schema_properties)
        cached_schema = _COMPACT_SORTED_JSON_ENCODER.encode(self.schema_payload())
        object.__setattr__(self, "_cached_schema", cached_schema)
        # The registry encoder keeps ensure_ascii=True, so the compact schema
        # string is ASCII-only and its character length matches UTF-8 bytes.
        object.__setattr__(self, "_cached_schema_bytes", len(cached_schema))

    @property
    def required_arguments(self) -> tuple[str, ...]:
        return self._cached_required_arguments

    def schema_payload(self) -> dict[str, Any]:
        schema_properties = self._cached_schema_properties
        copy_dict = _COPY_DICT
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {name: copy_dict(schema) for name, schema in schema_properties},
            "required": _COPY_LIST(self._cached_required_arguments_list),
        }

    def json_schema(self) -> str:
        return self._cached_schema

    def schema_byte_count(self) -> int:
        return self._cached_schema_bytes

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema_payload(),
            },
            "x-melix-tool-kind": self.tool_kind,
            "x-melix-observation-kind": self.observation_kind,
        }

    def as_worker_tool_definition(self) -> common_pb2.ToolDefinition:
        return common_pb2.ToolDefinition(
            name=self.name,
            description=self.description,
            json_schema=self.json_schema(),
        )


@dataclass(frozen=True, slots=True)
class ToolRegistryMetrics:
    tool_count: int
    schema_bytes: int
    required_argument_count: int


@dataclass(frozen=True, slots=True)
class ToolSelectionInput:
    current_user_turn: str = ""
    recent_user_turns: tuple[str, ...] = ()
    vector_selected_tool_ids: tuple[str, ...] = ()
    vector_available: bool = False
    max_selected_tools: int = len(BUILTIN_AGENTIC_TOOL_NAMES)


@dataclass(frozen=True, slots=True)
class ToolSelectionResult:
    registry: ToolRegistry
    receipt: dict[str, Any]


class ToolRegistry:
    __slots__ = (
        "_metrics",
        "_openai_tool_templates",
        "_parser",
        "_parser_contract_version",
        "_schema_version",
        "_selection_cache",
        "_tool_by_name",
        "_tool_names",
        "_tool_names_list",
        "_tools",
        "_toolset_version",
        "_worker_tool_config_bytes",
    )

    def __init__(
        self,
        tools: list[ToolDescriptor] | tuple[ToolDescriptor, ...],
        *,
        schema_version: str = TOOL_REGISTRY_SCHEMA_VERSION,
        toolset_version: str = BUILTIN_TOOLSET_VERSION,
        parser: str = DEFAULT_TOOL_PARSER,
        parser_contract_version: str = DEFAULT_TOOL_PARSER_CONTRACT_VERSION,
    ) -> None:
        self._tools = tuple(tools)
        self._schema_version = schema_version.strip()
        self._toolset_version = toolset_version.strip()
        self._parser = parser.strip()
        self._parser_contract_version = parser_contract_version.strip()
        self._validate()
        self._tool_names = tuple(tool.name for tool in self._tools)
        self._tool_names_list = list(self._tool_names)
        self._tool_by_name = {tool.name: tool for tool in self._tools}
        self._openai_tool_templates: tuple[_OpenAIToolTemplate, ...] = tuple(
            (
                tool.name,
                tool.description,
                tool.tool_kind,
                tool.observation_kind,
                tool._cached_schema_properties,
                tool._cached_required_arguments_list,
            )
            for tool in self._tools
        )
        self._selection_cache: dict[tuple[str, ...], ToolRegistry] = {}
        self._worker_tool_config_bytes: bytes = b""
        self._metrics = ToolRegistryMetrics(
            tool_count=len(self._tools),
            schema_bytes=sum(tool.schema_byte_count() for tool in self._tools),
            required_argument_count=sum(len(tool.required_arguments) for tool in self._tools),
        )

    @property
    def tools(self) -> tuple[ToolDescriptor, ...]:
        return self._tools

    def names(self) -> tuple[str, ...]:
        return self._tool_names

    def metrics(self) -> ToolRegistryMetrics:
        return self._metrics

    def select(self, names: list[str] | tuple[str, ...]) -> ToolRegistry:
        if isinstance(names, tuple):
            if names == self._tool_names:
                return self
            cached_selection = self._selection_cache.get(names)
            if cached_selection is not None:
                return cached_selection
        elif names == self._tool_names_list:
            return self

        if len(names) == 1:
            raw_name = names[0]
            normalized_name = raw_name.strip()
            if normalized_name:
                requested_names = (normalized_name,)
                if requested_names == self._tool_names:
                    return self
                cached_selection = self._selection_cache.get(requested_names)
                if cached_selection is not None:
                    if isinstance(names, tuple) and names != requested_names:
                        self._selection_cache[names] = cached_selection
                    return cached_selection
                tool = self._tool_by_name.get(normalized_name, _MISSING_TOOL_SENTINEL)
                if tool is _MISSING_TOOL_SENTINEL:
                    raise ToolRegistryError(
                        f"Unknown tool registry entry requested: {normalized_name}"
                    )
                selected_tool = cast(ToolDescriptor, tool)
                selection = ToolRegistry(
                    (selected_tool,),
                    schema_version=self._schema_version,
                    toolset_version=self._toolset_version,
                    parser=self._parser,
                    parser_contract_version=self._parser_contract_version,
                )
                raw_tuple_key = names if isinstance(names, tuple) and names != requested_names else None
                if len(self._selection_cache) >= _SELECTION_CACHE_MAX_SIZE - int(raw_tuple_key is not None):
                    self._selection_cache.clear()
                self._selection_cache[requested_names] = selection
                if raw_tuple_key is not None:
                    self._selection_cache[raw_tuple_key] = selection
                return selection

        requested_names_list: list[str] = []
        selected: list[ToolDescriptor] = []
        missing_names: list[str] = []
        seen_names: set[str] = set()
        tool_by_name = self._tool_by_name
        missing_tool_sentinel = _MISSING_TOOL_SENTINEL
        for name in names:
            normalized_name = name.strip()
            if not normalized_name or normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            requested_names_list.append(normalized_name)
            tool = tool_by_name.get(normalized_name, missing_tool_sentinel)
            if tool is missing_tool_sentinel:
                missing_names.append(normalized_name)
            else:
                selected.append(cast(ToolDescriptor, tool))
        requested_names = tuple(requested_names_list)
        if requested_names == self._tool_names:
            return self
        cached_selection = self._selection_cache.get(requested_names)
        if cached_selection is not None:
            return cached_selection
        if missing_names:
            joined = ", ".join(missing_names)
            raise ToolRegistryError(f"Unknown tool registry entry requested: {joined}")
        selection = ToolRegistry(
            selected,
            schema_version=self._schema_version,
            toolset_version=self._toolset_version,
            parser=self._parser,
            parser_contract_version=self._parser_contract_version,
        )
        raw_tuple_key = names if isinstance(names, tuple) and names != requested_names else None
        if len(self._selection_cache) >= _SELECTION_CACHE_MAX_SIZE - int(raw_tuple_key is not None):
            self._selection_cache.clear()
        self._selection_cache[requested_names] = selection
        if raw_tuple_key is not None:
            self._selection_cache[raw_tuple_key] = selection
        return selection

    def as_openai_tools(self) -> list[dict[str, Any]]:
        copy_dict = _COPY_DICT
        copy_list = _COPY_LIST
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            argument_name: copy_dict(schema)
                            for argument_name, schema in schema_properties
                        },
                        "required": copy_list(required_arguments),
                    },
                },
                "x-melix-tool-kind": tool_kind,
                "x-melix-observation-kind": observation_kind,
            }
            for (
                name,
                description,
                tool_kind,
                observation_kind,
                schema_properties,
                required_arguments,
            ) in self._openai_tool_templates
        ]

    def as_worker_tool_config(self) -> common_pb2.ToolConfig:
        if self._worker_tool_config_bytes:
            return _TOOL_CONFIG_FROM_BYTES(self._worker_tool_config_bytes)
        config = common_pb2.ToolConfig(
            tools=[tool.as_worker_tool_definition() for tool in self._tools],
            schema_format="openai-function",
            schema_version=self._schema_version,
            toolset_version=self._toolset_version,
            parser=self._parser,
            parser_contract_version=self._parser_contract_version,
        )
        self._worker_tool_config_bytes = config.SerializeToString()
        return config

    def _validate(self) -> None:
        if not self._schema_version:
            raise ToolRegistryError("Tool registry schema_version must be non-empty.")
        if not self._toolset_version:
            raise ToolRegistryError("Tool registry toolset_version must be non-empty.")
        if not self._parser:
            raise ToolRegistryError("Tool registry parser must be non-empty.")
        if not self._parser_contract_version:
            raise ToolRegistryError("Tool registry parser_contract_version must be non-empty.")
        seen_names: set[str] = set()
        for tool in self._tools:
            if tool.name in seen_names:
                raise ToolRegistryError(f"Duplicate tool registry entry: {tool.name}")
            seen_names.add(tool.name)


def built_in_tool_registry() -> ToolRegistry:
    return _BUILTIN_TOOL_CONFIG_REGISTRY


def built_in_tool_config(names: list[str] | tuple[str, ...] | None = None) -> common_pb2.ToolConfig:
    copy_tool_config = _copy_tool_config
    if names is None or names == BUILTIN_AGENTIC_TOOL_NAMES:
        return copy_tool_config(_BUILTIN_TOOL_CONFIG_TEMPLATE)
    if isinstance(names, tuple):
        cached_config = _BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES.get(names)
        if cached_config is not None:
            return copy_tool_config(cached_config)
        requested_names = names
    else:
        if names == _BUILTIN_TOOL_CONFIG_NAMES_LIST:
            return copy_tool_config(_BUILTIN_TOOL_CONFIG_TEMPLATE)
        requested_names = tuple(names)
    raw_requested_names = requested_names
    cached_config = _BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES.get(requested_names)
    if cached_config is not None:
        return copy_tool_config(cached_config)
    registry = _BUILTIN_TOOL_CONFIG_REGISTRY.select(requested_names)
    config = registry.as_worker_tool_config()
    normalized_names = registry.names()
    _BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES[normalized_names] = config
    if raw_requested_names != normalized_names:
        _BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES[raw_requested_names] = config
    return copy_tool_config(config)


def select_agentic_tools_for_turn(selection_input: ToolSelectionInput) -> ToolSelectionResult:
    registry = built_in_tool_registry()
    max_selected_tools = max(1, selection_input.max_selected_tools)
    selected_sources: dict[str, str] = {}
    selected_names: list[str] = []
    has_vector_selection = False
    has_keyword_selection = False

    def add_tool(tool_name: str, source: str) -> None:
        nonlocal has_keyword_selection, has_vector_selection
        if len(selected_names) >= max_selected_tools:
            return
        normalized_name = tool_name.strip()
        if not normalized_name or normalized_name in selected_sources:
            return
        if normalized_name not in _BUILTIN_AGENTIC_TOOL_NAME_SET:
            return
        selected_sources[normalized_name] = source
        selected_names.append(normalized_name)
        if source == "vector":
            has_vector_selection = True
        elif source == "keyword" or source == "keyword_context":
            has_keyword_selection = True

    for tool_name in ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES:
        add_tool(tool_name, "always")

    selection_mode = "fallback"
    fallback_reason = "no_keyword_match"
    if len(selected_names) >= max_selected_tools:
        return _build_tool_selection_result(
            registry,
            selected_names,
            selected_sources,
            selection_input,
            selection_mode,
            fallback_reason,
        )

    if selection_input.vector_available and selection_input.vector_selected_tool_ids:
        for tool_name in selection_input.vector_selected_tool_ids:
            add_tool(tool_name, "vector")
        if has_vector_selection:
            selection_mode = "vector"
            fallback_reason = ""

    if selection_mode != "vector":
        current_matches = _keyword_tool_matches(selection_input.current_user_turn)
        if selection_input.recent_user_turns:
            context_matches = _keyword_tool_matches(
                _recent_user_turns_keyword_context(selection_input.recent_user_turns)
            )
        else:
            context_matches = ()
        for tool_name in current_matches:
            add_tool(tool_name, "keyword")
        for tool_name in context_matches:
            add_tool(tool_name, "keyword_context")
        if has_keyword_selection:
            selection_mode = "keyword"
            fallback_reason = "vector_unavailable" if not selection_input.vector_available else "vector_no_match"

    return _build_tool_selection_result(
        registry,
        selected_names,
        selected_sources,
        selection_input,
        selection_mode,
        fallback_reason,
    )


def _build_tool_selection_result(
    registry: ToolRegistry,
    selected_names: list[str],
    selected_sources: dict[str, str],
    selection_input: ToolSelectionInput,
    selection_mode: str,
    fallback_reason: str,
) -> ToolSelectionResult:
    selected_registry = registry.select(tuple(selected_names))
    selected_tool_count = selected_registry.metrics().tool_count
    receipt = {
        "schema_version": "melix.agentic_tool_selection.v1",
        "toolset_version": BUILTIN_TOOLSET_VERSION,
        "selection_mode": selection_mode,
        "vector_available": selection_input.vector_available,
        "fallback_reason": fallback_reason,
        "selected_tools": [
            {"tool_id": tool_name, "source": selected_sources[tool_name]}
            for tool_name in selected_registry.names()
        ],
        "dropped_tool_count": max(0, registry.metrics().tool_count - selected_tool_count),
        "full_schema_bytes": registry.metrics().schema_bytes,
        "selected_schema_bytes": selected_registry.metrics().schema_bytes,
    }
    return ToolSelectionResult(registry=selected_registry, receipt=receipt)


def _recent_user_turns_keyword_context(recent_user_turns: tuple[str, ...]) -> str:
    if len(recent_user_turns) == 1:
        return recent_user_turns[0]
    return " ".join(recent_user_turns)


@lru_cache(maxsize=128)
def _keyword_tool_matches(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    normalized_text = text.casefold()
    if not normalized_text.strip():
        return ()
    boundary_text = ""
    matches: list[str] = []
    append_match = matches.append
    keyword_hint_rules = _BUILTIN_TOOL_KEYWORD_HINT_RULES
    keyword_boundary_text = _keyword_boundary_text
    for tool_name in _KEYWORD_MATCHABLE_TOOL_NAMES:
        rules = keyword_hint_rules.get(tool_name, ())
        for hint, literal in rules:
            if literal:
                if hint in normalized_text:
                    append_match(tool_name)
                    break
                continue
            if not boundary_text:
                boundary_text = keyword_boundary_text(normalized_text)
            if hint in boundary_text:
                append_match(tool_name)
                break
    return tuple(matches)


def _keyword_hint_matches(
    text: str,
    hint: str,
    *,
    literal: bool | None = None,
    boundary_text: str | None = None,
) -> bool:
    if not hint:
        return False
    normalized_text = text.casefold()
    if literal is None:
        literal = any(character in hint for character in _KEYWORD_LITERAL_HINT_CHARACTERS)
        if not literal:
            hint = _keyword_boundary_text(hint.casefold())
    if literal:
        return hint.casefold() in normalized_text
    if boundary_text is None:
        boundary_text = _keyword_boundary_text(normalized_text)
    return hint in boundary_text


def _keyword_boundary_text(text: str) -> str:
    return f" {text.translate(_KEYWORD_BOUNDARY_TRANSLATION)} "


def _compile_keyword_hint_rules(
    hints_by_tool: dict[str, tuple[str, ...]],
) -> dict[str, tuple[_KeywordHintRule, ...]]:
    literal_hint_characters = _KEYWORD_LITERAL_HINT_CHARACTERS
    keyword_boundary_text = _keyword_boundary_text
    compiled_rules: dict[str, tuple[_KeywordHintRule, ...]] = {}
    for tool_name, hints in hints_by_tool.items():
        rules: list[_KeywordHintRule] = []
        append_rule = rules.append
        for hint in hints:
            if not hint:
                continue
            casefolded_hint = hint.casefold()
            is_literal = any(character in hint for character in literal_hint_characters)
            append_rule(
                (casefolded_hint, True)
                if is_literal
                else (keyword_boundary_text(casefolded_hint), False)
            )
        compiled_rules[tool_name] = tuple(rules)
    return compiled_rules


def _arg(
    name: str,
    json_type: str,
    description: str,
    *,
    required: bool = True,
) -> ToolArgumentDescriptor:
    return ToolArgumentDescriptor(
        name=name,
        json_type=json_type,
        description=description,
        required=required,
    )


_BUILTIN_AGENTIC_TOOLS = (
    ToolDescriptor(
        name="image_crop",
        description="Crop or inspect a bounded region from a referenced image.",
        tool_kind="vision.image_crop",
        observation_kind="image_region",
        arguments=(
            _arg("media_ref", "string", "Identifier or URI for the source image."),
            _arg("region", "string", "Crop region as a named area or normalized box."),
            _arg("purpose", "string", "Reason the crop is needed for the current step.", required=False),
        ),
    ),
    ToolDescriptor(
        name="layout_parse",
        description="Extract visual layout elements from an image or document page.",
        tool_kind="vision.layout_parse",
        observation_kind="layout_elements",
        arguments=(
            _arg("media_ref", "string", "Identifier or URI for the source image or document."),
            _arg("detail_level", "string", "Requested layout detail such as blocks, lines, or tables.", required=False),
        ),
    ),
    ToolDescriptor(
        name="text_search",
        description="Search a local text corpus or fixture-backed index.",
        tool_kind="retrieval.text_search",
        observation_kind="search_results",
        arguments=(
            _arg("query", "string", "Text query to search for."),
            _arg("corpus_ref", "string", "Optional local corpus or fixture identifier.", required=False),
            _arg("max_results", "integer", "Maximum number of search results to return.", required=False),
        ),
    ),
    ToolDescriptor(
        name="image_search",
        description="Search local image evidence or fixture-backed image indexes.",
        tool_kind="retrieval.image_search",
        observation_kind="image_search_results",
        arguments=(
            _arg("query", "string", "Visual or textual query for image search."),
            _arg("corpus_ref", "string", "Optional image corpus or fixture identifier.", required=False),
            _arg("max_results", "integer", "Maximum number of image results to return.", required=False),
        ),
    ),
    ToolDescriptor(
        name="visit",
        description="Visit a local URL or fixture-backed page and return extracted content.",
        tool_kind="browser.visit",
        observation_kind="page_extract",
        arguments=(
            _arg("url", "string", "URL or fixture URL to visit."),
            _arg("extract", "string", "Extraction mode such as text, links, or screenshot.", required=False),
        ),
    ),
    ToolDescriptor(
        name="local_compute",
        description="Run deterministic local compute for parsing, arithmetic, or data shaping.",
        tool_kind="compute.local",
        observation_kind="compute_result",
        arguments=(
            _arg("code", "string", "Small deterministic compute snippet or expression."),
            _arg("timeout_ms", "integer", "Maximum execution time in milliseconds.", required=False),
        ),
    ),
)

_BUILTIN_TOOL_KEYWORD_HINTS = {
    "image_crop": (
        "crop",
        "cropped",
        "crop_",
        "region",
        "image region",
        "inspect image",
    ),
    "layout_parse": (
        "layout",
        "table",
        "tables",
        "ocr",
        "document layout",
        "page layout",
    ),
    "text_search": (
        "search",
        "text evidence",
        "local corpus",
        "corpus",
        "documents",
        "retrieve",
        "retrieval",
    ),
    "image_search": (
        "image search",
        "search images",
        "visual search",
        "find images",
        "image evidence",
    ),
    "visit": (
        "visit",
        "open",
        "read fixture://",
        "fixture://",
        "page",
        "url",
        "fetch",
    ),
}
_BUILTIN_TOOL_KEYWORD_HINT_RULES = _compile_keyword_hint_rules(_BUILTIN_TOOL_KEYWORD_HINTS)


_BUILTIN_TOOL_CONFIG_REGISTRY = ToolRegistry(_BUILTIN_AGENTIC_TOOLS)
_BUILTIN_TOOL_CONFIG_NAMES_LIST = list(BUILTIN_AGENTIC_TOOL_NAMES)
_BUILTIN_TOOL_CONFIG_BYTES = (
    _BUILTIN_TOOL_CONFIG_REGISTRY.as_worker_tool_config().SerializeToString()
)
_BUILTIN_TOOL_CONFIG_TEMPLATE = _TOOL_CONFIG_FROM_BYTES(_BUILTIN_TOOL_CONFIG_BYTES)
_BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES: dict[tuple[str, ...], common_pb2.ToolConfig] = {
    BUILTIN_AGENTIC_TOOL_NAMES: _BUILTIN_TOOL_CONFIG_TEMPLATE,
}


__all__ = [
    "ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES",
    "BUILTIN_AGENTIC_TOOL_NAMES",
    "BUILTIN_TOOLSET_VERSION",
    "DEFAULT_TOOL_PARSER",
    "DEFAULT_TOOL_PARSER_CONTRACT_VERSION",
    "TOOL_REGISTRY_SCHEMA_VERSION",
    "ToolArgumentDescriptor",
    "ToolDescriptor",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolRegistryMetrics",
    "ToolSelectionInput",
    "ToolSelectionResult",
    "built_in_tool_config",
    "built_in_tool_registry",
    "select_agentic_tools_for_turn",
]
