from __future__ import annotations

import json
import logging

from worker.runtime import stream_assembler
from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


def test_structural_tag_prefixes_are_cached_per_parser_mode() -> None:
    think_prefixes = tuple(
        RequestStreamAssembler._THINK_OPEN[:index]
        for index in range(1, len(RequestStreamAssembler._THINK_OPEN))
    )
    pipe_reasoning_prefixes = tuple(
        RequestStreamAssembler._PIPE_REASONING_OPEN[:index]
        for index in range(1, len(RequestStreamAssembler._PIPE_REASONING_OPEN))
    )
    tool_prefixes = tuple(
        RequestStreamAssembler._TOOL_OPEN[:index]
        for index in range(1, len(RequestStreamAssembler._TOOL_OPEN))
    )
    pipe_tool_prefixes = tuple(
        RequestStreamAssembler._PIPE_TOOL_OPEN[:index]
        for index in range(1, len(RequestStreamAssembler._PIPE_TOOL_OPEN))
    )

    tool_enabled = RequestStreamAssembler(
        request_id="req-prefixes-tools",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    tool_disabled = RequestStreamAssembler(
        request_id="req-prefixes-think-only",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="",
    )

    assert tool_enabled._structural_tag_prefixes == (
        think_prefixes + pipe_reasoning_prefixes + tool_prefixes + pipe_tool_prefixes
    )
    assert (
        tool_enabled._structural_open_tags
        is RequestStreamAssembler._TOOL_PARSER_STRUCTURAL_OPEN_TAGS
    )
    assert tool_enabled._structural_tag_prefixes is tool_enabled._structural_tag_prefixes
    assert tool_enabled._structural_tag_prefixes_reversed == (
        tuple(reversed(pipe_tool_prefixes))
        + tuple(reversed(tool_prefixes))
        + tuple(reversed(pipe_reasoning_prefixes))
        + tuple(reversed(think_prefixes))
    )
    assert (
        tool_enabled._structural_tag_prefixes_reversed
        is tool_enabled._structural_tag_prefixes_reversed
    )
    assert tool_disabled._structural_tag_prefixes == think_prefixes + pipe_reasoning_prefixes
    assert tool_enabled._structural_tag_prefixes is tool_enabled._structural_tag_prefixes
    assert tool_disabled._structural_tag_prefixes is tool_disabled._structural_tag_prefixes
    assert tool_disabled._structural_tag_prefixes is RequestStreamAssembler._REASONING_PREFIXES
    assert tool_disabled._structural_open_tags is RequestStreamAssembler._REASONING_OPEN_TAGS
    assert (
        tool_disabled._structural_tag_prefixes_reversed
        is RequestStreamAssembler._REASONING_PREFIXES_REVERSED
    )


def test_parser_mode_flags_are_computed_once_at_initialization() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-cached-parser-mode-flags",
        reasoning_enabled=False,
        structured_output_mode=" json_schema ",
        tool_parser_mode=" qwen ",
    )

    assert assembler._is_json_structured_output is True
    assert assembler._is_json_only_structured_output is False
    assert assembler._tool_parsing_enabled is True
    assert assembler._request_context_mode == "tool_parser"
    assert assembler._structural_tag_prefixes is assembler._structural_tag_prefixes_value
    assert assembler._structural_open_tags is assembler._structural_open_tags_value


def test_next_structural_tag_prefers_the_earliest_tool_tag() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-tool-first",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    assembler._buffer = '<tool_call>{"name":"search","arguments":{}}</tool_call><think>later</think>'

    assert assembler._next_structural_tag() == (RequestStreamAssembler._TOOL_OPEN, 0)


def test_next_structural_tag_prefers_earliest_pipe_reasoning_tag() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-reasoning-first",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    assembler._buffer = (
        "lead<|channel>thought hidden<channel|>"
        '<tool_call>{"name":"search","arguments":{}}</tool_call>'
    )

    assert assembler._next_structural_tag() == (
        RequestStreamAssembler._PIPE_REASONING_OPEN,
        4,
    )


