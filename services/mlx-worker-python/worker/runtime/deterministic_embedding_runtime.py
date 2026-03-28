from __future__ import annotations

import hashlib


class DeterministicEmbeddingRuntime:
    runtime_name = "deterministic-embed"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    def load_model(self, model_spec):
        return {
            "model_id": model_spec.model_id,
            "dimensions": self.dimensions,
        }

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 1536

    def embed_inputs(self, loaded_model, inputs: list[str]) -> list[list[float]]:
        dimensions = int(loaded_model.get("dimensions", self.dimensions))
        return [self._embed_text(text, dimensions) for text in inputs]

    @staticmethod
    def _embed_text(text: str, dimensions: int) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []

        for index in range(dimensions):
            start = (index * 4) % len(digest)
            chunk = digest[start : start + 4]
            if len(chunk) < 4:
                chunk = chunk + digest[: 4 - len(chunk)]
            raw = int.from_bytes(chunk, "little")
            normalized = (raw / 0xFFFFFFFF) * 2.0 - 1.0
            values.append(round(normalized, 6))

        return values
