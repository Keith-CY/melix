from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
import wave

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2
from worker.grpc_server import WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def _install_fake_mlx_audio(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stt_loader=None,
    tts_loader=None,
) -> None:
    mlx_audio = ModuleType("mlx_audio")
    mlx_audio_stt = ModuleType("mlx_audio.stt")
    mlx_audio_stt_utils = ModuleType("mlx_audio.stt.utils")
    mlx_audio_tts = ModuleType("mlx_audio.tts")
    mlx_audio_tts_utils = ModuleType("mlx_audio.tts.utils")

    if stt_loader is not None:
        mlx_audio_stt_utils.load_model = stt_loader
    if tts_loader is not None:
        mlx_audio_tts_utils.load_model = tts_loader

    monkeypatch.setitem(sys.modules, "mlx_audio", mlx_audio)
    monkeypatch.setitem(sys.modules, "mlx_audio.stt", mlx_audio_stt)
    monkeypatch.setitem(sys.modules, "mlx_audio.stt.utils", mlx_audio_stt_utils)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts", mlx_audio_tts)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", mlx_audio_tts_utils)


@pytest.mark.parametrize(
    ("builder", "expected_family"),
    [
        (WorkerModelCatalog.mlx_whisper_model, "whisper"),
        (WorkerModelCatalog.mlx_parakeet_model, "parakeet"),
    ],
)
def test_mlx_audio_transcription_runtime_uses_lazy_import_and_cleans_up_inline_audio_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder,
    expected_family: str,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioTranscriptionRuntime

    created_paths: list[Path] = []

    class FakeSTTModel:
        def generate(self, audio_path: str, **kwargs):
            return SimpleNamespace(
                text="decoded by mlx-audio",
                language=kwargs.get("language") or "en",
                segments=[],
                total_time=1.25,
            )

    def fake_load_model(model_path: str):
        return FakeSTTModel()

    _install_fake_mlx_audio(monkeypatch, stt_loader=fake_load_model)

    runtime = MLXAudioTranscriptionRuntime(temp_root=tmp_path)
    loaded = runtime.load_model(builder())

    assert loaded.backend_id == "mlx_audio.stt"
    assert loaded.family_id == expected_family
    assert loaded.runtime_name == "mlx-audio-stt"

    result = runtime.transcribe(
        loaded,
        inference_pb2.TranscribeRequest(
            audio_bytes=b"inline audio",
            language="en",
            format="wav",
        ),
    )

    created_paths.extend(tmp_path.iterdir())

    assert result.text == "decoded by mlx-audio"
    assert result.language == "en"
    assert result.duration_seconds == 1.25
    assert created_paths == []


