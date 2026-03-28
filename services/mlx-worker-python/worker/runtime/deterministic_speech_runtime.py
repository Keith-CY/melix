from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechProbeSnapshot:
    speech_latency_ms: float
    output_bytes: int


@dataclass(frozen=True)
class DeterministicSpeechResult:
    audio_bytes: bytes
    format: str


class DeterministicSpeechRuntime:
    runtime_name = "deterministic-speech"

    def __init__(self) -> None:
        self._last_probe = SpeechProbeSnapshot(0.0, 0)

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_kind": model_spec.model_kind}

    def estimate_resident_bytes(self, model_spec):
        return 3072

    def speak(self, loaded_model, request) -> DeterministicSpeechResult:
        output_format = request.format or "wav"
        payload = f"VOICE={request.voice or 'default'}\nFORMAT={output_format}\nTEXT={request.input}".encode("utf-8")
        self._last_probe = SpeechProbeSnapshot(
            speech_latency_ms=max(0.001, len(payload) / 1000.0),
            output_bytes=len(payload),
        )
        return DeterministicSpeechResult(audio_bytes=payload, format=output_format)

    def last_probe_snapshot(self) -> SpeechProbeSnapshot:
        return self._last_probe
