from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
import wave

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2, runtime_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.engine.speech_core import SpeechCore
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.audio_preprocessing import AudioPreprocessError, prepare_audio_input
from worker.runtime.audio_runtime_protocols import SpeechResult, SpeechStreamFrame
from worker.runtime.deterministic_speech_runtime import DeterministicSpeechRuntime
from worker.runtime.deterministic_transcription_runtime import DeterministicTranscriptionRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


class LegacySpeechRuntime:
    runtime_name = "legacy-speech"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024

    def speak(self, loaded_model, request):
        return SpeechResult(audio_bytes=b"legacy", format=request.format or "wav")

    def last_probe_snapshot(self):
        return object()


class FailingSpeechStreamRuntime(LegacySpeechRuntime):
    def stream_speak(self, loaded_model, request):
        raise RuntimeError("stream failed")


class FailingAfterEnvelopeSpeechStreamRuntime(LegacySpeechRuntime):
    def stream_speak(self, loaded_model, request):
        yield SpeechStreamFrame(kind="envelope", audio_bytes=b"RIFF")
        raise RuntimeError("stream interrupted")


def build_services(**registry_kwargs):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
        **registry_kwargs,
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    maintenance_core = MaintenanceCore(registry, jobs_root=Path(".runtime/test-model-ops"))
    return runtime_service, inference_service, maintenance_core


def load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_transcribe_returns_text_from_inline_audio_bytes() -> None:
    runtime_service, inference_service, maintenance_core = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_transcription_model())

    response = inference_service.Transcribe(
        inference_pb2.TranscribeRequest(
            id=common_pb2.RequestIdentity(request_id="transcribe-inline"),
            model_handle=model_handle,
            audio_bytes=b"hello deterministic audio",
            format="wav",
            task="transcribe",
            audio=common_pb2.MediaMetadata(
                media_type=common_pb2.MEDIA_TYPE_AUDIO,
                source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                mime_type="audio/wav",
                format="wav",
                filename="inline.wav",
            ),
            language="en",
        ),
        context=None,
    )
    model_info = maintenance_core.get_model_info(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-transcribe")
    )

    assert response.error.code == ""
    assert response.text == "hello deterministic audio"
    assert response.language == "en"
    assert response.duration_seconds > 0.0
    assert model_info.ok is True
    assert model_info.supported_modalities == ["audio", "text"]
    assert model_info.supported_tasks == ["transcribe"]


def test_transcribe_reads_audio_from_file_uri(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_transcription_model())
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio file transcript")

    response = inference_service.Transcribe(
        inference_pb2.TranscribeRequest(
            id=common_pb2.RequestIdentity(request_id="transcribe-uri"),
            model_handle=model_handle,
            audio_uri=audio_path.as_uri(),
            format="wav",
            task="transcribe",
            audio=common_pb2.MediaMetadata(
                media_type=common_pb2.MEDIA_TYPE_AUDIO,
                source_kind=common_pb2.MEDIA_SOURCE_URI,
                mime_type="audio/wav",
                format="wav",
                filename=audio_path.name,
            ),
        ),
        context=None,
    )

    assert response.error.code == ""
    assert response.text == "audio file transcript"
    assert response.duration_seconds > 0.0


def test_speak_returns_audio_bytes_and_format() -> None:
    runtime_service, inference_service, maintenance_core = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_speech_model())

    response = inference_service.Speak(
        inference_pb2.SpeakRequest(
            id=common_pb2.RequestIdentity(request_id="speak-1"),
            model_handle=model_handle,
            input="hello speech",
            voice="alloy",
            format="wav",
            instructions="neutral",
        ),
        context=None,
    )
    model_info = maintenance_core.get_model_info(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-speech")
    )

    assert response.error.code == ""
    assert response.format == "wav"
    assert response.audio_bytes == b"VOICE=alloy\nFORMAT=wav\nTEXT=hello speech"
    assert model_info.ok is True
    assert model_info.supported_modalities == ["text", "audio"]
    assert model_info.supported_tasks == ["speak"]


