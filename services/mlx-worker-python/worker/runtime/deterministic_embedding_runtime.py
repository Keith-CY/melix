from __future__ import annotations

from collections.abc import Sequence

from worker.runtime.artifact_embedding_runtime import ArtifactEmbeddingError
from worker.runtime.embedding_backends import (
    resolve_embedding_backend,
    resolve_embedding_family,
)


def _explicit_fixture_backend_id(value: object) -> str:
    backend_id = str(value or "").strip()
    if not backend_id:
        raise ArtifactEmbeddingError(
            "embedding_backend_unsupported",
            "Embedding backend must be explicit.",
        )
    return backend_id


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
    if cycle_length == 1:
        first_input = inputs[0]
        for index in range(1, input_count):
            if inputs[index] != first_input:
                return 0
        return 1
    if isinstance(inputs, (list, tuple)):
        cycle = inputs[:cycle_length]
        for index in range(cycle_length, input_count, cycle_length):
            if inputs[index : index + cycle_length] != cycle:
                return 0
        return cycle_length
    for index in range(cycle_length, input_count):
        if inputs[index] != inputs[index % cycle_length]:
            return 0
    return cycle_length


class DeterministicEmbeddingRuntime:
    runtime_name = "deterministic-embed"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    def load_model(self, model_spec):
        backend_id = _explicit_fixture_backend_id(
            model_spec.ext.get("embedding_backend_id", "")
        )
        family_id = model_spec.ext.get("embedding_family_id", "")
        backend = resolve_embedding_backend(backend_id, family_id)
        family = resolve_embedding_family(family_id, backend)
        dimensions = family.dimensions(model_spec.ext.get("embedding_dimensions", self.dimensions))
        metadata = backend.metadata(dimensions)
        metadata.update(family.metadata(dimensions))
        metadata["embedding_backend_id"] = backend_id
        metadata["embedding_execution_kind"] = "fixture"
        return {
            "model_id": model_spec.model_id,
            **metadata,
        }

    def estimate_resident_bytes(self, model_spec):
        backend = resolve_embedding_backend(
            _explicit_fixture_backend_id(model_spec.ext.get("embedding_backend_id", "")),
            model_spec.ext.get("embedding_family_id", ""),
        )
        return int(backend.descriptor.estimated_resident_bytes)

    def embed_inputs(
        self,
        loaded_model,
        inputs: Sequence[str],
        *,
        request_id: str = "",
    ) -> list[list[float]]:
        _ = request_id
        dimensions = int(loaded_model.get("dimensions", self.dimensions))
        backend = loaded_model.get("embedding_backend")
        if backend is None:
            backend = resolve_embedding_backend(
                _explicit_fixture_backend_id(loaded_model.get("embedding_backend_id", "")),
                loaded_model.get("embedding_family_id", ""),
            )
        family = loaded_model.get("embedding_family_adapter")
        if family is None:
            family = resolve_embedding_family(loaded_model.get("embedding_family_id", ""), backend)

        vectors: list[list[float]] = []
        append_vector = vectors.append
        embed_text = family.embed_text
        input_count = len(inputs)
        cycle_length = _repeated_input_cycle_length(inputs)
        if cycle_length:
            if cycle_length == 1:
                vector = embed_text(backend, inputs[0], dimensions)
                copy_vector = vector.copy
                vectors = [vector]
                vectors.extend(copy_vector() for _ in range(input_count - 1))
                return vectors
            for index in range(cycle_length):
                vector = embed_text(backend, inputs[index], dimensions)
                append_vector(vector)
            cycle_vectors = tuple(vectors)
            cycle_vector_copies = tuple(vector.copy for vector in cycle_vectors)
            for _ in range(input_count // cycle_length - 1):
                vectors.extend(copy_vector() for copy_vector in cycle_vector_copies)
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
