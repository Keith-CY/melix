from __future__ import annotations

from dataclasses import dataclass

from worker.runtime.audio_runtime_protocols import (
    SpeechStreamEnvelope,
    SpeechStreamFinish,
    SpeechStreamFrame,
)
from worker.runtime.deterministic_delay import sleep_if_configured
from worker.runtime.deterministic_probe_mixin import DeterministicProbeMixin
from worker.runtime.wav_helpers import (
    audio_to_pcm_chunks,
    progressive_wav_header,
    stream_chunk_sample_limit,
)


@dataclass(frozen=True)
class SpeechProbeSnapshot:
    speech_latency_ms: float
    output_bytes: int
    streaming_enabled: bool = False
    stream_interval_ms: int = 0
    first_audio_latency_ms: float = 0.0
    chunk_count: int = 0


@dataclass(frozen=True)
class DeterministicSpeechResult:
    audio_bytes: bytes
    format: str


class DeterministicSpeechRuntime(DeterministicProbeMixin[SpeechProbeSnapshot]):
    runtime_name = "deterministic-speech"

    def __init__(self) -> None:
        self._last_probe = SpeechProbeSnapshot(0.0, 0)

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_kind": model_spec.model_kind}

    def estimate_resident_bytes(self, model_spec):
        return 3072

    def speak(self, loaded_model, request) -> DeterministicSpeechResult:
        output_format = request.format or "wav"
        payload = (
            f"VOICE={request.voice or 'default'}\nFORMAT={output_format}\nTEXT={request.input}"
        ).encode("utf-8")
        sleep_if_configured("speech")
        self._last_probe = SpeechProbeSnapshot(
            speech_latency_ms=max(0.001, len(payload) / 1000.0),
            output_bytes=len(payload),
        )
        return DeterministicSpeechResult(audio_bytes=payload, format=output_format)

    def stream_speak(self, loaded_model, request):
        output_format = (request.format or "wav").lower()
        if output_format != "wav":
            raise ValueError("deterministic speech streaming only supports wav output.")

        from time import perf_counter

        payload = (
            f"VOICE={request.voice or 'default'}\nFORMAT=wav\nTEXT={request.input}"
        ).encode("utf-8")
        stream_interval_ms = max(1, int(request.stream_interval_ms or 20))
        sample_rate = 24_000
        samples = [((byte % 64) - 32) / 32.0 for byte in payload] or [0.0]
        started_at = perf_counter()
        header = progressive_wav_header(sample_rate)
        output_bytes = len(header)
        chunk_count = 0
        first_audio_latency_ms = 0.0

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
        sleep_if_configured("speech")
        for pcm_chunk in audio_to_pcm_chunks(
            samples,
            chunk_sample_limit=stream_chunk_sample_limit(sample_rate, stream_interval_ms),
        ):
            if first_audio_latency_ms == 0.0:
                first_audio_latency_ms = max((perf_counter() - started_at) * 1000.0, 0.001)
            chunk_count += 1
            output_bytes += len(pcm_chunk)
            yield SpeechStreamFrame(kind="audio_chunk", audio_bytes=pcm_chunk)

        speech_latency_ms = max((perf_counter() - started_at) * 1000.0, 0.001)
        self._last_probe = SpeechProbeSnapshot(
            speech_latency_ms=speech_latency_ms,
            output_bytes=output_bytes,
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
