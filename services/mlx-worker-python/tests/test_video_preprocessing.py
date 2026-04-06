from __future__ import annotations

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.runtime.video_preprocessing import (
    MAX_VIDEO_FRAME_BUDGET,
    PreparedVideoInput,
    VideoPreprocessError,
    prepare_video_input,
)


def test_prepare_video_input_accepts_inline_bytes_with_explicit_metadata() -> None:
    part = common_pb2.MessagePart(
        video_bytes=b"video-bytes",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_VIDEO,
            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
            mime_type="video/mp4",
            format="mp4",
            filename="inline.mp4",
            duration_ms=4_000,
            frame_budget=8,
            start_ms=200,
            end_ms=2_000,
        ),
    )

    prepared = prepare_video_input(part)

    assert prepared == PreparedVideoInput(
        source_kind="inline",
        reference="inline:video",
        mime_type="video/mp4",
        format="mp4",
        filename="inline.mp4",
        byte_length=11,
        duration_ms=4_000,
        frame_budget=8,
        start_ms=200,
        end_ms=2_000,
        sha256_hex="79fd615a866fe7f9eb4da8d9c41ab57e3bd48056df42fd2c13e4d461a87afbe3",
    )


def test_prepare_video_input_accepts_uri_and_infers_format_from_reference() -> None:
    part = common_pb2.MessagePart(
        video_uri="https://example.com/media/demo.mov",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_VIDEO,
            source_kind=common_pb2.MEDIA_SOURCE_URI,
            duration_ms=12_000,
            frame_budget=12,
            start_ms=500,
            end_ms=3_500,
        ),
    )

    prepared = prepare_video_input(part)

    assert prepared.source_kind == "uri"
    assert prepared.reference == "https://example.com/media/demo.mov"
    assert prepared.mime_type == ""
    assert prepared.format == "mov"
    assert prepared.filename == "demo.mov"
    assert prepared.duration_ms == 12_000
    assert prepared.frame_budget == 12
    assert prepared.start_ms == 500
    assert prepared.end_ms == 3_500
    assert len(prepared.sha256_hex) == 64


def test_prepare_video_input_accepts_local_uri_and_mime_type_resolution() -> None:
    part = common_pb2.MessagePart(
        video_uri="/tmp/local-demo",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_VIDEO,
            source_kind=common_pb2.MEDIA_SOURCE_URI,
            mime_type="video/webm",
        ),
    )

    prepared = prepare_video_input(part)

    assert prepared.source_kind == "uri"
    assert prepared.reference == "/tmp/local-demo"
    assert prepared.format == "webm"
    assert prepared.filename == "local-demo"
    assert len(prepared.sha256_hex) == 64


def test_prepare_video_input_infers_format_from_plain_local_path() -> None:
    part = common_pb2.MessagePart(
        video_uri="/tmp/local-demo.m4v",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_VIDEO,
            source_kind=common_pb2.MEDIA_SOURCE_URI,
        ),
    )

    prepared = prepare_video_input(part)

    assert prepared.format == "m4v"
    assert prepared.filename == "local-demo.m4v"
    assert len(prepared.sha256_hex) == 64


@pytest.mark.parametrize(
    ("part", "message"),
    [
        (
            common_pb2.MessagePart(
                media=common_pb2.MediaMetadata(format="mov"),
            ),
            "No video input provided.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="ftp://example.com/demo.mov",
                media=common_pb2.MediaMetadata(format="mov"),
            ),
            "Unsupported video URI scheme: ftp.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://example.com/demo",
                media=common_pb2.MediaMetadata(mime_type="video/x-matroska"),
            ),
            "Unsupported video format: video/x-matroska.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="/tmp/local-demo.m4v",
                media=common_pb2.MediaMetadata(frame_budget=MAX_VIDEO_FRAME_BUDGET + 1),
            ),
            f"frame_budget must be less than or equal to {MAX_VIDEO_FRAME_BUDGET}.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://example.com/demo.mov",
                media=common_pb2.MediaMetadata(
                    format="mov",
                    start_ms=900,
                    end_ms=600,
                ),
            ),
            "end_ms must be greater than or equal to start_ms.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://example.com/demo.mov",
                media=common_pb2.MediaMetadata(
                    format="mov",
                    duration_ms=1_000,
                    end_ms=1_200,
                ),
            ),
            "end_ms must be less than or equal to duration_ms.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://example.com/demo.avi",
                media=common_pb2.MediaMetadata(format="avi"),
            ),
            "Unsupported video format: avi.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://example.com/media/blob",
                media=common_pb2.MediaMetadata(),
            ),
            "input_video.format or input_video.mime_type is required.",
        ),
    ],
)
def test_prepare_video_input_rejects_invalid_contracts(
    part: common_pb2.MessagePart,
    message: str,
) -> None:
    with pytest.raises(VideoPreprocessError, match=message):
        prepare_video_input(part)