def test_plain_buffer_without_tag_marker_flushes_without_structural_scans(monkeypatch) -> None:
    assembler = RequestStreamAssembler(
        request_id="req-no-marker-fast-path",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    def fail_structural_scan() -> None:
        raise AssertionError("plain buffers should not scan for structural tags")

    monkeypatch.setattr(assembler, "_next_structural_tag", fail_structural_scan)
    deltas = assembler.accept(StreamFragment(raw_text="plain text chunk without markup"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == [
        "plain text chunk without markup"
    ]
    assert completed.assistant_text == "plain text chunk without markup"
    assert completed.metrics["stream_prefix_hold_chars"] == 0
    assert completed.metrics["stream_short_reply_flush_count"] == 0


def test_plain_token_metadata_keeps_fast_path_and_metrics(monkeypatch) -> None:
    assembler = RequestStreamAssembler(
        request_id="req-no-marker-token-fast-path",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    def fail_structural_scan() -> None:
        raise AssertionError("plain token metadata should not force structural scans")

    monkeypatch.setattr(assembler, "_next_structural_tag", fail_structural_scan)
    deltas = assembler.accept(
        StreamFragment(
            raw_text="plain metadata chunk",
            token_ids=(10, 11),
            token_logprobs=(-0.1, -0.2),
            parser_observation="flush_tokens=2",
        )
    )
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == [
        "plain metadata chunk"
    ]
    assert [delta.parser_observation for delta in deltas if delta.content_text] == [
        "flush_tokens=2"
    ]
    assert completed.assistant_text == "plain metadata chunk"
    assert completed.metrics["generated_token_count"] == 2
    assert completed.metrics["logprob_entry_count"] == 2
    assert completed.metrics["stream_interval_delta_flush_count"] == 1
    assert completed.metrics["stream_prefix_hold_chars"] == 0
    assert completed.metrics["stream_short_reply_flush_count"] == 0


def test_token_byte_delta_decodes_complete_ascii_without_incremental_decoder(monkeypatch) -> None:
    assembler = RequestStreamAssembler(
        request_id="req-token-byte-fast-path",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    decoder_calls = 0
    original_decoder_factory = stream_assembler._UTF8_INCREMENTAL_DECODER

    def tracked_decoder_factory():
        nonlocal decoder_calls
        decoder_calls += 1  # pragma: no cover - this fast-path guard must stay cold
        return original_decoder_factory()  # pragma: no cover

    monkeypatch.setattr(stream_assembler, "_UTF8_INCREMENTAL_DECODER", tracked_decoder_factory)

    deltas = assembler.accept(StreamFragment(token_bytes=b"hello "))
    deltas += assembler.accept(StreamFragment(token_bytes=b"world"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas] == ["hello ", "world"]
    assert completed.assistant_text == "hello world"
    assert completed.raw_text == "hello world"
    assert completed.metrics["generated_token_count"] == 2
    assert completed.metrics["byte_fallback_decode_error_count"] == 0
    assert decoder_calls == 0


def test_token_byte_delta_preserves_split_multibyte_sequence(monkeypatch) -> None:
    assembler = RequestStreamAssembler(
        request_id="req-token-byte-split-multibyte",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    decoder_calls = 0
    original_decoder_factory = stream_assembler._UTF8_INCREMENTAL_DECODER

    def tracked_decoder_factory():
        nonlocal decoder_calls
        decoder_calls += 1
        return original_decoder_factory()

    monkeypatch.setattr(stream_assembler, "_UTF8_INCREMENTAL_DECODER", tracked_decoder_factory)

    assert assembler.accept(StreamFragment(token_bytes="€".encode("utf-8")[:1])) == []
    deltas = assembler.accept(StreamFragment(token_bytes="€".encode("utf-8")[1:]))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas] == ["€"]
    assert completed.assistant_text == "€"
    assert completed.raw_text == "€"
    assert completed.metrics["generated_token_count"] == 2
    assert completed.metrics["byte_fallback_merge_count"] == 1
    assert decoder_calls == 2


def test_token_byte_raw_parts_materialize_before_raw_text_delta() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-token-byte-then-raw-text",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )

    first = assembler.accept(StreamFragment(token_bytes=b"hello "))
    second = assembler.accept(StreamFragment(raw_text="hello world"))
    completed = assembler.completed()

    assert [delta.content_text for delta in first + second] == ["hello ", "world"]
    assert completed.assistant_text == "hello world"
    assert completed.raw_text == "hello world"
    assert completed.metrics["non_monotonic_stream_count"] == 0


def test_plain_buffer_with_marker_still_holds_partial_structural_prefix() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-marker-still-held",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    first = assembler.accept(StreamFragment(raw_text="alpha<tool_ca"))
    second = assembler.accept(
        StreamFragment(
            raw_text='alpha<tool_call>{"name":"search","arguments":{"q":"alpha"}}</tool_call>'
        )
    )
    completed = assembler.completed()

    assert [delta.content_text for delta in first if delta.content_text] == ["alpha"]
    assert [delta.tool_call.tool_name for delta in second if delta.tool_call] == ["search"]
    assert completed.assistant_text == "alpha"
    assert completed.metrics["stream_prefix_hold_chars"] == len("<tool_ca")


def test_pipe_tool_call_marker_is_parsed_without_public_markup_leak() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                '<|tool_call>call:native_mcp:execute_command{"command":"gh auth status"}'
                "<tool_call|>"
            )
        )
    )
    completed = assembler.completed()
    calls = [delta.tool_call for delta in deltas if delta.tool_call]

    assert len(calls) == 1
    assert calls[0].tool_name == "native_mcp:execute_command"
    assert calls[0].arguments_json_fragment == '{"command":"gh auth status"}'
    assert completed.assistant_text == ""
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_pipe_tool_call_relaxed_object_arguments_are_parsed() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-relaxed",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                '<|tool_call>call:native_mcp:execute_command{command: "gh auth status"}'
                "<tool_call|>"
            )
        )
    )
    calls = [delta.tool_call for delta in deltas if delta.tool_call]

    assert len(calls) == 1
    assert calls[0].arguments_json_fragment == '{"command":"gh auth status"}'


def test_pipe_tool_call_empty_parentheses_arguments_are_parsed() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-empty-parens",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text="<|tool_call>call:github_auth:github_auth_check()<tool_call|>"
        )
    )
    completed = assembler.completed()
    calls = [delta.tool_call for delta in deltas if delta.tool_call]

    assert len(calls) == 1
    assert calls[0].tool_name == "github_auth:github_auth_check"
    assert calls[0].arguments_json_fragment == "{}"
    assert completed.assistant_text == ""
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_pipe_tool_call_whitespace_parentheses_arguments_are_parsed() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-whitespace-parens",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text="<|tool_call>call:github_auth:github_auth_check( \n )<tool_call|>"
        )
    )
    completed = assembler.completed()
    calls = [delta.tool_call for delta in deltas if delta.tool_call]

    assert len(calls) == 1
    assert calls[0].tool_name == "github_auth:github_auth_check"
    assert calls[0].arguments_json_fragment == "{}"
    assert completed.metrics["malformed_tool_fragment_count"] == 0


