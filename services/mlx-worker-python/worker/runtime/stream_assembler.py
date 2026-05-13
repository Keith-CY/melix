from __future__ import annotations

import codecs
from dataclasses import dataclass, replace
from functools import lru_cache
import json
import logging
import re

logger = logging.getLogger(__name__)
_UTF8_INCREMENTAL_DECODER = codecs.getincrementaldecoder("utf-8")
_COMPACT_SORTED_JSON_ENCODER = json.JSONEncoder(separators=(",", ":"), sort_keys=True)


@lru_cache(maxsize=32)
def _cached_effective_parser_config_json(
    reasoning_enabled: bool,
    request_context_mode: str,
    structured_output_mode: str,
    tool_parser_mode: str,
) -> str:
    return _COMPACT_SORTED_JSON_ENCODER.encode(
        {
            "reasoning_enabled": reasoning_enabled,
            "request_context_mode": request_context_mode,
            "structured_output_mode": structured_output_mode,
            "tool_parser_mode": tool_parser_mode,
        },
    )


class StreamFragment:
    __slots__ = (
        "text",
        "raw_text",
        "token_ids",
        "token_logprobs",
        "token_bytes",
        "parser_observation",
    )

    def __init__(
        self,
        text: str = "",
        raw_text: str | None = None,
        token_ids: tuple[int, ...] = (),
        token_logprobs: tuple[float, ...] = (),
        token_bytes: bytes | None = None,
        parser_observation: str = "",
    ) -> None:
        self.text = text
        self.raw_text = raw_text
        self.token_ids = token_ids
        self.token_logprobs = token_logprobs
        self.token_bytes = token_bytes
        self.parser_observation = parser_observation


@dataclass(frozen=True, slots=True)
class AssembledToolCall:
    call_id: str
    tool_name: str
    arguments_json_fragment: str
    fragment_index: int
    parser_mode: str
    complete: bool = True


@dataclass(frozen=True, slots=True)
class AssemblyDelta:
    content_text: str = ""
    reasoning_text: str = ""
    raw_text: str = ""
    tool_call: AssembledToolCall | None = None
    parser_observation: str = ""


@dataclass(frozen=True, slots=True)
class AssemblyCompletion:
    assistant_text: str
    reasoning_text: str
    raw_text: str
    metrics: dict[str, int | str]


