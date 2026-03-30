from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import unicodedata


@dataclass(frozen=True)
class EmbeddingBackendDescriptor:
    backend_id: str
    family_id: str
    pooling_mode: str
    normalization: str
    estimated_resident_bytes: int


class DeterministicEmbeddingBackend:
    descriptor: EmbeddingBackendDescriptor

    def metadata(self, dimensions: int) -> dict[str, object]:
        return {
            "embedding_backend_id": self.descriptor.backend_id,
            "embedding_family_id": self.descriptor.family_id,
            "embedding_pooling_mode": self.descriptor.pooling_mode,
            "embedding_normalization": self.descriptor.normalization,
            "estimated_resident_bytes": self.descriptor.estimated_resident_bytes,
            "dimensions": dimensions,
            "embedding_backend": self,
        }

    def embed_text(self, text: str, dimensions: int) -> list[float]:
        raise NotImplementedError

    def _project_digest(self, seed_text: str, dimensions: int) -> list[float]:
        digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
        values: list[float] = []

        for index in range(dimensions):
            start = (index * 4) % len(digest)
            chunk = digest[start : start + 4]
            if len(chunk) < 4:
                chunk = chunk + digest[: 4 - len(chunk)]
            raw = int.from_bytes(chunk, "little")
            normalized = (raw / 0xFFFFFFFF) * 2.0 - 1.0
            values.append(normalized)

        l2_norm = math.sqrt(sum(value * value for value in values))
        if l2_norm == 0.0:
            return [0.0] * dimensions
        return [round(value / l2_norm, 6) for value in values]

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        return " ".join(text.split())


class BERTEmbeddingBackend(DeterministicEmbeddingBackend):
    descriptor = EmbeddingBackendDescriptor(
        backend_id="bert-v1",
        family_id="bert",
        pooling_mode="cls",
        normalization="l2",
        estimated_resident_bytes=1536,
    )

    def embed_text(self, text: str, dimensions: int) -> list[float]:
        canonical = self._collapse_whitespace(text.strip().lower())
        return self._project_digest(f"bert::{canonical}", dimensions)


class XLMREmbeddingBackend(DeterministicEmbeddingBackend):
    descriptor = EmbeddingBackendDescriptor(
        backend_id="xlmr-v1",
        family_id="xlmr",
        pooling_mode="mean",
        normalization="l2",
        estimated_resident_bytes=1792,
    )

    def embed_text(self, text: str, dimensions: int) -> list[float]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        canonical = self._collapse_whitespace(normalized.strip())
        return self._project_digest(f"xlmr::{canonical}", dimensions)


def resolve_embedding_backend(backend_id: str) -> DeterministicEmbeddingBackend:
    normalized = backend_id.strip().lower()
    if normalized == "" or normalized == "bert-v1":
        return BERTEmbeddingBackend()
    if normalized == "xlmr-v1":
        return XLMREmbeddingBackend()
    raise ValueError(f"Unsupported embedding backend: {backend_id}")
