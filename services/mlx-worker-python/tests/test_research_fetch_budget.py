from __future__ import annotations

import json

import pytest

from worker.productization.research_fetch_budget import (
    ResearchFetchBudgetPolicy,
    fetch_stream_with_budget,
)


def chunked(payload: bytes, size: int) -> tuple[bytes, ...]:
    return tuple(payload[index : index + size] for index in range(0, len(payload), size))


def test_text_fetch_soft_truncates_with_model_visible_notice_and_redacted_receipt() -> None:
    payload = b"alpha beta gamma delta epsilon"
    result = fetch_stream_with_budget(
        source_id="source-1",
        url="https://research.example.test/report.html?api_key=sk-secret",
        content_type="text/html; charset=utf-8",
        chunks=chunked(payload, 5),
        declared_total_bytes=len(payload),
        policy=ResearchFetchBudgetPolicy(default_max_bytes=16, hard_max_bytes=64),
    )

    assert result.content.startswith("[Melix partial content:")
    assert "alpha beta" in result.content
    assert "epsilon" not in result.content
    assert result.receipt["schema_version"] == "melix.research_fetch_budget_receipt.v1"
    assert result.receipt["source_id"] == "source-1"
    assert result.receipt["requested_max_bytes"] == 0
    assert result.receipt["default_max_bytes"] == 16
    assert result.receipt["effective_max_bytes"] == 16
    assert result.receipt["hard_max_bytes"] == 64
    assert result.receipt["fetched_bytes"] == 16
    assert result.receipt["declared_total_bytes"] == len(payload)
    assert result.receipt["truncated"] is True
    assert result.receipt["status"] == "truncated"
    assert result.receipt["blocked_reason"] == ""
    assert result.receipt["content_type"] == "text/html"
    assert result.receipt["partial_content_notice"] == "[Melix partial content: fetched 16 of 30 bytes.]"
    assert result.receipt["refetch_hint"] == "Increase max_bytes to fetch the complete source."
    assert result.receipt["raw_url_included"] is False
    receipt_payload = json.dumps(result.receipt, sort_keys=True)
    assert "research.example.test/report.html" not in receipt_payload
    assert "api_key" not in receipt_payload
    assert "sk-secret" not in receipt_payload


def test_declared_total_above_hard_max_refuses_before_stream_consumption() -> None:
    consumed = False

    def chunks():
        nonlocal consumed
        consumed = True
        yield b"this should never be read"

    result = fetch_stream_with_budget(
        source_id="source-large",
        url="https://research.example.test/large",
        content_type="text/plain",
        chunks=chunks(),
        declared_total_bytes=1_000,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=100, hard_max_bytes=256),
    )

    assert consumed is False
    assert result.content == ""
    assert result.receipt["status"] == "blocked"
    assert result.receipt["blocked_reason"] == "declared_total_exceeds_hard_max"
    assert result.receipt["fetched_bytes"] == 0
    assert result.receipt["declared_total_bytes"] == 1_000
    assert result.receipt["truncated"] is False


def test_requested_max_bytes_clamps_to_hard_max_and_honors_smaller_overrides() -> None:
    clamped = fetch_stream_with_budget(
        source_id="source-clamped",
        url="https://research.example.test/source",
        content_type="text/plain",
        chunks=(b"abcdef",),
        declared_total_bytes=6,
        requested_max_bytes=1_000,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=4, hard_max_bytes=8),
    )
    smaller = fetch_stream_with_budget(
        source_id="source-smaller",
        url="https://research.example.test/source",
        content_type="text/plain",
        chunks=(b"abcdef",),
        declared_total_bytes=6,
        requested_max_bytes=3,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=4, hard_max_bytes=8),
    )

    assert clamped.receipt["requested_max_bytes"] == 1_000
    assert clamped.receipt["effective_max_bytes"] == 8
    assert clamped.content == "abcdef"
    assert smaller.receipt["requested_max_bytes"] == 3
    assert smaller.receipt["effective_max_bytes"] == 3
    assert smaller.receipt["status"] == "truncated"
    assert "abc" in smaller.content
    assert "def" not in smaller.content


def test_cache_key_separates_truncated_and_full_fetches() -> None:
    truncated = fetch_stream_with_budget(
        source_id="source-cache",
        url="https://research.example.test/source",
        content_type="text/plain",
        chunks=(b"abcdef",),
        declared_total_bytes=6,
        requested_max_bytes=3,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=6, hard_max_bytes=10),
    )
    full = fetch_stream_with_budget(
        source_id="source-cache",
        url="https://research.example.test/source",
        content_type="text/plain",
        chunks=(b"abcdef",),
        declared_total_bytes=6,
        requested_max_bytes=6,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=6, hard_max_bytes=10),
    )
    full_again = fetch_stream_with_budget(
        source_id="source-cache",
        url=" https://research.example.test/source ",
        content_type="text/plain; charset=utf-8",
        chunks=(b"abcdef",),
        declared_total_bytes=6,
        requested_max_bytes=6,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=6, hard_max_bytes=10),
    )

    assert truncated.receipt["cache_key"] != full.receipt["cache_key"]
    assert full.receipt["cache_key"] == full_again.receipt["cache_key"]


def test_truncated_binary_and_pdf_sources_are_blocked_as_unparseable_evidence() -> None:
    for content_type in ("application/pdf", "application/octet-stream"):
        result = fetch_stream_with_budget(
            source_id="source-binary",
            url="https://research.example.test/file",
            content_type=content_type,
            chunks=(b"0123456789",),
            declared_total_bytes=10,
            requested_max_bytes=4,
            policy=ResearchFetchBudgetPolicy(default_max_bytes=4, hard_max_bytes=16),
        )

        assert result.content == ""
        assert result.receipt["status"] == "blocked"
        assert result.receipt["blocked_reason"] == "binary_truncation_not_parseable"
        assert result.receipt["truncated"] is True
        assert result.receipt["fetched_bytes"] == 4


