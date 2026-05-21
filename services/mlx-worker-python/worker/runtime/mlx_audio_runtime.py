from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import perf_counter
import wave

from worker.runtime.audio_preprocessing import prepare_audio_input
from worker.runtime.audio_runtime_protocols import (
    AudioBackendUnavailableError,
    AudioProcessorValidationError,
    AudioRuntimeLoadedModel,
    SpeechStreamEnvelope,
    SpeechStreamFinish,
    SpeechStreamFrame,
    SpeechResult,
    TranscriptionResult,
)
from worker.runtime.runtime_utils import callable_kwarg_signature
from worker.runtime.wav_helpers import (
    audio_to_pcm_chunks,
    progressive_wav_header,
    stream_chunk_sample_limit,
    write_pcm_chunks,
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


def _audio_to_wav_bytes(audio, sample_rate: int) -> bytes:
    chunk_sample_limit = 65536

    with BytesIO() as buffer:
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(int(sample_rate))
            write_pcm_chunks(
                audio,
                chunk_sample_limit=chunk_sample_limit,
                write_chunk=handle.writeframesraw,
            )
        return buffer.getvalue()


def _speech_request_context(loaded_model: AudioRuntimeLoadedModel, request) -> str:
    request_id = getattr(getattr(request, "id", None), "request_id", "") or "<unknown>"
    return (
        f"request_id={request_id}, backend_id={loaded_model.backend_id}, "
        f"family_id={loaded_model.family_id}"
    )


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
    streaming_enabled: bool = False
    stream_interval_ms: int = 0
    first_audio_latency_ms: float = 0.0
    chunk_count: int = 0


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

        generate_signature = callable_kwarg_signature(model.generate)
        generate_parameter_names = generate_signature.parameter_names
        speech_generate_parameters = generate_signature.keyword_accessible_params
        supports_voice = generate_signature.declares("voice")
        supports_instructions = generate_signature.declares("instruct")
        if supports_voice and supports_instructions:
            voice_mode = "hybrid"
        elif supports_instructions:
            voice_mode = "instructional"
        elif supports_voice:
            voice_mode = "named"
        else:
            voice_mode = "plain"

        return AudioRuntimeLoadedModel(
            backend_id=backend_id,
            family_id=model_spec.ext.get("melix.audio.family_id", "unknown") or "unknown",
            runtime_name=self.runtime_name,
            model=model,
            load_latency_ms=max((perf_counter() - started_at) * 1000.0, 0.001),
            voice_metadata=_voice_metadata_for_model(model),
            voice_mode=voice_mode,
            supports_instructions=supports_instructions,
            speech_generate_parameters=speech_generate_parameters,
            output_formats=("wav",),
            generate_parameter_names=generate_parameter_names,
        )

    def estimate_resident_bytes(self, model_spec) -> int:
        return 0

    def _speech_generation_kwargs(
        self,
        loaded_model: AudioRuntimeLoadedModel,
        request,
    ) -> tuple[dict[str, object], int]:
        requested_format = (request.format or "wav").lower()
        if requested_format != "wav":
            raise ValueError("mlx-audio speech backend only supports wav output.")

        voice_mode = loaded_model.voice_mode
        supports_voice = voice_mode == "hybrid" or voice_mode == "named"
        supports_instructions = loaded_model.supports_instructions
        if (
            not voice_mode
            and not loaded_model.speech_generate_parameters
            and not loaded_model.generate_parameter_names
        ):
            generate_signature = callable_kwarg_signature(loaded_model.model.generate)
            supports_voice = generate_signature.declares("voice")
            supports_instructions = generate_signature.declares("instruct")
        kwargs = {
            "text": request.input,
            "verbose": False,
        }
        voice_fallback_count = 0

        if supports_voice and request.voice:
            kwargs["voice"] = request.voice

        if supports_instructions:
            if request.instructions:
                kwargs["instruct"] = request.instructions
            elif not supports_voice and request.voice:
                kwargs["instruct"] = request.voice
                voice_fallback_count = 1

        return kwargs, voice_fallback_count

    def speak(self, loaded_model: AudioRuntimeLoadedModel, request) -> SpeechResult:
        kwargs, voice_fallback_count = self._speech_generation_kwargs(loaded_model, request)

        started_at = perf_counter()
        with self._execution_gate:
            results = loaded_model.model.generate(**kwargs)
            audio_chunks = []
            sample_rate = 24_000
            for result in results if hasattr(results, "__iter__") else [results]:
                audio_chunks.append(getattr(result, "audio", []))
                sample_rate = int(getattr(result, "sample_rate", sample_rate) or sample_rate)

        if not audio_chunks:
            raise ValueError(
                "mlx-audio speech backend produced no audio "
                f"({_speech_request_context(loaded_model, request)})."
            )

        wav_bytes = _audio_to_wav_bytes(audio_chunks, sample_rate)
        self._last_probe = MLXAudioSpeechProbeSnapshot(
            speech_latency_ms=max((perf_counter() - started_at) * 1000.0, 0.001),
            output_bytes=len(wav_bytes),
            voice_fallback_count=voice_fallback_count,
        )
        return SpeechResult(audio_bytes=wav_bytes, format="wav")

    def stream_speak(self, loaded_model: AudioRuntimeLoadedModel, request):
        kwargs, voice_fallback_count = self._speech_generation_kwargs(loaded_model, request)
        stream_interval_ms = max(1, int(request.stream_interval_ms or 20))

        started_at = perf_counter()
        output_bytes = 0
        chunk_count = 0
        first_audio_latency_ms = 0.0
        sent_envelope = False
        emitted_audio = False
        sample_rate = 24_000

        # Qwen3-TTS can lazily produce GPU-backed chunks from the generate iterator.
        # Keep the gate across iterator consumption to avoid interleaving non-reentrant
        # model state between concurrent speech requests.
        with self._execution_gate:
            results = loaded_model.model.generate(**kwargs)
            iterable_results = results if hasattr(results, "__iter__") else [results]
            for result in iterable_results:
                audio = getattr(result, "audio", [])
                sample_rate = int(getattr(result, "sample_rate", sample_rate) or sample_rate)
                if not sent_envelope:
                    header = progressive_wav_header(sample_rate)
                    output_bytes += len(header)
                    sent_envelope = True
                    yield SpeechStreamFrame(
                        kind="envelope",
                        audio_bytes=header,
                        envelope=SpeechStreamEnvelope(
                            format="wav",
                            container="wav",
                            codec="pcm_s16le",
                            sample_rate_hz=sample_rate,
                            channel_count=1,
                            bits_per_sample=16,
                            stream_interval_ms=stream_interval_ms,
                            wav_sizes_unknown=True,
                        ),
                    )

                for pcm_chunk in audio_to_pcm_chunks(
                    audio,
                    chunk_sample_limit=stream_chunk_sample_limit(sample_rate, stream_interval_ms),
                ):
                    if not pcm_chunk:
                        continue
                    if not emitted_audio:
                        first_audio_latency_ms = max((perf_counter() - started_at) * 1000.0, 0.001)
                    emitted_audio = True
                    chunk_count += 1
                    output_bytes += len(pcm_chunk)
                    yield SpeechStreamFrame(kind="audio_chunk", audio_bytes=pcm_chunk)

        if not emitted_audio:
            raise ValueError(
                "mlx-audio speech backend produced no audio "
                f"({_speech_request_context(loaded_model, request)})."
            )

        speech_latency_ms = max((perf_counter() - started_at) * 1000.0, 0.001)
        # SpeechCore records the runtime probe when it observes the finish frame,
        # so populate the snapshot before yielding that frame.
        self._last_probe = MLXAudioSpeechProbeSnapshot(
            speech_latency_ms=speech_latency_ms,
            output_bytes=output_bytes,
            voice_fallback_count=voice_fallback_count,
            streaming_enabled=True,
            stream_interval_ms=stream_interval_ms,
            first_audio_latency_ms=first_audio_latency_ms,
            chunk_count=chunk_count,
        )
        yield SpeechStreamFrame(
            kind="finish",
            finish=SpeechStreamFinish(
                streaming_enabled=True,
                stream_interval_ms=stream_interval_ms,
                first_audio_latency_ms=first_audio_latency_ms,
                speech_latency_ms=speech_latency_ms,
                audio_bytes=output_bytes,
                audio_chunk_count=chunk_count,
            ),
        )

    def last_probe_snapshot(self) -> MLXAudioSpeechProbeSnapshot:
        return self._last_probe
