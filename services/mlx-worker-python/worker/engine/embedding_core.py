from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry


class EmbeddingCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def embed(self, request: inference_pb2.EmbedRequest) -> inference_pb2.EmbedResponse:
        loaded_model = self._registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            return inference_pb2.EmbedResponse(
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle.")
            )

        if loaded_model.runtime_kind != "embedding":
            return inference_pb2.EmbedResponse(
                error=common_pb2.ErrorStatus(
                    code="invalid_argument",
                    message="Loaded model does not support embeddings.",
                )
            )

        try:
            vectors = self._registry.embedding_runtime.embed_inputs(
                loaded_model.runtime_model,
                request.inputs,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            return inference_pb2.EmbedResponse(
                error=common_pb2.ErrorStatus(code="runtime_error", message=str(exc))
            )

        response = inference_pb2.EmbedResponse()
        for values in vectors:
            embedding = response.embeddings.add()
            embedding.values.extend(values)
        return response