def test_speak_stream_returns_progressive_wav_and_runtime_streaming_metrics() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_speech_model())

    events = list(
        inference_service.SpeakStream(
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="speak-stream-1"),
                model_handle=model_handle,
                input="hello streamed audio",
                voice="alloy",
                format="wav",
                streaming_enabled=True,
                stream_interval_ms=25,
            ),
            context=None,
        )
    )
    payload = b"".join(event.audio_bytes for event in events if event.audio_bytes)
    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats

    assert [event.kind for event in events] == [
        inference_pb2.SPEAK_STREAM_EVENT_KIND_ENVELOPE,
        inference_pb2.SPEAK_STREAM_EVENT_KIND_AUDIO_CHUNK,
        inference_pb2.SPEAK_STREAM_EVENT_KIND_FINISH,
    ]
    assert events[0].envelope.format == "wav"
    assert events[0].envelope.codec == "pcm_s16le"
    assert events[0].envelope.stream_interval_ms == 25
    assert payload.startswith(b"RIFF")
    with wave.open(BytesIO(payload), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 24_000
        assert handle.readframes(1)
    assert events[-1].finish.speech_streaming_enabled is True
    assert events[-1].finish.speech_streaming_interval_ms == 25
    assert events[-1].finish.speech_first_audio_latency_ms > 0.0
    assert events[-1].finish.audio_chunk_count == 1
    assert stats.last_speech_streaming_enabled is True
    assert stats.last_speech_streaming_interval_ms == 25
    assert stats.last_speech_first_audio_latency_ms > 0.0
    assert stats.last_audio_chunk_count == 1
    assert stats.last_audio_output_bytes == len(payload)


def test_audio_preprocessing_accepts_plain_local_paths_and_fills_metadata(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.raw"
    audio_path.write_bytes(b"path based audio")

    prepared = prepare_audio_input(
        inference_pb2.TranscribeRequest(
            audio_uri=str(audio_path),
            audio=common_pb2.MediaMetadata(
                media_type=common_pb2.MEDIA_TYPE_AUDIO,
                source_kind=common_pb2.MEDIA_SOURCE_URI,
            ),
        )
    )

    assert prepared.source_kind == "uri"
    assert prepared.format == "raw"
    assert prepared.filename == "sample.raw"
    assert prepared.decoded_text() == "path based audio"
    assert prepared.chunk_count >= 1


def test_audio_preprocessing_zero_copy_uri_skips_exists_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"zero copy audio")
    stat_calls = 0
    exists_spy = Mock(return_value=True)
    original_stat = Path.stat

    def counted_stat(self: Path):
        nonlocal stat_calls
        if self == audio_path:
            stat_calls += 1
        return original_stat(self)

    monkeypatch.setattr(Path, "stat", counted_stat)
    monkeypatch.setattr(Path, "exists", exists_spy)

    prepared = prepare_audio_input(
        inference_pb2.TranscribeRequest(audio_uri=audio_path.as_uri(), format="wav"),
        read_uri_bytes=False,
    )

    assert prepared.bytes_data == b""
    assert prepared.local_path == str(audio_path)
    assert prepared.preprocess_input_bytes == len(b"zero copy audio")
    assert exists_spy.call_count == 0
    assert stat_calls == 1


def test_audio_preprocessing_rejects_missing_and_unsupported_inputs(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.wav"

    with pytest.raises(AudioPreprocessError, match="No audio input provided"):
        prepare_audio_input(inference_pb2.TranscribeRequest())

    with pytest.raises(AudioPreprocessError, match="Missing local audio input"):
        prepare_audio_input(inference_pb2.TranscribeRequest(audio_uri=str(missing_path)))

    with pytest.raises(AudioPreprocessError, match="Unsupported audio URI scheme"):
        prepare_audio_input(inference_pb2.TranscribeRequest(audio_uri="https://example.com/audio.wav"))


def test_transcribe_and_speak_reject_wrong_loaded_model_kinds() -> None:
    runtime_service, inference_service, _ = build_services()
    text_model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    transcribe = inference_service.Transcribe(
        inference_pb2.TranscribeRequest(
            id=common_pb2.RequestIdentity(request_id="wrong-transcribe"),
            model_handle=text_model_handle,
            audio_bytes=b"hello",
        ),
        context=None,
    )
    speak = inference_service.Speak(
        inference_pb2.SpeakRequest(
            id=common_pb2.RequestIdentity(request_id="wrong-speak"),
            model_handle=text_model_handle,
            input="hello",
        ),
        context=None,
    )
    speak_stream = list(
        inference_service.SpeakStream(
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="wrong-speak-stream"),
                model_handle=text_model_handle,
                input="hello",
            ),
            context=None,
        )
    )
    missing_stream = list(
        inference_service.SpeakStream(
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="missing-speak-stream"),
                model_handle="missing",
                input="hello",
            ),
            context=None,
        )
    )

    assert transcribe.error.code == "invalid_argument"
    assert speak.error.code == "invalid_argument"
    assert speak_stream[0].error.code == "invalid_argument"
    assert missing_stream[0].error.code == "not_found"


