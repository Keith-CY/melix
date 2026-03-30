from __future__ import annotations

from worker.runtime.embedding_backends import resolve_embedding_backend


class DeterministicEmbeddingRuntime:
    runtime_name = "deterministic-embed"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    def load_model(self, model_spec):
        backend = resolve_embedding_backend(model_spec.ext.get("embedding_backend_id", "bert-v1"))
        metadata = backend.metadata(self.dimensions)
        return {
            "model_id": model_spec.model_id,
            **metadata,
        }

    def estimate_resident_bytes(self, model_spec):
        backend = resolve_embedding_backend(model_spec.ext.get("embedding_backend_id", "bert-v1"))
        return int(backend.descriptor.estimated_resident_bytes)

    def embed_inputs(self, loaded_model, inputs: list[str]) -> list[list[float]]:
        dimensions = int(loaded_model.get("dimensions", self.dimensions))
        backend = loaded_model.get("embedding_backend")
        if backend is None:
            backend = resolve_embedding_backend(loaded_model.get("embedding_backend_id", "bert-v1"))
        return [backend.embed_text(text, dimensions) for text in inputs]
