from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
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
_KeywordHintRuleSet = tuple[str, tuple[str, ...], tuple[str, ...]]

TOOL_REGISTRY_SCHEMA_VERSION = "melix.agentic_tool_registry.v1"
TOOL_SCHEMA_CONSISTENCY_RECEIPT_SCHEMA_VERSION = (
    "melix.agentic_tool_schema_consistency.v1"
)
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
SELECTABLE_AGENTIC_TOOL_NAMES = (
    "image_crop",
    "layout_parse",
    "text_search",
    "image_search",
    "skill_lookup",
    "memory_lookup",
    "visit",
    "workspace_file",
    "local_compute",
)
_BUILTIN_AGENTIC_TOOL_NAME_SET = frozenset(SELECTABLE_AGENTIC_TOOL_NAMES)
ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES = ("local_compute",)
_EMPTY_AGENTIC_TOOL_NAME_SET: frozenset[str] = frozenset()
NETWORK_CAPABLE_AGENTIC_TOOL_NAMES = ("visit",)
_NETWORK_CAPABLE_AGENTIC_TOOL_NAME_SET = frozenset(NETWORK_CAPABLE_AGENTIC_TOOL_NAMES)
_NETWORK_CAPABLE_AGENTIC_TOOL_NAME_LIST = list(NETWORK_CAPABLE_AGENTIC_TOOL_NAMES)
_WEB_POLICY_EXPLICIT_ALLOW_LIST = ["web"]
_WEB_POLICY_EXPLICIT_DENY_LIST = ["web"]
_KEYWORD_MATCHABLE_TOOL_NAMES = tuple(
    tool_name
    for tool_name in SELECTABLE_AGENTIC_TOOL_NAMES
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
        cached_required_arguments = self._cached_required_arguments_list
        copy_dict = _COPY_DICT
        copy_list = _COPY_LIST
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {name: copy_dict(schema) for name, schema in schema_properties},
            "required": copy_list(cached_required_arguments),
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
    max_selected_tools: int = len(SELECTABLE_AGENTIC_TOOL_NAMES)
    allow_web: bool | None = None


@dataclass(frozen=True, slots=True)
class ToolSelectionResult:
    registry: ToolRegistry
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolSchemaConsistencyDecision:
    consistent: bool
    receipt: dict[str, Any]
    referenced_tools: tuple[str, ...]
    callable_tools: tuple[str, ...]
    missing_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolIndexMetadata:
    tool_id: str
    retrieval_description: str
    routing_hints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tool_id = self.tool_id.strip()
        retrieval_description = self.retrieval_description.strip()
        routing_hints = tuple(
            hint.strip() for hint in self.routing_hints if hint.strip()
        )
        if not _TOOL_NAME_RE.fullmatch(tool_id):
            raise ToolRegistryError(f"Invalid tool index metadata id: {tool_id}")
        if not retrieval_description:
            raise ToolRegistryError(
                f"Tool index metadata {tool_id} must include a retrieval description."
            )
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "retrieval_description", retrieval_description)
        object.__setattr__(self, "routing_hints", routing_hints)


class ToolRegistry:
    __slots__ = (
        "_empty_selection",
        "_metrics",
        "_openai_tool_templates",
        "_parser",
        "_parser_contract_version",
        "_schema_version",
        "_selection_cache",
        "_tool_by_name",
        "_tool_name_set",
        "_tool_names",
        "_tool_names_list",
        "_tools",
        "_toolset_version",
        "_worker_tool_config_bytes",
        "_worker_tool_config_template",
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
        self._tool_name_set = frozenset(self._tool_names)
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
        self._empty_selection: ToolRegistry | None = None
        self._worker_tool_config_bytes: bytes = b""
        self._worker_tool_config_template: common_pb2.ToolConfig | None = None
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
        if not names:
            cached_selection = self._empty_selection
            if cached_selection is not None:
                return cached_selection
            selection = ToolRegistry(
                (),
                schema_version=self._schema_version,
                toolset_version=self._toolset_version,
                parser=self._parser,
                parser_contract_version=self._parser_contract_version,
            )
            self._empty_selection = selection
            self._selection_cache[()] = selection
            return selection
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
            tool_by_name = self._tool_by_name
            missing_tool_sentinel = _MISSING_TOOL_SENTINEL
            tool = tool_by_name.get(raw_name, missing_tool_sentinel)
            if tool is not missing_tool_sentinel:
                requested_names = (raw_name,)
                cached_selection = self._selection_cache.get(requested_names)
                if cached_selection is not None:
                    return cached_selection
                selection = ToolRegistry(
                    (cast(ToolDescriptor, tool),),
                    schema_version=self._schema_version,
                    toolset_version=self._toolset_version,
                    parser=self._parser,
                    parser_contract_version=self._parser_contract_version,
                )
                if len(self._selection_cache) >= _SELECTION_CACHE_MAX_SIZE:
                    self._selection_cache.clear()
                self._selection_cache[requested_names] = selection
                return selection
            if raw_name and not raw_name[0].isspace() and not raw_name[-1].isspace():
                raise ToolRegistryError(
                    f"Unknown tool registry entry requested: {raw_name}"
                )
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
                tool = tool_by_name.get(normalized_name, missing_tool_sentinel)
                if tool is missing_tool_sentinel:
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
            if not name:
                continue
            if name[0].isspace() or name[-1].isspace():
                normalized_name = name.strip()
                if not normalized_name:
                    continue
            else:
                normalized_name = name
            if normalized_name in seen_names:
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
        openai_tool_templates = self._openai_tool_templates
        if not openai_tool_templates:
            return []
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
            ) in openai_tool_templates
        ]

    def as_worker_tool_config(self) -> common_pb2.ToolConfig:
        cached_template = self._worker_tool_config_template
        if cached_template is not None:
            return _copy_tool_config(cached_template)
        config = common_pb2.ToolConfig(
            tools=[tool.as_worker_tool_definition() for tool in self._tools],
            schema_format="openai-function",
            schema_version=self._schema_version,
            toolset_version=self._toolset_version,
            parser=self._parser,
            parser_contract_version=self._parser_contract_version,
        )
        self._worker_tool_config_bytes = config.SerializeToString()
        self._worker_tool_config_template = config
        return _copy_tool_config(config)

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


