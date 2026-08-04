from __future__ import annotations

from typing import Any

from worker.runtime.artifact_embedding_runtime import (
    ArtifactEmbeddingError,
    MLXEmbeddingRuntime,
)
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.runtime_utils import callable_accepts_kwarg


_ARTIFACT_BACKEND_IDS = {"mlx-bert-v1", "mlx-xlmr-v1"}
_FIXTURE_BACKEND_IDS = {
    "deterministic-fixture-v1",
}


class EmbeddingRuntime:
    runtime_name = "embedding-router"

    def __init__(
        self,
        *,
        artifact_runtime: MLXEmbeddingRuntime | None = None,
        fixture_runtime: DeterministicEmbeddingRuntime | None = None,
        executor: MLXRuntimeExecutor | None = None,
    ) -> None:
        self._artifact_runtime = artifact_runtime or MLXEmbeddingRuntime(executor=executor)
        self._fixture_runtime = fixture_runtime or DeterministicEmbeddingRuntime()

    def _runtime_for_backend(self, backend_id: str) -> object:
        normalized = backend_id.strip().lower()
        if normalized in _ARTIFACT_BACKEND_IDS:
            return self._artifact_runtime
        if normalized in _FIXTURE_BACKEND_IDS:
            return self._fixture_runtime
        raise ArtifactEmbeddingError(
            "embedding_backend_unsupported",
            f"Unsupported embedding backend: {backend_id or '<missing>'}.",
        )

    def _runtime_for_model_spec(self, model_spec: Any) -> object:
        backend_id = str(model_spec.ext.get("embedding_backend_id", "") or "")
        return self._runtime_for_backend(backend_id)

    def estimate_resident_bytes(self, model_spec: Any) -> int:
        runtime = self._runtime_for_model_spec(model_spec)
        return int(runtime.estimate_resident_bytes(model_spec))

    def load_model(self, model_spec: Any) -> dict[str, object]:
        runtime = self._runtime_for_model_spec(model_spec)
        loaded_model = runtime.load_model(model_spec)
        loaded_model["embedding_runtime"] = runtime
        return loaded_model

    @staticmethod
    def estimate_loaded_resident_bytes(loaded_model: dict[str, object]) -> int | None:
        runtime = loaded_model.get("embedding_runtime")
        estimator = getattr(runtime, "estimate_loaded_resident_bytes", None)
        if not callable(estimator):
            return None
        return int(estimator(loaded_model))

    def embed_inputs(
        self,
        loaded_model: dict[str, object],
        inputs: Any,
        *,
        request_id: str = "",
    ) -> list[list[float]]:
        runtime = loaded_model.get("embedding_runtime")
        if runtime is None:
            backend_id = str(loaded_model.get("embedding_backend_id", "") or "")
            runtime = self._runtime_for_backend(backend_id)
        embed_inputs = runtime.embed_inputs
        if callable_accepts_kwarg(embed_inputs, "request_id"):
            return embed_inputs(loaded_model, inputs, request_id=request_id)
        return embed_inputs(loaded_model, inputs)

    @staticmethod
    def close_loaded_model(loaded_model: dict[str, object]) -> None:
        runtime = loaded_model.get("embedding_runtime")
        close_loaded_model = getattr(runtime, "close_loaded_model", None)
        if callable(close_loaded_model):
            close_loaded_model(loaded_model)
