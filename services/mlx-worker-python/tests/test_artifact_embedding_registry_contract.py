from __future__ import annotations

from collections.abc import Mapping

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.registry import (
    MemoryBudgetExceeded,
    WorkerRegistry,
    _loaded_model_estimated_resident_bytes,
    _spec_with_embedding_load_receipt,
)


class SnapshotEstimateRuntime:
    def __init__(self, *, source_estimate: int, loaded_estimate: int) -> None:
        self.source_estimate = source_estimate
        self.loaded_estimate = loaded_estimate
        self.closed_model_ids: list[str] = []

    def estimate_resident_bytes(self, _model_spec) -> int:
        return self.source_estimate

    def load_model(self, model_spec) -> dict[str, object]:
        return {
            "model_id": model_spec.model_id,
            "embedding_load_receipt": {
                "estimated_resident_bytes": self.loaded_estimate,
            },
        }

    @staticmethod
    def estimate_loaded_resident_bytes(loaded_model) -> int:
        return int(
            loaded_model["embedding_load_receipt"]["estimated_resident_bytes"]
        )

    def close_loaded_model(self, loaded_model) -> None:
        self.closed_model_ids.append(loaded_model["model_id"])


class ReceiptRuntime:
    load_receipt = {
        "requested_backend_id": "mlx-bert-v1",
        "effective_backend_id": "mlx-bert-v1",
        "model_hash": "sha256:model",
        "tokenizer_hash": "sha256:tokenizer",
        "requested_pooling_mode": "mean",
        "artifact_pooling_mode": "mean",
        "effective_pooling_mode": "mean",
        "requested_normalization": "l2",
        "artifact_normalization": "l2",
        "effective_normalization": "l2",
        "requested_dimensions": 4,
        "effective_dimensions": 4,
        "requested_max_length": 32,
        "effective_max_length": 32,
        "requested_vector_kind": "single_dense",
        "effective_vector_kind": "single_dense",
        "requested_dtype": "float32",
        "effective_dtype": "float32",
        "vector_kind": "single_dense",
        "dtype": "float32",
        "estimated_resident_bytes": 8,
        "measured_resident_bytes": 7,
    }
    request_receipt = {
        "request_id": "request-1",
        "backend_id": "mlx-bert-v1",
        "batch_size": 2,
        "input_token_count": 5,
        "forward_count": 1,
        "output_row_count": 2,
        "dimensions": 4,
        "vector_kind": "single_dense",
        "dtype": "float32",
        "finite_output": True,
    }

    @staticmethod
    def estimate_resident_bytes(_model_spec) -> int:
        return 8

    def load_model(self, model_spec) -> dict[str, object]:
        return {
            "model_id": model_spec.model_id,
            "embedding_load_receipt": dict(self.load_receipt),
            "embedding_request_receipt": dict(self.request_receipt),
        }

    @staticmethod
    def estimate_loaded_resident_bytes(_loaded_model) -> int:
        return 8

    @staticmethod
    def close_loaded_model(_loaded_model) -> None:
        return None


def _embedding_model_spec(model_id: str) -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id=model_id,
        model_kind="embedding",
        ext={"embedding_backend_id": "mlx-bert-v1"},
    )


def test_worker_registry_reconciles_snapshot_bound_embedding_residency() -> None:
    runtime = SnapshotEstimateRuntime(source_estimate=8, loaded_estimate=80)
    registry = WorkerRegistry(
        embedding_runtime=runtime,
        process_memory_budget_bytes=100,
    )

    loaded = registry.load_model(
        _embedding_model_spec("snapshot-sized-embedding"),
        memory_budget_bytes=90,
    )

    assert loaded.estimated_resident_bytes == 80
    assert registry.runtime_stats().model_resident_bytes == 80
    assert registry._reserved_model_resident_bytes == 0
    assert runtime.closed_model_ids == []