def agentic_tool_catalog_registry() -> ToolRegistry:
    return _AGENTIC_TOOL_CATALOG_REGISTRY


def agentic_tool_index_metadata() -> dict[str, ToolIndexMetadata]:
    return dict(_BUILTIN_TOOL_INDEX_METADATA)


def preflight_agentic_tool_schema_consistency(
    affordances: Sequence[Any],
    *,
    registry: ToolRegistry,
    catalog: ToolRegistry | None = None,
    source: str = "tool_affordance",
) -> ToolSchemaConsistencyDecision:
    if catalog is None:
        catalog = agentic_tool_catalog_registry()
    callable_tools = registry.names()
    callable_tool_set = registry._tool_name_set
    catalog_tools = catalog.names()
    catalog_tool_set = catalog._tool_name_set
    if _BUILTIN_AGENTIC_TOOL_NAME_SET.issubset(
        catalog_tool_set
    ) and callable_tool_set.issubset(catalog_tool_set):
        known_tool_names = catalog_tool_set
    else:
        known_tool_names = callable_tool_set | catalog_tool_set | _BUILTIN_AGENTIC_TOOL_NAME_SET
    referenced_tools, invalid_affordance_count = _referenced_tool_affordance_names(
        affordances,
        known_tool_names,
        catalog_tools,
        callable_tools,
        include_builtin_order_source=catalog_tools != SELECTABLE_AGENTIC_TOOL_NAMES,
        include_registry_order_source=not callable_tool_set.issubset(catalog_tool_set),
    )
    missing_tools = tuple(
        tool_name for tool_name in referenced_tools if tool_name not in callable_tool_set
    )
    consistent = not missing_tools
    receipt = {
        "schema_version": TOOL_SCHEMA_CONSISTENCY_RECEIPT_SCHEMA_VERSION,
        "toolset_version": BUILTIN_TOOLSET_VERSION,
        "outcome": "consistent" if consistent else "mismatch",
        "source": _safe_tool_affordance_source(source),
        "referenced_tools": list(referenced_tools),
        "callable_tools": list(callable_tools),
        "missing_tools": list(missing_tools),
        "invalid_affordance_count": invalid_affordance_count,
        "checked_affordance_count": len(affordances),
        "allowed_next_step": "assemble_prompt" if consistent else "strip_missing_affordances",
        "corrective_action": "" if consistent else "remove_unavailable_tool_affordances",
    }
    return ToolSchemaConsistencyDecision(
        consistent=consistent,
        receipt=receipt,
        referenced_tools=referenced_tools,
        callable_tools=callable_tools,
        missing_tools=missing_tools,
    )


