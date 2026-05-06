from __future__ import annotations

from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamFragment:
    text: str = ""
    raw_text: str | None = None


@dataclass(frozen=True)
class AssembledToolCall:
    call_id: str
    tool_name: str
    arguments_json_fragment: str
    fragment_index: int
    parser_mode: str
    complete: bool = True


@dataclass(frozen=True)
class AssemblyDelta:
    content_text: str = ""
    reasoning_text: str = ""
    raw_text: str = ""
    tool_call: AssembledToolCall | None = None


@dataclass(frozen=True)
class AssemblyCompletion:
    assistant_text: str
    reasoning_text: str
    raw_text: str
    metrics: dict[str, int | str]


class RequestStreamAssembler:
    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"
    _TOOL_OPEN = "<tool_call>"
    _TOOL_CLOSE = "</tool_call>"
    _THINK_PREFIXES = tuple("<think>"[:index] for index in range(1, len("<think>")))
    _TOOL_PREFIXES = tuple("<tool_call>"[:index] for index in range(1, len("<tool_call>")))

    def __init__(
        self,
        request_id: str,
        reasoning_enabled: bool,
        structured_output_mode: str = "",
        tool_parser_mode: str = "",
    ) -> None:
        self._request_id = request_id
        self._reasoning_enabled = reasoning_enabled
        self._structured_output_mode = structured_output_mode.strip().lower()
        self._tool_parser_mode = tool_parser_mode.strip().lower()
        self._tool_parsing_enabled_value = bool(self._tool_parser_mode)
        self._is_json_structured_output_value = self._structured_output_mode in {
            "json_object",
            "json_schema",
        }
        self._is_json_only_structured_output_value = (
            self._is_json_structured_output_value and not self._tool_parsing_enabled_value
        )
        self._structural_tag_prefixes_value = self._THINK_PREFIXES
        if self._tool_parsing_enabled_value:
            self._request_context_mode_value = "tool_parser"
            self._structural_tag_prefixes_value = self._THINK_PREFIXES + self._TOOL_PREFIXES
        elif self._is_json_structured_output_value:
            self._request_context_mode_value = "structured_json"
        elif self._reasoning_enabled:
            self._request_context_mode_value = "reasoning_only"
        else:
            self._request_context_mode_value = "plain"
        self._raw_seen = ""
        self._buffer = ""
        self._json_started = False
        self._assistant_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tool_fragment_index = 0
        self._emitted_tool_keys: set[tuple[str, str]] = set()
        self._metrics: dict[str, int | str] = {
            "parser_state_bleed_count": 0,
            "duplicate_tool_delta_count": 0,
            "reasoning_leak_count": 0,
            "malformed_tool_fragment_count": 0,
            "malformed_reasoning_count": 0,
            "non_monotonic_stream_count": 0,
            "suppressed_reasoning_count": 0,
            "stream_prefix_hold_chars": 0,
            "stream_short_reply_flush_count": 0,
            "stream_parser_request_context_mode": self._request_context_mode,
            "tool_call_markup_leak_count": 0,
            "reasoning_channel_recovery_count": 0,
        }

    def accept(self, fragment: StreamFragment) -> list[AssemblyDelta]:
        raw = fragment.raw_text if fragment.raw_text is not None else fragment.text
        if not raw:
            return []

        delta = self._unseen_delta(raw)
        if not delta:
            return []

        if self._is_json_only_structured_output:
            return self._accept_json_structured_output(delta)

        self._buffer += delta
        return self._drain_buffer(final=False)

    def completed(self) -> AssemblyCompletion:
        if self._is_json_only_structured_output:
            if not self._json_started:
                self._metrics["reasoning_leak_count"] += int("<think" in self._buffer)
                self._buffer = ""
        else:
            self._drain_buffer(final=True)
        return AssemblyCompletion(
            assistant_text="".join(self._assistant_parts),
            reasoning_text="".join(self._reasoning_parts),
            raw_text=self._raw_seen,
            metrics=dict(self._metrics),
        )

    @property
    def _is_json_structured_output(self) -> bool:
        return self._is_json_structured_output_value

    @property
    def _is_json_only_structured_output(self) -> bool:
        return self._is_json_only_structured_output_value

    @property
    def _tool_parsing_enabled(self) -> bool:
        return self._tool_parsing_enabled_value

    @property
    def _request_context_mode(self) -> str:
        return self._request_context_mode_value

    @property
    def _structural_tag_prefixes(self) -> tuple[str, ...]:
        return self._structural_tag_prefixes_value

    def _unseen_delta(self, raw: str) -> str:
        if raw.startswith(self._raw_seen):
            delta = raw[len(self._raw_seen) :]
            self._raw_seen = raw
            return delta

        self._metrics["non_monotonic_stream_count"] += 1
        logger.warning(
            "Non-monotonic stream fragment for request_id=%s; seen_chars=%d raw_chars=%d",
            self._request_id,
            len(self._raw_seen),
            len(raw),
        )
        # Some adapters reset to a shorter raw fragment after a transport
        # retry. Emit the full reset fragment as recoverable content and make
        # the compatibility loss visible through metrics/logs.
        self._raw_seen += raw
        return raw

    def _accept_json_structured_output(self, delta: str) -> list[AssemblyDelta]:
        self._buffer += delta
        if not self._json_started:
            json_start = self._first_json_delimiter(self._buffer)
            if json_start is None:
                return []
            self._buffer = self._buffer[json_start:]
            self._json_started = True

        if not self._buffer:
            return []

        content = self._buffer
        self._buffer = ""
        if "<think" in content:
            self._metrics["reasoning_leak_count"] += 1
        self._assistant_parts.append(content)
        return [AssemblyDelta(content_text=content, raw_text=delta)]

    def _drain_buffer(self, final: bool) -> list[AssemblyDelta]:
        deltas: list[AssemblyDelta] = []
        while self._buffer:
            next_tag = self._next_structural_tag()
            if next_tag is None:
                if not final:
                    held_suffix = self._partial_structural_tag_suffix()
                    if held_suffix:
                        self._record_prefix_hold(held_suffix)
                        visible_prefix = self._buffer[: -len(held_suffix)]
                        if visible_prefix:
                            self._buffer = held_suffix
                            if len(visible_prefix) <= 8:
                                self._metrics["stream_short_reply_flush_count"] += 1
                            deltas.append(self._content_delta(visible_prefix))
                            continue
                        break
                content = self._buffer
                self._buffer = ""
                deltas.append(self._content_delta(content))
                continue

            tag, offset = next_tag
            if offset > 0:
                content = self._buffer[:offset]
                self._buffer = self._buffer[offset:]
                deltas.append(self._content_delta(content))
                continue

            if tag == self._THINK_OPEN:
                close_index = self._buffer.find(self._THINK_CLOSE, len(self._THINK_OPEN))
                if close_index < 0:
                    if final:
                        self._metrics["malformed_reasoning_count"] += 1
                        self._metrics["reasoning_channel_recovery_count"] += 1
                        self._buffer = ""
                    break
                body = self._buffer[len(self._THINK_OPEN) : close_index]
                self._buffer = self._buffer[close_index + len(self._THINK_CLOSE) :]
                # Parse reasoning tags even when reasoning is disabled so
                # hidden preambles never fall through as public content.
                if self._reasoning_enabled:
                    self._reasoning_parts.append(body)
                    deltas.append(AssemblyDelta(reasoning_text=body, raw_text=body))
                else:
                    self._metrics["suppressed_reasoning_count"] += 1
                continue

            if tag == self._TOOL_OPEN:
                close_index = self._buffer.find(self._TOOL_CLOSE, len(self._TOOL_OPEN))
                if close_index < 0:
                    if final:
                        self._metrics["malformed_tool_fragment_count"] += 1
                        self._buffer = ""
                    break
                body = self._buffer[len(self._TOOL_OPEN) : close_index]
                self._buffer = self._buffer[close_index + len(self._TOOL_CLOSE) :]
                tool_delta = self._tool_delta(body)
                if tool_delta is not None:
                    deltas.append(AssemblyDelta(raw_text=body, tool_call=tool_delta))
                continue

            break
        return deltas

    def _next_structural_tag(self) -> tuple[str, int] | None:
        think_index = self._buffer.find(self._THINK_OPEN)
        if not self._tool_parsing_enabled:
            return None if think_index < 0 else (self._THINK_OPEN, think_index)

        tool_index = self._buffer.find(self._TOOL_OPEN)
        if think_index < 0:
            return None if tool_index < 0 else (self._TOOL_OPEN, tool_index)
        if tool_index < 0 or think_index <= tool_index:
            return (self._THINK_OPEN, think_index)
        return (self._TOOL_OPEN, tool_index)

    def _has_partial_structural_tag_suffix(self) -> bool:
        return self._buffer.endswith(self._structural_tag_prefixes)

    def _partial_structural_tag_suffix(self) -> str:
        for prefix in reversed(self._structural_tag_prefixes):
            if self._buffer.endswith(prefix):
                return prefix
        return ""

    def _record_prefix_hold(self, suffix: str) -> None:
        self._metrics["stream_prefix_hold_chars"] = max(
            self._metrics["stream_prefix_hold_chars"],
            len(suffix),
        )

    def _content_delta(self, content: str) -> AssemblyDelta:
        if self._tool_parsing_enabled and "<tool_call" in content:
            self._metrics["tool_call_markup_leak_count"] += 1
        self._assistant_parts.append(content)
        return AssemblyDelta(content_text=content, raw_text=content)

    def _tool_delta(self, body: str) -> AssembledToolCall | None:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._metrics["malformed_tool_fragment_count"] += 1
            return None

        if not isinstance(payload, dict):
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        name = str(payload.get("name") or payload.get("tool_name") or "").strip()
        if not name:
            self._metrics["malformed_tool_fragment_count"] += 1
            return None

        arguments = payload.get("arguments", {})
        call_id = str(payload.get("id") or payload.get("call_id") or "").strip()
        arguments_fragment = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        # Prefer model-provided call ids for dedupe so identical repeated calls
        # can be emitted. Legacy call-id-less fragments keep content dedupe to
        # suppress non-monotonic replay from older parsers.
        key = ("call_id", call_id) if call_id else ("legacy", f"{name}\0{arguments_fragment}")
        if key in self._emitted_tool_keys:
            self._metrics["duplicate_tool_delta_count"] += 1
            return None
        self._emitted_tool_keys.add(key)

        self._tool_fragment_index += 1
        return AssembledToolCall(
            call_id=call_id or f"{self._request_id}-tool-{self._tool_fragment_index}",
            tool_name=name,
            arguments_json_fragment=arguments_fragment,
            fragment_index=self._tool_fragment_index,
            parser_mode=self._tool_parser_mode,
        )

    def _first_json_delimiter(self, text: str) -> int | None:
        object_index = text.find("{")
        array_index = text.find("[")
        if object_index < 0:
            return None if array_index < 0 else array_index
        if array_index < 0 or object_index <= array_index:
            return object_index
        return array_index