def test_action_qualified_tool_name_is_normalized_to_declared_openai_tool() -> None:
    cases = (
        (
            "terminal.execute",
            '<|tool_call>call:terminal.execute{"command":"pwd"}<tool_call|>',
            "terminal",
            '{"command":"pwd"}',
        ),
        (
            "terminal:run_command",
            '<|tool_call>call:terminal:run_command{"command":"gh auth status"}<tool_call|>',
            "terminal",
            '{"command":"gh auth status"}',
        ),
        (
            "process/start",
            '<|tool_call>call:process/start{"command":"npm test"}<tool_call|>',
            "process",
            '{"command":"npm test"}',
        ),
    )

    for request_id, raw_text, expected_name, expected_arguments in cases:
        assembler = RequestStreamAssembler(
            request_id=request_id,
            reasoning_enabled=False,
            structured_output_mode="",
            tool_parser_mode="xml",
            allowed_tool_names=("terminal", "process"),
        )
        deltas = assembler.accept(StreamFragment(raw_text=raw_text))
        completed = assembler.completed()
        calls = [delta.tool_call for delta in deltas if delta.tool_call]

        assert len(calls) == 1
        assert calls[0].tool_name == expected_name
        assert calls[0].arguments_json_fragment == expected_arguments
        assert completed.metrics["tool_call_name_normalized_count"] == 1
        assert completed.metrics["unknown_tool_delta_count"] == 0


def test_unknown_tool_name_is_suppressed_when_openai_tools_are_declared() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-unknown-tool",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
        allowed_tool_names=("terminal",),
    )

    deltas = assembler.accept(
        StreamFragment(raw_text="<|tool_call>call:github_auth:github_auth_check()<tool_call|>")
    )
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert completed.assistant_text == ""
    assert completed.metrics["unknown_tool_delta_count"] == 1
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_pipe_tool_call_relaxed_object_arguments_preserve_quoted_commas() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-commas",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                '<|tool_call>call:native_mcp:execute_command{'
                'command: "printf \\"hello, world\\"", note: \'alpha, beta\', count: 2'
                "}<tool_call|>"
            )
        )
    )
    calls = [delta.tool_call for delta in deltas if delta.tool_call]

    assert len(calls) == 1
    assert calls[0].arguments_json_fragment == (
        '{"command":"printf \\"hello, world\\"","count":2,"note":"alpha, beta"}'
    )


def test_pipe_tool_call_marker_wins_when_it_appears_before_legacy_marker() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-first",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="xml",
    )
    assembler._buffer = (
        '<|tool_call>call:native_mcp:execute_command{"command":"gh auth status"}'
        "<tool_call|>"
        '<tool_call>{"name":"search","arguments":{}}</tool_call>'
    )

    assert assembler._next_structural_tag() == (
        RequestStreamAssembler._PIPE_TOOL_OPEN,
        0,
    )


def test_pipe_tool_call_marker_wins_when_it_appears_before_thinking_marker() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-before-think",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="xml",
    )
    assembler._buffer = (
        '<|tool_call>call:native_mcp:execute_command{"command":"gh auth status"}'
        "<tool_call|><think>later</think>"
    )

    assert assembler._next_structural_tag() == (
        RequestStreamAssembler._PIPE_TOOL_OPEN,
        0,
    )


def test_pipe_tool_call_partial_prefix_is_held() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-prefix",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    first = assembler.accept(StreamFragment(raw_text="alpha<|tool_ca"))
    second = assembler.accept(
        StreamFragment(
            raw_text=(
                'alpha<|tool_call>call:native_mcp:execute_command{"command":"gh auth status"}'
                "<tool_call|>"
            )
        )
    )
    completed = assembler.completed()

    assert [delta.content_text for delta in first if delta.content_text] == ["alpha"]
    assert [delta.tool_call.tool_name for delta in second if delta.tool_call] == [
        "native_mcp:execute_command"
    ]
    assert completed.assistant_text == "alpha"
    assert completed.metrics["stream_prefix_hold_chars"] == len("<|tool_ca")


def test_pipe_tool_call_markup_in_public_content_is_counted_as_leak() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-leak",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(StreamFragment(raw_text="visible <|tool_callx"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == [
        "visible <|tool_callx"
    ]
    assert completed.metrics["tool_call_markup_leak_count"] == 1


def test_pipe_tool_call_malformed_relaxed_arguments_are_skipped() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-malformed",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                "<|tool_call>call:native_mcp:execute_command{command}"
                "<tool_call|>"
            )
        )
    )
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert completed.metrics["malformed_tool_fragment_count"] == 1
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_relaxed_pipe_tool_call_arguments_parse_scalar_types() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-tool-call-scalars",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
    )

    parsed = assembler._parse_relaxed_object_arguments(
        "{text: bare, count: 2, ratio: 1.5, enabled: true, disabled: false, empty: null}"
    )

    assert parsed == {
        "text": "bare",
        "count": 2,
        "ratio": 1.5,
        "enabled": True,
        "disabled": False,
        "empty": None,
    }
    assert assembler._parse_relaxed_object_arguments("{}") == {}
    assert assembler._parse_relaxed_object_arguments("not-an-object") is None
    assert assembler._parse_relaxed_object_arguments("{: missing}") is None


