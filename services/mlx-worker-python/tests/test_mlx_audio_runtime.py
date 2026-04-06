from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import inference_pb2
from worker.model_registry.catalog import WorkerModelCatalog


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