def test_mlx_audio_transcription_runtime_uses_local_uri_path_without_reading_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime import audio_preprocessing
    from worker.runtime.mlx_audio_runtime import MLXAudioTranscriptionRuntime

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"local audio payload")
    captured_paths: list[str] = []

    class FakeSTTModel:
        def generate(self, audio_path: str, **kwargs):
            captured_paths.append(audio_path)
            return SimpleNamespace(text="decoded local uri", language="", total_time=0.0)

    def fake_load_model(model_path: str):
        return FakeSTTModel()

    def fail_read_bytes(self: Path) -> bytes:
        if self == audio_path:
            raise AssertionError("MLX local audio URI path should not read file bytes")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    _install_fake_mlx_audio(monkeypatch, stt_loader=fake_load_model)

    runtime = MLXAudioTranscriptionRuntime(temp_root=tmp_path / "transient")
    loaded = runtime.load_model(WorkerModelCatalog.mlx_whisper_model())
    result = runtime.transcribe(
        loaded,
        inference_pb2.TranscribeRequest(audio_uri=audio_path.as_uri(), language="en", format="wav"),
    )
    probe = runtime.last_probe_snapshot()

    assert captured_paths == [str(audio_path)]
    assert result.text == "decoded local uri"
    assert result.language == "en"
    assert result.duration_seconds == round(audio_path.stat().st_size / 16000.0, 6)
    assert probe.preprocess_input_bytes == audio_path.stat().st_size
    assert probe.preprocess_peak_memory_bytes == audio_path.stat().st_size

    fail_urlparse = lambda uri: (_ for _ in ()).throw(  # noqa: E731
        AssertionError(f"local audio URI should use the fast path: {uri}")
    )

    monkeypatch.setattr(audio_preprocessing, "urlparse", fail_urlparse)
    assert audio_preprocessing._path_from_uri(audio_path.as_uri()) == audio_path

    fail_unquote = lambda path: (_ for _ in ()).throw(  # noqa: E731
        AssertionError(f"unencoded local audio URI should skip unquote: {path}")
    )
    monkeypatch.setattr(audio_preprocessing, "unquote", fail_unquote)
    assert audio_preprocessing._path_from_uri(audio_path.as_uri()) == audio_path

    monkeypatch.setattr(audio_preprocessing, "unquote", lambda path: str(audio_path))
    assert audio_preprocessing._path_from_uri("file:///tmp/audio%20sample.wav") == audio_path

    monkeypatch.setattr(audio_preprocessing, "urlparse", fail_urlparse)
    assert audio_preprocessing._path_from_uri(str(audio_path)) == audio_path

    monkeypatch.setattr(audio_preprocessing, "urlparse", fail_urlparse)
    assert audio_preprocessing._path_from_uri(f"file://localhost{audio_path}") == audio_path

    monkeypatch.setattr(
        audio_preprocessing,
        "urlparse",
        lambda uri: SimpleNamespace(scheme="file", path=str(audio_path)),
    )
    assert audio_preprocessing._path_from_uri(f"file://remote-host{audio_path}") == audio_path

    monkeypatch.setattr(
        audio_preprocessing,
        "urlparse",
        lambda uri: SimpleNamespace(scheme="file", path=str(audio_path)),
    )
    assert audio_preprocessing._path_from_uri("custom://audio.wav") == audio_path

    monkeypatch.setattr(
        audio_preprocessing,
        "urlparse",
        lambda uri: SimpleNamespace(scheme="https", path="/audio.wav"),
    )
    with pytest.raises(audio_preprocessing.AudioPreprocessError, match="Unsupported audio URI scheme"):
        audio_preprocessing._path_from_uri("https://example.com/audio.wav")
    with pytest.raises(audio_preprocessing.AudioPreprocessError, match="Missing local audio input"):
        audio_preprocessing.prepare_audio_input(
            inference_pb2.TranscribeRequest(audio_uri=str(tmp_path / "missing.wav"), format="wav"),
            read_uri_bytes=False,
        )

    monkeypatch.setattr(Path, "read_bytes", original_read_bytes)
    prepared = audio_preprocessing.prepare_audio_input(
        inference_pb2.TranscribeRequest(audio_uri=audio_path.as_uri(), format="wav")
    )
    assert prepared.bytes_data == b"local audio payload"


def test_mlx_audio_speech_runtime_detects_voice_mode_and_maps_voice_and_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    captured_calls: list[dict[str, object]] = []

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, speed=1.0, verbose=False):
            captured_calls.append(
                {
                    "text": text,
                    "voice": voice,
                    "instruct": instruct,
                    "speed": speed,
                    "verbose": verbose,
                }
            )
            yield FakeChunk([0.1, -0.1, 0.0])

    def fake_load_model(model_path: str, strict: bool = True):
        return FakeTTSModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())

    assert loaded.backend_id == "mlx_audio.tts"
    assert loaded.family_id == "qwen3-tts"
    assert loaded.voice_mode == "hybrid"
    assert loaded.supports_instructions is True

    result = runtime.speak(
        loaded,
        inference_pb2.SpeakRequest(
            input="hello hybrid voice",
            voice="alloy",
            instructions="Speak calmly.",
            format="wav",
        ),
    )

    assert result.format == "wav"
    assert result.audio_bytes.startswith(b"RIFF")
    assert captured_calls == [
        {
            "text": "hello hybrid voice",
            "voice": "alloy",
            "instruct": "Speak calmly.",
            "speed": 1.0,
            "verbose": False,
        }
    ]