def _referenced_tool_affordance_names(
    affordances: Sequence[Any],
    known_tool_names: set[str] | frozenset[str],
    catalog_names: tuple[str, ...],
    registry_names: tuple[str, ...],
    *,
    include_builtin_order_source: bool = True,
    include_registry_order_source: bool = True,
) -> tuple[tuple[str, ...], int]:
    seen_tool_names: set[str] = set()
    invalid_affordance_count = 0
    for affordance in affordances:
        tool_name = _tool_affordance_name(affordance)
        if tool_name is None or tool_name not in known_tool_names:
            invalid_affordance_count += 1
            continue
        seen_tool_names.add(tool_name)
    if not seen_tool_names:
        return (), invalid_affordance_count
    ordered_names: list[str] = []
    ordered_name_set: set[str] | None = None
    if include_builtin_order_source:
        ordered_name_set = set()
        for ordered_source_names in (catalog_names, SELECTABLE_AGENTIC_TOOL_NAMES):
            for tool_name in ordered_source_names:
                if tool_name in seen_tool_names and tool_name not in ordered_name_set:
                    ordered_names.append(tool_name)
                    ordered_name_set.add(tool_name)
    else:
        for tool_name in catalog_names:
            if tool_name in seen_tool_names:
                ordered_names.append(tool_name)
    if include_registry_order_source:
        if ordered_name_set is None:
            ordered_name_set = set(ordered_names)
        for tool_name in registry_names:
            if tool_name in seen_tool_names and tool_name not in ordered_name_set:
                ordered_names.append(tool_name)
                ordered_name_set.add(tool_name)
    return tuple(ordered_names), invalid_affordance_count


def _tool_affordance_name(affordance: Any) -> str | None:
    if isinstance(affordance, str):
        return _normalized_tool_affordance_name(affordance)
    if isinstance(affordance, Mapping):
        for key in ("tool_id", "tool_name", "name"):
            raw_value = affordance.get(key)
            if isinstance(raw_value, str):
                return _normalized_tool_affordance_name(raw_value)
            if raw_value is not None:
                return None
    return None


def _normalized_tool_affordance_name(raw_name: str) -> str | None:
    normalized_name = raw_name.strip()
    if not normalized_name:
        return None
    if not _TOOL_NAME_RE.fullmatch(normalized_name):
        return None
    return normalized_name


def _safe_tool_affordance_source(source: str) -> str:
    normalized_source = source.strip()
    if _TOOL_NAME_RE.fullmatch(normalized_source):
        return normalized_source
    return "unspecified"


def built_in_tool_config(names: list[str] | tuple[str, ...] | None = None) -> common_pb2.ToolConfig:
    copy_tool_config = _copy_tool_config
    if names is None or names is BUILTIN_AGENTIC_TOOL_NAMES:
        return copy_tool_config(_BUILTIN_TOOL_CONFIG_TEMPLATE)
    if isinstance(names, tuple):
        if names == BUILTIN_AGENTIC_TOOL_NAMES:
            return copy_tool_config(_BUILTIN_TOOL_CONFIG_TEMPLATE)
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
    registry = _AGENTIC_TOOL_CATALOG_REGISTRY.select(requested_names)
    config = registry.as_worker_tool_config()
    normalized_names = registry.names()
    _BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES[normalized_names] = config
    if raw_requested_names != normalized_names:
        _BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES[raw_requested_names] = config
    return copy_tool_config(config)


def _append_selected_tool(
    selected_names: list[str],
    selected_sources: dict[str, str],
    selected_tools: list[dict[str, str]],
    tool_name: str,
    source: str,
    max_selected_tools: int,
) -> bool:
    if len(selected_names) >= max_selected_tools or not tool_name:
        return False
    if tool_name[0].isspace() or tool_name[-1].isspace():
        normalized_name = tool_name.strip()
        if not normalized_name:
            return False
    else:
        normalized_name = tool_name
    if normalized_name in selected_sources:
        return False
    if normalized_name not in _BUILTIN_AGENTIC_TOOL_NAME_SET:
        return False
    selected_sources[normalized_name] = source
    selected_names.append(normalized_name)
    selected_tools.append({"tool_id": normalized_name, "source": source})
    return True


def _append_policy_selected_tool(
    selected_names: list[str],
    selected_sources: dict[str, str],
    selected_tools: list[dict[str, str]],
    tool_name: str,
    source: str,
    max_selected_tools: int,
    disabled_tool_names: frozenset[str] | None,
    denied_tool_names: list[str] | None,
) -> bool:
    if len(selected_names) >= max_selected_tools or not tool_name:
        return False
    if tool_name[0].isspace() or tool_name[-1].isspace():
        normalized_name = tool_name.strip()
        if not normalized_name:
            return False
    else:
        normalized_name = tool_name
    if normalized_name in selected_sources:
        return False
    if normalized_name not in _BUILTIN_AGENTIC_TOOL_NAME_SET:
        return False
    if disabled_tool_names is not None and normalized_name in disabled_tool_names:
        if denied_tool_names is not None and normalized_name not in denied_tool_names:
            denied_tool_names.append(normalized_name)
        return False
    selected_sources[normalized_name] = source
    selected_names.append(normalized_name)
    selected_tools.append({"tool_id": normalized_name, "source": source})
    return True


