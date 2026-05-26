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
_MISSING_TOOL_ARGUMENTS = object()


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

    @property
    def token_count(self) -> int:
        return 1


class TokenCountedAssemblyDelta(AssemblyDelta):
    __slots__ = ("_token_count",)

    def __init__(
        self,
        *,
        content_text: str = "",
        reasoning_text: str = "",
        raw_text: str = "",
        tool_call: AssembledToolCall | None = None,
        parser_observation: str = "",
        token_count: int,
    ) -> None:
        super().__init__(
            content_text=content_text,
            reasoning_text=reasoning_text,
            raw_text=raw_text,
            tool_call=tool_call,
            parser_observation=parser_observation,
        )
        object.__setattr__(self, "_token_count", token_count)

    @property
    def token_count(self) -> int:
        return self._token_count


@dataclass(frozen=True, slots=True)
class AssemblyCompletion:
    assistant_text: str
    reasoning_text: str
    raw_text: str
    tool_call_count: int
    metrics: dict[str, int | str]


@dataclass(slots=True)
class ChannelAssemblyState:
    preferred_channel_source: str = ""
    pending_marker_tail: str = ""
    pending_annotated_segment_count: int = 0
    open_tool_event_count: int = 0
    max_pending_marker_tail_chars: int = 0
    terminal_marker_tail_flush_count: int = 0
    orphan_tool_event_flush_count: int = 0

    def record_channel_source(self, source: str) -> None:
        if source == "tool_call_tag":
            self.preferred_channel_source = source
        elif source == "reasoning_tag":
            if self.preferred_channel_source != "tool_call_tag":
                self.preferred_channel_source = source
        elif source == "raw_text" and not self.preferred_channel_source:
            self.preferred_channel_source = source

    def hold_marker_tail(self, tail: str) -> None:
        self.pending_marker_tail = tail
        self.max_pending_marker_tail_chars = max(self.max_pending_marker_tail_chars, len(tail))

    def clear_marker_tail(self) -> None:
        self.pending_marker_tail = ""

    def record_reasoning_source(self) -> None:
        if self.preferred_channel_source != "tool_call_tag":
            self.preferred_channel_source = "reasoning_tag"

    def flush_terminal_marker_tail(self) -> None:
        if self.pending_marker_tail:
            self.terminal_marker_tail_flush_count += 1
        self.pending_marker_tail = ""

    def open_tool_event(self) -> None:
        self.record_channel_source("tool_call_tag")
        # The grammar only allows one open tool event; keep this as a 0/1 gauge.
        if self.open_tool_event_count == 0:
            self.open_tool_event_count = 1

    def close_tool_event(self) -> None:
        self.open_tool_event_count = 0

    def flush_orphan_tool_events(self) -> None:
        if self.open_tool_event_count:
            self.orphan_tool_event_flush_count += self.open_tool_event_count
        self.open_tool_event_count = 0


