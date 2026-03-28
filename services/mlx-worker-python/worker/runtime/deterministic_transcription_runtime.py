from __future__ import annotations

from dataclasses import dataclass

from worker.runtime.audio_preprocessing import prepare_audio_input


@dataclass(frozen=True)
class TranscriptionProbeSnapshot:
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    estimated_duration_seconds: float
    chunk_count: int
    transcription_latency_ms: float


@dataclass(frozen=True)
class DeterministicTranscript:
    text: str
    language: str
    duration_seconds: float


class DeterministicTranscriptionRuntime:
    runtime_name = "deterministic-transcription"

    def __init__(self) -> None:
        self._last_probe = TranscriptionProbeSnapshot(0.0, 0, 0, 0.0, 0, 0.0)

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_kind": model_spec.model_kind}

    def estimate_resident_bytes(self, model_spec):
        return 3584

    def transcribe(self, loaded_model, request) -> DeterministicTranscript:
        prepared = prepare_audio_input(request)
        transcript = prepared.decoded_text() or "<silence>"
        self._last_probe = TranscriptionProbeSnapshot(
            preprocess_latency_ms=prepared.preprocess_latency_ms,
            preprocess_input_bytes=prepared.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
            estimated_duration_seconds=prepared.duration_seconds,
            chunk_count=prepared.chunk_count,
            transcription_latency_ms=max(0.0, prepared.preprocess_latency_ms / 2.0),
        )
        return DeterministicTranscript(
            text=transcript,
            language=request.language or "und",
            duration_seconds=prepared.duration_seconds,
        )

    def last_probe_snapshot(self) -> TranscriptionProbeSnapshot:
        return self._last_probe