def select_agentic_tools_for_turn(selection_input: ToolSelectionInput) -> ToolSelectionResult:
    vector_selected_tool_ids = selection_input.vector_selected_tool_ids
    recent_user_turns = selection_input.recent_user_turns
    vector_available = selection_input.vector_available
    current_user_turn = selection_input.current_user_turn
    if selection_input.allow_web is not None:
        return _select_agentic_tools_for_turn_with_policy(selection_input)
    registry = agentic_tool_catalog_registry()
    max_selected_tools = selection_input.max_selected_tools
    if max_selected_tools <= 1:
        return _build_always_only_tool_selection_result(registry, selection_input)
    if (
        not vector_selected_tool_ids
        and not recent_user_turns
        and (not current_user_turn or current_user_turn.isspace())
    ):
        return _build_always_only_tool_selection_result(registry, selection_input)
    current_matches: tuple[str, ...] | None = None
    context_matches: tuple[str, ...] | None = None
    if not vector_selected_tool_ids:
        current_matches = _keyword_tool_matches(current_user_turn)
        if not current_matches:
            if recent_user_turns:
                context_matches = _keyword_tool_matches(
                    _recent_user_turns_keyword_context(recent_user_turns)
                )
                if not context_matches:
                    return _build_always_only_tool_selection_result(
                        registry, selection_input
                    )
            else:
                return _build_always_only_tool_selection_result(registry, selection_input)
    selected_name = "local_compute"
    selected_sources: dict[str, str] = {selected_name: "always"}
    selected_names: list[str] = [selected_name]
    selected_tools: list[dict[str, str]] = [{"tool_id": selected_name, "source": "always"}]
    append_selected_tool = _append_selected_tool
    has_vector_selection = False
    has_keyword_selection = False

    selection_mode = "fallback"
    fallback_reason = "no_keyword_match"
    if len(selected_names) >= max_selected_tools:
        return _build_tool_selection_result(
            registry,
            selected_names,
            selected_tools,
            selection_input,
            selection_mode,
            fallback_reason,
        )

    if vector_available and vector_selected_tool_ids:
        for tool_name in vector_selected_tool_ids:
            if append_selected_tool(
                selected_names,
                selected_sources,
                selected_tools,
                tool_name,
                "vector",
                max_selected_tools,
            ):
                has_vector_selection = True
        if has_vector_selection:
            return _build_tool_selection_result(
                registry,
                selected_names,
                selected_tools,
                selection_input,
                "vector",
                "",
            )

    if current_matches is None:
        current_matches = _keyword_tool_matches(current_user_turn)
    for tool_name in current_matches:
        if append_selected_tool(
            selected_names,
            selected_sources,
            selected_tools,
            tool_name,
            "keyword",
            max_selected_tools,
        ):
            has_keyword_selection = True
    if recent_user_turns and len(selected_names) < max_selected_tools:
        if context_matches is None:
            context_matches = _keyword_tool_matches(
                _recent_user_turns_keyword_context(recent_user_turns)
            )
        for tool_name in context_matches:
            if append_selected_tool(
                selected_names,
                selected_sources,
                selected_tools,
                tool_name,
                "keyword_context",
                max_selected_tools,
            ):
                has_keyword_selection = True
    if has_keyword_selection:
        selection_mode = "keyword"
        fallback_reason = "vector_unavailable" if not vector_available else "vector_no_match"

    if not has_vector_selection and not has_keyword_selection:
        return _build_always_only_tool_selection_result(registry, selection_input)

    return _build_tool_selection_result(
        registry,
        selected_names,
        selected_tools,
        selection_input,
        selection_mode,
        fallback_reason,
    )


