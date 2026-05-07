from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry
from worker.runtime.audio_runtime_protocols import SpeechStreamFrame


class SpeechCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def speak(self, request: inference_pb2.SpeakRequest) -> inference_pb2.SpeakResponse:
        loaded_model = self._registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            return inference_pb2.SpeakResponse(
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle.")
            )

        if loaded_model.runtime_kind != "speech":
            return inference_pb2.SpeakResponse(
                error=common_pb2.ErrorStatus(
                    code="invalid_argument",
                    message="Loaded model does not support speech synthesis.",
                )
            )

        self._registry.start_request(request.id.request_id, runtime_kind="speech")
        try:
            runtime = self._registry.runtime_for_loaded_model(loaded_model)
            result = runtime.speak(
                loaded_model.runtime_model,
                request,
            )
            if hasattr(runtime, "last_probe_snapshot"):
                self._registry.record_speech_probe(
                    runtime.last_probe_snapshot()
                )
        except Exception as exc:  # pragma: no cover - defensive branch
            return inference_pb2.SpeakResponse(
                error=common_pb2.ErrorStatus(code="runtime_error", message=str(exc))
            )
        finally:
            self._registry.finish_request(request.id.request_id)

        return inference_pb2.SpeakResponse(
            audio_bytes=result.audio_bytes,
            format=result.format,
        )

    def speak_stream(self, request: inference_pb2.SpeakRequest):
        loaded_model = self._registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            yield self._stream_error("not_found", "Unknown model handle.")
            return

        if loaded_model.runtime_kind != "speech":
            yield self._stream_error(
                "invalid_argument",
                "Loaded model does not support speech synthesis.",
            )
            return

        self._registry.start_request(request.id.request_id, runtime_kind="speech")
        try:
            runtime = self._registry.runtime_for_loaded_model(loaded_model)
            if not hasattr(runtime, "stream_speak"):
                yield self._stream_error(
                    "unimplemented",
                    "Loaded speech runtime does not support progressive streaming.",
                )
                return

            for frame in runtime.stream_speak(
                loaded_model.runtime_model,
                request,
            ):
                if frame.kind == "finish" and hasattr(runtime, "last_probe_snapshot"):
                    self._registry.record_speech_probe(runtime.last_probe_snapshot())
                yield self._stream_event(frame)
        except Exception as exc:  # pragma: no cover - defensive branch
            yield self._stream_error("runtime_error", str(exc))
        finally:
            self._registry.finish_request(request.id.request_id)

    @staticmethod
    def _stream_error(code: str, message: str) -> inference_pb2.SpeakStreamEvent:
        return inference_pb2.SpeakStreamEvent(
            kind=inference_pb2.SPEAK_STREAM_EVENT_KIND_ERROR,
            error=common_pb2.ErrorStatus(code=code, message=message),
        )

    @staticmethod
    def _stream_event(frame: SpeechStreamFrame) -> inference_pb2.SpeakStreamEvent:
        if frame.kind == "envelope":
            event = inference_pb2.SpeakStreamEvent(
                kind=inference_pb2.SPEAK_STREAM_EVENT_KIND_ENVELOPE,
                audio_bytes=frame.audio_bytes,
            )
            if frame.envelope is not None:
                event.envelope.format = frame.envelope.format
                event.envelope.container = frame.envelope.container
                event.envelope.codec = frame.envelope.codec
                event.envelope.sample_rate_hz = frame.envelope.sample_rate_hz
                event.envelope.channel_count = frame.envelope.channel_count
                event.envelope.bits_per_sample = frame.envelope.bits_per_sample
                event.envelope.stream_interval_ms = frame.envelope.stream_interval_ms
                event.envelope.wav_sizes_unknown = frame.envelope.wav_sizes_unknown
                event.envelope.ext.update(frame.envelope.ext)
            return event

        if frame.kind == "audio_chunk":
            return inference_pb2.SpeakStreamEvent(
                kind=inference_pb2.SPEAK_STREAM_EVENT_KIND_AUDIO_CHUNK,
                audio_bytes=frame.audio_bytes,
            )

        if frame.kind == "finish":
            event = inference_pb2.SpeakStreamEvent(kind=inference_pb2.SPEAK_STREAM_EVENT_KIND_FINISH)
            if frame.finish is not None:
                event.finish.speech_streaming_enabled = frame.finish.streaming_enabled
                event.finish.speech_streaming_interval_ms = frame.finish.stream_interval_ms
                event.finish.speech_first_audio_latency_ms = frame.finish.first_audio_latency_ms
                event.finish.speech_latency_ms = frame.finish.speech_latency_ms
                event.finish.audio_bytes = frame.finish.audio_bytes
                event.finish.audio_chunk_count = frame.finish.audio_chunk_count
            return event

        return SpeechCore._stream_error("runtime_error", f"Unknown speech stream frame kind: {frame.kind}")