def test_speak_stream_maps_unimplemented_runtime_errors_and_unknown_frames() -> None:
    runtime_service, inference_service, _ = build_services(speech_runtime=LegacySpeechRuntime())
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_speech_model())

    events = list(
        inference_service.SpeakStream(
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="legacy-speak-stream"),
                model_handle=model_handle,
                input="hello",
            ),
            context=None,
        )
    )
    unknown_frame = SpeechCore._stream_event(SpeechStreamFrame(kind="unexpected"))  # type: ignore[arg-type]

    assert events[0].error.code == "unimplemented"
    assert unknown_frame.error.code == "runtime_error"
    assert "unexpected" in unknown_frame.error.message


def test_speak_stream_maps_runtime_exceptions() -> None:
    runtime_service, inference_service, _ = build_services(speech_runtime=FailingSpeechStreamRuntime())
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_speech_model())

    events = list(
        inference_service.SpeakStream(
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="failing-speak-stream"),
                model_handle=model_handle,
                input="hello",
            ),
            context=None,
        )
    )

    assert events[0].error.code == "runtime_error"
    assert events[0].error.message == "stream failed"


def test_speak_stream_propagates_exceptions_after_audio_is_committed() -> None:
    runtime_service, inference_service, _ = build_services(
        speech_runtime=FailingAfterEnvelopeSpeechStreamRuntime()
    )
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_speech_model())

    stream = inference_service.SpeakStream(
        inference_pb2.SpeakRequest(
            id=common_pb2.RequestIdentity(request_id="failing-mid-stream"),
            model_handle=model_handle,
            input="hello",
        ),
        context=None,
    )

    first_event = next(stream)
    assert first_event.kind == inference_pb2.SPEAK_STREAM_EVENT_KIND_ENVELOPE
    assert first_event.audio_bytes == b"RIFF"
    with pytest.raises(RuntimeError, match="stream interrupted"):
        next(stream)


def test_deterministic_audio_runtimes_expose_probe_snapshots() -> None:
    transcription_runtime = DeterministicTranscriptionRuntime()
    transcript = transcription_runtime.transcribe(
        {},
        inference_pb2.TranscribeRequest(audio_bytes=b" ", language=""),
    )
    transcription_probe = transcription_runtime.last_probe_snapshot()

    speech_runtime = DeterministicSpeechRuntime()
    speech = speech_runtime.speak({}, inference_pb2.SpeakRequest(input="hello", voice="", format=""))
    speech_probe = speech_runtime.last_probe_snapshot()

    assert transcript.text == "<silence>"
    assert transcript.language == "und"
    assert transcription_probe.chunk_count >= 1
    assert transcription_probe.estimated_duration_seconds > 0.0
    assert speech.audio_bytes.startswith(b"VOICE=default")
    assert speech.format == "wav"
    assert speech_probe.output_bytes == len(speech.audio_bytes)
    assert speech_probe.speech_latency_ms > 0.0