def test_partial_structural_tag_suffix_checks_only_last_marker_candidate() -> None:
    class RecordingBuffer(str):
        def __new__(cls) -> "RecordingBuffer":
            instance = str.__new__(cls, "older<think>done</think>chunk-ending-with-partial-<tool")
            instance.rfind_calls = []
            return instance

        def rfind(self, sub: str, *args: object) -> int:  # type: ignore[override]
            self.rfind_calls.append(sub)
            return super().rfind(sub, *args)

    assembler = RequestStreamAssembler(
        request_id="req-partial-suffix-fast-path",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    buffer = RecordingBuffer()
    assembler._buffer = buffer

    assert assembler._has_partial_structural_tag_suffix() is True
    assert buffer.rfind_calls == ["<"]


def test_partial_structural_tag_suffix_returns_last_marker_match() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-partial-suffix-single-pass",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    assembler._buffer = "finished <think>trace</think> answer <tool"

    assert assembler._partial_structural_tag_suffix() == "<tool"


def test_partial_structural_tag_suffix_ignores_complete_or_unknown_markers() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-partial-suffix-no-false-positives",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assembler._buffer = "answer <tool_call>"
    assert assembler._partial_structural_tag_suffix() == ""

    assembler._buffer = "answer without marker"
    assert assembler._partial_structural_tag_suffix() == ""

    assembler._buffer = "answer <thi"
    assert assembler._partial_structural_tag_suffix() == "<thi"

    assembler._buffer = "answer <|channel>tho"
    assert assembler._partial_structural_tag_suffix() == "<|channel>tho"

    assembler._buffer = "answer <xml"
    assert assembler._partial_structural_tag_suffix() == ""

    assembler._buffer = "answer"
    assert assembler._partial_structural_tag_suffix() == ""


def test_partial_pipe_reasoning_leak_marker_increments_metric() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-partial-pipe-reasoning-leak",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )

    deltas = assembler.accept(StreamFragment(raw_text="visible <|channel>tho"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas] == ["visible "]
    assert completed.assistant_text == "visible <|channel>tho"
    assert completed.metrics["reasoning_leak_count"] == 1


def test_json_structured_output_partial_pipe_reasoning_prefix_counts_as_leak() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-json-partial-pipe-reasoning-prefix",
        reasoning_enabled=False,
        structured_output_mode="json_schema",
        tool_parser_mode="",
    )

    assert assembler.accept(StreamFragment(raw_text="<|channel>tho hidden preamble")) == []
    completed = assembler.completed()

    assert completed.assistant_text == ""
    assert completed.metrics["reasoning_leak_count"] == 1


def test_partial_structural_tag_suffix_checks_all_prefixes_in_one_endswith_call() -> None:
    test_partial_structural_tag_suffix_checks_only_last_marker_candidate()


def test_partial_structural_tag_suffix_returns_match_without_tuple_prescan() -> None:
    test_partial_structural_tag_suffix_returns_last_marker_match()


def test_stream_assembler_instances_do_not_share_request_state() -> None:
    assemblers = [
        RequestStreamAssembler(
            request_id=f"req-{index}",
            reasoning_enabled=True,
            structured_output_mode="",
            tool_parser_mode="qwen",
        )
        for index in range(1_000)
    ]

    for index, assembler in enumerate(assemblers):
        deltas = assembler.accept(
            StreamFragment(raw_text=f"<think>trace-{index}</think>answer-{index}")
        )
        assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == [f"trace-{index}"]
        assert [delta.content_text for delta in deltas if delta.content_text] == [f"answer-{index}"]

    for index, assembler in enumerate(assemblers):
        completed = assembler.completed()
        assert completed.assistant_text == f"answer-{index}"
        assert completed.reasoning_text == f"trace-{index}"
        assert completed.metrics["parser_state_bleed_count"] == 0


def test_stream_assembler_emits_only_unseen_tool_call_tails_for_cumulative_chunks() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-tools",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    first = assembler.accept(
        StreamFragment(
            raw_text='<tool_call>{"name":"tools-search","arguments":{"query":"alpha"}}'
        )
    )
    second = assembler.accept(
        StreamFragment(
            raw_text=(
                '<tool_call>{"name":"tools-search","arguments":{"query":"alpha"}}</tool_call>'
                '<tool_call>{"name":"tools-math","arguments":{"expr":"{1+2}"}}</tool_call>'
            )
        )
    )
    third = assembler.accept(
        StreamFragment(
            raw_text=(
                '<tool_call>{"name":"tools-search","arguments":{"query":"alpha"}}</tool_call>'
                '<tool_call>{"name":"tools-math","arguments":{"expr":"{1+2}"}}</tool_call>'
            )
        )
    )

    assert [delta.tool_call.tool_name for delta in first if delta.tool_call] == []
    assert [delta.tool_call.tool_name for delta in second if delta.tool_call] == [
        "tools-search",
        "tools-math",
    ]
    assert [delta.tool_call.tool_name for delta in third if delta.tool_call] == []
    assert assembler.completed().metrics["duplicate_tool_delta_count"] == 0
    assert assembler.completed().metrics["stream_parser_request_context_mode"] == "tool_parser"
    assert assembler.completed().metrics["tool_call_markup_leak_count"] == 0


