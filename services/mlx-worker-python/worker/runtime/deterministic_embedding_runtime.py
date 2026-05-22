from __future__ import annotations

from worker.runtime.embedding_backends import (
    resolve_embedding_backend,
    resolve_embedding_family,
)


class DeterministicEmbeddingRuntime:
    runtime_name = "deterministic-embed"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    def load_model(self, model_spec):
        backend = resolve_embedding_backend(model_spec.ext.get("embedding_backend_id", "bert-v1"))
        family = resolve_embedding_family(model_spec.ext.get("embedding_family_id", ""), backend)
        dimensions = family.dimensions(model_spec.ext.get("embedding_dimensions", self.dimensions))
        metadata = backend.metadata(dimensions)
        metadata.update(family.metadata(dimensions))
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
        family = loaded_model.get("embedding_family_adapter")
        if family is None:
            family = resolve_embedding_family(loaded_model.get("embedding_family_id", ""), backend)

        vector_cache: dict[str, list[float]] = {}
        vectors: list[list[float]] = []
        cache_get = vector_cache.get
        append_vector = vectors.append
        embed_text = family.embed_text
        for text in inputs:
            vector = cache_get(text)
            if vector is None:
                vector = embed_text(backend, text, dimensions)
                vector_cache[text] = vector
                append_vector(vector)
            else:
                append_vector(vector.copy())
        return vectors
