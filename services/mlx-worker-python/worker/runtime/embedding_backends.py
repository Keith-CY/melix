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


@dataclass(frozen=True)
class EmbeddingFamilyDescriptor:
    family_id: str
    pooling_mode: str
    normalization: str
    default_dimensions: int


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
        base_values = [
            (int.from_bytes(digest[start : start + 4], "little") / 0xFFFFFFFF) * 2.0
            - 1.0
            for start in range(0, len(digest), 4)
        ]
        full_repeats, remainder = divmod(dimensions, len(base_values))
        values = base_values * full_repeats + base_values[:remainder]

        l2_norm = math.sqrt(sum(value * value for value in values))
        if l2_norm == 0.0:
            return [0.0] * dimensions
        return [round(value / l2_norm, 6) for value in values]

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        return " ".join(text.split())


class DeterministicEmbeddingFamilyAdapter:
    descriptor: EmbeddingFamilyDescriptor

    def metadata(self, dimensions: int) -> dict[str, object]:
        return {
            "embedding_family_id": self.descriptor.family_id,
            "embedding_pooling_mode": self.descriptor.pooling_mode,
            "embedding_normalization": self.descriptor.normalization,
            "dimensions": dimensions,
            "embedding_family_adapter": self,
        }

    def dimensions(self, configured_dimensions: object | None) -> int:
        return _coerce_dimensions(configured_dimensions, self.descriptor.default_dimensions)

    def embed_text(
        self,
        backend: DeterministicEmbeddingBackend,
        text: str,
        dimensions: int,
    ) -> list[float]:
        raise NotImplementedError


class DefaultEmbeddingFamilyAdapter(DeterministicEmbeddingFamilyAdapter):
    def __init__(self, descriptor: EmbeddingFamilyDescriptor) -> None:
        self.descriptor = descriptor

    def embed_text(
        self,
        backend: DeterministicEmbeddingBackend,
        text: str,
        dimensions: int,
    ) -> list[float]:
        return backend.embed_text(text, dimensions)


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


class BGEEmbeddingFamilyAdapter(DeterministicEmbeddingFamilyAdapter):
    descriptor = EmbeddingFamilyDescriptor(
        family_id="bge-m3",
        pooling_mode="cls",
        normalization="l2",
        default_dimensions=8,
    )

    def embed_text(
        self,
        backend: DeterministicEmbeddingBackend,
        text: str,
        dimensions: int,
    ) -> list[float]:
        return backend.embed_text(
            f"Represent this sentence for retrieval: {text}",
            dimensions,
        )


class MXBAIEmbeddingFamilyAdapter(DeterministicEmbeddingFamilyAdapter):
    descriptor = EmbeddingFamilyDescriptor(
        family_id="mxbai-embed",
        pooling_mode="mean",
        normalization="l2",
        default_dimensions=10,
    )

    def embed_text(
        self,
        backend: DeterministicEmbeddingBackend,
        text: str,
        dimensions: int,
    ) -> list[float]:
        return backend.embed_text(
            f"Represent this paragraph for retrieval: {text}",
            dimensions,
        )


def resolve_embedding_backend(backend_id: str) -> DeterministicEmbeddingBackend:
    normalized = backend_id.strip().lower()
    if normalized == "" or normalized == "bert-v1":
        return BERTEmbeddingBackend()
    if normalized == "xlmr-v1":
        return XLMREmbeddingBackend()
    raise ValueError(f"Unsupported embedding backend: {backend_id}")


def resolve_embedding_family(
    family_id: str,
    backend: DeterministicEmbeddingBackend,
) -> DeterministicEmbeddingFamilyAdapter:
    normalized = family_id.strip().lower()
    if normalized == "" or normalized == backend.descriptor.family_id:
        return DefaultEmbeddingFamilyAdapter(
            EmbeddingFamilyDescriptor(
                family_id=backend.descriptor.family_id,
                pooling_mode=backend.descriptor.pooling_mode,
                normalization=backend.descriptor.normalization,
                default_dimensions=8,
            )
        )
    if normalized == "bge-m3":
        return BGEEmbeddingFamilyAdapter()
    if normalized == "mxbai-embed":
        return MXBAIEmbeddingFamilyAdapter()
    raise ValueError(f"Unsupported embedding family: {family_id}")


def _coerce_dimensions(value: object | None, default_dimensions: int) -> int:
    if isinstance(value, int):
        return value if value > 0 else default_dimensions
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            parsed = int(stripped)
            if parsed > 0:
                return parsed
    return default_dimensions