def test_policy_limits_must_be_positive_and_ordered() -> None:
    with pytest.raises(ValueError, match="default_max_bytes must be positive"):
        ResearchFetchBudgetPolicy(default_max_bytes=0, hard_max_bytes=10)
    with pytest.raises(ValueError, match="hard_max_bytes must be positive"):
        ResearchFetchBudgetPolicy(default_max_bytes=1, hard_max_bytes=0)
    with pytest.raises(ValueError, match="default_max_bytes must not exceed hard_max_bytes"):
        ResearchFetchBudgetPolicy(default_max_bytes=20, hard_max_bytes=10)


def test_unknown_total_truncation_handles_empty_chunks_without_overreading() -> None:
    result = fetch_stream_with_budget(
        source_id="source-unknown-total",
        url="/local/research/source.txt",
        content_type="text/plain",
        chunks=(b"", b"ab", b"cdef"),
        requested_max_bytes=2,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=4, hard_max_bytes=8),
    )

    assert result.content == "[Melix partial content: fetched 2 of an unknown total bytes.]\nab"
    assert result.receipt["content_type"] == "text/plain"
    assert result.receipt["declared_total_bytes"] == 0
    assert result.receipt["fetched_bytes"] == 2
    assert result.receipt["status"] == "truncated"
    assert result.receipt["truncated"] is True


def test_declared_large_total_does_not_mark_short_stream_as_budget_truncated() -> None:
    result = fetch_stream_with_budget(
        source_id="source-short-stream",
        url="https://research.example.test/short",
        content_type="text/plain",
        chunks=(b"short",),
        declared_total_bytes=100,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=16, hard_max_bytes=128),
    )

    assert result.content == "short"
    assert result.receipt["fetched_bytes"] == 5
    assert result.receipt["declared_total_bytes"] == 100
    assert result.receipt["status"] == "ok"
    assert result.receipt["truncated"] is False
    assert result.receipt["partial_content_notice"] == ""


def test_invalid_budget_inputs_fall_back_without_leaking_normalized_url_details() -> None:
    bad_inputs = fetch_stream_with_budget(
        source_id="source-bad-inputs",
        url="HTTPS://Research.Example.Test:8443/path?q=secret",
        content_type="",
        chunks=(b"abc",),
        declared_total_bytes="unknown",  # type: ignore[arg-type]
        requested_max_bytes="NaN",  # type: ignore[arg-type]
        policy=ResearchFetchBudgetPolicy(default_max_bytes=5, hard_max_bytes=10),
    )
    non_positive = fetch_stream_with_budget(
        source_id="source-negative",
        url="HTTPS://Research.Example.Test:8443/path?q=secret",
        content_type="",
        chunks=(b"abc",),
        declared_total_bytes=-20,
        requested_max_bytes=-1,
        policy=ResearchFetchBudgetPolicy(default_max_bytes=5, hard_max_bytes=10),
    )

    assert bad_inputs.content == "abc"
    assert bad_inputs.receipt["requested_max_bytes"] == 0
    assert bad_inputs.receipt["declared_total_bytes"] == 0
    assert bad_inputs.receipt["effective_max_bytes"] == 5
    assert bad_inputs.receipt["content_type"] == "application/octet-stream"
    assert non_positive.receipt["requested_max_bytes"] == 0
    assert non_positive.receipt["declared_total_bytes"] == 0
    assert bad_inputs.receipt["cache_key"] == non_positive.receipt["cache_key"]
    receipt_payload = json.dumps(bad_inputs.receipt, sort_keys=True)
    assert "Research.Example.Test" not in receipt_payload
    assert "q=secret" not in receipt_payload


def test_malformed_urls_are_hashed_without_raising_or_leaking_receipt_details() -> None:
    result = fetch_stream_with_budget(
        source_id="source-malformed-url",
        url="https://Research.Example.Test:bad-port/path?q=secret",
        content_type="text/plain",
        chunks=(b"abc",),
        policy=ResearchFetchBudgetPolicy(default_max_bytes=5, hard_max_bytes=10),
    )

    assert result.content == "abc"
    assert result.receipt["status"] == "ok"
    assert result.receipt["raw_url_included"] is False
    receipt_payload = json.dumps(result.receipt, sort_keys=True)
    assert "Research.Example.Test" not in receipt_payload
    assert "bad-port" not in receipt_payload
    assert "q=secret" not in receipt_payload

    invalid_ipv6 = fetch_stream_with_budget(
        source_id="source-invalid-ipv6",
        url="https://[::1/path?q=secret",
        content_type="text/plain",
        chunks=(b"abc",),
        policy=ResearchFetchBudgetPolicy(default_max_bytes=5, hard_max_bytes=10),
    )

    assert invalid_ipv6.content == "abc"
    invalid_payload = json.dumps(invalid_ipv6.receipt, sort_keys=True)
    assert "[::1" not in invalid_payload
    assert "q=secret" not in invalid_payload


def test_non_string_url_and_content_type_inputs_are_defensive() -> None:
    result = fetch_stream_with_budget(
        source_id="source-defensive-inputs",
        url=None,  # type: ignore[arg-type]
        content_type=None,  # type: ignore[arg-type]
        chunks=(b"abc",),
        policy=ResearchFetchBudgetPolicy(default_max_bytes=5, hard_max_bytes=10),
    )

    assert result.content == "abc"
    assert result.receipt["content_type"] == "application/octet-stream"
    assert result.receipt["status"] == "ok"
    assert result.receipt["source_url_hash"]
