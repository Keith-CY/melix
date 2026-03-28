from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2


def test_message_part_metadata_preserves_multimodal_source_identity() -> None:
    part = common_pb2.MessagePart(
        image_uri="file:///tmp/cat.png",
        media=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_IMAGE,
            source_kind=common_pb2.MEDIA_SOURCE_URI,
            mime_type="image/png",
            format="png",
            preprocessing_hints={"detail": "high"},
        ),
    )

    round_tripped = common_pb2.MessagePart()
    round_tripped.ParseFromString(part.SerializeToString())

    assert round_tripped.image_uri == "file:///tmp/cat.png"
    assert round_tripped.media.media_type == common_pb2.MEDIA_TYPE_IMAGE
    assert round_tripped.media.source_kind == common_pb2.MEDIA_SOURCE_URI
    assert round_tripped.media.mime_type == "image/png"
    assert round_tripped.media.preprocessing_hints["detail"] == "high"


def test_audio_contracts_support_uri_and_inline_shapes() -> None:
    transcribe = inference_pb2.TranscribeRequest(
        audio_uri="file:///tmp/sample.wav",
        audio=common_pb2.MediaMetadata(
            media_type=common_pb2.MEDIA_TYPE_AUDIO,
            source_kind=common_pb2.MEDIA_SOURCE_URI,
            mime_type="audio/wav",
            format="wav",
        ),
        language="en",
    )
    speak = inference_pb2.SpeakRequest(
        input="hello",
        voice="alloy",
        format="wav",
        ext={"style": "neutral"},
    )

    assert transcribe.audio_uri == "file:///tmp/sample.wav"
    assert transcribe.audio.media_type == common_pb2.MEDIA_TYPE_AUDIO
    assert transcribe.audio.source_kind == common_pb2.MEDIA_SOURCE_URI
    assert transcribe.language == "en"
    assert speak.voice == "alloy"
    assert speak.ext["style"] == "neutral"


def test_model_info_contract_supports_task_visibility() -> None:
    info = maintenance_pb2.GetModelInfoResponse(
        ok=True,
        model_kind="speech",
        supported_modalities=["text", "audio"],
        supported_tasks=["speak"],
    )

    assert info.supported_modalities == ["text", "audio"]
    assert info.supported_tasks == ["speak"]