class RequestStreamAssembler:
    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"
    _PIPE_REASONING_OPEN = "<|channel>thought"
    _PIPE_REASONING_CLOSE = "<channel|>"
    _TOOL_OPEN = "<tool_call>"
    _TOOL_CLOSE = "</tool_call>"
    _PIPE_TOOL_OPEN = "<|tool_call>"
    _PIPE_TOOL_CLOSE = "<tool_call|>"
    _PIPE_CHANNEL_OPEN = "<|channel>"
    _PIPE_CHANNEL_HEADER_CLOSE = "<channel|>"
    _REASONING_OPEN_TAGS = (_THINK_OPEN, _PIPE_CHANNEL_OPEN)
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
    _PIPE_CHANNEL_PREFIXES = tuple(
        "<|channel>"[:index] for index in range(1, len("<|channel>"))
    )
    _REASONING_PREFIXES = _THINK_PREFIXES + _PIPE_CHANNEL_PREFIXES
    _REASONING_PARTIAL_SUFFIXES = frozenset(
        _THINK_PREFIXES + _PIPE_CHANNEL_PREFIXES + _PIPE_REASONING_PREFIXES
    )
    _TOOL_PARSER_PARTIAL_SUFFIXES = frozenset(
        _THINK_PREFIXES
        + _PIPE_CHANNEL_PREFIXES
        + _PIPE_REASONING_PREFIXES
        + _TOOL_PREFIXES
        + _PIPE_TOOL_PREFIXES
    )
    _THINK_PREFIXES_REVERSED = tuple(reversed(_THINK_PREFIXES))
    _PIPE_REASONING_PREFIXES_REVERSED = tuple(reversed(_PIPE_REASONING_PREFIXES))
    _REASONING_PREFIXES_REVERSED = tuple(reversed(_REASONING_PREFIXES))
    _TOOL_PREFIXES_REVERSED = tuple(reversed(_TOOL_PREFIXES))
    _PIPE_TOOL_PREFIXES_REVERSED = tuple(reversed(_PIPE_TOOL_PREFIXES))
    _PIPE_CHANNEL_PREFIXES_REVERSED = tuple(reversed(_PIPE_CHANNEL_PREFIXES))
    _VISIBLE_TAIL_MARKERS = ("\nFinal answer", "\nFinal:", "\nAnswer:", "\nAssistant:", "\nResult:")
    _HIDDEN_PIPE_CHANNELS = frozenset({"analysis", "thought", "reasoning"})
    _VISIBLE_PIPE_CHANNELS = frozenset({"commentary", "final"})
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
        self._partial_structural_tag_suffixes_value = self._REASONING_PARTIAL_SUFFIXES
        self._structural_tag_prefixes_reversed_value = self._REASONING_PREFIXES_REVERSED
        self._structural_open_tags_value = self._REASONING_OPEN_TAGS
        if self._tool_parsing_enabled_value:
            self._request_context_mode_value = "tool_parser"
            self._structural_open_tags_value = self._TOOL_PARSER_STRUCTURAL_OPEN_TAGS
            self._structural_tag_prefixes_value = (
                self._REASONING_PREFIXES + self._TOOL_PREFIXES + self._PIPE_TOOL_PREFIXES
            )
            self._partial_structural_tag_suffixes_value = self._TOOL_PARSER_PARTIAL_SUFFIXES
            self._structural_tag_prefixes_reversed_value = (
                self._PIPE_CHANNEL_PREFIXES_REVERSED
                + self._PIPE_TOOL_PREFIXES_REVERSED
                + self._TOOL_PREFIXES_REVERSED
                + self._THINK_PREFIXES_REVERSED
            )
        elif self._is_json_structured_output_value:
            self._request_context_mode_value = "structured_json"
        elif self._reasoning_enabled:
            self._request_context_mode_value = "reasoning_only"
        else:
            self._request_context_mode_value = "plain"
        self._raw_seen = ""
        self._raw_seen_assistant_part_count = 0
        self._buffer = ""
        self._pending_token_bytes = b""
        self.channel_state = ChannelAssemblyState()
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
            "partial_tool_candidate_count": 0,
            "harmony_channel_hidden_count": 0,
            "harmony_channel_unknown_count": 0,
            "harmony_channel_markup_leak_count": 0,
            "pending_marker_tail_chars": 0,
            "max_pending_marker_tail_chars": 0,
            "terminal_marker_tail_flush_count": 0,
            "pending_annotated_segment_count": 0,
            "open_tool_event_count": 0,
            "orphan_tool_event_flush_count": 0,
            "channel_state_preferred_source": "",
        }

    def accept(self, fragment: StreamFragment) -> list[AssemblyDelta]:
        token_count = 0
        byte_delta = None
        token_bytes = fragment.token_bytes
        if token_bytes is not None and not fragment.token_ids and not fragment.token_logprobs:
            token_count = 1
            self._metrics["generated_token_count"] += 1
            byte_delta = self._token_byte_delta(token_bytes)
        elif fragment.token_ids or fragment.token_logprobs:
            token_count = self._record_token_metadata(fragment)
            if token_bytes is not None:
                byte_delta = self._token_byte_delta(token_bytes)
        if byte_delta is not None:
            if not byte_delta:
                return []
            delta = byte_delta
        elif fragment.raw_text is None:
            delta = fragment.text
            if delta:
                self._materialized_raw_seen()
                self._raw_seen += delta
            else:
                return []
        elif fragment.raw_text:
            delta = self._unseen_delta(fragment.raw_text)
        else:
            return []

        if not delta:
            return []

        raw_delta_from_token_bytes = byte_delta is not None
        if (
            not self._is_json_only_structured_output_value
            and not self._buffer
            and not fragment.parser_observation
            and "<" not in delta
        ):
            self._assistant_parts.append(delta)
            if raw_delta_from_token_bytes:
                self._raw_seen_assistant_part_count += 1
            if token_count < 2:
                return [AssemblyDelta(content_text=delta, raw_text=delta)]
            self._metrics["stream_interval_delta_flush_count"] += 1
            return [
                TokenCountedAssemblyDelta(
                    content_text=delta,
                    raw_text=delta,
                    token_count=token_count,
                )
            ]

        if raw_delta_from_token_bytes:
            self._materialized_raw_seen()
            self._raw_seen += delta

        if self._is_json_only_structured_output_value:
            deltas = self._accept_json_structured_output(delta, token_count=token_count)
        else:
            self._buffer += delta
            deltas = self._drain_buffer(final=False)
            if token_count > 0:
                deltas = self._annotate_token_counts(deltas, token_count)
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
        self._sync_channel_state_metrics()
        metrics = dict(self._metrics)
        metrics["effective_parser_config_json"] = self._effective_parser_config_json()
        return AssemblyCompletion(
            assistant_text="".join(self._assistant_parts),
            reasoning_text="".join(self._reasoning_parts),
            raw_text=self._materialized_raw_seen(),
            tool_call_count=self._tool_fragment_index,
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
        if self._raw_seen_assistant_part_count:
            self._materialized_raw_seen()
        raw_seen = self._raw_seen
        if raw.startswith(raw_seen):
            delta = raw[len(raw_seen) :]
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

    def _materialized_raw_seen(self) -> str:
        if self._raw_seen_assistant_part_count:
            if self._raw_seen_assistant_part_count == len(self._assistant_parts):
                raw_parts = self._assistant_parts
            else:
                raw_parts = self._assistant_parts[-self._raw_seen_assistant_part_count :]
            self._raw_seen += "".join(raw_parts)
            self._raw_seen_assistant_part_count = 0
        return self._raw_seen

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
                return token_bytes.decode()
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
            self._with_parser_observation(delta, parser_observation)
            if delta.content_text or delta.reasoning_text or delta.tool_call is not None
            else delta
            for delta in deltas
        ]

    @staticmethod
    def _with_parser_observation(
        delta: AssemblyDelta,
        parser_observation: str,
    ) -> AssemblyDelta:
        if delta.token_count == 1:
            return replace(delta, parser_observation=parser_observation)
        return TokenCountedAssemblyDelta(
            content_text=delta.content_text,
            reasoning_text=delta.reasoning_text,
            raw_text=delta.raw_text,
            tool_call=delta.tool_call,
            parser_observation=parser_observation,
            token_count=delta.token_count,
        )

    def _accept_json_structured_output(self, delta: str, token_count: int = 0) -> list[AssemblyDelta]:
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
        if token_count <= 1:
            return [AssemblyDelta(content_text=content, raw_text=delta)]
        return [
            TokenCountedAssemblyDelta(
                content_text=content,
                raw_text=delta,
                token_count=token_count,
            )
        ]

    def _drain_buffer(self, final: bool) -> list[AssemblyDelta]:
        deltas: list[AssemblyDelta] = []
        channel_state = self.channel_state
        metrics = self._metrics
        while self._buffer:
            if "<" not in self._buffer:
                content = self._buffer
                self._buffer = ""
                deltas.append(self._content_delta(content))
                continue

            next_tag = self._next_structural_tag()
            if next_tag is None:
                held_suffix = self._partial_structural_tag_suffix()
                if held_suffix:
                    visible_prefix = self._buffer[: -len(held_suffix)]
                    if visible_prefix:
                        self._buffer = held_suffix
                        if len(visible_prefix) <= 8:
                            metrics["stream_short_reply_flush_count"] += 1
                        if not final:
                            held_len = len(held_suffix)
                            channel_state.pending_marker_tail = held_suffix
                            if held_len > channel_state.max_pending_marker_tail_chars:
                                channel_state.max_pending_marker_tail_chars = held_len
                            if held_len > metrics["stream_prefix_hold_chars"]:
                                metrics["stream_prefix_hold_chars"] = held_len
                        deltas.append(self._content_delta(visible_prefix))
                        continue
                    if final and self._should_flush_terminal_marker_tail(held_suffix):
                        if channel_state.pending_marker_tail:
                            channel_state.terminal_marker_tail_flush_count += 1
                        channel_state.pending_marker_tail = ""
                        self._buffer = ""
                        continue
                    if not final:
                        self._record_prefix_hold(held_suffix)
                        break
                if self.channel_state.pending_marker_tail:
                    self.channel_state.clear_marker_tail()
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
                if self.channel_state.pending_marker_tail:
                    self.channel_state.clear_marker_tail()
                if channel_state.preferred_channel_source != "tool_call_tag":
                    channel_state.preferred_channel_source = "reasoning_tag"
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
                if channel_state.pending_marker_tail:
                    channel_state.pending_marker_tail = ""
                channel_state.preferred_channel_source = "tool_call_tag"
                if channel_state.open_tool_event_count == 0:
                    channel_state.open_tool_event_count = 1
                close_tag = self._PIPE_TOOL_CLOSE if tag == self._PIPE_TOOL_OPEN else self._TOOL_CLOSE
                close_index = self._buffer.find(close_tag, len(tag))
                if close_index < 0:
                    if final:
                        metrics["malformed_tool_fragment_count"] += 1
                        if channel_state.open_tool_event_count:
                            channel_state.orphan_tool_event_flush_count += (
                                channel_state.open_tool_event_count
                            )
                        channel_state.open_tool_event_count = 0
                        self._buffer = ""
                    break
                body = self._buffer[len(tag) : close_index]
                self._buffer = self._buffer[close_index + len(close_tag) :]
                tool_delta = self._tool_delta(body)
                channel_state.open_tool_event_count = 0
                if tool_delta is not None:
                    deltas.append(AssemblyDelta(raw_text=body, tool_call=tool_delta))
                continue

            if tag == self._PIPE_CHANNEL_OPEN:
                if self.channel_state.pending_marker_tail:
                    self.channel_state.clear_marker_tail()
                channel_deltas = self._drain_pipe_channel(final=final)
                if channel_deltas is None:
                    break
                deltas.extend(channel_deltas)
                continue

            break
        return deltas

    def _annotate_token_counts(
        self,
        deltas: list[AssemblyDelta],
        token_count: int,
    ) -> list[AssemblyDelta]:
        if token_count <= 0 or not deltas:
            return deltas
        if len(deltas) == 1:
            return [self._with_token_count(deltas[0], token_count)]

        weights = [self._estimated_delta_token_count(delta) for delta in deltas]
        if sum(weights) > token_count:
            weights = self._compress_delta_token_counts(weights, token_count)
        elif sum(weights) < token_count:
            weights = self._distribute_extra_delta_tokens(deltas, weights, token_count - sum(weights))

        return [self._with_token_count(delta, count) for delta, count in zip(deltas, weights)]

    @staticmethod
    def _with_token_count(delta: AssemblyDelta, token_count: int) -> AssemblyDelta:
        if token_count == 1:
            return delta
        return TokenCountedAssemblyDelta(
            content_text=delta.content_text,
            reasoning_text=delta.reasoning_text,
            raw_text=delta.raw_text,
            tool_call=delta.tool_call,
            parser_observation=delta.parser_observation,
            token_count=token_count,
        )

    @staticmethod
    def _estimated_delta_token_count(delta: AssemblyDelta) -> int:
        if delta.content_text:
            return max(1, len(delta.content_text.split()))
        if delta.reasoning_text:
            return max(1, len(delta.reasoning_text.split()))
        return 1

    @staticmethod
    def _compress_delta_token_counts(weights: list[int], token_count: int) -> list[int]:
        compressed = [1 for _ in weights]
        remaining = token_count - len(compressed)
        if remaining <= 0:
            return compressed[:token_count] + [0 for _ in weights[token_count:]]
        extras = [max(weight - 1, 0) for weight in weights]
        while remaining > 0 and any(extras):
            for index, extra in enumerate(extras):
                if remaining <= 0:
                    break
                if extra <= 0:
                    continue
                compressed[index] += 1
                extras[index] -= 1
                remaining -= 1
        return compressed

    @staticmethod
    def _distribute_extra_delta_tokens(
        deltas: list[AssemblyDelta],
        weights: list[int],
        extra_tokens: int,
    ) -> list[int]:
        adjusted = list(weights)
        priority_indexes = [
            index for index, delta in enumerate(deltas) if delta.tool_call is not None
        ] or [
            index for index, delta in enumerate(deltas) if delta.reasoning_text
        ] or list(range(len(deltas)))
        cursor = 0
        while extra_tokens > 0:
            index = priority_indexes[cursor % len(priority_indexes)]
            adjusted[index] += 1
            extra_tokens -= 1
            cursor += 1
        return adjusted

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
        think_index = buffer.find(self._THINK_OPEN)
        has_pipe_marker = "<|" in buffer
        if not has_pipe_marker:
            if not self._tool_parsing_enabled_value:
                return None if think_index < 0 else (self._THINK_OPEN, think_index)

            tool_index = buffer.find(self._TOOL_OPEN)
            if tool_index >= 0 and (think_index < 0 or tool_index < think_index):
                return (self._TOOL_OPEN, tool_index)
            return None if think_index < 0 else (self._THINK_OPEN, think_index)

        pipe_channel_index = buffer.find(self._PIPE_CHANNEL_OPEN)
        earliest_tag = self._THINK_OPEN
        earliest_index = think_index
        if pipe_channel_index >= 0 and (earliest_index < 0 or pipe_channel_index < earliest_index):
            earliest_tag = self._PIPE_CHANNEL_OPEN
            earliest_index = pipe_channel_index
        if self._tool_parsing_enabled_value:
            tool_index = buffer.find(self._TOOL_OPEN)
            if tool_index >= 0 and (earliest_index < 0 or tool_index < earliest_index):
                earliest_tag = self._TOOL_OPEN
                earliest_index = tool_index
            pipe_tool_index = buffer.find(self._PIPE_TOOL_OPEN)
            if pipe_tool_index >= 0 and (earliest_index < 0 or pipe_tool_index < earliest_index):
                earliest_tag = self._PIPE_TOOL_OPEN
                earliest_index = pipe_tool_index
        return None if earliest_index < 0 else (earliest_tag, earliest_index)

    def _next_structural_tag_after(self, start: int) -> int:
        buffer = self._buffer
        if buffer.find("<", start) < 0:
            return -1
        earliest = buffer.find(self._THINK_OPEN, start)
        pipe_channel_index = buffer.find(self._PIPE_CHANNEL_OPEN, start)
        if pipe_channel_index >= 0 and (earliest < 0 or pipe_channel_index < earliest):
            earliest = pipe_channel_index
        if self._tool_parsing_enabled_value:
            tool_index = buffer.find(self._TOOL_OPEN, start)
            if tool_index >= 0 and (earliest < 0 or tool_index < earliest):
                earliest = tool_index
            pipe_tool_index = buffer.find(self._PIPE_TOOL_OPEN, start)
            if pipe_tool_index >= 0 and (earliest < 0 or pipe_tool_index < earliest):
                earliest = pipe_tool_index
        return earliest

    def _has_partial_structural_tag_suffix(self) -> bool:
        return bool(self._partial_structural_tag_suffix())

    def _partial_structural_tag_suffix(self) -> str:
        marker_index = self._buffer.rfind("<")
        if marker_index < 0:
            return ""

        suffix = self._buffer[marker_index:]
        if suffix in self._partial_structural_tag_suffixes_value:
            return suffix
        return ""

    def _contains_reasoning_leak_marker(self, content: str) -> bool:
        return self._REASONING_LEAK_PREFIXES[0] in content or (
            "<|" in content and self._REASONING_LEAK_PREFIXES[1] in content
        )

    def _record_prefix_hold(self, suffix: str) -> None:
        self.channel_state.hold_marker_tail(suffix)
        self._metrics["stream_prefix_hold_chars"] = max(
            self._metrics["stream_prefix_hold_chars"],
            len(suffix),
        )

    @staticmethod
    def _should_flush_terminal_marker_tail(suffix: str) -> bool:
        # A single "<" may be literal content; only suppress multi-char marker prefixes.
        return len(suffix) > 1

    def _sync_channel_state_metrics(self) -> None:
        self._metrics["pending_marker_tail_chars"] = len(self.channel_state.pending_marker_tail)
        self._metrics["max_pending_marker_tail_chars"] = (
            self.channel_state.max_pending_marker_tail_chars
        )
        self._metrics["terminal_marker_tail_flush_count"] = (
            self.channel_state.terminal_marker_tail_flush_count
        )
        self._metrics["pending_annotated_segment_count"] = (
            self.channel_state.pending_annotated_segment_count
        )
        self._metrics["open_tool_event_count"] = self.channel_state.open_tool_event_count
        self._metrics["orphan_tool_event_flush_count"] = (
            self.channel_state.orphan_tool_event_flush_count
        )
        preferred_source = self.channel_state.preferred_channel_source
        if not preferred_source and self._assistant_parts:
            preferred_source = "raw_text"
        self._metrics["channel_state_preferred_source"] = preferred_source

    def _content_delta(self, content: str) -> AssemblyDelta:
        if "<" in content:
            if self._tool_parsing_enabled_value and (
                "<tool_call" in content or ("<|" in content and "<|tool_call" in content)
            ):
                self._metrics["tool_call_markup_leak_count"] += 1
            if self._contains_reasoning_leak_marker(content):
                self._metrics["reasoning_leak_count"] += 1
                self._metrics["harmony_channel_markup_leak_count"] += 1
        self._assistant_parts.append(content)
        return AssemblyDelta(content_text=content, raw_text=content)

    def _drain_pipe_channel(self, final: bool) -> list[AssemblyDelta] | None:
        header_close_index = self._buffer.find(
            self._PIPE_CHANNEL_HEADER_CLOSE,
            len(self._PIPE_CHANNEL_OPEN),
        )
        if header_close_index < 0:
            if final:
                self._metrics["malformed_reasoning_count"] += 1
                if self._buffer.startswith(self._PIPE_REASONING_OPEN):
                    self._metrics["reasoning_channel_recovery_count"] += 1
                    body = self._buffer[len(self._PIPE_REASONING_OPEN) :]
                    self._buffer = ""
                    hidden, visible = self._recover_unclosed_reasoning_body(body)
                    return self._hidden_pipe_channel_deltas(
                        hidden=hidden,
                        visible=visible,
                    )
                self._buffer = ""
                return []
            return None

        header = self._buffer[len(self._PIPE_CHANNEL_OPEN) : header_close_index]
        body_start = header_close_index + len(self._PIPE_CHANNEL_HEADER_CLOSE)
        channel_name = self._pipe_channel_name(header)
        legacy_hidden = self._legacy_pipe_channel_header_body(header, channel_name)
        if legacy_hidden is not None or self._tool_parsing_enabled_value:
            next_index = self._next_structural_tag_after(body_start)
            has_boundary = next_index >= 0
            if has_boundary:
                visible = self._buffer[body_start:next_index]
                self._buffer = self._buffer[next_index:]
            else:
                visible = self._buffer[body_start:]
                self._buffer = ""
            return self._hidden_pipe_channel_deltas(
                hidden=legacy_hidden or "",
                visible=visible,
            )

        next_index = self._next_structural_tag_after(body_start)
        has_boundary = next_index >= 0

        if has_boundary:
            body = self._buffer[body_start:next_index]
            self._buffer = self._buffer[next_index:]
        elif channel_name in self._VISIBLE_PIPE_CHANNELS or final:
            body = self._buffer[body_start:]
            self._buffer = ""
        else:
            return None

        return self._pipe_channel_deltas(
            channel_name=channel_name,
            body=body,
            recover_visible_tail=final and not has_boundary,
        )

    @staticmethod
    def _pipe_channel_name(header: str) -> str:
        stripped = header.strip()
        if not stripped:
            return ""
        for index, character in enumerate(stripped):
            if character.isspace():
                return stripped[:index].lower()
        return stripped.lower()

    @classmethod
    def _legacy_pipe_channel_header_body(cls, header: str, channel_name: str) -> str | None:
        if channel_name not in cls._HIDDEN_PIPE_CHANNELS:
            return None
        body = header[len(channel_name) :]
        return body if body.strip() else None

    def _pipe_channel_deltas(
        self,
        channel_name: str,
        body: str,
        recover_visible_tail: bool,
    ) -> list[AssemblyDelta]:
        if channel_name in self._VISIBLE_PIPE_CHANNELS:
            return [self._content_delta(body)] if body else []

        if channel_name in self._HIDDEN_PIPE_CHANNELS:
            self.channel_state.record_reasoning_source()
            self._metrics["harmony_channel_hidden_count"] += 1
            hidden = body
            visible = ""
            if recover_visible_tail:
                recovered_hidden, recovered_visible = self._recover_unclosed_reasoning_body(body)
                if recovered_hidden or recovered_visible:
                    hidden = recovered_hidden
                    visible = recovered_visible
            return self._hidden_pipe_channel_deltas(hidden=hidden, visible=visible)

        self._metrics["harmony_channel_unknown_count"] += 1
        return []

    def _hidden_pipe_channel_deltas(self, hidden: str, visible: str = "") -> list[AssemblyDelta]:
        if not hidden.strip():
            self._metrics["empty_thinking_sentinel_count"] += 1
        deltas: list[AssemblyDelta] = []
        if hidden.strip():
            if self._reasoning_enabled:
                self._reasoning_parts.append(hidden)
                deltas.append(AssemblyDelta(reasoning_text=hidden, raw_text=hidden))
            else:
                self._metrics["suppressed_reasoning_count"] += 1
                self._metrics["reasoning_parser_bypassed_count"] += 1
        if visible:
            deltas.append(self._content_delta(visible))
        return deltas

    def _tool_delta(self, body: str) -> AssembledToolCall | None:
        payload = self._parse_tool_body(body)
        if payload is None:
            return None

        if not isinstance(payload, dict):
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        if not payload:
            self._metrics["partial_tool_candidate_count"] += 1
            return None
        name = str(payload.get("name") or payload.get("tool_name") or "").strip()
        if not name:
            self._metrics["malformed_tool_fragment_count"] += 1
            return None
        # A named tool object without arguments is still incomplete; suppress it
        # so callers can use partial_tool_candidate_count for healing decisions.
        arguments = payload.get("arguments", _MISSING_TOOL_ARGUMENTS)
        if arguments is _MISSING_TOOL_ARGUMENTS:
            self._metrics["partial_tool_candidate_count"] += 1
            return None
        resolved_name = self._resolve_tool_name(name)
        if resolved_name is None:
            self._metrics["unknown_tool_delta_count"] += 1
            return None
        if resolved_name != name:
            self._metrics["tool_call_name_normalized_count"] += 1
            name = resolved_name

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