def test_mlx_audio_speech_runtime_streams_progressive_wav_chunks_with_bounded_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    captured_calls: list[dict[str, object]] = []

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 1_000

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, verbose=False):
            captured_calls.append(
                {"text": text, "voice": voice, "instruct": instruct, "verbose": verbose}
            )
            yield FakeChunk([0.0, 0.5, -0.5, 1.0, -1.0])

    def fake_load_model(model_path: str, strict: bool = True):
        return FakeTTSModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
    frames = list(
        runtime.stream_speak(
            loaded,
            inference_pb2.SpeakRequest(
                input="hello streamed hybrid voice",
                voice="alloy",
                instructions="Speak calmly.",
                format="wav",
                streaming_enabled=True,
                stream_interval_ms=2,
            ),
        )
    )
    payload = b"".join(frame.audio_bytes for frame in frames if frame.audio_bytes)
    probe = runtime.last_probe_snapshot()

    assert [frame.kind for frame in frames] == ["envelope", "audio_chunk", "audio_chunk", "audio_chunk", "finish"]
    assert frames[0].envelope is not None
    assert frames[0].envelope.format == "wav"
    assert frames[0].envelope.sample_rate_hz == 1_000
    assert frames[0].envelope.stream_interval_ms == 2
    assert [len(frame.audio_bytes) for frame in frames if frame.kind == "audio_chunk"] == [4, 4, 2]
    assert payload.startswith(b"RIFF")
    with wave.open(BytesIO(payload), "rb") as handle:
        assert handle.getframerate() == 1_000
        assert handle.getnchannels() == 1
        assert handle.readframes(5)
    assert frames[-1].finish is not None
    assert frames[-1].finish.streaming_enabled is True
    assert frames[-1].finish.stream_interval_ms == 2
    assert frames[-1].finish.audio_chunk_count == 3
    assert frames[-1].finish.audio_bytes == len(payload)
    assert probe.streaming_enabled is True
    assert probe.stream_interval_ms == 2
    assert probe.first_audio_latency_ms > 0.0
    assert probe.chunk_count == 3
    assert captured_calls == [
        {
            "text": "hello streamed hybrid voice",
            "voice": "alloy",
            "instruct": "Speak calmly.",
            "verbose": False,
        }
    ]


def test_mlx_audio_speech_runtime_reports_context_when_unary_generation_has_no_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    class EmptyTTSModel:
        def generate(self, text, verbose=False):
            _ = text
            _ = verbose
            return []

    def fake_load_model(model_path: str, strict: bool = True):
        _ = model_path
        _ = strict
        return EmptyTTSModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())

    with pytest.raises(ValueError) as error:
        runtime.speak(
            loaded,
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="speak-empty"),
                input="empty audio",
                format="wav",
            ),
        )

    message = str(error.value)
    assert "request_id=speak-empty" in message
    assert "backend_id=mlx_audio.tts" in message
    assert "family_id=qwen3-tts" in message


def test_mlx_audio_speech_runtime_reports_context_when_stream_generation_has_no_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    class EmptyTTSModel:
        def generate(self, text, verbose=False):
            _ = text
            _ = verbose
            return [SimpleNamespace(audio=[], sample_rate=24_000)]

    def fake_load_model(model_path: str, strict: bool = True):
        _ = model_path
        _ = strict
        return EmptyTTSModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
    frames = []

    with pytest.raises(ValueError) as error:
        for frame in runtime.stream_speak(
            loaded,
            inference_pb2.SpeakRequest(
                id=common_pb2.RequestIdentity(request_id="speak-stream-empty"),
                input="empty streamed audio",
                format="wav",
                streaming_enabled=True,
            ),
        ):
            frames.append(frame)

    assert [frame.kind for frame in frames] == ["envelope"]
    message = str(error.value)
    assert "request_id=speak-stream-empty" in message
    assert "backend_id=mlx_audio.tts" in message
    assert "family_id=qwen3-tts" in message


