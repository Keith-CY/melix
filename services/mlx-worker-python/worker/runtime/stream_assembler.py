from __future__ import annotations

from dataclasses import dataclass
import json


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
    metrics: dict[str, int]


class RequestStreamAssembler:
    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"
    _TOOL_OPEN = "<tool_call>"
    _TOOL_CLOSE = "</tool_call>"

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
        self._raw_seen = ""
        self._buffer = ""
        self._json_started = False
        self._assistant_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tool_fragment_index = 0
        self._emitted_tool_keys: set[tuple[str, str]] = set()
        self._metrics: dict[str, int] = {
            "parser_state_bleed_count": 0,
            "duplicate_tool_delta_count": 0,
            "reasoning_leak_count": 0,
            "malformed_tool_fragment_count": 0,
        }

    def accept(self, fragment: StreamFragment) -> list[AssemblyDelta]:
        raw = fragment.raw_text if fragment.raw_text is not None else fragment.text
        if not raw:
            return []

        delta = self._unseen_delta(raw)
        if not delta:
            return []

        if self._is_json_structured_output:
            return self._accept_json_structured_output(delta)

        self._buffer += delta
        return self._drain_buffer(final=False)

    def completed(self) -> AssemblyCompletion:
        if self._is_json_structured_output:
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
        return self._structured_output_mode in {"json", "json_object", "json_schema"}

    @property
    def _tool_parsing_enabled(self) -> bool:
        return bool(self._tool_parser_mode) and not self._is_json_structured_output

    def _unseen_delta(self, raw: str) -> str:
        if raw.startswith(self._raw_seen):
            delta = raw[len(self._raw_seen) :]
            self._raw_seen = raw
            return delta

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
                if not final and self._has_partial_structural_tag_suffix():
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
                        self._metrics["malformed_tool_fragment_count"] += 1
                        self._buffer = ""
                    break
                body = self._buffer[len(self._THINK_OPEN) : close_index]
                self._buffer = self._buffer[close_index + len(self._THINK_CLOSE) :]
                if self._reasoning_enabled:
                    self._reasoning_parts.append(body)
                    deltas.append(AssemblyDelta(reasoning_text=body, raw_text=body))
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
        candidates: list[tuple[str, int]] = []
        think_index = self._buffer.find(self._THINK_OPEN)
        if think_index >= 0:
            candidates.append((self._THINK_OPEN, think_index))
        if self._tool_parsing_enabled:
            tool_index = self._buffer.find(self._TOOL_OPEN)
            if tool_index >= 0:
                candidates.append((self._TOOL_OPEN, tool_index))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[1])

    def _has_partial_structural_tag_suffix(self) -> bool:
        tags = [self._THINK_OPEN]
        if self._tool_parsing_enabled:
            tags.append(self._TOOL_OPEN)
        return any(
            self._buffer.endswith(tag[:prefix_length])
            for tag in tags
            for prefix_length in range(1, len(tag))
        )

    def _content_delta(self, content: str) -> AssemblyDelta:
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
        arguments_fragment = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        key = (name, arguments_fragment)
        if key in self._emitted_tool_keys:
            self._metrics["duplicate_tool_delta_count"] += 1
            return None
        self._emitted_tool_keys.add(key)

        self._tool_fragment_index += 1
        return AssembledToolCall(
            call_id=f"{self._request_id}-tool-{self._tool_fragment_index}",
            tool_name=name,
            arguments_json_fragment=arguments_fragment,
            fragment_index=self._tool_fragment_index,
            parser_mode=self._tool_parser_mode,
        )

    def _first_json_delimiter(self, text: str) -> int | None:
        indexes = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not indexes:
            return None
        return min(indexes)