@pytest.mark.parametrize(
    ("process_budget", "request_budget", "expected_budget"),
    [
        (50, 0, 50),
        (100, 50, 50),
    ],
)
def test_worker_registry_rejects_snapshot_bound_embedding_residency_and_closes(
    process_budget: int,
    request_budget: int,
    expected_budget: int,
) -> None:
    runtime = SnapshotEstimateRuntime(source_estimate=8, loaded_estimate=80)
    registry = WorkerRegistry(
        embedding_runtime=runtime,
        process_memory_budget_bytes=process_budget,
    )

    with pytest.raises(MemoryBudgetExceeded) as caught:
        registry.load_model(
            _embedding_model_spec("snapshot-too-large-embedding"),
            memory_budget_bytes=request_budget,
        )

    assert caught.value.budget_bytes == expected_budget
    assert caught.value.projected_resident_bytes == 80
    assert registry.runtime_stats().model_resident_bytes == 0
    assert registry._reserved_model_resident_bytes == 0
    assert runtime.closed_model_ids == ["snapshot-too-large-embedding"]


def test_loaded_model_resident_estimate_falls_back_without_snapshot_estimate() -> None:
    class NoEstimateRuntime:
        pass

    class EmptyEstimateRuntime:
        @staticmethod
        def estimate_loaded_resident_bytes(_loaded_model) -> None:
            return None

    assert _loaded_model_estimated_resident_bytes(
        NoEstimateRuntime(), object(), fallback=13
    ) == 13
    assert _loaded_model_estimated_resident_bytes(
        EmptyEstimateRuntime(), object(), fallback=17
    ) == 17


@pytest.mark.parametrize("estimate", [True, -1, 1.5, "8"])
def test_loaded_model_resident_estimate_rejects_invalid_values(estimate: object) -> None:
    class InvalidEstimateRuntime:
        @staticmethod
        def estimate_loaded_resident_bytes(_loaded_model) -> object:
            return estimate

    with pytest.raises(
        RuntimeError,
        match="invalid loaded-model resident-byte estimate",
    ):
        _loaded_model_estimated_resident_bytes(
            InvalidEstimateRuntime(), object(), fallback=8
        )


def test_load_receipt_projection_requires_mapping_receipt() -> None:
    model_spec = common_pb2.ModelSpec(model_id="fixture", ext={"existing": "value"})

    assert _spec_with_embedding_load_receipt(model_spec, object()) is model_spec
    assert _spec_with_embedding_load_receipt(model_spec, {}) is model_spec
    assert (
        _spec_with_embedding_load_receipt(
            model_spec,
            {"embedding_load_receipt": object()},
        )
        is model_spec
    )


def test_registry_projects_complete_embedding_receipts_and_invalidates_summary() -> None:
    runtime = ReceiptRuntime()
    registry = WorkerRegistry(embedding_runtime=runtime)

    loaded = registry.load_model(_embedding_model_spec("receipt-embedding"))
    assert loaded.spec.ext["embedding_backend_id"] == "mlx-bert-v1"
    assert loaded.spec.ext["melix.embedding.load.schema"] == (
        "melix.embedding_load_receipt.v1"
    )
    for field_name, value in runtime.load_receipt.items():
        assert loaded.spec.ext[f"melix.embedding.load.{field_name}"] == str(value)
    assert loaded.spec.ext["melix.embedding.load.artifact_pooling_mode"] == "mean"
    assert loaded.spec.ext["melix.embedding.load.artifact_normalization"] == "l2"

    first_summary = registry.list_loaded_model_summaries()[0]
    assert first_summary.model.ext["melix.embedding.request.schema"] == (
        "melix.embedding_request_receipt.v1"
    )
    for field_name, value in runtime.request_receipt.items():
        assert first_summary.model.ext[f"melix.embedding.request.{field_name}"] == str(
            value
        )

    assert isinstance(loaded.runtime_model, Mapping)
    request_receipt = loaded.runtime_model["embedding_request_receipt"]
    assert isinstance(request_receipt, dict)
    request_receipt["request_id"] = "request-2"
    assert (
        registry.list_loaded_model_summaries()[0].model.ext[
            "melix.embedding.request.request_id"
        ]
        == "request-1"
    )

    registry.record_embedding_request_receipt("missing-handle")
    registry.record_embedding_request_receipt(loaded.handle)

    assert (
        registry.list_loaded_model_summaries()[0].model.ext[
            "melix.embedding.request.request_id"
        ]
        == "request-2"
    )