def test_json_structured_output_strips_reasoning_prefix_before_first_json_delimiter() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-json",
        reasoning_enabled=False,
        structured_output_mode="json_object",
        tool_parser_mode="",
    )

    deltas = assembler.accept(
        StreamFragment(raw_text='<think>internal plan</think>  {"answer": "done"}')
    )

    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == []
    assert "".join(delta.content_text for delta in deltas if delta.content_text) == '{"answer": "done"}'
    completed = assembler.completed()
    assert completed.assistant_text == '{"answer": "done"}'
    assert completed.reasoning_text == ""
    assert completed.metrics["reasoning_leak_count"] == 0


def test_explicit_tool_parser_survives_structured_json_mode() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-json-tools",
        reasoning_enabled=True,
        structured_output_mode="json_schema",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                '<think>plan</think>'
                '<tool_call>{"name":"search","arguments":{"q":"json"}}</tool_call>'
                '{"answer":"done"}'
            )
        )
    )
    completed = assembler.completed()

    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == ["plan"]
    calls = [delta.tool_call for delta in deltas if delta.tool_call]
    assert [call.tool_name for call in calls] == ["search"]
    assert [delta.content_text for delta in deltas if delta.content_text] == ['{"answer":"done"}']
    assert completed.assistant_text == '{"answer":"done"}'
    assert completed.metrics["stream_parser_request_context_mode"] == "tool_parser"
    assert completed.metrics["tool_call_markup_leak_count"] == 0
    assert completed.metrics["reasoning_leak_count"] == 0


def test_bare_json_structured_output_mode_is_not_treated_as_json_only() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-bare-json-mode",
        reasoning_enabled=False,
        structured_output_mode="json",
        tool_parser_mode="",
    )

    deltas = assembler.accept(StreamFragment(raw_text='<think>internal</think>{"answer":"done"}'))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == ['{"answer":"done"}']
    assert completed.metrics["suppressed_reasoning_count"] == 1


def test_plain_reasoning_disabled_request_suppresses_think_blocks_with_metric() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-reasoning-disabled",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(StreamFragment(raw_text="<think>hidden</think>visible"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == ["visible"]
    assert completed.reasoning_text == ""
    assert completed.metrics["suppressed_reasoning_count"] == 1


def test_truncated_tool_call_is_recoverable_and_not_public_content() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-truncated",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(raw_text='visible <tool_call>{"name":"tools-search","arguments":{"query":"alpha"}')
    )
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert completed.assistant_text == "visible "
    assert completed.metrics["malformed_tool_fragment_count"] == 1


def test_empty_and_repeated_fragments_do_not_emit_deltas() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-empty",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assert assembler.accept(StreamFragment(raw_text="")) == []
    assert assembler.accept(StreamFragment(raw_text="hello"))[0].content_text == "hello"
    assert assembler.accept(StreamFragment(raw_text="hello")) == []
    assert assembler.completed().assistant_text == "hello"


def test_json_structured_output_without_json_delimiter_drops_hidden_prefix_on_completion() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-json-prefix",
        reasoning_enabled=False,
        structured_output_mode="json_schema",
        tool_parser_mode="",
    )

    assert assembler.accept(StreamFragment(raw_text="<think>hidden preamble")) == []
    completed = assembler.completed()

    assert completed.assistant_text == ""
    assert completed.reasoning_text == ""
    assert completed.metrics["reasoning_leak_count"] == 1


def test_split_structural_tag_preserves_content_until_tag_is_complete() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-split-tag",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    first = assembler.accept(StreamFragment(raw_text="alpha<"))
    deltas = assembler.accept(StreamFragment(raw_text="alpha<think>hidden</think> omega"))

    assert [delta.content_text for delta in first if delta.content_text] == ["alpha"]
    assert [delta.content_text for delta in deltas if delta.content_text] == [" omega"]
    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == ["hidden"]
    completed = assembler.completed()
    assert completed.metrics["stream_prefix_hold_chars"] == 1
    assert completed.metrics["stream_short_reply_flush_count"] == 1


def test_split_structural_tag_prefix_longer_than_one_character_is_not_public_content() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-split-tag-prefix",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    first = assembler.accept(StreamFragment(raw_text="alpha<thi"))
    deltas = assembler.accept(StreamFragment(raw_text="alpha<think>hidden</think> omega"))

    assert [delta.content_text for delta in first if delta.content_text] == ["alpha"]
    assert [delta.content_text for delta in deltas if delta.content_text] == [" omega"]
    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == ["hidden"]
    completed = assembler.completed()
    assert completed.metrics["stream_prefix_hold_chars"] == len("<thi")
    assert completed.metrics["stream_short_reply_flush_count"] == 1