def test_mlx_audio_speech_runtime_reuses_generate_signature_from_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import worker.runtime.mlx_audio_runtime as mlx_audio_runtime
    from worker.runtime import runtime_utils
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    signature_calls = 0
    runtime_utils.clear_callable_kwarg_signature_cache()
    original_signature = runtime_utils.inspect.signature

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, speed=1.0, verbose=False):
            yield FakeChunk([0.1, -0.1, 0.0])

    def fake_load_model(model_path: str, strict: bool = True):
        return FakeTTSModel()

    def tracked_signature(callable_obj):
        nonlocal signature_calls
        signature_calls += 1
        return original_signature(callable_obj)

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)
    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
    assert loaded.generate_parameter_names == ("text", "voice", "instruct", "speed", "verbose")
    assert signature_calls == 1
    runtime_utils.clear_callable_kwarg_signature_cache()

    for index in range(3):
        result = runtime.speak(
            loaded,
            inference_pb2.SpeakRequest(
                input=f"hello cached signature {index}",
                voice="alloy",
                instructions="Speak calmly.",
                format="wav",
            ),
        )
        assert result.audio_bytes.startswith(b"RIFF")

    assert signature_calls == 1


def test_mlx_audio_speech_runtime_reuses_cached_generate_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import worker.runtime.mlx_audio_runtime as mlx_audio_runtime
    from worker.runtime import runtime_utils

    captured_calls: list[dict[str, object]] = []

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, verbose=False):
            captured_calls.append(
                {"text": text, "voice": voice, "instruct": instruct, "verbose": verbose}
            )
            yield FakeChunk([0.1, -0.1])

    def fake_load_model(model_path: str, strict: bool = True):
        return FakeTTSModel()

    signature_calls = 0
    runtime_utils.clear_callable_kwarg_signature_cache()
    original_signature = runtime_utils.inspect.signature

    def tracked_signature(callable_object):
        nonlocal signature_calls
        signature_calls += 1
        return original_signature(callable_object)

    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)
    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = mlx_audio_runtime.MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())

    assert signature_calls == 1

    for index in range(2):
        result = runtime.speak(
            loaded,
            inference_pb2.SpeakRequest(
                input=f"cached signature {index}",
                voice="alloy",
                instructions="Speak calmly.",
                format="wav",
            ),
        )
        assert result.audio_bytes.startswith(b"RIFF")

    assert signature_calls == 1
    assert captured_calls == [
        {
            "text": "cached signature 0",
            "voice": "alloy",
            "instruct": "Speak calmly.",
            "verbose": False,
        },
        {
            "text": "cached signature 1",
            "voice": "alloy",
            "instruct": "Speak calmly.",
            "verbose": False,
        },
    ]
    runtime_utils.clear_callable_kwarg_signature_cache()


def test_mlx_audio_speech_runtime_preserves_signature_fallback_for_legacy_loaded_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    import worker.runtime.mlx_audio_runtime as mlx_audio_runtime
    from worker.runtime import runtime_utils

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    captured_calls: list[dict[str, object]] = []

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, verbose=False):
            captured_calls.append(
                {
                    "text": text,
                    "voice": voice,
                    "instruct": instruct,
                    "verbose": verbose,
                }
            )
            yield FakeChunk([0.1, -0.1])

    def fake_load_model(model_path: str, strict: bool = True):
        _ = model_path
        _ = strict
        return FakeTTSModel()

    signature_calls = 0
    runtime_utils.clear_callable_kwarg_signature_cache()
    original_signature = runtime_utils.inspect.signature

    def tracked_signature(callable_object):
        nonlocal signature_calls
        signature_calls += 1
        return original_signature(callable_object)

    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)
    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = mlx_audio_runtime.MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
    legacy_loaded = replace(
        loaded,
        voice_mode="",
        supports_instructions=False,
        speech_generate_parameters=frozenset(),
        generate_parameter_names=(),
    )

    assert signature_calls == 1
    result = runtime.speak(
        legacy_loaded,
        inference_pb2.SpeakRequest(
            input="legacy cached payload",
            voice="alloy",
            instructions="Speak calmly.",
            format="wav",
        ),
    )

    assert result.audio_bytes.startswith(b"RIFF")
    assert signature_calls == 1
    assert captured_calls == [
        {
            "text": "legacy cached payload",
            "voice": "alloy",
            "instruct": "Speak calmly.",
            "verbose": False,
        }
    ]
    runtime_utils.clear_callable_kwarg_signature_cache()


