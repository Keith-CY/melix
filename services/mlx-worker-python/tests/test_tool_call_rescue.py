from __future__ import annotations

import ast
import xml.etree.ElementTree as ElementTree

from worker.runtime import tool_call_rescue
from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


def test_tool_call_rescue_parses_xml_fenced_and_vendor_formats() -> None:
    cases = (
        (
            "req-rescue-xml-invoke",
            '<invoke name="visit">{"url":"fixture://docs/provider-contract","extract":"text"}</invoke>',
            "visit",
            '{"extract":"text","url":"fixture://docs/provider-contract"}',
        ),
        (
            "req-rescue-fenced-json",
            '```json\n{"tool":"search","args":{"query":"Melix release notes","max_results":1}}\n```',
            "text_search",
            '{"max_results":1,"query":"Melix release notes"}',
        ),
        (
            "req-rescue-tool-call-marker",
            '[TOOL_CALL]{"name":"web_search","arguments":{"query":"Melix bootstrap"}}[/TOOL_CALL]',
            "text_search",
            '{"query":"Melix bootstrap"}',
        ),
        (
            "req-rescue-minimax-tool-code",
            '<tool_code>browse({"url":"fixture://kb/server-session","extract":"text"})</tool_code>',
            "visit",
            '{"extract":"text","url":"fixture://kb/server-session"}',
        ),
        (
            "req-rescue-deepseek-xml",
            (
                "<tool_call><name>calculator</name>"
                '<arguments>{"code":"18 + 24"}</arguments></tool_call>'
            ),
            "local_compute",
            '{"code":"18 + 24"}',
        ),
    )

    for request_id, raw_text, expected_name, expected_arguments in cases:
        assembler = RequestStreamAssembler(
            request_id=request_id,
            reasoning_enabled=False,
            structured_output_mode="",
            tool_parser_mode="xml",
            allowed_tool_names=("text_search", "visit", "local_compute"),
        )

        deltas = assembler.accept(StreamFragment(raw_text=raw_text))
        completed = assembler.completed()
        calls = [delta.tool_call for delta in deltas if delta.tool_call]

        assert len(calls) == 1
        assert calls[0].tool_name == expected_name
        assert calls[0].arguments_json_fragment == expected_arguments
        assert completed.assistant_text == ""
        assert completed.metrics["tool_call_markup_leak_count"] == 0
        assert completed.metrics["unknown_tool_delta_count"] == 0
        assert "xml_invoke_tool_call" in str(
            completed.metrics["stream_parser_accepted_wire_formats"]
        )
        assert completed.metrics["stream_parser_rescue_path"] == "local_tool_call_format_rescue"


def test_qwen_parser_rescue_requires_declared_xml_fallback() -> None:
    raw_text = '[TOOL_CALL]{"name":"search","arguments":{"query":"Melix"}}[/TOOL_CALL]'
    qwen_only = RequestStreamAssembler(
        request_id="req-qwen-no-rescue-fallback",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
        allowed_tool_names=("text_search",),
    )

    qwen_deltas = qwen_only.accept(StreamFragment(raw_text=raw_text))
    qwen_completed = qwen_only.completed()

    assert [delta.tool_call for delta in qwen_deltas if delta.tool_call] == []
    assert qwen_completed.assistant_text == raw_text
    assert qwen_completed.metrics["stream_parser_rescue_path"] == ""

    qwen_with_fallback = RequestStreamAssembler(
        request_id="req-qwen-rescue-fallback",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="qwen",
        tool_parser_fallback_mode="xml",
        allowed_tool_names=("text_search",),
    )

    fallback_deltas = qwen_with_fallback.accept(StreamFragment(raw_text=raw_text))
    fallback_completed = qwen_with_fallback.completed()
    fallback_calls = [delta.tool_call for delta in fallback_deltas if delta.tool_call]

    assert [call.tool_name for call in fallback_calls] == ["text_search"]
    assert fallback_completed.assistant_text == ""
    assert fallback_completed.metrics["stream_parser_rescue_path"] == (
        "local_tool_call_format_rescue"
    )