def test_split_tool_tag_prefix_longer_than_one_character_is_not_public_content() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-split-tool-tag-prefix",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    first = assembler.accept(StreamFragment(raw_text="alpha<tool_ca"))
    deltas = assembler.accept(
        StreamFragment(
            raw_text='alpha<tool_call>{"name":"search","arguments":{"q":"alpha"}}</tool_call>'
        )
    )

    assert [delta.content_text for delta in first if delta.content_text] == ["alpha"]
    assert [delta.content_text for delta in deltas if delta.content_text] == []
    calls = [delta.tool_call for delta in deltas if delta.tool_call]
    assert [call.tool_name for call in calls] == ["search"]
    completed = assembler.completed()
    assert completed.metrics["stream_prefix_hold_chars"] == len("<tool_ca")
    assert completed.metrics["stream_short_reply_flush_count"] == 1


def test_short_visible_prefix_flushes_before_held_marker_prefix() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-short-prefix-flush",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(StreamFragment(raw_text="OK<"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == ["OK"]
    assert completed.assistant_text == "OK<"
    assert completed.metrics["stream_prefix_hold_chars"] == 1
    assert completed.metrics["stream_short_reply_flush_count"] == 1


def test_truncated_reasoning_is_recoverable_and_not_public_content() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-truncated-reasoning",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assert assembler.accept(StreamFragment(raw_text="<think>unfinished")) == []
    completed = assembler.completed()

    assert completed.assistant_text == ""
    assert completed.reasoning_text == ""
    assert completed.metrics["malformed_reasoning_count"] == 1
    assert completed.metrics["reasoning_channel_recovery_count"] == 1
    assert completed.metrics["malformed_tool_fragment_count"] == 0


def test_malformed_non_object_and_nameless_tool_calls_are_skipped() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-bad-tools",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                '<tool_call>{"name":"broken"</tool_call>'
                "<tool_call>[]</tool_call>"
                '<tool_call>{"arguments":{"query":"alpha"}}</tool_call>'
                "visible"
            )
        )
    )
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert [delta.content_text for delta in deltas if delta.content_text] == ["visible"]
    assert completed.metrics["malformed_tool_fragment_count"] == 3
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_duplicate_tool_call_fragments_are_skipped_when_raw_stream_replays_out_of_order() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-duplicate-tool",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    first = assembler.accept(
        StreamFragment(raw_text='<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>')
    )
    replay = assembler.accept(
        StreamFragment(raw_text='prefix <tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>')
    )
    completed = assembler.completed()

    assert [delta.tool_call.tool_name for delta in first if delta.tool_call] == ["search"]
    assert [delta.tool_call for delta in replay if delta.tool_call] == []
    assert completed.metrics["duplicate_tool_delta_count"] == 1
    assert completed.metrics["non_monotonic_stream_count"] == 1


def test_duplicate_model_call_id_skips_argument_serialization(monkeypatch) -> None:
    assembler = RequestStreamAssembler(
        request_id="req-duplicate-call-id-fast-path",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    dumps_calls = 0
    original_dumps = stream_assembler.json.dumps

    def counting_dumps(*args, **kwargs):
        nonlocal dumps_calls
        dumps_calls += 1
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(stream_assembler.json, "dumps", counting_dumps)
    raw_tool_call = (
        '<tool_call>{"id":"call-duplicate","name":"search","arguments":'
        '{"query":"alpha","payload":[1,2,3,4,5]}}</tool_call>'
    )

    first = assembler.accept(StreamFragment(raw_text=raw_tool_call))
    replay = assembler.accept(StreamFragment(raw_text=f"prefix {raw_tool_call}"))
    completed = assembler.completed()

    assert [delta.tool_call.call_id for delta in first if delta.tool_call] == ["call-duplicate"]
    assert [delta.tool_call for delta in replay if delta.tool_call] == []
    assert dumps_calls == 1
    assert completed.metrics["duplicate_tool_delta_count"] == 1
    assert completed.metrics["non_monotonic_stream_count"] == 1


def test_non_monotonic_raw_stream_is_observable(caplog) -> None:
    assembler = RequestStreamAssembler(
        request_id="req-non-monotonic",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    caplog.set_level(logging.WARNING, logger="worker.runtime.stream_assembler")
    assert assembler.accept(StreamFragment(raw_text="hello world"))[0].content_text == "hello world"
    assert assembler.accept(StreamFragment(raw_text="reset stream"))[0].content_text == "reset stream"
    completed = assembler.completed()

    assert completed.metrics["non_monotonic_stream_count"] == 1
    assert "Non-monotonic stream fragment" in caplog.text
    assert "req-non-monotonic" in caplog.text


def test_repeated_tool_calls_with_distinct_call_ids_are_emitted() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-repeated-tool",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                '<tool_call>{"id":"call-1","name":"search","arguments":{"q":"apple"}}</tool_call>'
                '<tool_call>{"id":"call-2","name":"search","arguments":{"q":"apple"}}</tool_call>'
            )
        )
    )

    calls = [delta.tool_call for delta in deltas if delta.tool_call]
    assert [call.call_id for call in calls] == ["call-1", "call-2"]
    assert [call.tool_name for call in calls] == ["search", "search"]
    assert assembler.completed().metrics["duplicate_tool_delta_count"] == 0


def test_first_json_delimiter_prefers_array_when_it_appears_first() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-array-first",
        reasoning_enabled=False,
        structured_output_mode="json_schema",
        tool_parser_mode="",
    )

    assert assembler._first_json_delimiter("prefix [1, 2]{\"later\": true}") == 7