def test_mlx_audio_speech_runtime_reuses_loaded_signature_metadata_during_speak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime import runtime_utils
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    captured_calls: list[dict[str, object]] = []

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, verbose=False):
            captured_calls.append(
                {
                    "text": text,
                    "voice": voice,
                    "instruct": instruct,
                    "verbose": verbose,
                }
            )
            yield FakeChunk([0.1, -0.1, 0.0])

    def fake_load_model(model_path: str, strict: bool = True):
        return FakeTTSModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)
    runtime_utils.clear_callable_kwarg_signature_cache()
    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
    monkeypatch.setattr(
        runtime_utils.inspect,
        "signature",
        lambda _callable: pytest.fail("speak() should reuse loaded speech signature metadata"),
    )

    result = runtime.speak(
        loaded,
        inference_pb2.SpeakRequest(
            input="cached signature metadata",
            voice="alloy",
            instructions="Speak brightly.",
            format="wav",
        ),
    )

    assert result.format == "wav"
    assert result.audio_bytes.startswith(b"RIFF")
    assert captured_calls == [
        {
            "text": "cached signature metadata",
            "voice": "alloy",
            "instruct": "Speak brightly.",
            "verbose": False,
        }
    ]
    runtime_utils.clear_callable_kwarg_signature_cache()


def test_mlx_audio_speech_runtime_does_not_treat_variadic_kwargs_as_voice_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime import runtime_utils
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    captured_calls: list[dict[str, object]] = []

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    class FakeVariadicModel:
        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            yield FakeChunk([0.1, -0.1])

    def fake_load_model(model_path: str, strict: bool = True):
        _ = model_path
        _ = strict
        return FakeVariadicModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())

    assert loaded.voice_mode == "plain"
    assert loaded.supports_instructions is False
    assert loaded.generate_parameter_names == ()

    monkeypatch.setattr(
        runtime_utils.inspect,
        "signature",
        lambda _callable: pytest.fail("plain voice_mode should skip legacy signature fallback"),
    )

    result = runtime.speak(
        loaded,
        inference_pb2.SpeakRequest(
            input="plain variadic audio",
            voice="alloy",
            instructions="Speak calmly.",
            format="wav",
        ),
    )

    assert result.audio_bytes.startswith(b"RIFF")
    assert captured_calls == [{"text": "plain variadic audio", "verbose": False}]


def test_mlx_audio_speech_runtime_falls_back_to_voice_descriptor_only_for_instructional_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime

    captured_calls: list[dict[str, object]] = []

    class FakeChunk:
        def __init__(self, audio):
            self.audio = audio
            self.sample_rate = 24_000

    class FakeInstructionalModel:
        def generate(self, text, instruct=None, speed=1.0, verbose=False):
            captured_calls.append(
                {
                    "text": text,
                    "instruct": instruct,
                    "speed": speed,
                    "verbose": verbose,
                }
            )
            yield FakeChunk([0.1, 0.2])

    def fake_load_model(model_path: str, strict: bool = True):
        return FakeInstructionalModel()

    _install_fake_mlx_audio(monkeypatch, tts_loader=fake_load_model)

    runtime = MLXAudioSpeechRuntime()
    loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())

    assert loaded.voice_mode == "instructional"

    runtime.speak(
        loaded,
        inference_pb2.SpeakRequest(
            input="fallback to voice descriptor",
            voice="warm narrator",
            format="wav",
        ),
    )
    probe = runtime.last_probe_snapshot()

    assert captured_calls == [
        {
            "text": "fallback to voice descriptor",
            "instruct": "warm narrator",
            "speed": 1.0,
            "verbose": False,
        }
    ]
    assert probe.voice_fallback_count == 1