class RequestStreamAssembler:
    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"
    _PIPE_REASONING_OPEN = "<|channel>thought"
    _PIPE_REASONING_CLOSE = "<channel|>"
    _TOOL_OPEN = "<tool_call>"
    _TOOL_CLOSE = "</tool_call>"
    _PIPE_TOOL_OPEN = "<|tool_call>"
    _PIPE_TOOL_CLOSE = "<tool_call|>"
    _REASONING_OPEN_TAGS = (_THINK_OPEN, _PIPE_REASONING_OPEN)
    _TOOL_OPEN_TAGS = (_TOOL_OPEN, _PIPE_TOOL_OPEN)
    _TOOL_PARSER_STRUCTURAL_OPEN_TAGS = _REASONING_OPEN_TAGS + _TOOL_OPEN_TAGS
    _THINK_PREFIXES = tuple("<think>"[:index] for index in range(1, len("<think>")))
    _PIPE_REASONING_PREFIXES = tuple(
        "<|channel>thought"[:index] for index in range(1, len("<|channel>thought"))
    )
    _TOOL_PREFIXES = tuple("<tool_call>"[:index] for index in range(1, len("<tool_call>")))
    _PIPE_TOOL_PREFIXES = tuple(
        "<|tool_call>"[:index] for index in range(1, len("<|tool_call>"))
    )
    _REASONING_LEAK_PREFIXES = ("<think", "<|channel")
    _REASONING_PREFIXES = _THINK_PREFIXES + _PIPE_REASONING_PREFIXES
    _THINK_PREFIXES_REVERSED = tuple(reversed(_THINK_PREFIXES))
    _PIPE_REASONING_PREFIXES_REVERSED = tuple(reversed(_PIPE_REASONING_PREFIXES))
    _REASONING_PREFIXES_REVERSED = tuple(reversed(_REASONING_PREFIXES))
    _TOOL_PREFIXES_REVERSED = tuple(reversed(_TOOL_PREFIXES))
    _PIPE_TOOL_PREFIXES_REVERSED = tuple(reversed(_PIPE_TOOL_PREFIXES))
    _VISIBLE_TAIL_MARKERS = ("\nFinal answer", "\nFinal:", "\nAnswer:", "\nAssistant:", "\nResult:")
    _PIPE_CALL_RE = re.compile(
        r"^\s*call:(?P<name>[A-Za-z0-9_.:/-]+)\s*(?P<args>\{.*\}|\(\s*\))\s*$",
        re.DOTALL,
    )

    def __init__(
        self,
        request_id: str,
        reasoning_enabled: bool,
        structured_output_mode: str = "",
        tool_parser_mode: str = "",
        allowed_tool_names: tuple[str, ...] | None = None,
    ) -> None:
        self._request_id = request_id
        self._reasoning_enabled = reasoning_enabled
        self._structured_output_mode = structured_output_mode.strip().lower()
        self._tool_parser_mode = tool_parser_mode.strip().lower()
        if allowed_tool_names:
            self._allowed_tool_names = tuple(
                dict.fromkeys(name.strip() for name in allowed_tool_names if name.strip())
            )
            self._allowed_tool_name_set = set(self._allowed_tool_names)
            self._allowed_tool_names_by_casefold = {
                name.casefold(): name for name in self._allowed_tool_names
            }
            # Longest-first matching keeps a declared tool such as
            # "terminal.execute" from being normalized to "terminal".
            self._allowed_tool_names_by_prefix = tuple(
                sorted(self._allowed_tool_names, key=len, reverse=True)
            )
        else:
            self._allowed_tool_names = ()
            self._allowed_tool_name_set = frozenset()
            self._allowed_tool_names_by_casefold = {}
            self._allowed_tool_names_by_prefix = ()
        self._tool_parsing_enabled_value = bool(self._tool_parser_mode)
        self._is_json_structured_output_value = self._structured_output_mode in {
            "json_object",
            "json_schema",
        }
        self._is_json_only_structured_output_value = (
            self._is_json_structured_output_value and not self._tool_parsing_enabled_value
        )
        self._structural_tag_prefixes_value = self._REASONING_PREFIXES
        self._structural_tag_prefixes_reversed_value = self._REASONING_PREFIXES_REVERSED
        self._structural_open_tags_value = self._REASONING_OPEN_TAGS
        if self._tool_parsing_enabled_value:
            self._request_context_mode_value = "tool_parser"
            self._structural_open_tags_value = self._TOOL_PARSER_STRUCTURAL_OPEN_TAGS
            self._structural_tag_prefixes_value = (
                self._REASONING_PREFIXES + self._TOOL_PREFIXES + self._PIPE_TOOL_PREFIXES
            )
            self._structural_tag_prefixes_reversed_value = (
                self._PIPE_TOOL_PREFIXES_REVERSED
                + self._TOOL_PREFIXES_REVERSED
                + self._REASONING_PREFIXES_REVERSED
            )
        elif self._is_json_structured_output_value:
            self._request_context_mode_value = "structured_json"
        elif self._reasoning_enabled:
            self._request_context_mode_value = "reasoning_only"
        else:
            self._request_context_mode_value = "plain"
        self._raw_seen = ""
        self._buffer = ""
        self._pending_token_bytes = b""
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
            "generated_token_count": 0,
            "logprob_entry_count": 0,
            "token_logprob_mismatch_count": 0,
            "stream_interval_delta_flush_count": 0,
            "byte_fallback_merge_count": 0,
            "byte_fallback_decode_error_count": 0,
            "empty_thinking_sentinel_count": 0,
            "reasoning_parser_bypassed_count": 0,
            "tool_call_name_normalized_count": 0,
            "unknown_tool_delta_count": 0,
        }

    def accept(self, fragment: StreamFragment) -> list[AssemblyDelta]:
        token_count = 0
        byte_delta = None
        token_bytes = fragment.token_bytes
        if fragment.token_ids or fragment.token_logprobs or token_bytes is not None:
            token_count = self._record_token_metadata(fragment)
            if token_bytes is not None:
                byte_delta = self._token_byte_delta(token_bytes)
        raw = fragment.raw_text if fragment.raw_text is not None else fragment.text
        if byte_delta is not None:
            if not byte_delta:
                return []
            delta = byte_delta
            self._raw_seen += byte_delta
        elif raw:
            delta = self._unseen_delta(raw)
        else:
            return []

        if not delta:
            return []

        if (
            not self._is_json_only_structured_output_value
            and not self._buffer
            and token_count <= 1
            and not fragment.parser_observation
            and "<" not in delta
        ):
            self._assistant_parts.append(delta)
            return [AssemblyDelta(content_text=delta, raw_text=delta)]

        if self._is_json_only_structured_output_value:
            deltas = self._accept_json_structured_output(delta)
        else:
            self._buffer += delta
            deltas = self._drain_buffer(final=False)
        if token_count > 1 and deltas:
            self._metrics["stream_interval_delta_flush_count"] += 1
        if fragment.parser_observation:
            return self._annotate_deltas(deltas, fragment.parser_observation)
        return deltas

    def completed(self) -> AssemblyCompletion:
        if self._pending_token_bytes:
            self._metrics["byte_fallback_decode_error_count"] += 1
            self._buffer += self._pending_token_bytes.decode("utf-8", errors="replace")
            self._pending_token_bytes = b""
        if self._is_json_only_structured_output:
            if not self._json_started:
                self._metrics["reasoning_leak_count"] += int(
                    self._contains_reasoning_leak_marker(self._buffer)
                )
                self._buffer = ""
        else:
            self._drain_buffer(final=True)
        metrics = dict(self._metrics)
        metrics["effective_parser_config_json"] = self._effective_parser_config_json()
        return AssemblyCompletion(
            assistant_text="".join(self._assistant_parts),
            reasoning_text="".join(self._reasoning_parts),
            raw_text=self._raw_seen,
            metrics=metrics,
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

    @property
    def _structural_tag_prefixes_reversed(self) -> tuple[str, ...]:
        return self._structural_tag_prefixes_reversed_value

    @property
    def _structural_open_tags(self) -> tuple[str, ...]:
        return self._structural_open_tags_value

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

    def _record_token_metadata(self, fragment: StreamFragment) -> int:
        if (
            fragment.token_bytes is None
            and not fragment.token_ids
            and not fragment.token_logprobs
        ):
            return 0
        token_count = len(fragment.token_ids)
        logprob_count = len(fragment.token_logprobs)
        if token_count == 0 and logprob_count > 0:
            token_count = logprob_count
        if token_count == 0 and fragment.token_bytes is not None:
            token_count = 1

        self._metrics["generated_token_count"] += token_count
        self._metrics["logprob_entry_count"] += logprob_count
        if fragment.token_ids and fragment.token_logprobs and token_count != logprob_count:
            self._metrics["token_logprob_mismatch_count"] += 1
        return token_count

    def _token_byte_delta(self, token_bytes: bytes | None) -> str | None:
        if token_bytes is None:
            return None
        had_pending = bool(self._pending_token_bytes)
        if not had_pending:
            try:
                return token_bytes.decode("utf-8")
            except UnicodeDecodeError:
                pass
        self._pending_token_bytes += token_bytes
        decoder = _UTF8_INCREMENTAL_DECODER()
        try:
            decoded = decoder.decode(self._pending_token_bytes, final=False)
        except UnicodeDecodeError:
            self._metrics["byte_fallback_decode_error_count"] += 1
            decoded = self._pending_token_bytes.decode("utf-8", errors="replace")
            self._pending_token_bytes = b""
            return decoded

        buffered, _ = decoder.getstate()
        if buffered:
            self._pending_token_bytes = bytes(buffered)
            if not decoded:
                return ""
        else:
            self._pending_token_bytes = b""
        if had_pending:
            self._metrics["byte_fallback_merge_count"] += 1
        return decoded

    def _effective_parser_config_json(self) -> str:
        return _cached_effective_parser_config_json(
            self._reasoning_enabled,
            self._request_context_mode_value,
            self._structured_output_mode,
            self._tool_parser_mode,
        )

    def _annotate_deltas(
        self,
        deltas: list[AssemblyDelta],
        parser_observation: str,
    ) -> list[AssemblyDelta]:
        if not parser_observation:
            return deltas
        return [
            replace(delta, parser_observation=parser_observation)
            if delta.content_text or delta.reasoning_text or delta.tool_call is not None
            else delta
            for delta in deltas
        ]

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
        if self._contains_reasoning_leak_marker(content):
            self._metrics["reasoning_leak_count"] += 1
        self._assistant_parts.append(content)
        return [AssemblyDelta(content_text=content, raw_text=delta)]

    def _drain_buffer(self, final: bool) -> list[AssemblyDelta]:
        deltas: list[AssemblyDelta] = []
        while self._buffer:
            if "<" not in self._buffer:
                content = self._buffer
                self._buffer = ""
                deltas.append(self._content_delta(content))
                continue

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

            if tag == self._THINK_OPEN or tag == self._PIPE_REASONING_OPEN:
                close_tag = (
                    self._PIPE_REASONING_CLOSE
                    if tag == self._PIPE_REASONING_OPEN
                    else self._THINK_CLOSE
                )
                close_index = self._buffer.find(close_tag, len(tag))
                if close_index < 0:
                    if final:
                        self._metrics["malformed_reasoning_count"] += 1
                        self._metrics["reasoning_channel_recovery_count"] += 1
                        body = self._buffer[len(tag) :]
                        hidden, visible = self._recover_unclosed_reasoning_body(body)
                        if hidden:
                            if self._reasoning_enabled:
                                self._reasoning_parts.append(hidden)
                            else:
                                self._metrics["suppressed_reasoning_count"] += 1
                                self._metrics["reasoning_parser_bypassed_count"] += 1
                        self._buffer = ""
                        if visible:
                            deltas.append(self._content_delta(visible))
                    break
                body = self._buffer[len(tag) : close_index]
                self._buffer = self._buffer[close_index + len(close_tag) :]
                if body.strip() == "":
                    self._metrics["empty_thinking_sentinel_count"] += 1
                    continue
                # Parse reasoning tags even when reasoning is disabled so
                # hidden preambles never fall through as public content.
                if self._reasoning_enabled:
                    self._reasoning_parts.append(body)
                    deltas.append(AssemblyDelta(reasoning_text=body, raw_text=body))
                else:
                    self._metrics["suppressed_reasoning_count"] += 1
                    self._metrics["reasoning_parser_bypassed_count"] += 1
                continue

            if tag == self._TOOL_OPEN or tag == self._PIPE_TOOL_OPEN:
                close_tag = self._PIPE_TOOL_CLOSE if tag == self._PIPE_TOOL_OPEN else self._TOOL_CLOSE
                close_index = self._buffer.find(close_tag, len(tag))
                if close_index < 0:
                    if final:
                        self._metrics["malformed_tool_fragment_count"] += 1
                        self._buffer = ""
                    break
                body = self._buffer[len(tag) : close_index]
                self._buffer = self._buffer[close_index + len(close_tag) :]
                tool_delta = self._tool_delta(body)
                if tool_delta is not None:
                    deltas.append(AssemblyDelta(raw_text=body, tool_call=tool_delta))
                continue

            break
        return deltas

    def _recover_unclosed_reasoning_body(self, body: str) -> tuple[str, str]:
        stripped = body.strip()
        if not stripped:
            return "", ""
        for marker in ("\n\n", "\r\n\r\n"):
            if marker in body:
                hidden, visible = body.split(marker, 1)
                return hidden.strip(), visible.strip()
        # Conservative English section-label fallback for malformed streams.
        # Non-English or alternate labels intentionally fall back to no split
        # rather than leaking hidden reasoning as public assistant content.
        for marker in self._VISIBLE_TAIL_MARKERS:
            index = body.find(marker)
            if index >= 0:
                return body[:index].strip(), body[index + 1 :].strip()
        return "", ""

    def _next_structural_tag(self) -> tuple[str, int] | None:
        buffer = self._buffer
        for tag in self._structural_open_tags_value:
            if buffer.startswith(tag):
                return (tag, 0)

        best_tag = ""
        best_index = -1
        for tag in self._structural_open_tags_value:
            index = buffer.find(tag, 1)
            if index >= 0 and (best_index < 0 or index < best_index):
                best_tag = tag
                best_index = index
        if best_index < 0:
            return None
        return (best_tag, best_index)

    def _has_partial_structural_tag_suffix(self) -> bool:
        return bool(self._partial_structural_tag_suffix())

    def _partial_structural_tag_suffix(self) -> str:
        marker_index = self._buffer.rfind("<")
        if marker_index < 0:
            return ""

        suffix = self._buffer[marker_index:]
        suffix_len = len(suffix)
        if self._tool_parsing_enabled_value:
            if (
                0 < suffix_len < len(self._TOOL_OPEN)
                and self._TOOL_OPEN.startswith(suffix)
            ):
                return suffix
            if (
                0 < suffix_len < len(self._PIPE_TOOL_OPEN)
                and self._PIPE_TOOL_OPEN.startswith(suffix)
            ):
                return suffix
        if (
            0 < suffix_len < len(self._THINK_OPEN)
            and self._THINK_OPEN.startswith(suffix)
        ):
            return suffix
        if (
            0 < suffix_len < len(self._PIPE_REASONING_OPEN)
            and self._PIPE_REASONING_OPEN.startswith(suffix)
        ):
            return suffix
        return ""

    def _contains_reasoning_leak_marker(self, content: str) -> bool:
        return self._REASONING_LEAK_PREFIXES[0] in content or (
            self._REASONING_LEAK_PREFIXES[1] in content
        )

    def _record_prefix_hold(self, suffix: str) -> None:
        self._metrics["stream_prefix_hold_chars"] = max(
            self._metrics["stream_prefix_hold_chars"],
            len(suffix),
        )

    def _content_delta(self, content: str) -> AssemblyDelta:
        if self._tool_parsing_enabled_value and (
            "<tool_call" in content or "<|tool_call" in content
        ):
            self._metrics["tool_call_markup_leak_count"] += 1
        if self._contains_reasoning_leak_marker(content):
            self._metrics["reasoning_leak_count"] += 1
        self._assistant_parts.append(content)
        return AssemblyDelta(content_text=content, raw_text=content)

    def _tool_delta(self, body: str) -> AssembledToolCall | None:
        payload = self._parse_tool_body(body)
        if payload is None:
            return None

        if not isinstance(payload, dict):
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        name = str(payload.get("name") or payload.get("tool_name") or "").strip()
        if not name:
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        resolved_name = self._resolve_tool_name(name)
        if resolved_name is None:
            self._metrics["unknown_tool_delta_count"] += 1
            return None
        if resolved_name != name:
            self._metrics["tool_call_name_normalized_count"] += 1
            name = resolved_name

        arguments = payload.get("arguments", {})
        call_id = str(payload.get("id") or payload.get("call_id") or "").strip()
        # Prefer model-provided call ids for dedupe so identical repeated calls
        # can be emitted. When a call id has already been seen, skip before
        # canonicalizing arguments because the fragment will be discarded.
        if call_id:
            key = ("call_id", call_id)
            if key in self._emitted_tool_keys:
                self._metrics["duplicate_tool_delta_count"] += 1
                return None
            arguments_fragment = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        else:
            arguments_fragment = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
            # Legacy call-id-less fragments keep content dedupe to suppress
            # non-monotonic replay from older parsers.
            key = ("legacy", f"{name}\0{arguments_fragment}")
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

    def _parse_tool_body(self, body: str) -> dict[str, object] | list[object] | None:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return self._parse_pipe_tool_body(body)

    def _parse_pipe_tool_body(self, body: str) -> dict[str, object] | None:
        match = self._PIPE_CALL_RE.match(body)
        if match is None:
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        if match.group("args").startswith("("):
            return {
                "name": match.group("name"),
                "arguments": {},
            }
        try:
            arguments = json.loads(match.group("args"))
        except json.JSONDecodeError:
            arguments = self._parse_relaxed_object_arguments(match.group("args"))
            if arguments is None:
                self._metrics["malformed_tool_fragment_count"] += 1
                return None
        if not isinstance(arguments, dict):
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        return {
            "name": match.group("name"),
            "arguments": arguments,
        }

    def _resolve_tool_name(self, name: str) -> str | None:
        if not self._allowed_tool_names:
            return name
        if name in self._allowed_tool_name_set:
            return name
        declared = self._allowed_tool_names_by_casefold.get(name.casefold())
        if declared is not None:
            return declared
        for declared in self._allowed_tool_names_by_prefix:
            if self._is_action_qualified_tool_name(name, declared):
                return declared
        return None

    @staticmethod
    def _is_action_qualified_tool_name(name: str, declared: str) -> bool:
        folded_name = name.casefold()
        folded_declared = declared.casefold()
        if len(folded_name) <= len(folded_declared):
            return False
        if not folded_name.startswith(folded_declared):
            return False
        return folded_name[len(folded_declared)] in {".", ":", "/"}

    def _parse_relaxed_object_arguments(self, text: str) -> dict[str, object] | None:
        stripped = text.strip()
        if not (stripped.startswith("{") and stripped.endswith("}")):
            return None
        content = stripped[1:-1].strip()
        if not content:
            return {}
        values: dict[str, object] = {}
        for item in self._split_relaxed_object_items(content):
            separator_index = self._relaxed_key_value_separator(item)
            if separator_index is None:
                return None
            key = item[:separator_index]
            value = item[separator_index + 1 :]
            normalized_key = key.strip().strip("\"'")
            if not normalized_key:
                return None
            values[normalized_key] = self._parse_relaxed_scalar(value.strip())
        return values

    @staticmethod
    def _split_relaxed_object_items(content: str) -> list[str]:
        items: list[str] = []
        start = 0
        quote: str | None = None
        escaped = False
        for index, char in enumerate(content):
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char == '"' or char == "'":
                quote = char
                continue
            if char == ",":
                items.append(content[start:index].strip())
                start = index + 1
        items.append(content[start:].strip())
        return items

    @staticmethod
    def _relaxed_key_value_separator(item: str) -> int | None:
        quote: str | None = None
        escaped = False
        for index, char in enumerate(item):
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char == '"' or char == "'":
                quote = char
                continue
            if char == ":":
                return index
        return None

    @staticmethod
    def _parse_relaxed_scalar(value: str) -> object:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return RequestStreamAssembler._unescape_relaxed_quoted_string(value[1:-1])
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered == "null":
            return None
        try:
            if any(marker in value for marker in (".", "e", "E")):
                return float(value)
            return int(value)
        except ValueError:
            return value

    @staticmethod
    def _unescape_relaxed_quoted_string(value: str) -> str:
        if "\\" not in value:
            return value
        decoded: list[str] = []
        escaped = False
        escapes = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
        }
        for char in value:
            if escaped:
                decoded.append(escapes.get(char, char))
                escaped = False
            elif char == "\\":
                escaped = True
            else:
                decoded.append(char)
        if escaped:
            decoded.append("\\")
        return "".join(decoded)

    def _first_json_delimiter(self, text: str) -> int | None:
        object_index = text.find("{")
        array_index = text.find("[")
        if object_index < 0:
            return None if array_index < 0 else array_index
        if array_index < 0 or object_index <= array_index:
            return object_index
        return array_index