def test_request_context_mode_marks_structured_json_and_plain_streams() -> None:
    structured = RequestStreamAssembler(
        request_id="req-structured-context",
        reasoning_enabled=False,
        structured_output_mode="json_schema",
        tool_parser_mode="",
    )
    structured_with_tools = RequestStreamAssembler(
        request_id="req-structured-tool-context",
        reasoning_enabled=False,
        structured_output_mode="json_schema",
        tool_parser_mode="qwen",
    )
    plain = RequestStreamAssembler(
        request_id="req-plain-context",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )

    assert structured.completed().metrics["stream_parser_request_context_mode"] == "structured_json"
    assert structured_with_tools.completed().metrics["stream_parser_request_context_mode"] == "tool_parser"
    assert plain.completed().metrics["stream_parser_request_context_mode"] == "plain"


def test_stream_interval_flush_tracks_generated_token_and_logprob_parity() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-stream-interval-metadata",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text="Alpha Beta",
            token_ids=(101, 102),
            token_logprobs=(-0.1, -0.2),
            parser_observation="flush_tokens=2",
        )
    )
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == ["Alpha Beta"]
    assert [delta.parser_observation for delta in deltas if delta.content_text] == ["flush_tokens=2"]
    assert completed.metrics["generated_token_count"] == 2
    assert completed.metrics["logprob_entry_count"] == 2
    assert completed.metrics["stream_interval_delta_flush_count"] == 1
    assert completed.metrics["token_logprob_mismatch_count"] == 0


def test_byte_fallback_token_fragments_decode_to_complete_unicode_text() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-byte-fallback",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )

    first = assembler.accept(
        StreamFragment(
            token_bytes=b"\xe6\x9d",
            token_ids=(201,),
            token_logprobs=(-0.3,),
            parser_observation="byte-prefix",
        )
    )
    second = assembler.accept(
        StreamFragment(
            token_bytes=b"\xb1",
            token_ids=(202,),
            token_logprobs=(-0.4,),
            parser_observation="byte-complete",
        )
    )
    completed = assembler.completed()

    assert first == []
    assert [delta.content_text for delta in second if delta.content_text] == ["東"]
    assert [delta.parser_observation for delta in second if delta.content_text] == ["byte-complete"]
    assert completed.assistant_text == "東"
    assert completed.metrics["byte_fallback_merge_count"] == 1
    assert completed.metrics["generated_token_count"] == 2
    assert completed.metrics["logprob_entry_count"] == 2


def test_empty_thinking_block_is_suppressed_as_thinking_off_sentinel() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-empty-thinking-sentinel",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(StreamFragment(raw_text="<think>\n\t </think>42"))
    completed = assembler.completed()

    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == []
    assert [delta.content_text for delta in deltas if delta.content_text] == ["42"]
    assert completed.reasoning_text == ""
    assert completed.assistant_text == "42"
    assert completed.metrics["empty_thinking_sentinel_count"] == 1
    assert completed.metrics["reasoning_leak_count"] == 0


def test_pipe_reasoning_channel_is_suppressed_and_visible_tail_emitted() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-pipe-reasoning-channel",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(raw_text="<|channel>thought\ninternal plan<channel|>READY")
    )
    completed = assembler.completed()

    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == []
    assert [delta.content_text for delta in deltas if delta.content_text] == ["READY"]
    assert completed.assistant_text == "READY"
    assert completed.reasoning_text == ""
    assert completed.metrics["suppressed_reasoning_count"] == 1
    assert completed.metrics["reasoning_parser_bypassed_count"] == 1
    assert completed.metrics["reasoning_leak_count"] == 0


def test_empty_pipe_reasoning_channel_is_suppressed_as_thinking_off_sentinel() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-empty-pipe-reasoning-sentinel",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(StreamFragment(raw_text="<|channel>thought\n<channel|>READY"))
    completed = assembler.completed()

    assert [delta.content_text for delta in deltas if delta.content_text] == ["READY"]
    assert completed.assistant_text == "READY"
    assert completed.reasoning_text == ""
    assert completed.metrics["empty_thinking_sentinel_count"] == 1
    assert completed.metrics["reasoning_leak_count"] == 0


def test_unclosed_reasoning_channel_recovers_visible_answer_tail_at_eos() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-unclosed-reasoning-visible-tail",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assert assembler.accept(StreamFragment(raw_text="<think>plan step\n\nFinal answer")) == []
    completed = assembler.completed()

    assert completed.reasoning_text == "plan step"
    assert completed.assistant_text == "Final answer"
    assert completed.metrics["malformed_reasoning_count"] == 1
    assert completed.metrics["reasoning_channel_recovery_count"] == 1


def test_unclosed_pipe_reasoning_channel_recovers_visible_answer_tail_at_eos() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-unclosed-pipe-reasoning-visible-tail",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assert assembler.accept(StreamFragment(raw_text="<|channel>thought\nplan step\n\nFinal answer")) == []
    completed = assembler.completed()

    assert completed.reasoning_text == "plan step"
    assert completed.assistant_text == "Final answer"
    assert completed.metrics["malformed_reasoning_count"] == 1
    assert completed.metrics["reasoning_channel_recovery_count"] == 1
    assert completed.metrics["reasoning_leak_count"] == 0


def test_reasoning_disabled_request_suppresses_hidden_blocks_without_reasoning_metadata() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-disabled-reasoning-bypass",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(StreamFragment(raw_text="<think>hidden</think>visible"))
    completed = assembler.completed()

    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == []
    assert [delta.content_text for delta in deltas if delta.content_text] == ["visible"]
    assert completed.reasoning_text == ""
    assert completed.metrics["reasoning_parser_bypassed_count"] == 1