@pytest.mark.parametrize(
    ("builder", "runtime_class_name", "backend_id"),
    [
        (WorkerModelCatalog.mlx_whisper_model, "MLXAudioTranscriptionRuntime", "mlx_audio.stt"),
        (WorkerModelCatalog.mlx_kokoro_model, "MLXAudioSpeechRuntime", "mlx_audio.tts"),
    ],
)
def test_mlx_audio_runtimes_reject_local_models_missing_processor_assets(
    tmp_path: Path,
    builder,
    runtime_class_name: str,
    backend_id: str,
) -> None:
    import worker.runtime.mlx_audio_runtime as mlx_audio_runtime
    from worker.runtime.audio_runtime_protocols import AudioProcessorValidationError

    model_dir = tmp_path / "managed-audio-model"
    model_dir.mkdir()
    model_spec = builder()
    model_spec.model_path = str(model_dir)
    runtime = getattr(mlx_audio_runtime, runtime_class_name)()

    with pytest.raises(AudioProcessorValidationError) as error:
        runtime.load_model(model_spec)

    assert error.value.details["backend_id"] == backend_id
    assert error.value.details["missing_asset_class"] == "processor_config"
    assert error.value.details["load_stage"] == "load_model:processor_asset_preflight"
    assert error.value.details["audio_processor_validation_result"] == "0"
    assert "processor_config.json" in error.value.details["required_files"]


