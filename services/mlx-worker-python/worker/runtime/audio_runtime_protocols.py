from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class AudioBackendUnavailableError(RuntimeError):
    pass


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
    output_formats: tuple[str, ...] = ()


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

    def last_probe_snapshot(self): ...
