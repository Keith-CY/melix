from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2


_COMPACT_SORTED_JSON_ENCODER = json.JSONEncoder(separators=(",", ":"), sort_keys=True)
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SELECTION_CACHE_MAX_SIZE = 32

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


class ToolRegistryError(ValueError):
    pass


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    tool_kind: str
    observation_kind: str
    arguments: tuple[ToolArgumentDescriptor, ...]
    _cached_required_arguments: tuple[str, ...] = field(default=(), init=False, repr=False)
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
        schema_properties = tuple(
            (argument.name, argument.json_schema()) for argument in self.arguments
        )
        object.__setattr__(self, "_cached_schema_properties", schema_properties)
        cached_schema = _COMPACT_SORTED_JSON_ENCODER.encode(self.schema_payload())
        object.__setattr__(self, "_cached_schema", cached_schema)
        object.__setattr__(self, "_cached_schema_bytes", len(cached_schema.encode("utf-8")))

    @property
    def required_arguments(self) -> tuple[str, ...]:
        return self._cached_required_arguments

    def schema_payload(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                name: schema.copy() for name, schema in self._cached_schema_properties
            },
            "required": list(self.required_arguments),
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


@dataclass(frozen=True)
class ToolRegistryMetrics:
    tool_count: int
    schema_bytes: int
    required_argument_count: int


class ToolRegistry:
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
        self._tool_by_name = {tool.name: tool for tool in self._tools}
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

        requested_names_list: list[str] = []
        seen_names: set[str] = set()
        for name in names:
            normalized_name = name.strip()
            if not normalized_name or normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            requested_names_list.append(normalized_name)
        requested_names = tuple(requested_names_list)
        if requested_names == self._tool_names:
            return self
        cached_selection = self._selection_cache.get(requested_names)
        if cached_selection is not None:
            return cached_selection
        missing_names = [name for name in requested_names if name not in self._tool_by_name]
        if missing_names:
            joined = ", ".join(missing_names)
            raise ToolRegistryError(f"Unknown tool registry entry requested: {joined}")
        selected = [self._tool_by_name[name] for name in requested_names]
        selection = ToolRegistry(
            selected,
            schema_version=self._schema_version,
            toolset_version=self._toolset_version,
            parser=self._parser,
            parser_contract_version=self._parser_contract_version,
        )
        cache_raw_tuple = isinstance(names, tuple) and names != requested_names
        if len(self._selection_cache) >= _SELECTION_CACHE_MAX_SIZE - int(cache_raw_tuple):
            self._selection_cache.clear()
        self._selection_cache[requested_names] = selection
        if cache_raw_tuple:
            self._selection_cache[names] = selection
        return selection

    def as_openai_tools(self) -> list[dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self._tools]

    def as_worker_tool_config(self) -> common_pb2.ToolConfig:
        if self._worker_tool_config_bytes:
            return common_pb2.ToolConfig.FromString(self._worker_tool_config_bytes)
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
    return ToolRegistry(_BUILTIN_AGENTIC_TOOLS)


def built_in_tool_config(names: list[str] | tuple[str, ...] | None = None) -> common_pb2.ToolConfig:
    if names is None or tuple(names) == BUILTIN_AGENTIC_TOOL_NAMES:
        return common_pb2.ToolConfig.FromString(_BUILTIN_TOOL_CONFIG_BYTES)
    registry = _BUILTIN_TOOL_CONFIG_REGISTRY.select(names)
    return registry.as_worker_tool_config()


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


_BUILTIN_TOOL_CONFIG_REGISTRY = ToolRegistry(_BUILTIN_AGENTIC_TOOLS)
_BUILTIN_TOOL_CONFIG_BYTES = (
    _BUILTIN_TOOL_CONFIG_REGISTRY.as_worker_tool_config().SerializeToString()
)


__all__ = [
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
    "built_in_tool_config",
    "built_in_tool_registry",
]