def _select_agentic_tools_for_turn_with_policy(selection_input: ToolSelectionInput) -> ToolSelectionResult:
    registry = agentic_tool_catalog_registry()
    max_selected_tools = selection_input.max_selected_tools
    allow_web = selection_input.allow_web
    disabled_tool_names = _disabled_agentic_tool_names(selection_input) if allow_web is False else None
    denied_tool_names: list[str] | None = [] if allow_web is False else None
    allowed_policy_receipt = (
        _agentic_tool_policy_receipt(selection_input, _EMPTY_AGENTIC_TOOL_NAME_SET, None)
        if allow_web is True
        else None
    )
    if max_selected_tools <= 1:
        return _build_always_only_tool_selection_result(
            registry,
            selection_input,
            tool_policy_receipt=(
                _agentic_tool_policy_receipt(selection_input, disabled_tool_names, denied_tool_names)
                if allow_web is False
                else allowed_policy_receipt
            ),
        )
    current_user_turn = selection_input.current_user_turn
    if (
        not selection_input.vector_selected_tool_ids
        and not selection_input.recent_user_turns
        and (not current_user_turn or current_user_turn.isspace())
    ):
        return _build_always_only_tool_selection_result(
            registry,
            selection_input,
            tool_policy_receipt=(
                _agentic_tool_policy_receipt(selection_input, disabled_tool_names, denied_tool_names)
                if allow_web is False
                else allowed_policy_receipt
            ),
        )
    current_matches: tuple[str, ...] | None = None
    context_matches: tuple[str, ...] | None = None
    if not selection_input.vector_selected_tool_ids:
        current_matches = _keyword_tool_matches(current_user_turn)
        if not current_matches:
            if selection_input.recent_user_turns:
                context_matches = _keyword_tool_matches(
                    _recent_user_turns_keyword_context(selection_input.recent_user_turns)
                )
                if not context_matches:
                    return _build_always_only_tool_selection_result(
                        registry,
                        selection_input,
                        tool_policy_receipt=(
                            _agentic_tool_policy_receipt(
                                selection_input, disabled_tool_names, denied_tool_names
                            )
                            if allow_web is False
                            else allowed_policy_receipt
                        ),
                    )
            else:
                return _build_always_only_tool_selection_result(
                    registry,
                    selection_input,
                    tool_policy_receipt=(
                        _agentic_tool_policy_receipt(
                            selection_input, disabled_tool_names, denied_tool_names
                        )
                        if allow_web is False
                        else allowed_policy_receipt
                    ),
                )
    selected_sources: dict[str, str] = {}
    selected_names: list[str] = []
    selected_tools: list[dict[str, str]] = []
    append_selected_tool = _append_policy_selected_tool
    has_vector_selection = False
    has_keyword_selection = False

    for tool_name in ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES:
        append_selected_tool(
            selected_names,
            selected_sources,
            selected_tools,
            tool_name,
            "always",
            max_selected_tools,
            disabled_tool_names,
            denied_tool_names,
        )

    selection_mode = "fallback"
    fallback_reason = "no_keyword_match"

    if selection_input.vector_available and selection_input.vector_selected_tool_ids:
        for tool_name in selection_input.vector_selected_tool_ids:
            if append_selected_tool(
                selected_names,
                selected_sources,
                selected_tools,
                tool_name,
                "vector",
                max_selected_tools,
                disabled_tool_names,
                denied_tool_names,
            ):
                has_vector_selection = True
        if has_vector_selection:
            return _build_tool_selection_result(
                registry,
                selected_names,
                selected_tools,
                selection_input,
                "vector",
                "",
                tool_policy_receipt=(
                    _agentic_tool_policy_receipt(
                        selection_input, disabled_tool_names, denied_tool_names
                    )
                    if allow_web is False
                    else allowed_policy_receipt
                ),
            )

    if selection_mode != "vector":
        if current_matches is None:
            current_matches = _keyword_tool_matches(selection_input.current_user_turn)
        for tool_name in current_matches:
            if append_selected_tool(
                selected_names,
                selected_sources,
                selected_tools,
                tool_name,
                "keyword",
                max_selected_tools,
                disabled_tool_names,
                denied_tool_names,
            ):
                has_keyword_selection = True
        if selection_input.recent_user_turns and len(selected_names) < max_selected_tools:
            if context_matches is None:
                context_matches = _keyword_tool_matches(
                    _recent_user_turns_keyword_context(selection_input.recent_user_turns)
                )
            for tool_name in context_matches:
                if append_selected_tool(
                    selected_names,
                    selected_sources,
                    selected_tools,
                    tool_name,
                    "keyword_context",
                    max_selected_tools,
                    disabled_tool_names,
                    denied_tool_names,
                ):
                    has_keyword_selection = True
        if has_keyword_selection:
            selection_mode = "keyword"
            fallback_reason = "vector_unavailable" if not selection_input.vector_available else "vector_no_match"

    if not has_vector_selection and not has_keyword_selection:
        return _build_always_only_tool_selection_result(
            registry,
            selection_input,
            fallback_reason=_policy_fallback_reason(denied_tool_names),
            tool_policy_receipt=(
                _agentic_tool_policy_receipt(selection_input, disabled_tool_names, denied_tool_names)
                if allow_web is False
                else allowed_policy_receipt
            ),
        )

    return _build_tool_selection_result(
        registry,
        selected_names,
        selected_tools,
        selection_input,
        selection_mode,
        fallback_reason,
        tool_policy_receipt=(
            _agentic_tool_policy_receipt(selection_input, disabled_tool_names, denied_tool_names)
            if allow_web is False
            else allowed_policy_receipt
        ),
    )