def test_mlx_audio_processor_validation_accepts_local_processor_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.runtime.mlx_audio_runtime import MLXAudioTranscriptionRuntime

    model_dir = tmp_path / "managed-whisper"
    model_dir.mkdir()
    (model_dir / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    captured_paths: list[str] = []

    class FakeSTTModel:
        def generate(self, audio_path: str, **kwargs):
            _ = audio_path
            _ = kwargs
            return SimpleNamespace(text="ok", language="en", total_time=1.0)

    def fake_load_model(model_path: str):
        captured_paths.append(model_path)
        return FakeSTTModel()

    _install_fake_mlx_audio(monkeypatch, stt_loader=fake_load_model)
    model_spec = WorkerModelCatalog.mlx_whisper_model()
    model_spec.model_path = str(model_dir)

    loaded = MLXAudioTranscriptionRuntime().load_model(model_spec)

    assert loaded.backend_id == "mlx_audio.stt"
    assert captured_paths == [str(model_dir)]


def test_audio_to_wav_bytes_streams_nested_samples_and_clamps_values() -> None:
    from worker.runtime.mlx_audio_runtime import _audio_to_wav_bytes

    class ArrayLike:
        def tolist(self):
            return [0.5, (2.0, -2.0)]

    wav_bytes = _audio_to_wav_bytes([[0.0, ArrayLike()], (-0.5,)], sample_rate=16_000)

    with wave.open(BytesIO(wav_bytes), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 16_000
        assert handle.getnframes() == 5
        frames = handle.readframes(5)

    decoded = [
        int.from_bytes(frames[index : index + 2], byteorder="little", signed=True)
        for index in range(0, len(frames), 2)
    ]
    assert decoded == [0, 16383, 32767, -32767, -16383]

    scalar_wav_bytes = _audio_to_wav_bytes(0.25, sample_rate=8_000)
    with wave.open(BytesIO(scalar_wav_bytes), "rb") as handle:
        assert handle.getframerate() == 8_000
        assert handle.getnframes() == 1
        assert int.from_bytes(handle.readframes(1), byteorder="little", signed=True) == 8191


def test_audio_to_wav_bytes_does_not_materialize_flat_sample_list(monkeypatch: pytest.MonkeyPatch) -> None:
    import worker.runtime.mlx_audio_runtime as mlx_audio_runtime

    calls: list[int] = []
    original_writeframesraw = wave.Wave_write.writeframesraw

    def tracked_writeframesraw(self, data):
        calls.append(len(data))
        return original_writeframesraw(self, data)

    monkeypatch.setattr(wave.Wave_write, "writeframesraw", tracked_writeframesraw)

    wav_bytes = mlx_audio_runtime._audio_to_wav_bytes((0.1 for _ in range(9000)), sample_rate=24_000)

    assert calls == [18000]
    with wave.open(BytesIO(wav_bytes), "rb") as handle:
        assert handle.getnframes() == 9000
        assert handle.getframerate() == 24_000

    class FlatArrayLike:
        def __init__(self) -> None:
            self.tolist_calls = 0
            self.flat = (0.1 for _ in range(4))

        def tolist(self):
            self.tolist_calls += 1
            raise AssertionError("flat audio arrays should stream without tolist materialization")

    flat_audio = FlatArrayLike()
    flat_wav_bytes = mlx_audio_runtime._audio_to_wav_bytes(flat_audio, sample_rate=12_000)

    assert flat_audio.tolist_calls == 0
    with pytest.raises(AssertionError, match="flat audio arrays"):
        flat_audio.tolist()
    with wave.open(BytesIO(flat_wav_bytes), "rb") as handle:
        assert handle.getnframes() == 4
        assert handle.getframerate() == 12_000

    import worker.runtime.wav_helpers as wav_helpers

    class NormalizedFloat(float):
        def __float__(self):  # pragma: no cover - covered only by regression failure
            raise AssertionError("audio_to_pcm_chunks should not re-cast normalized samples")

    monkeypatch.setattr(
        wav_helpers,
        "iter_samples",
        lambda audio: iter((NormalizedFloat(0.5), NormalizedFloat(2.0), NormalizedFloat(-2.0))),
    )

    chunks = list(wav_helpers.audio_to_pcm_chunks(object(), chunk_sample_limit=2))
    decoded = [
        int.from_bytes(chunk[index : index + 2], byteorder="little", signed=True)
        for chunk in chunks
        for index in range(0, len(chunk), 2)
    ]
    assert decoded == [16383, 32767, -32767]


def test_iter_samples_preserves_already_float_samples_without_recast() -> None:
    from worker.runtime.wav_helpers import iter_samples

    class NormalizedFloat(float):
        def __float__(self):  # pragma: no cover - covered only by regression failure
            raise AssertionError("iter_samples should not re-cast float sample values")

    class FlatAudio:
        @property
        def flat(self):
            return iter((NormalizedFloat(0.5), NormalizedFloat(-0.25)))

    nested_samples = list(
        iter_samples(
            [
                NormalizedFloat(0.125),
                (NormalizedFloat(0.25), FlatAudio()),
            ]
        )
    )

    assert nested_samples == [0.125, 0.25, 0.5, -0.25]
    assert all(isinstance(sample, NormalizedFloat) for sample in nested_samples)


def test_audio_to_wav_bytes_writes_little_endian_chunks_on_big_endian_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import worker.runtime.mlx_audio_runtime as mlx_audio_runtime
    import worker.runtime.wav_helpers as wav_helpers

    monkeypatch.setattr(wav_helpers.sys, "byteorder", "big")

    wav_bytes = mlx_audio_runtime._audio_to_wav_bytes((0.1 for _ in range(66000)), sample_rate=24_000)

    assert wav_bytes.startswith(b"RIFF")
    with wave.open(BytesIO(wav_bytes), "rb") as handle:
        assert handle.getnframes() == 66000


def test_worker_load_model_returns_actionable_audio_processor_validation_error(tmp_path: Path) -> None:
    model_dir = tmp_path / "managed-whisper"
    model_dir.mkdir()
    model_spec = WorkerModelCatalog.mlx_whisper_model()
    model_spec.model_path = str(model_dir)
    service = WorkerRuntimeService(WorkerRegistry(model_catalog=WorkerModelCatalog()))

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model_spec),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "audio_processor_validation_failed"
    assert response.error.details["missing_asset_class"] == "processor_config"
    assert response.error.details["load_stage"] == "load_model:processor_asset_preflight"
    assert response.error.details["audio_processor_validation_result"] == "0"
