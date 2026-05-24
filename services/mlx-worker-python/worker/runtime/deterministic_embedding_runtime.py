from __future__ import annotations

from collections.abc import Sequence

from worker.runtime.embedding_backends import (
    resolve_embedding_backend,
    resolve_embedding_family,
)


def _repeated_input_cycle_length(inputs: Sequence[str]) -> int:
    input_count = len(inputs)
    if input_count < 1024:
        return 0
    seen_inputs: set[str] = set()
    seen_inputs_add = seen_inputs.add
    for index, text in enumerate(inputs):
        if text in seen_inputs:
            cycle_length = index
            break
        seen_inputs_add(text)
    else:
        return 0
    if cycle_length == 0 or input_count % cycle_length != 0:
        return 0
    cycle = inputs[:cycle_length]
    for index in range(cycle_length, input_count, cycle_length):
        if inputs[index : index + cycle_length] != cycle:
            return 0
    return cycle_length


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

    def embed_inputs(self, loaded_model, inputs: Sequence[str]) -> list[list[float]]:
        dimensions = int(loaded_model.get("dimensions", self.dimensions))
        backend = loaded_model.get("embedding_backend")
        if backend is None:
            backend = resolve_embedding_backend(loaded_model.get("embedding_backend_id", "bert-v1"))
        family = loaded_model.get("embedding_family_adapter")
        if family is None:
            family = resolve_embedding_family(loaded_model.get("embedding_family_id", ""), backend)

        vectors: list[list[float]] = []
        append_vector = vectors.append
        embed_text = family.embed_text
        cycle_length = _repeated_input_cycle_length(inputs)
        if cycle_length:
            for index in range(cycle_length):
                vector = embed_text(backend, inputs[index], dimensions)
                append_vector(vector)
            cycle_vectors = tuple(vectors)
            repeat_count = len(inputs) // cycle_length - 1
            for _ in range(repeat_count):
                for vector in cycle_vectors:
                    append_vector(vector.copy())
            return vectors

        vector_cache: dict[str, list[float]] = {}
        cache_get = vector_cache.get
        for text in inputs:
            vector = cache_get(text)
            if vector is None:
                vector = embed_text(backend, text, dimensions)
                vector_cache[text] = vector
                append_vector(vector)
            else:
                append_vector(vector.copy())
        return vectors
