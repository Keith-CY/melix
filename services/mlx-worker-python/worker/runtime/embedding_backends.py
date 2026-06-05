from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
import unicodedata

_SHA256 = hashlib.sha256
_UNPACK_DIGEST_UINT32 = struct.Struct("<8I").unpack
_DIGEST_UINT32_SCALE = 2.0 / 0xFFFFFFFF


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
        base_values = [
            raw * _DIGEST_UINT32_SCALE - 1.0
            for raw in _UNPACK_DIGEST_UINT32(_SHA256(seed_text.encode("utf-8")).digest())
        ]
        full_repeats, remainder = divmod(dimensions, 8)
        squared_sum = sum(value * value for value in base_values) * full_repeats
        if remainder == 1:
            value = base_values[0]
            squared_sum += value * value
        else:
            for index in range(remainder):
                value = base_values[index]
                squared_sum += value * value

        l2_norm = math.sqrt(squared_sum)
        if l2_norm == 0.0:
            return [0.0] * dimensions
        inverse_l2_norm = 1.0 / l2_norm
        normalized_base = [round(value * inverse_l2_norm, 6) for value in base_values]
        if remainder == 0:
            if full_repeats == 1:
                return normalized_base
            return normalized_base * full_repeats
        result = normalized_base * full_repeats
        if remainder == 1:
            result.append(normalized_base[0])
        else:
            for index in range(remainder):
                result.append(normalized_base[index])
        return result

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