def test_tool_call_rescue_parses_nested_and_function_envelopes() -> None:
    cases = (
        (
            "req-rescue-function-json",
            '```json\n{"function":{"name":"search","arguments":"{\\"query\\":\\"Melix docs\\"}"}}\n```',
            "text_search",
            '{"query":"Melix docs"}',
        ),
        (
            "req-rescue-invoke-children",
            (
                "<invoke><tool_name>browse</tool_name>"
                '<args>{"url":"fixture://docs/provider-contract"}</args></invoke>'
            ),
            "visit",
            '{"url":"fixture://docs/provider-contract"}',
        ),
        (
            "req-rescue-invoke-attribute-args",
            '<invoke tool="search" arguments="{query: \'Melix bootstrap\'}"></invoke>',
            "text_search",
            '{"query":"Melix bootstrap"}',
        ),
        (
            "req-rescue-function-kwargs",
            "<tool_code>calculator(code='18 + 24')</tool_code>",
            "local_compute",
            '{"code":"18 + 24"}',
        ),
        (
            "req-rescue-function-attribute",
            "<tool_code>browser.visit(url='fixture://kb/server-session')</tool_code>",
            "visit",
            '{"url":"fixture://kb/server-session"}',
        ),
    )

    for request_id, raw_text, expected_name, expected_arguments in cases:
        assembler = RequestStreamAssembler(
            request_id=request_id,
            reasoning_enabled=False,
            structured_output_mode="",
            tool_parser_mode="xml",
            allowed_tool_names=("text_search", "visit", "local_compute"),
        )

        deltas = assembler.accept(StreamFragment(raw_text=raw_text))
        completed = assembler.completed()
        calls = [delta.tool_call for delta in deltas if delta.tool_call]

        assert len(calls) == 1
        assert calls[0].tool_name == expected_name
        assert calls[0].arguments_json_fragment == expected_arguments
        assert completed.metrics["malformed_tool_fragment_count"] == 0
        assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_parses_fenced_json_tool_call_arrays() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-rescue-fenced-array",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
        allowed_tool_names=("text_search", "visit"),
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                "```json\n"
                '[{"tool":"search","args":{"query":"Melix"}},'
                '{"name":"browse","arguments":{"url":"fixture://docs/provider-contract"}}]'
                "\n```"
            )
        )
    )
    completed = assembler.completed()
    calls = [delta.tool_call for delta in deltas if delta.tool_call]

    assert [call.tool_name for call in calls] == ["text_search", "visit"]
    assert [call.arguments_json_fragment for call in calls] == [
        '{"query":"Melix"}',
        '{"url":"fixture://docs/provider-contract"}',
    ]
    assert completed.assistant_text == ""
    assert completed.metrics["malformed_tool_fragment_count"] == 0
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_strips_markup_around_visible_text() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-rescue-visible-tail",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
        allowed_tool_names=("text_search",),
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                "before "
                '[TOOL_CALL]{"name":"search","arguments":{"query":"Melix"}}[/TOOL_CALL]'
                " after"
            )
        )
    )
    completed = assembler.completed()

    assert [delta.tool_call.tool_name for delta in deltas if delta.tool_call] == ["text_search"]
    assert completed.assistant_text == "before  after"
    assert "[TOOL_CALL]" not in completed.assistant_text
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_holds_split_prefix_without_public_leak() -> None:
    cases = (
        (
            "req-rescue-split-bracket",
            "before [TOOL_",
            'before [TOOL_CALL]{"name":"search","arguments":{"query":"Melix"}}[/TOOL_CALL] after',
            "text_search",
            len("[TOOL_"),
        ),
        (
            "req-rescue-split-invoke",
            "before <inv",
            'before <invoke name="browse">{"url":"fixture://docs/provider-contract"}</invoke> after',
            "visit",
            len("<inv"),
        ),
        (
            "req-rescue-split-fence",
            "before ```j",
            'before ```json\n{"name":"calculator","arguments":{"code":"18 + 24"}}\n``` after',
            "local_compute",
            len("```j"),
        ),
    )

    for request_id, first_raw, second_raw, expected_name, expected_hold_chars in cases:
        assembler = RequestStreamAssembler(
            request_id=request_id,
            reasoning_enabled=False,
            structured_output_mode="",
            tool_parser_mode="xml",
            allowed_tool_names=("text_search", "visit", "local_compute"),
        )

        first = assembler.accept(StreamFragment(raw_text=first_raw))
        second = assembler.accept(StreamFragment(raw_text=second_raw))
        completed = assembler.completed()

        assert [delta.content_text for delta in first if delta.content_text] == ["before "]
        assert [delta.tool_call.tool_name for delta in second if delta.tool_call] == [expected_name]
        assert completed.assistant_text == "before  after"
        assert completed.metrics["stream_prefix_hold_chars"] == expected_hold_chars
        assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_preserves_non_tool_json_fence_as_visible_text() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-rescue-visible-json-fence",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
        allowed_tool_names=("text_search",),
    )

    raw_text = '```json\n{"status":"ok"}\n```'
    array_text = '```json\n[{"arguments":{"query":"Melix"}}]\n```'
    deltas = assembler.accept(StreamFragment(raw_text=raw_text))
    deltas += assembler.accept(StreamFragment(raw_text=raw_text + array_text))
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert completed.assistant_text == raw_text + array_text
    assert completed.metrics["malformed_tool_fragment_count"] == 0
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_malformed_json_is_counted_and_suppressed() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-rescue-malformed-json",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
        allowed_tool_names=("text_search",),
    )

    deltas = assembler.accept(
        StreamFragment(raw_text='[TOOL_CALL]{"name":"text_search","arguments":{[/TOOL_CALL]')
    )
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert completed.assistant_text == ""
    assert completed.metrics["malformed_tool_fragment_count"] == 1
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_python_fence_tool_json_reports_retryable_error() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-rescue-python-fence-tool-json",
        reasoning_enabled=False,
        structured_output_mode="",
        tool_parser_mode="xml",
        allowed_tool_names=("text_search",),
    )

    deltas = assembler.accept(
        StreamFragment(
            raw_text=(
                "```python\n"
                '{"name":"search","arguments":{"query":"Melix wrong envelope"}}'
                "\n```"
            )
        )
    )
    completed = assembler.completed()

    assert [delta.tool_call for delta in deltas if delta.tool_call] == []
    assert completed.assistant_text == ""
    assert completed.metrics["tool_parser_retryable_error_count"] == 1
    assert completed.metrics["tool_parser_retryable_error_code"] == (
        "tool_call_wrong_envelope_python_fence"
    )
    assert "Move the JSON tool call into an accepted tool-call envelope" in str(
        completed.metrics["tool_parser_retryable_error_message"]
    )
    assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_unclosed_envelopes_wait_then_suppress_at_completion() -> None:
    cases = (
        ("req-rescue-unclosed-bracket", "[TOOL_CALL]", "open"),
        ("req-rescue-unclosed-fence-header", "```json", "open"),
        ("req-rescue-unclosed-fence-body", '```json\n{"name":"search","arguments":{}}', "open"),
        ("req-rescue-unclosed-invoke-header", "<invoke", "open"),
        ("req-rescue-unclosed-invoke-body", '<invoke name="search">{"query":"Melix"}', "open"),
        ("req-rescue-unclosed-tool-code", "<tool_code>search({'query':'Melix'})", "open"),
    )

    for request_id, raw_text, expected_source in cases:
        assembler = RequestStreamAssembler(
            request_id=request_id,
            reasoning_enabled=False,
            structured_output_mode="",
            tool_parser_mode="xml",
            allowed_tool_names=("text_search",),
        )

        assert assembler.accept(StreamFragment(raw_text=raw_text)) == []
        completed = assembler.completed()

        assert completed.assistant_text == ""
        assert completed.metrics["malformed_tool_fragment_count"] == 1
        assert completed.metrics["tool_call_markup_leak_count"] == 0
        assert str(completed.metrics["channel_state_preferred_source"]) in {
            expected_source,
            "tool_call_tag",
            "",
        }


