from __future__ import annotations

import json

from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment
from worker.runtime.token_route_receipt import TokenRouteReceipt


def test_token_route_receipt_records_visible_reasoning_and_tool_spans() -> None:
    receipt = TokenRouteReceipt(
        router_id="melix.worker.token_router",
        router_version="1",
        reasoning_enabled=False,
        reasoning_mode="disabled",
        tool_choice_policy="auto",
    )

    receipt.append_token_ids((101, 102, 103, 104))
    receipt.record_span(channel="visible_text", channel_source="raw_text")
    receipt.record_span(channel="hidden_reasoning", channel_source="reasoning_tag")
    receipt.record_span(channel="tool_call", channel_source="tool_call_tag")
    receipt.record_span(channel="visible_text", channel_source="raw_text")
    payload = json.loads(receipt.to_json())

    assert payload["router_id"] == "melix.worker.token_router"
    assert payload["router_version"] == "1"
    assert payload["tool_choice_policy"] == "auto"
    assert payload["reasoning_mode"] == "disabled"
    assert payload["visible_text_tokens"] == 2
    assert payload["hidden_reasoning_tokens"] == 1
    assert payload["fallback_raw_text_used"] is False
    assert [
        (
            record["token_id"],
            record["channel"],
            record["channel_source"],
            record["tool_choice_policy"],
            record["reasoning_mode"],
        )
        for record in payload["routes"]
    ] == [
        (101, "visible_text", "raw_text", "auto", "disabled"),
        (102, "hidden_reasoning", "reasoning_tag", "auto", "disabled"),
        (103, "tool_call", "tool_call_tag", "auto", "disabled"),
        (104, "visible_text", "raw_text", "auto", "disabled"),
    ]


def test_token_route_receipt_marks_raw_text_fallback_when_token_ids_are_absent() -> None:
    receipt = TokenRouteReceipt(
        router_id="melix.worker.token_router",
        router_version="1",
        reasoning_enabled=True,
    )

    receipt.record_span(channel="hidden_reasoning", channel_source="reasoning_tag")
    receipt.record_span(channel="visible_text", channel_source="raw_text")
    payload = json.loads(receipt.to_json())

    assert payload["fallback_raw_text_used"] is True
    assert payload["visible_text_tokens"] == 1
    assert payload["hidden_reasoning_tokens"] == 1
    assert [record["token_id"] for record in payload["routes"]] == [0, 1]


def test_token_route_receipt_uses_bounded_route_samples_for_long_streams() -> None:
    receipt = TokenRouteReceipt(
        router_id="melix.worker.token_router",
        router_version="1",
        reasoning_enabled=False,
    )

    for index in range(128):
        receipt.append_token_ids((index,))
        receipt.record_span(channel="visible_text", channel_source="raw_text")
    payload_json = receipt.to_json()
    payload = json.loads(payload_json)

    assert payload["visible_text_tokens"] == 128
    assert payload["hidden_reasoning_tokens"] == 0
    assert payload["route_count"] == 128
    assert payload["routes_sampled"] == 64
    assert len(payload["routes"]) == 64
    assert payload["routes"][0]["token_id"] == 0
    assert payload["routes"][-1]["token_id"] == 63
    assert payload["token_id"] == 127
    assert len(payload_json) < 9000


def test_token_route_receipt_inactive_path_skips_plain_visible_text_routes() -> None:
    receipt = TokenRouteReceipt(
        router_id="melix.worker.token_router",
        router_version="1",
        reasoning_enabled=False,
        enabled=False,
    )

    receipt.append_token_ids((101,))
    receipt.record_span(channel="visible_text", channel_source="raw_text")
    first_payload_json = receipt.to_json()
    second_payload_json = receipt.to_json()
    payload = json.loads(first_payload_json)

    assert first_payload_json is second_payload_json
    assert payload["route_tracking_enabled"] is False
    assert payload["route_count"] == 0
    assert payload["routes"] == []
    assert payload["visible_text_tokens"] == 0


def test_completion_keeps_finalized_tool_call_deltas_available_to_engine() -> None:
    assembler = RequestStreamAssembler(
        request_id="req-tool-count",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )

    deltas = assembler.accept(
        StreamFragment(raw_text='<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>')
    )
    completed = assembler.completed()

    assert [delta.tool_call.tool_name for delta in deltas if delta.tool_call] == ["search"]
    assert completed.assistant_text == ""
    assert completed.metrics["malformed_tool_fragment_count"] == 0
