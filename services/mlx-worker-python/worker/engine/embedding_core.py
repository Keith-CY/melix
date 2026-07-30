from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry


_EMBED_RESPONSE = inference_pb2.EmbedResponse
_ERROR_STATUS = common_pb2.ErrorStatus


class EmbeddingCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def embed(self, request: inference_pb2.EmbedRequest) -> inference_pb2.EmbedResponse:
        registry = self._registry
        loaded_model = registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            return _EMBED_RESPONSE(
                error=_ERROR_STATUS(code="not_found", message="Unknown model handle.")
            )

        if loaded_model.runtime_kind != "embedding":
            return _EMBED_RESPONSE(
                error=_ERROR_STATUS(
                    code="invalid_argument",
                    message="Loaded model does not support embeddings.",
                )
            )

        runtime_embed_inputs = registry.embedding_runtime.embed_inputs
        runtime_model = loaded_model.runtime_model
        request_inputs = request.inputs

        try:
            vectors = runtime_embed_inputs(
                runtime_model,
                request_inputs,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            return _EMBED_RESPONSE(
                error=_ERROR_STATUS(code="runtime_error", message=str(exc))
            )

        response = _EMBED_RESPONSE()
        embeddings = response.embeddings
        add_embedding = embeddings.add
        for values in vectors:
            embedding = add_embedding()
            embedding_values = embedding.values
            embedding_values.extend(values)
        return response