def _build_always_only_tool_selection_result(
    registry: ToolRegistry,
    selection_input: ToolSelectionInput,
    *,
    fallback_reason: str = "no_keyword_match",
    tool_policy_receipt: dict[str, Any] | None = None,
) -> ToolSelectionResult:
    selected_name = "local_compute"
    if registry is _AGENTIC_TOOL_CATALOG_REGISTRY:
        selected_registry = _ALWAYS_ONLY_TOOL_REGISTRY
        registry_metrics = _AGENTIC_TOOL_CATALOG_METRICS
        selected_metrics = _ALWAYS_ONLY_TOOL_METRICS
        dropped_tool_count = _ALWAYS_ONLY_DROPPED_TOOL_COUNT
        if (
            tool_policy_receipt is None
            and fallback_reason == "no_keyword_match"
            and not selection_input.vector_available
        ):
            receipt = _ALWAYS_ONLY_RECEIPT_BASE.copy()
            receipt["selected_tools"] = [_ALWAYS_ONLY_SELECTED_TOOL_RECEIPT.copy()]
            return ToolSelectionResult(registry=selected_registry, receipt=receipt)
    else:
        selected_registry = registry.select((selected_name,))
        registry_metrics = registry.metrics()
        selected_metrics = selected_registry.metrics()
        dropped_tool_count = max(0, registry_metrics.tool_count - selected_metrics.tool_count)
    receipt = {
        "schema_version": "melix.agentic_tool_selection.v1",
        "toolset_version": BUILTIN_TOOLSET_VERSION,
        "selection_mode": "fallback",
        "vector_available": selection_input.vector_available,
        "fallback_reason": fallback_reason,
        "selected_tools": [{"tool_id": selected_name, "source": "always"}],
        "dropped_tool_count": dropped_tool_count,
        "full_schema_bytes": registry_metrics.schema_bytes,
        "selected_schema_bytes": selected_metrics.schema_bytes,
    }
    if tool_policy_receipt is not None:
        receipt["tool_policy_receipt"] = tool_policy_receipt
    return ToolSelectionResult(registry=selected_registry, receipt=receipt)


def _build_tool_selection_result(
    registry: ToolRegistry,
    selected_names: list[str],
    selected_tools: list[dict[str, str]],
    selection_input: ToolSelectionInput,
    selection_mode: str,
    fallback_reason: str,
    *,
    tool_policy_receipt: dict[str, Any] | None = None,
) -> ToolSelectionResult:
    if len(selected_names) == 1:
        selected_name = selected_names[0]
        selected_registry = registry.select((selected_name,))
    else:
        selected_registry = registry.select(tuple(selected_names))
    registry_metrics = registry.metrics()
    selected_metrics = selected_registry.metrics()
    selected_tool_count = selected_metrics.tool_count
    receipt = {
        "schema_version": "melix.agentic_tool_selection.v1",
        "toolset_version": BUILTIN_TOOLSET_VERSION,
        "selection_mode": selection_mode,
        "vector_available": selection_input.vector_available,
        "fallback_reason": fallback_reason,
        "selected_tools": selected_tools,
        "dropped_tool_count": max(0, registry_metrics.tool_count - selected_tool_count),
        "full_schema_bytes": registry_metrics.schema_bytes,
        "selected_schema_bytes": selected_metrics.schema_bytes,
    }
    if tool_policy_receipt is not None:
        receipt["tool_policy_receipt"] = tool_policy_receipt
    return ToolSelectionResult(registry=selected_registry, receipt=receipt)


def _disabled_agentic_tool_names(selection_input: ToolSelectionInput) -> frozenset[str]:
    if selection_input.allow_web is False:
        return _NETWORK_CAPABLE_AGENTIC_TOOL_NAME_SET
    return _EMPTY_AGENTIC_TOOL_NAME_SET


def _policy_fallback_reason(denied_tool_names: list[str] | None) -> str:
    return "policy_disabled" if denied_tool_names else "no_keyword_match"


def _agentic_tool_policy_receipt(
    selection_input: ToolSelectionInput,
    disabled_tool_names: frozenset[str] | None,
    denied_tool_names: list[str] | None,
) -> dict[str, Any] | None:
    if selection_input.allow_web is None and not disabled_tool_names and not denied_tool_names:
        return None
    disabled_tool_names = disabled_tool_names or _EMPTY_AGENTIC_TOOL_NAME_SET
    copy_list = _COPY_LIST
    if disabled_tool_names is _NETWORK_CAPABLE_AGENTIC_TOOL_NAME_SET:
        disabled = copy_list(_NETWORK_CAPABLE_AGENTIC_TOOL_NAME_LIST)
    else:
        disabled = [
            tool_name for tool_name in SELECTABLE_AGENTIC_TOOL_NAMES if tool_name in disabled_tool_names
        ]
    requested = copy_list(denied_tool_names) if denied_tool_names else []
    return {
        "schema_version": "melix.agentic_tool_policy.v1",
        "allow_web": selection_input.allow_web,
        "explicit_allows": copy_list(_WEB_POLICY_EXPLICIT_ALLOW_LIST)
        if selection_input.allow_web is True
        else [],
        "explicit_denies": copy_list(_WEB_POLICY_EXPLICIT_DENY_LIST)
        if selection_input.allow_web is False
        else [],
        "resolved_disabled_tools": disabled,
        "requested_tools": requested,
    }


