from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


class AudioBackendUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioProcessorValidationError(RuntimeError):
    model_id: str
    model_path: str
    backend_id: str
    family_id: str
    missing_asset_class: str
    load_stage: str
    required_files: tuple[str, ...]

    def __str__(self) -> str:
        required = ", ".join(self.required_files)
        return (
            f"Audio model {self.model_id} is missing required {self.missing_asset_class} "
            f"processor assets before {self.load_stage}. Expected one of: {required}. "
            "Reinstall or redownload the managed audio model before retrying."
        )

    @property
    def details(self) -> dict[str, str]:
        return {
            "model_id": self.model_id,
            "model_path": self.model_path,
            "backend_id": self.backend_id,
            "family_id": self.family_id,
            "missing_asset_class": self.missing_asset_class,
            "load_stage": self.load_stage,
            "required_files": ",".join(self.required_files),
            "required_action": "redownload_audio_model",
            "audio_processor_validation_result": "0",
        }


@dataclass(frozen=True)
class AudioRuntimeLoadedModel:
    backend_id: str
    family_id: str
    runtime_name: str
    model: object
    load_latency_ms: float = 0.0
    voice_metadata: dict[str, Any] = field(default_factory=dict)
    voice_mode: str = ""
    supports_instructions: bool = False
    speech_generate_parameters: frozenset[str] = field(default_factory=frozenset)
    output_formats: tuple[str, ...] = ()
    generate_parameter_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class AudioModelLoadProbeSnapshot:
    model_load_latency_ms: float


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float


@dataclass(frozen=True)
class SpeechResult:
    audio_bytes: bytes
    format: str


@dataclass(frozen=True)
class SpeechStreamEnvelope:
    format: str
    container: str
    codec: str
    sample_rate_hz: int
    channel_count: int
    bits_per_sample: int
    stream_interval_ms: int
    wav_sizes_unknown: bool
    ext: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechStreamFinish:
    streaming_enabled: bool
    stream_interval_ms: int
    first_audio_latency_ms: float
    speech_latency_ms: float
    audio_bytes: int
    audio_chunk_count: int


@dataclass(frozen=True)
class SpeechStreamFrame:
    kind: Literal["envelope", "audio_chunk", "finish"]
    audio_bytes: bytes = b""
    envelope: SpeechStreamEnvelope | None = None
    finish: SpeechStreamFinish | None = None


class TranscriptionRuntimeProtocol(Protocol):
    runtime_name: str

    def load_model(self, model_spec) -> AudioRuntimeLoadedModel: ...

    def estimate_resident_bytes(self, model_spec) -> int: ...

    def transcribe(self, loaded_model: AudioRuntimeLoadedModel, request) -> TranscriptionResult: ...

    def last_probe_snapshot(self): ...


class SpeechRuntimeProtocol(Protocol):
    runtime_name: str

    def load_model(self, model_spec) -> AudioRuntimeLoadedModel: ...

    def estimate_resident_bytes(self, model_spec) -> int: ...

    def speak(self, loaded_model: AudioRuntimeLoadedModel, request) -> SpeechResult: ...

    def stream_speak(self, loaded_model: AudioRuntimeLoadedModel, request): ...

    def last_probe_snapshot(self): ...
