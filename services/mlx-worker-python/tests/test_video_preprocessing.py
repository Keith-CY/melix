from __future__ import annotations

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.runtime import video_preprocessing
from worker.runtime.video_preprocessing import (
    MAX_VIDEO_FRAME_BUDGET,
    PreparedVideoInput,
    VideoPreprocessError,
    _parse_video_reference,
    _uri_identity_hash,
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
        bytes_data=b"video-bytes",
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
    assert prepared.bytes_data == b""
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
    assert prepared.bytes_data == b""
    assert prepared.format == "webm"
    assert prepared.filename == "local-demo"
    assert len(prepared.sha256_hex) == 64


class _CountingMedia:
    def __init__(self) -> None:
        self.byte_length_reads = 0

    def __getattribute__(self, name: str):
        if name == "byte_length":
            byte_length_reads = object.__getattribute__(self, "byte_length_reads")
            object.__setattr__(self, "byte_length_reads", byte_length_reads + 1)
            return 123
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        return "" if name in {"mime_type", "format", "filename"} else 0


class _CountingVideoPart:
    def __init__(self, media: _CountingMedia) -> None:
        self.media = media
        self.video_bytes = b""
        self.video_uri = "https://example.com/media/demo.mov"


def test_prepare_video_input_reuses_uri_byte_length_for_metadata_and_identity_hash() -> None:
    media = _CountingMedia()
    part = _CountingVideoPart(media)

    prepared = prepare_video_input(part)

    assert prepared.byte_length == 123
    assert media.byte_length_reads == 1
    assert len(prepared.sha256_hex) == 64


def test_prepare_video_input_reuses_parsed_uri_when_filename_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parse_calls = 0
    original_parse = video_preprocessing._parse_video_reference

    def counting_parse(reference: str):
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(reference)

    monkeypatch.setattr(video_preprocessing, "_parse_video_reference", counting_parse)
    part = common_pb2.MessagePart(
        video_uri="https://example.com/media/demo.mov",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_VIDEO,
            source_kind=common_pb2.MEDIA_SOURCE_URI,
        ),
    )

    prepared = prepare_video_input(part)

    assert prepared.format == "mov"
    assert prepared.filename == "demo.mov"
    assert parse_calls == 1


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


def test_parse_video_reference_decodes_remote_and_file_uris_once() -> None:
    remote = _parse_video_reference("https://example.com/media/demo%20clip.mov?cache=1")
    local = _parse_video_reference("file:///tmp/local%20demo.webm")

    assert remote.scheme == "https"
    assert remote.authority == "example.com"
    assert remote.decoded_path == "/media/demo clip.mov"
    assert remote.path_name == "demo clip.mov"
    assert remote.path_suffix == "mov"

    assert local.scheme == "file"
    assert local.authority == ""
    assert local.decoded_path == "/tmp/local demo.webm"
    assert local.path_name == "local demo.webm"
    assert local.path_suffix == "webm"


@pytest.mark.parametrize(
    ("reference", "expected_name", "expected_suffix"),
    [
        ("https://example.com/media/archive.demo.MP4", "archive.demo.MP4", "mp4"),
        ("https://example.com/media/demo.mov/", "demo.mov", "mov"),
        ("/tmp/.mp4", ".mp4", ""),
        ("relative/video.", "video.", ""),
    ],
)
def test_parse_video_reference_preserves_pathlib_suffix_edges(
    reference: str,
    expected_name: str,
    expected_suffix: str,
) -> None:
    parsed = _parse_video_reference(reference)

    assert parsed.path_name == expected_name
    assert parsed.path_suffix == expected_suffix


def test_uri_identity_hash_preserves_nul_framed_payload_digest() -> None:
    expected = "e3730f5d0390fa0e5ca66427b4af3d8222d03dbcbabde46cb417fe93681038f5"

    assert (
        _uri_identity_hash(
            uri="https://example.com/media/demo.mov",
            mime_type="video/quicktime",
            format_name="mov",
            filename="demo.mov",
            byte_length=123,
            duration_ms=12_000,
            frame_budget=12,
            start_ms=500,
            end_ms=3_500,
        )
        == expected
    )


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
                video_uri="http://example.com/demo.mov",
                media=common_pb2.MediaMetadata(format="mov"),
            ),
            "Unsupported video URI scheme: http.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https:///demo.mov",
                media=common_pb2.MediaMetadata(format="mov"),
            ),
            "Remote video URI requires a host.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://localhost/demo.mov",
                media=common_pb2.MediaMetadata(format="mov"),
            ),
            "Remote video URI host is not allowed: localhost.",
        ),
        (
            common_pb2.MessagePart(
                video_uri="https://127.0.0.1/demo.mov",
                media=common_pb2.MediaMetadata(format="mov"),
            ),
            "Remote video URI host is not allowed: 127.0.0.1.",
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