def _recent_user_turns_keyword_context(recent_user_turns: tuple[str, ...]) -> str:
    if len(recent_user_turns) == 1:
        return recent_user_turns[0]
    return " ".join(recent_user_turns)


@lru_cache(maxsize=128)
def _keyword_tool_matches(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    if text.isspace():
        return ()
    normalized_text = text.lower()
    boundary_text = ""
    matches: list[str] = []
    append_match = matches.append
    keyword_boundary_text = _keyword_boundary_text
    for tool_name, literal_hints, boundary_hints in _BUILTIN_TOOL_KEYWORD_HINT_RULE_ITEMS:
        matched = False
        for hint in literal_hints:
            if hint in normalized_text:
                append_match(tool_name)
                matched = True
                break
        if matched:
            continue
        if boundary_hints:
            if not boundary_text:
                boundary_text = keyword_boundary_text(normalized_text)
            for hint in boundary_hints:
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


_AGENTIC_TOOL_CATALOG_TOOLS = (
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
        name="skill_lookup",
        description="Look up local agent skills from a fixture-backed skill store.",
        tool_kind="skill.lookup",
        observation_kind="skill_lookup_results",
        arguments=(
            _arg("query", "string", "Skill lookup query."),
            _arg("store_ref", "string", "Optional local skill store or fixture identifier.", required=False),
            _arg("max_results", "integer", "Maximum number of skill results to return.", required=False),
        ),
    ),
    ToolDescriptor(
        name="memory_lookup",
        description="Look up pinned or retrieved memories from a fixture-backed memory store.",
        tool_kind="memory.lookup",
        observation_kind="memory_lookup_results",
        arguments=(
            _arg("query", "string", "Memory lookup query."),
            _arg("store_ref", "string", "Optional local memory store or fixture identifier.", required=False),
            _arg("max_results", "integer", "Maximum number of memory results to return.", required=False),
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
        name="workspace_file",
        description="Read, write, or edit files inside the active workspace after path-policy checks.",
        tool_kind="workspace_file.operation",
        observation_kind="workspace_file_result",
        arguments=(
            _arg("operation", "string", "Workspace file operation: read, write, or edit."),
            _arg("path", "string", "Workspace-relative or admitted absolute file path."),
            _arg("content", "string", "Text content for write operations.", required=False),
            _arg("old_text", "string", "Exact text to replace for edit operations.", required=False),
            _arg("new_text", "string", "Replacement text for edit operations.", required=False),
            _arg(
                "expected_replacements",
                "integer",
                "Optional exact replacement count for edit operations.",
                required=False,
            ),
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

_BUILTIN_TOOL_INDEX_METADATA = {
    "image_crop": ToolIndexMetadata(
        tool_id="image_crop",
        retrieval_description="Crop or inspect a bounded region from a referenced image.",
        routing_hints=(
            "crop",
            "cropped",
            "crop_",
            "region",
            "image region",
            "inspect image",
        ),
    ),
    "layout_parse": ToolIndexMetadata(
        tool_id="layout_parse",
        retrieval_description="Extract visual layout elements from an image or document page.",
        routing_hints=(
            "layout",
            "table",
            "tables",
            "ocr",
            "document layout",
            "page layout",
        ),
    ),
    "text_search": ToolIndexMetadata(
        tool_id="text_search",
        retrieval_description="Search a local text corpus or fixture-backed index.",
        routing_hints=(
            "search",
            "text evidence",
            "local corpus",
            "corpus",
            "documents",
            "retrieve",
            "retrieval",
        ),
    ),
    "image_search": ToolIndexMetadata(
        tool_id="image_search",
        retrieval_description="Search local image evidence or fixture-backed image indexes.",
        routing_hints=(
            "image search",
            "search images",
            "visual search",
            "find images",
            "image evidence",
        ),
    ),
    "skill_lookup": ToolIndexMetadata(
        tool_id="skill_lookup",
        retrieval_description="Look up local agent skills from a fixture-backed skill store.",
        routing_hints=(
            "skill lookup",
            "repo skill",
            "agent skill",
            "skill search",
            "find skill",
        ),
    ),
    "memory_lookup": ToolIndexMetadata(
        tool_id="memory_lookup",
        retrieval_description="Look up pinned or retrieved memories from a fixture-backed memory store.",
        routing_hints=(
            "memory lookup",
            "pinned memory",
            "retrieved memory",
            "remembered preference",
            "operator preference",
        ),
    ),
    "visit": ToolIndexMetadata(
        tool_id="visit",
        retrieval_description="Visit a local URL or fixture-backed page and return extracted content.",
        routing_hints=(
            "visit",
            "open",
            "read fixture://",
            "fixture://",
            "page",
            "url",
            "fetch",
        ),
    ),
    "workspace_file": ToolIndexMetadata(
        tool_id="workspace_file",
        retrieval_description=(
            "Read, write, or edit files inside the active workspace after path-policy checks."
        ),
        routing_hints=(
            "workspace file",
            "local file",
            "read file",
            "write file",
            "edit file",
            "file path",
            "workspace-local",
        ),
    ),
    "local_compute": ToolIndexMetadata(
        tool_id="local_compute",
        retrieval_description="Run deterministic local compute for parsing, arithmetic, or data shaping.",
    ),
}
_BUILTIN_TOOL_KEYWORD_HINTS = {
    tool_name: metadata.routing_hints
    for tool_name, metadata in _BUILTIN_TOOL_INDEX_METADATA.items()
    if tool_name not in ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES
}
_BUILTIN_TOOL_KEYWORD_HINT_RULES = _compile_keyword_hint_rules(_BUILTIN_TOOL_KEYWORD_HINTS)
_BUILTIN_TOOL_KEYWORD_HINT_RULE_ITEMS: tuple[_KeywordHintRuleSet, ...] = tuple(
    (
        tool_name,
        tuple(hint for hint, literal in _BUILTIN_TOOL_KEYWORD_HINT_RULES.get(tool_name, ()) if literal),
        tuple(hint for hint, literal in _BUILTIN_TOOL_KEYWORD_HINT_RULES.get(tool_name, ()) if not literal),
    )
    for tool_name in _KEYWORD_MATCHABLE_TOOL_NAMES
)


_BUILTIN_TOOL_NAME_SET = frozenset(BUILTIN_AGENTIC_TOOL_NAMES)
_BUILTIN_AGENTIC_TOOLS = tuple(
    tool for tool in _AGENTIC_TOOL_CATALOG_TOOLS if tool.name in _BUILTIN_TOOL_NAME_SET
)
_AGENTIC_TOOL_CATALOG_REGISTRY = ToolRegistry(_AGENTIC_TOOL_CATALOG_TOOLS)
_AGENTIC_TOOL_CATALOG_METRICS = _AGENTIC_TOOL_CATALOG_REGISTRY.metrics()
_ALWAYS_ONLY_TOOL_REGISTRY = _AGENTIC_TOOL_CATALOG_REGISTRY.select(("local_compute",))
_ALWAYS_ONLY_TOOL_METRICS = _ALWAYS_ONLY_TOOL_REGISTRY.metrics()
_ALWAYS_ONLY_DROPPED_TOOL_COUNT = max(
    0,
    _AGENTIC_TOOL_CATALOG_METRICS.tool_count - _ALWAYS_ONLY_TOOL_METRICS.tool_count,
)
_ALWAYS_ONLY_SELECTED_TOOL_RECEIPT = {"tool_id": "local_compute", "source": "always"}
_ALWAYS_ONLY_RECEIPT_BASE: dict[str, Any] = {
    "schema_version": "melix.agentic_tool_selection.v1",
    "toolset_version": BUILTIN_TOOLSET_VERSION,
    "selection_mode": "fallback",
    "vector_available": False,
    "fallback_reason": "no_keyword_match",
    "selected_tools": [],
    "dropped_tool_count": _ALWAYS_ONLY_DROPPED_TOOL_COUNT,
    "full_schema_bytes": _AGENTIC_TOOL_CATALOG_METRICS.schema_bytes,
    "selected_schema_bytes": _ALWAYS_ONLY_TOOL_METRICS.schema_bytes,
}
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
    "NETWORK_CAPABLE_AGENTIC_TOOL_NAMES",
    "SELECTABLE_AGENTIC_TOOL_NAMES",
    "TOOL_REGISTRY_SCHEMA_VERSION",
    "TOOL_SCHEMA_CONSISTENCY_RECEIPT_SCHEMA_VERSION",
    "ToolArgumentDescriptor",
    "ToolDescriptor",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolIndexMetadata",
    "ToolRegistryMetrics",
    "ToolSchemaConsistencyDecision",
    "ToolSelectionInput",
    "ToolSelectionResult",
    "agentic_tool_index_metadata",
    "agentic_tool_catalog_registry",
    "built_in_tool_config",
    "built_in_tool_registry",
    "preflight_agentic_tool_schema_consistency",
    "select_agentic_tools_for_turn",
]
