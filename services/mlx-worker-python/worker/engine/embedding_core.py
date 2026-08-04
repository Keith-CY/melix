from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry
from worker.runtime.artifact_embedding_runtime import ArtifactEmbeddingError
from worker.runtime.runtime_utils import callable_accepts_kwarg


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
            if callable_accepts_kwarg(runtime_embed_inputs, "request_id"):
                vectors = runtime_embed_inputs(
                    runtime_model,
                    request_inputs,
                    request_id=request.id.request_id,
                )
            else:
                vectors = runtime_embed_inputs(runtime_model, request_inputs)
        except ArtifactEmbeddingError as exc:
            return _EMBED_RESPONSE(
                error=_ERROR_STATUS(code=exc.code, message=str(exc))
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
        record_request_receipt = getattr(
            registry,
            "record_embedding_request_receipt",
            None,
        )
        if record_request_receipt is not None:
            record_request_receipt(loaded_model.handle)
        return response
