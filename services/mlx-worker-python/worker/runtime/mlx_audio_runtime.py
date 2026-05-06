from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import perf_counter
import array
import sys
import wave

from worker.runtime.audio_preprocessing import prepare_audio_input
from worker.runtime.audio_runtime_protocols import (
    AudioBackendUnavailableError,
    AudioProcessorValidationError,
    AudioRuntimeLoadedModel,
    SpeechResult,
    TranscriptionResult,
)


_AUDIO_PROCESSOR_CONFIG_FILES = (
    "processor_config.json",
    "preprocessor_config.json",
    "feature_extractor_config.json",
)


def _normalize_language(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None:
        return ""
    normalized = str(value).strip()
    return "" if normalized.lower() == "none" else normalized


def _iter_samples(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (float, int)):
        yield float(value)
        return
    for item in value:
        if isinstance(item, (list, tuple)) or hasattr(item, "tolist"):
            yield from _iter_samples(item)
        else:
            yield float(item)


def _audio_to_wav_bytes(audio, sample_rate: int) -> bytes:
    chunk = array.array("h")
    chunk_sample_limit = 65536

    with BytesIO() as buffer:
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(int(sample_rate))
            for sample in _iter_samples(audio):
                clamped = max(-1.0, min(1.0, float(sample)))
                chunk.append(int(clamped * 32767.0))
                if len(chunk) >= chunk_sample_limit:
                    if sys.byteorder != "little":
                        chunk.byteswap()
                    handle.writeframesraw(chunk.tobytes())
                    chunk = array.array("h")
            if chunk:
                if sys.byteorder != "little":
                    chunk.byteswap()
                handle.writeframesraw(chunk.tobytes())
        return buffer.getvalue()


def _voice_metadata_for_model(model) -> dict[str, object]:
    for attr_name in ("voices", "available_voices", "speaker_names"):
        value = getattr(model, attr_name, None)
        if value:
            return {"voices": list(value)}
    return {}


def _validate_local_audio_processor_assets(model_spec, *, backend_id: str, load_stage: str) -> None:
    model_path = str(getattr(model_spec, "model_path", "") or "").strip()
    if not model_path:
        return
    model_dir = Path(model_path).expanduser()
    if not model_dir.exists():
        return
    if model_dir.is_file():
        model_dir = model_dir.parent
    if any((model_dir / file_name).is_file() for file_name in _AUDIO_PROCESSOR_CONFIG_FILES):
        return
    raise AudioProcessorValidationError(
        model_id=str(getattr(model_spec, "model_id", "") or ""),
        model_path=str(model_dir),
        backend_id=backend_id,
        family_id=str(getattr(model_spec, "ext", {}).get("melix.audio.family_id", "unknown") or "unknown"),
        missing_asset_class="processor_config",
        load_stage=load_stage,
        required_files=_AUDIO_PROCESSOR_CONFIG_FILES,
    )


@dataclass(frozen=True)
class MLXAudioTranscriptionProbeSnapshot:
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    estimated_duration_seconds: float
    chunk_count: int
    transcription_latency_ms: float
    language_fallback_count: int


@dataclass(frozen=True)
class MLXAudioSpeechProbeSnapshot:
    speech_latency_ms: float
    output_bytes: int
    voice_fallback_count: int


class MLXAudioTranscriptionRuntime:
    runtime_name = "mlx-audio-stt"

    def __init__(self, temp_root: Path | str | None = None, execution_gate: Lock | None = None) -> None:
        self._temp_root = Path(temp_root) if temp_root is not None else None
        self._execution_gate = execution_gate or Lock()
        self._last_probe = MLXAudioTranscriptionProbeSnapshot(0.0, 0, 0, 0.0, 0, 0.0, 0)

    def load_model(self, model_spec) -> AudioRuntimeLoadedModel:
        started_at = perf_counter()
        backend_id = model_spec.ext.get("melix.audio.backend_id", "mlx_audio.stt") or "mlx_audio.stt"
        _validate_local_audio_processor_assets(
            model_spec,
            backend_id=backend_id,
            load_stage="load_model:processor_asset_preflight",
        )
        try:
            from mlx_audio.stt.utils import load_model
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise AudioBackendUnavailableError(
                "mlx-audio STT backend is unavailable. Install the audio-stt profile."
            ) from exc

        model = load_model(model_spec.model_path)
        return AudioRuntimeLoadedModel(
            backend_id=backend_id,
            family_id=model_spec.ext.get("melix.audio.family_id", "unknown") or "unknown",
            runtime_name=self.runtime_name,
            model=model,
            load_latency_ms=max((perf_counter() - started_at) * 1000.0, 0.001),
        )

    def estimate_resident_bytes(self, model_spec) -> int:
        return 0

    def transcribe(self, loaded_model: AudioRuntimeLoadedModel, request) -> TranscriptionResult:
        prepared = prepare_audio_input(request, read_uri_bytes=not bool(request.audio_uri))
        started_at = perf_counter()
        cleanup_path: Path | None = None
        audio_path = prepared.local_path

        if not audio_path:
            suffix = f".{prepared.format or 'wav'}"
            temp_kwargs = {"suffix": suffix, "delete": False}
            if self._temp_root is not None:
                self._temp_root.mkdir(parents=True, exist_ok=True)
                temp_kwargs["dir"] = self._temp_root
            with NamedTemporaryFile(**temp_kwargs) as handle:
                handle.write(prepared.bytes_data)
                cleanup_path = Path(handle.name)
                audio_path = handle.name

        kwargs: dict[str, str] = {}
        if request.language:
            kwargs["language"] = request.language

        try:
            with self._execution_gate:
                result = loaded_model.model.generate(audio_path, **kwargs)
        finally:
            if cleanup_path is not None:
                cleanup_path.unlink(missing_ok=True)

        detected_language = _normalize_language(getattr(result, "language", ""))
        language_fallback_count = 0
        if not detected_language:
            detected_language = request.language or "und"
            language_fallback_count = 1 if request.language else 0

        duration_seconds = float(getattr(result, "total_time", 0.0) or 0.0)
        if duration_seconds <= 0:
            duration_seconds = prepared.duration_seconds
        transcription_latency_ms = max((perf_counter() - started_at) * 1000.0, 0.001)
        self._last_probe = MLXAudioTranscriptionProbeSnapshot(
            preprocess_latency_ms=prepared.preprocess_latency_ms,
            preprocess_input_bytes=prepared.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
            estimated_duration_seconds=duration_seconds,
            chunk_count=prepared.chunk_count,
            transcription_latency_ms=transcription_latency_ms,
            language_fallback_count=language_fallback_count,
        )
        return TranscriptionResult(
            text=getattr(result, "text", "") or "",
            language=detected_language,
            duration_seconds=duration_seconds,
        )

    def last_probe_snapshot(self) -> MLXAudioTranscriptionProbeSnapshot:
        return self._last_probe


class MLXAudioSpeechRuntime:
    runtime_name = "mlx-audio-tts"

    def __init__(self, execution_gate: Lock | None = None) -> None:
        self._execution_gate = execution_gate or Lock()
        self._last_probe = MLXAudioSpeechProbeSnapshot(0.0, 0, 0)

    def load_model(self, model_spec) -> AudioRuntimeLoadedModel:
        started_at = perf_counter()
        backend_id = model_spec.ext.get("melix.audio.backend_id", "mlx_audio.tts") or "mlx_audio.tts"
        _validate_local_audio_processor_assets(
            model_spec,
            backend_id=backend_id,
            load_stage="load_model:processor_asset_preflight",
        )
        try:
            from mlx_audio.tts.utils import load_model
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise AudioBackendUnavailableError(
                "mlx-audio TTS backend is unavailable. Install the audio-tts profile."
            ) from exc

        try:
            model = load_model(model_spec.model_path, strict=True)
        except TypeError:
            model = load_model(model_spec.model_path)

        generate_parameter_names = tuple(signature(model.generate).parameters)
        supports_voice = "voice" in generate_parameter_names
        supports_instructions = "instruct" in generate_parameter_names
        if supports_voice and supports_instructions:
            voice_mode = "hybrid"
        elif supports_instructions:
            voice_mode = "instructional"
        else:
            voice_mode = "named"

        return AudioRuntimeLoadedModel(
            backend_id=backend_id,
            family_id=model_spec.ext.get("melix.audio.family_id", "unknown") or "unknown",
            runtime_name=self.runtime_name,
            model=model,
            load_latency_ms=max((perf_counter() - started_at) * 1000.0, 0.001),
            voice_metadata=_voice_metadata_for_model(model),
            voice_mode=voice_mode,
            supports_instructions=supports_instructions,
            output_formats=("wav",),
            generate_parameter_names=generate_parameter_names,
        )

    def estimate_resident_bytes(self, model_spec) -> int:
        return 0

    def speak(self, loaded_model: AudioRuntimeLoadedModel, request) -> SpeechResult:
        requested_format = (request.format or "wav").lower()
        if requested_format != "wav":
            raise ValueError("mlx-audio speech backend only supports wav output.")

        params = loaded_model.generate_parameter_names or tuple(signature(loaded_model.model.generate).parameters)
        kwargs = {
            "text": request.input,
            "verbose": False,
        }
        voice_fallback_count = 0

        if "voice" in params and request.voice:
            kwargs["voice"] = request.voice

        if "instruct" in params:
            if request.instructions:
                kwargs["instruct"] = request.instructions
            elif "voice" not in params and request.voice:
                kwargs["instruct"] = request.voice
                voice_fallback_count = 1

        started_at = perf_counter()
        with self._execution_gate:
            results = loaded_model.model.generate(**kwargs)
            audio_chunks = []
            sample_rate = 24_000
            for result in results if hasattr(results, "__iter__") else [results]:
                audio_chunks.append(getattr(result, "audio", []))
                sample_rate = int(getattr(result, "sample_rate", sample_rate) or sample_rate)

        if not audio_chunks:
            raise ValueError("mlx-audio speech backend produced no audio.")

        wav_bytes = _audio_to_wav_bytes(audio_chunks, sample_rate)
        self._last_probe = MLXAudioSpeechProbeSnapshot(
            speech_latency_ms=max((perf_counter() - started_at) * 1000.0, 0.001),
            output_bytes=len(wav_bytes),
            voice_fallback_count=voice_fallback_count,
        )
        return SpeechResult(audio_bytes=wav_bytes, format="wav")

    def last_probe_snapshot(self) -> MLXAudioSpeechProbeSnapshot:
        return self._last_probe