def test_tool_call_rescue_rejects_invalid_function_and_argument_shapes() -> None:
    cases = (
        "<tool_code>browse('fixture://docs/provider-contract')</tool_code>",
        "<tool_code>browse({'url':'fixture://docs/provider-contract'}, {'extra': true})</tool_code>",
        "<tool_code>browse(*args)</tool_code>",
        "<tool_code>browse(url=unknown)</tool_code>",
        "<tool_code>not_a_call</tool_code>",
        '<invoke name="search">not-json-args</invoke>',
    )

    for index, raw_text in enumerate(cases):
        assembler = RequestStreamAssembler(
            request_id=f"req-rescue-invalid-{index}",
            reasoning_enabled=False,
            structured_output_mode="",
            tool_parser_mode="xml",
            allowed_tool_names=("text_search", "visit"),
        )

        deltas = assembler.accept(StreamFragment(raw_text=raw_text))
        completed = assembler.completed()

        assert [delta.tool_call for delta in deltas if delta.tool_call] == []
        assert completed.assistant_text == ""
        assert completed.metrics["malformed_tool_fragment_count"] >= 1
        assert completed.metrics["tool_call_markup_leak_count"] == 0


def test_tool_call_rescue_helper_branches_cover_defensive_shapes() -> None:
    assert tool_call_rescue.extract_rescue_envelope("payload", "unknown", final=False)
    assert tool_call_rescue.find_fenced_tool_open("```python\nprint('x')\n```") == -1
    assert tool_call_rescue.partial_fenced_tool_label("") is True
    assert tool_call_rescue.find_xml_invoke_open("<invokeLater>") == -1
    assert tool_call_rescue.looks_like_tool_payload("") is False
    assert tool_call_rescue.looks_like_tool_payload("[1, 2]") is False
    assert tool_call_rescue.looks_like_tool_payload('[{"arguments":{}}]') is False
    assert tool_call_rescue.looks_like_tool_payload("<not-xml") is True
    assert tool_call_rescue.function_call_syntax("not a call") is False
    assert tool_call_rescue.parse_tool_body("") is None
    assert tool_call_rescue.parse_tool_body("<broken") is None
    assert tool_call_rescue.parse_tool_body("not a call") is None
    assert tool_call_rescue.parse_xml_tool_body("plain") is None
    assert tool_call_rescue.parse_xml_tool_body("<broken") is None
    assert tool_call_rescue.parse_xml_tool_body("<unknown></unknown>") is None
    assert tool_call_rescue.parse_function_tool_body("not_a_call") is None
    assert tool_call_rescue.parse_function_tool_body("browse('url')") is None
    assert tool_call_rescue.parse_function_tool_body("browse({}, {})") is None
    assert tool_call_rescue.parse_function_tool_body("browse(**kwargs)") is None
    assert tool_call_rescue.parse_function_tool_body("browse(url=unknown)") is None
    ast_node = ast.Constant(value="x")
    assert tool_call_rescue.ast_call_name(ast_node) == ""
    assert ast_node.value == "x"
    assert tool_call_rescue.local_xml_tag("{urn:test}tool_call") == "tool_call"
    root = ElementTree.fromstring("<tool_call><other>x</other></tool_call>")
    assert tool_call_rescue.xml_child_text(root, "name") == ""
    assert tool_call_rescue.parse_xml_arguments("") == {}
    assert tool_call_rescue.coerce_tool_arguments("") == {}
    assert tool_call_rescue.coerce_tool_arguments([]) is None
    assert (
        tool_call_rescue.resolve_tool_name(
            "unknown",
            allowed_tool_names=("text_search", "visit"),
            allowed_tool_name_set={"text_search", "visit"},
            allowed_tool_names_by_casefold={"text_search": "text_search", "visit": "visit"},
            allowed_tool_names_by_prefix=("text_search", "visit"),
        )
        is None
    )
