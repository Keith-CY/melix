from __future__ import annotations

import ast
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from worker.runtime.tool_observation import (
    ToolObservationPolicy,
    ToolObservationRecord,
    normalize_tool_observation,
)
from worker.runtime.tool_registry import ToolDescriptor, ToolRegistry, built_in_tool_registry


class AgenticToolRuntimeError(ValueError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


@dataclass(frozen=True)
class AgenticToolExecutionResult:
    tool_call_id: str
    tool_name: str
    status: str
    observation: ToolObservationRecord
    duration_ms: float = 0.0

    def as_trace_turns(self, *, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            {
                "role": "assistant",
                "tool_call": {
                    "id": self.tool_call_id,
                    "name": self.tool_name,
                    "arguments": dict(arguments),
                },
            },
            {
                "role": "tool",
                "tool_call_id": self.tool_call_id,
                "observation": self.observation.as_agentic_trace_observation(),
            },
        )


@dataclass(frozen=True)
class AgenticToolRun:
    registry_receipt: dict[str, Any]
    tool_calls: tuple[dict[str, Any], ...]
    observations: tuple[dict[str, Any], ...]
    metrics: dict[str, float]
    trace_turns: tuple[dict[str, Any], ...]

    def to_sample_evidence(self) -> dict[str, Any]:
        return {
            "registry": self.registry_receipt,
            "tool_calls": [dict(call) for call in self.tool_calls],
            "observations": [dict(observation) for observation in self.observations],
            "metrics": dict(self.metrics),
        }


class DeterministicAgenticToolRuntime:
    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        fixture_context: dict[str, Any] | None = None,
        observation_policy: ToolObservationPolicy | None = None,
    ) -> None:
        self._registry = registry or built_in_tool_registry()
        self._tool_by_name = {tool.name: tool for tool in self._registry.tools}
        self._fixture_context = dict(fixture_context or {})
        self._observation_policy = observation_policy or ToolObservationPolicy()

    def run_tool_calls(self, tool_calls: list[object] | tuple[object, ...] | None) -> AgenticToolRun:
        normalized_calls = _normalize_tool_calls(tool_calls)
        observations: list[dict[str, Any]] = []
        trace_turns: list[dict[str, Any]] = []
        status_counts = {"completed": 0, "timeout": 0, "failed": 0}
        emitted_bytes = 0
        latency_ms = 0.0
        for call_index, call in enumerate(normalized_calls):
            result = self.execute(
                tool_name=str(call["name"]),
                arguments=dict(call["arguments"]),
                tool_call_id=str(call.get("id") or f"call-{call_index + 1}"),
            )
            latency_ms += result.duration_ms
            status_counts[result.status] += 1
            observation_payload = result.observation.as_agentic_trace_observation()
            observations.append(observation_payload)
            emitted_bytes += result.observation.metrics.emitted_bytes
            trace_turns.extend(result.as_trace_turns(arguments=dict(call["arguments"])))
        metrics = {
            "agentic_tool.call_count": float(len(normalized_calls)),
            "agentic_tool.observation_count": float(len(observations)),
            "agentic_tool.completed_count": float(status_counts["completed"]),
            "agentic_tool.timeout_count": float(status_counts["timeout"]),
            "agentic_tool.failed_count": float(status_counts["failed"]),
            "agentic_tool.observation_emitted_bytes": float(emitted_bytes),
            "agentic_tool.latency_ms": round(latency_ms, 6),
        }
        return AgenticToolRun(
            registry_receipt=self.registry_receipt(),
            tool_calls=tuple(normalized_calls),
            observations=tuple(observations),
            metrics=metrics,
            trace_turns=tuple(trace_turns),
        )

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
    ) -> AgenticToolExecutionResult:
        descriptor = self._tool_by_name.get(tool_name)
        if descriptor is None:
            raise AgenticToolRuntimeError(f"Unknown agentic tool requested: {tool_name}")
        _validate_required_arguments(descriptor, arguments)
        started_at = perf_counter()
        try:
            payload = self._execute_payload(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                arguments=arguments,
            )
        except AgenticToolRuntimeError as exc:
            payload = {"error": str(exc), "_status": "failed"}
            payload.update(exc.details)
        except (SyntaxError, TypeError, ValueError) as exc:
            payload = {"error": str(exc), "_status": "failed"}
        status = str(payload.pop("_status", "completed"))
        observation = normalize_tool_observation(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            observation_kind=descriptor.observation_kind,
            status=status,  # type: ignore[arg-type]
            payload=payload,
            policy=self._observation_policy,
        )
        return AgenticToolExecutionResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status=status,
            observation=observation,
            duration_ms=round(max(0.0, (perf_counter() - started_at) * 1_000.0), 6),
        )

    def registry_receipt(self) -> dict[str, Any]:
        metrics = self._registry.metrics()
        return {
            "schema_version": "melix.agentic_tool_run.v1",
            "registry_schema_version": self._registry.as_worker_tool_config().schema_version,
            "toolset_version": self._registry.as_worker_tool_config().toolset_version,
            "parser": self._registry.as_worker_tool_config().parser,
            "parser_contract_version": self._registry.as_worker_tool_config().parser_contract_version,
            "tools": list(self._registry.names()),
            "tool_count": metrics.tool_count,
            "schema_bytes": metrics.schema_bytes,
            "required_argument_count": metrics.required_argument_count,
        }

    def _execute_payload(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        status_override = _status_override_payload(
            fixture_context=self._fixture_context,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        if status_override is not None:
            return status_override
        if tool_name == "text_search":
            return _text_search_payload(
                arguments=arguments,
                fixture_context=self._fixture_context,
                tool_call_id=tool_call_id,
            )
        if tool_name == "image_search":
            return _image_search_payload(
                arguments=arguments,
                fixture_context=self._fixture_context,
                tool_call_id=tool_call_id,
            )
        if tool_name == "visit":
            return _visit_payload(
                arguments=arguments,
                fixture_context=self._fixture_context,
                tool_call_id=tool_call_id,
            )
        if tool_name == "layout_parse":
            return _layout_parse_payload(
                arguments=arguments,
                fixture_context=self._fixture_context,
                tool_call_id=tool_call_id,
            )
        if tool_name == "image_crop":
            return _image_crop_payload(
                arguments=arguments,
                fixture_context=self._fixture_context,
                tool_call_id=tool_call_id,
            )
        if tool_name == "local_compute":
            return _local_compute_payload(arguments=arguments, tool_call_id=tool_call_id)
        raise AgenticToolRuntimeError(f"Unsupported agentic tool: {tool_name}")


def execute_agentic_tool_calls(
    tool_calls: list[object] | tuple[object, ...] | None,
    *,
    fixture_context: dict[str, Any] | None = None,
    observation_policy: ToolObservationPolicy | None = None,
) -> AgenticToolRun:
    runtime = DeterministicAgenticToolRuntime(
        fixture_context=fixture_context,
        observation_policy=observation_policy,
    )
    return runtime.run_tool_calls(tool_calls)


def _normalize_tool_calls(tool_calls: list[object] | tuple[object, ...] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw_call in enumerate(tool_calls or (), start=1):
        if not isinstance(raw_call, dict):
            raise AgenticToolRuntimeError("Agentic tool calls must be JSON objects.")
        name = str(raw_call.get("name", "")).strip()
        if not name:
            raise AgenticToolRuntimeError("Agentic tool calls must include a name.")
        raw_arguments = raw_call.get("arguments", {})
        if raw_arguments is None:
            raw_arguments = {}
        if not isinstance(raw_arguments, dict):
            raise AgenticToolRuntimeError("Agentic tool call arguments must be an object.")
        normalized.append(
            {
                "id": str(raw_call.get("id", "") or f"call-{index}"),
                "name": name,
                "arguments": dict(raw_arguments),
            }
        )
    return normalized


def _validate_required_arguments(descriptor: ToolDescriptor, arguments: dict[str, Any]) -> None:
    missing = [name for name in descriptor.required_arguments if str(arguments.get(name, "")).strip() == ""]
    if missing:
        joined = ", ".join(missing)
        raise AgenticToolRuntimeError(f"Missing required arguments for {descriptor.name}: {joined}")


def _status_override_payload(
    *,
    fixture_context: dict[str, Any],
    tool_name: str,
    tool_call_id: str,
) -> dict[str, Any] | None:
    overrides = _context_mapping(fixture_context, "tool_status_overrides")
    raw_override = overrides.get(tool_call_id)
    if raw_override is None:
        raw_override = overrides.get(tool_name)
    if raw_override is None:
        raw_override = overrides.get("*")
    if raw_override is None:
        return None
    if isinstance(raw_override, str):
        override = {"status": raw_override}
    elif isinstance(raw_override, dict):
        override = dict(raw_override)
    else:
        raise AgenticToolRuntimeError("Agentic tool status override must be a string or JSON object.")

    raw_status = _optional_untrusted_text(
        override.get("status", ""),
        field="tool_status_overrides.status",
        source_type="tool_status_override",
        source_id=tool_name,
    ).lower()
    message = _optional_untrusted_text(
        override.get("message", ""),
        field="tool_status_overrides.message",
        source_type="tool_status_override",
        source_id=tool_name,
    )
    failure_stage = _optional_untrusted_text(
        override.get("failure_stage", ""),
        field="tool_status_overrides.failure_stage",
        source_type="tool_status_override",
        source_id=tool_name,
    )
    if raw_status == "timeout":
        return {
            "text": message or f"{tool_name} timed out before producing a result.",
            "failure_stage": failure_stage or "tool_timeout",
            "_status": "timeout",
        }
    if raw_status in ("cancel", "cancelled", "canceled"):
        return {
            "error": message or f"{tool_name} was cancelled before producing a result.",
            "failure_stage": failure_stage or "cancelled",
            "cancelled": True,
            "_status": "failed",
        }
    if raw_status == "failed":
        return {
            "error": message or f"{tool_name} failed before producing a result.",
            "failure_stage": failure_stage or "tool_execution",
            "_status": "failed",
        }
    raise AgenticToolRuntimeError(f"Unsupported agentic tool status override: {raw_status or '<empty>'}")


def _text_search_payload(
    *,
    arguments: dict[str, Any],
    fixture_context: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    query = _tool_argument_text(arguments, "query", tool_call_id=tool_call_id)
    max_results = _positive_int(arguments.get("max_results"), default=3)
    corpus_ref = _optional_tool_argument_text(arguments, "corpus_ref", tool_call_id=tool_call_id) or "default"
    corpus = _context_list(fixture_context, "text_corpus", corpus_ref)
    lowered_query = query.lower()
    results: list[dict[str, str]] = []
    for index, item in enumerate(corpus, start=1):
        source_id = _source_id(item.get("id"), default=f"doc-{index}")
        text = _optional_untrusted_text(
            item.get("text", ""),
            field="text_corpus.text",
            source_type="retrieved_document",
            source_id=source_id,
            strip=False,
        )
        if lowered_query in text.lower():
            results.append({"id": source_id, "text": text})
        if len(results) >= max_results:
            break
    return {"query": query, "corpus_ref": corpus_ref, "results": results, "result_count": len(results)}


def _image_search_payload(
    *,
    arguments: dict[str, Any],
    fixture_context: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    query = _tool_argument_text(arguments, "query", tool_call_id=tool_call_id)
    max_results = _positive_int(arguments.get("max_results"), default=3)
    corpus_ref = _optional_tool_argument_text(arguments, "corpus_ref", tool_call_id=tool_call_id) or "default"
    corpus = _context_list(fixture_context, "image_corpus", corpus_ref)
    lowered_query = query.lower()
    results: list[dict[str, str]] = []
    for index, item in enumerate(corpus, start=1):
        source_id = _source_id(item.get("id"), default=f"image-{index}")
        caption = _optional_untrusted_text(
            item.get("caption", ""),
            field="image_corpus.caption",
            source_type="retrieved_image",
            source_id=source_id,
            strip=False,
        )
        if lowered_query in caption.lower():
            media_ref = _optional_untrusted_text(
                item.get("media_ref", item.get("uri", "")),
                field="image_corpus.media_ref",
                source_type="retrieved_image",
                source_id=source_id,
            )
            results.append({"id": source_id, "media_ref": media_ref, "caption": caption})
        if len(results) >= max_results:
            break
    return {"query": query, "corpus_ref": corpus_ref, "results": results, "result_count": len(results)}


def _visit_payload(
    *,
    arguments: dict[str, Any],
    fixture_context: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    url = _tool_argument_text(arguments, "url", tool_call_id=tool_call_id)
    pages = _context_mapping(fixture_context, "pages")
    page = pages.get(url)
    if isinstance(page, dict):
        return {
            "url": url,
            "title": _optional_untrusted_text(
                page.get("title", ""),
                field="pages.title",
                source_type="retrieved_page",
                source_id=url,
                strip=False,
            ),
            "text": _optional_untrusted_text(
                page.get("text", ""),
                field="pages.text",
                source_type="retrieved_page",
                source_id=url,
                strip=False,
            ),
        }
    if page is None:
        return {"url": url, "text": "", "found": False}
    return {
        "url": url,
        "text": _optional_untrusted_text(
            page,
            field="pages.text",
            source_type="retrieved_page",
            source_id=url,
            strip=False,
        ),
        "found": True,
    }


def _layout_parse_payload(
    *,
    arguments: dict[str, Any],
    fixture_context: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    media_ref = _tool_argument_text(arguments, "media_ref", tool_call_id=tool_call_id)
    layouts = _context_mapping(fixture_context, "layouts")
    layout = layouts.get(media_ref, [])
    if not isinstance(layout, list):
        raise _invalid_untrusted_value_type(
            field="layouts",
            source_type="retrieved_layout",
            source_id=media_ref,
            expected_type="list",
            actual_type=type(layout).__name__,
        )
    detail_level = (
        _optional_tool_argument_text(arguments, "detail_level", tool_call_id=tool_call_id)
        or "blocks"
    )
    return {
        "media_ref": media_ref,
        "detail_level": detail_level,
        "elements": layout,
        "element_count": len(layout),
    }


def _image_crop_payload(
    *,
    arguments: dict[str, Any],
    fixture_context: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    media_ref = _tool_argument_text(arguments, "media_ref", tool_call_id=tool_call_id)
    region = _tool_argument_text(arguments, "region", tool_call_id=tool_call_id)
    crops = _context_mapping(fixture_context, "crops")
    crop_key = f"{media_ref}#{region}"
    crop = crops.get(crop_key, crops.get(media_ref, {}))
    if isinstance(crop, dict):
        payload = dict(crop)
    else:
        payload = {
            "text": _optional_untrusted_text(
                crop,
                field="crops.text",
                source_type="retrieved_crop",
                source_id=crop_key if crop_key in crops else media_ref,
                strip=False,
            )
        }
    payload.update({"media_ref": media_ref, "region": region})
    purpose = _optional_tool_argument_text(arguments, "purpose", tool_call_id=tool_call_id)
    if purpose:
        payload["purpose"] = purpose
    return payload


def _local_compute_payload(*, arguments: dict[str, Any], tool_call_id: str) -> dict[str, Any]:
    code = _tool_argument_text(arguments, "code", tool_call_id=tool_call_id)
    if code == "timeout":
        return {"text": "local_compute timed out before producing a result.", "_status": "timeout"}
    result = _safe_arithmetic_eval(code)
    return {"code": code, "result": result}


def _safe_arithmetic_eval(expression: str) -> int | float:
    tree = ast.parse(expression, mode="eval")
    return _eval_arithmetic_node(tree.body)


def _eval_arithmetic_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _eval_arithmetic_node(node.left)
        right = _eval_arithmetic_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise AgenticToolRuntimeError("local_compute division by zero.")
        return left / right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_arithmetic_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise AgenticToolRuntimeError("local_compute only supports deterministic arithmetic expressions.")


def _context_mapping(fixture_context: dict[str, Any], key: str) -> dict[str, Any]:
    value = fixture_context.get(key, {})
    return value if isinstance(value, dict) else {}


def _context_list(fixture_context: dict[str, Any], key: str, corpus_ref: str) -> list[dict[str, Any]]:
    if key == "image_corpus":
        item_source_type = "retrieved_image"
        item_source_id_prefix = "image"
    elif key == "text_corpus":
        item_source_type = "retrieved_document"
        item_source_id_prefix = "doc"
    else:
        raise AgenticToolRuntimeError(f"Unsupported retrieved corpus key: {key}.")

    value = fixture_context.get(key, [])
    if isinstance(value, dict):
        value = value.get(corpus_ref, [])
    if not isinstance(value, list):
        raise _invalid_untrusted_value_type(
            field=key,
            source_type="retrieved_corpus",
            source_id=corpus_ref,
            expected_type="list",
            actual_type=type(value).__name__,
        )

    context_items: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise _invalid_untrusted_value_type(
                field=f"{key}.item",
                source_type=item_source_type,
                source_id=f"{item_source_id_prefix}-{index}",
                expected_type="object",
                actual_type=type(item).__name__,
            )
        context_items.append(item)
    return context_items


def _tool_argument_text(arguments: dict[str, Any], name: str, *, tool_call_id: str) -> str:
    return _optional_untrusted_text(
        arguments.get(name, ""),
        field=f"arguments.{name}",
        source_type="tool_argument",
        source_id=tool_call_id,
    )


def _optional_tool_argument_text(arguments: dict[str, Any], name: str, *, tool_call_id: str) -> str:
    return _optional_untrusted_text(
        arguments.get(name, ""),
        field=f"arguments.{name}",
        source_type="tool_argument",
        source_id=tool_call_id,
    )


def _optional_untrusted_text(
    value: Any,
    *,
    field: str,
    source_type: str,
    source_id: str,
    strip: bool = True,
) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise _invalid_untrusted_value_type(
            field=field,
            source_type=source_type,
            source_id=source_id,
            expected_type="str",
            actual_type=type(value).__name__,
        )
    return value.strip() if strip else value


def _invalid_untrusted_value_type(
    *,
    field: str,
    source_type: str,
    source_id: str,
    expected_type: str,
    actual_type: str,
) -> AgenticToolRuntimeError:
    return AgenticToolRuntimeError(
        f"Invalid untrusted value type for {field}: expected {expected_type}, got {actual_type}.",
        details={
            "reason": "invalid_untrusted_input_type",
            "field": field,
            "source_type": source_type,
            "source_id": source_id,
            "expected_type": expected_type,
            "actual_type": actual_type,
            "corrective_action": "Provide this untrusted value as a JSON string.",
        },
    )


def _source_id(value: Any, *, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


__all__ = [
    "AgenticToolExecutionResult",
    "AgenticToolRun",
    "AgenticToolRuntimeError",
    "DeterministicAgenticToolRuntime",
    "execute_agentic_tool_calls",
]
