from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry


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
            result = self._registry.speech_runtime.speak(
                loaded_model.runtime_model,
                request,
            )
            if hasattr(self._registry.speech_runtime, "last_probe_snapshot"):
                self._registry.record_speech_probe(
                    self._registry.speech_runtime.last_probe_snapshot()
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