def test_audio_catalog_models_expose_backend_metadata_and_real_backend_entries() -> None:
    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MLX_AUDIO_WHISPER_MODEL_PATH": "mlx-community/whisper-large-v3-turbo-asr-fp16",
            "MELIX_MLX_AUDIO_PARAKEET_MODEL_PATH": "mlx-community/parakeet-tdt-0.6b-v2",
            "MELIX_MLX_AUDIO_KOKORO_MODEL_PATH": "mlx-community/Kokoro-82M-bf16",
            "MELIX_MLX_AUDIO_QWEN3_TTS_MODEL_PATH": "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit",
        }
    )

    deterministic_transcription = catalog.get("melix-dev-transcribe")
    deterministic_speech = catalog.get("melix-dev-speech")
    whisper = catalog.get("melix-whisper-mlx")
    parakeet = catalog.get("melix-parakeet-mlx")
    kokoro = catalog.get("melix-kokoro-mlx")
    qwen3_tts = catalog.get("melix-qwen3-tts-mlx")

    assert deterministic_transcription is not None
    assert deterministic_transcription.ext["melix.audio.backend_id"] == "deterministic"
    assert deterministic_transcription.ext["melix.audio.family_id"] == "deterministic-transcription"
    assert deterministic_transcription.ext["melix.audio.install_profile"] == ""
    assert deterministic_transcription.ext["melix.audio.languages"] == "und"
    assert deterministic_transcription.ext["melix.capability.supported_modalities"] == "audio,text"
    assert deterministic_transcription.ext["melix.capability.supported_tasks"] == "transcribe"

    assert deterministic_speech is not None
    assert deterministic_speech.ext["melix.audio.backend_id"] == "deterministic"
    assert deterministic_speech.ext["melix.audio.family_id"] == "deterministic-speech"
    assert deterministic_speech.ext["melix.audio.output_formats"] == "wav,mp3"
    assert deterministic_speech.ext["melix.audio.voice_mode"] == "named"
    assert deterministic_speech.ext["melix.audio.supports_instructions"] == "false"

    assert whisper is not None
    assert whisper.model_kind == "transcription"
    assert whisper.model_path == "mlx-community/whisper-large-v3-turbo-asr-fp16"
    assert whisper.ext["melix.audio.backend_id"] == "mlx_audio.stt"
    assert whisper.ext["melix.audio.install_profile"] == "audio-stt"
    assert whisper.ext["melix.audio.family_id"] == "whisper"

    assert parakeet is not None
    assert parakeet.model_kind == "transcription"
    assert parakeet.model_path == "mlx-community/parakeet-tdt-0.6b-v2"
    assert parakeet.ext["melix.audio.backend_id"] == "mlx_audio.stt"
    assert parakeet.ext["melix.audio.install_profile"] == "audio-stt"
    assert parakeet.ext["melix.audio.family_id"] == "parakeet"

    assert kokoro is not None
    assert kokoro.model_kind == "speech"
    assert kokoro.model_path == "mlx-community/Kokoro-82M-bf16"
    assert kokoro.ext["melix.audio.backend_id"] == "mlx_audio.tts"
    assert kokoro.ext["melix.audio.install_profile"] == "audio-tts"
    assert kokoro.ext["melix.audio.family_id"] == "kokoro"
    assert kokoro.ext["melix.audio.output_formats"] == "wav"
    assert kokoro.ext["melix.audio.voice_catalog_summary"] == "Named English voices exposed by the Kokoro speaker catalog."
    assert kokoro.ext["melix.audio.voice_locales"] == "en"
    assert kokoro.ext["melix.audio.default_locale"] == "en"
    assert kokoro.ext["melix.audio.packaged_default_locale"] == "en"
    assert kokoro.ext["melix.audio.locale_policy"] == "request>model_default>packaged_default"

    assert qwen3_tts is not None
    assert qwen3_tts.model_kind == "speech"
    assert qwen3_tts.model_path == "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit"
    assert qwen3_tts.ext["melix.audio.backend_id"] == "mlx_audio.tts"
    assert qwen3_tts.ext["melix.audio.install_profile"] == "audio-tts"
    assert qwen3_tts.ext["melix.audio.family_id"] == "qwen3-tts"
    assert qwen3_tts.ext["melix.audio.languages"] == "zh,en"
    assert qwen3_tts.ext["melix.audio.voice_mode"] == "hybrid"
    assert qwen3_tts.ext["melix.audio.supports_instructions"] == "true"
    assert (
        qwen3_tts.ext["melix.audio.voice_catalog_summary"]
        == "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
    )
    assert qwen3_tts.ext["melix.audio.voice_locales"] == "zh,en"
    assert qwen3_tts.ext["melix.audio.default_locale"] == "zh"
    assert qwen3_tts.ext["melix.audio.packaged_default_locale"] == "zh"
    assert qwen3_tts.ext["melix.audio.locale_policy"] == "request>model_default>packaged_default"