def test_effective_parser_config_receipt_is_available_from_completion_metrics() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-effective-parser-config",
        reasoning_enabled=True,
        structured_output_mode="json_schema",
        tool_parser_mode="qwen",
    )

    config = json.loads(str(assembler.completed().metrics["effective_parser_config_json"]))

    assert config == {
        "reasoning_enabled": True,
        "request_context_mode": "tool_parser",
        "structured_output_mode": "json_schema",
        "tool_parser_mode": "qwen",
    }


def test_effective_parser_config_receipt_reuses_encoding_for_same_config(monkeypatch) -> None:
    stream_assembler._cached_effective_parser_config_json.cache_clear()
    encode_calls = 0
    original_encode = stream_assembler._COMPACT_SORTED_JSON_ENCODER.encode

    def counting_encode(payload):
        nonlocal encode_calls
        encode_calls += 1
        return original_encode(payload)

    monkeypatch.setattr(stream_assembler._COMPACT_SORTED_JSON_ENCODER, "encode", counting_encode)

    first = RequestStreamAssembler(
        request_id="req-effective-parser-cache-1",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    second = RequestStreamAssembler(
        request_id="req-effective-parser-cache-2",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )

    assert first.completed().metrics["effective_parser_config_json"] == (
        second.completed().metrics["effective_parser_config_json"]
    )
    assert encode_calls == 1
    stream_assembler._cached_effective_parser_config_json.cache_clear()


def test_token_metadata_records_logprob_only_and_mismatch_cases() -> None:
    logprob_only = RequestStreamAssembler(
        request_id="req-logprob-only",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    logprob_only.accept(StreamFragment(raw_text="x", token_logprobs=(-0.5,)))
    logprob_metrics = logprob_only.completed().metrics
    assert logprob_metrics["generated_token_count"] == 1
    assert logprob_metrics["logprob_entry_count"] == 1

    mismatch = RequestStreamAssembler(
        request_id="req-logprob-mismatch",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    mismatch.accept(StreamFragment(raw_text="xy", token_ids=(1, 2), token_logprobs=(-0.5,)))
    mismatch_metrics = mismatch.completed().metrics
    assert mismatch_metrics["generated_token_count"] == 2
    assert mismatch_metrics["logprob_entry_count"] == 1
    assert mismatch_metrics["token_logprob_mismatch_count"] == 1


def test_byte_fallback_defensive_paths_are_observable() -> None:
    incomplete = RequestStreamAssembler(
        request_id="req-incomplete-byte",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    assert incomplete.accept(StreamFragment(token_bytes=b"\xe6")) == []
    incomplete_completed = incomplete.completed()
    assert incomplete_completed.assistant_text == "\ufffd"
    assert incomplete_completed.metrics["generated_token_count"] == 1
    assert incomplete_completed.metrics["byte_fallback_decode_error_count"] == 1

    invalid = RequestStreamAssembler(
        request_id="req-invalid-byte",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="",
    )
    deltas = invalid.accept(StreamFragment(token_bytes=b"\xff"))
    invalid_completed = invalid.completed()
    assert [delta.content_text for delta in deltas if delta.content_text] == ["\ufffd"]
    assert invalid_completed.metrics["byte_fallback_decode_error_count"] == 1


def test_unclosed_reasoning_recovery_handles_disabled_and_marker_paths() -> None:
    disabled = RequestStreamAssembler(
        request_id="req-disabled-unclosed-reasoning",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    disabled.accept(StreamFragment(raw_text="<think>hidden\n\nVisible"))
    disabled_completed = disabled.completed()
    assert disabled_completed.assistant_text == "Visible"
    assert disabled_completed.reasoning_text == ""
    assert disabled_completed.metrics["reasoning_parser_bypassed_count"] == 1

    marker = RequestStreamAssembler(
        request_id="req-marker-unclosed-reasoning",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    marker.accept(StreamFragment(raw_text="<think>hidden\nAnswer: 42"))
    marker_completed = marker.completed()
    assert marker_completed.reasoning_text == "hidden"
    assert marker_completed.assistant_text == "Answer: 42"

    blank = RequestStreamAssembler(
        request_id="req-blank-unclosed-reasoning",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    blank.accept(StreamFragment(raw_text="<think>   "))
    blank_completed = blank.completed()
    assert blank_completed.assistant_text == ""
    assert blank_completed.reasoning_text == ""


def test_unclosed_reasoning_recovery_preserves_hidden_when_visible_tail_is_empty() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-empty-visible-unclosed-reasoning",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assembler.accept(StreamFragment(raw_text="<think>hidden plan\n\n"))
    completed = assembler.completed()

    assert completed.reasoning_text == "hidden plan"
    assert completed.assistant_text == ""
    assert completed.metrics["reasoning_channel_recovery_count"] == 1


def test_unclosed_reasoning_recovery_marker_avoids_plain_phrase_false_positive() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-final-phrase-not-visible-marker",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assembler.accept(StreamFragment(raw_text="<think>hidden\nFinal boss is defeated."))
    completed = assembler.completed()

    assert completed.reasoning_text == ""
    assert completed.assistant_text == ""
    assert completed.metrics["reasoning_channel_recovery_count"] == 1
