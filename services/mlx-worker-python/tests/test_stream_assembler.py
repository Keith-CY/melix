from __future__ import annotations

from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


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
        tool_parser_mode="qwen",
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

    assert assembler.accept(StreamFragment(raw_text="alpha<")) == []
    deltas = assembler.accept(StreamFragment(raw_text="alpha<think>hidden</think> omega"))

    assert [delta.content_text for delta in deltas if delta.content_text] == ["alpha", " omega"]
    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == ["hidden"]


def test_split_structural_tag_prefix_longer_than_one_character_is_not_public_content() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-split-tag-prefix",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    assert assembler.accept(StreamFragment(raw_text="alpha<thi")) == []
    deltas = assembler.accept(StreamFragment(raw_text="alpha<think>hidden</think> omega"))

    assert [delta.content_text for delta in deltas if delta.content_text] == ["alpha", " omega"]
    assert [delta.reasoning_text for delta in deltas if delta.reasoning_text] == ["hidden"]


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
    assert completed.metrics["malformed_tool_fragment_count"] == 1


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
