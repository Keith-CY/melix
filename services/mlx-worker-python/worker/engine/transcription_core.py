from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry


class TranscriptionCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def transcribe(self, request: inference_pb2.TranscribeRequest) -> inference_pb2.TranscribeResponse:
        loaded_model = self._registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            return inference_pb2.TranscribeResponse(
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle.")
            )

        if loaded_model.runtime_kind != "transcription":
            return inference_pb2.TranscribeResponse(
                error=common_pb2.ErrorStatus(
                    code="invalid_argument",
                    message="Loaded model does not support transcription.",
                )
            )

        self._registry.start_request(request.id.request_id, runtime_kind="transcription")
        try:
            transcript = self._registry.transcription_runtime.transcribe(
                loaded_model.runtime_model,
                request,
            )
            if hasattr(self._registry.transcription_runtime, "last_probe_snapshot"):
                self._registry.record_transcription_probe(
                    self._registry.transcription_runtime.last_probe_snapshot()
                )
        except Exception as exc:  # pragma: no cover - defensive branch
            return inference_pb2.TranscribeResponse(
                error=common_pb2.ErrorStatus(code="runtime_error", message=str(exc))
            )
        finally:
            self._registry.finish_request(request.id.request_id)

        return inference_pb2.TranscribeResponse(
            text=transcript.text,
            language=transcript.language,
            duration_seconds=transcript.duration_seconds,
        )
