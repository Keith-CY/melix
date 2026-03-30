import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.rerank_backends import (
    BasicRerankFamilyAdapter,
    DeterministicRerankBackend,
    JinaV3RerankFamilyAdapter,
    RerankFamilyAdapter,
    resolve_rerank_backend,
    resolve_rerank_family,
)


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_services(environment: dict[str, str] | None = None):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(environment=environment),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    return runtime_service, inference_service


def load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_rerank_returns_sorted_scores_and_honors_top_k() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_rerank_model())

    first = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-1"),
            model_handle=model_handle,
            query="swift control plane runtime",
            documents=[
                "swift control plane runtime",
                "embedding worker batch path",
                "control plane swift worker route",
            ],
            top_k=2,
        ),
        context=None,
    )
    second = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-2"),
            model_handle=model_handle,
            query="swift control plane runtime",
            documents=[
                "swift control plane runtime",
                "embedding worker batch path",
                "control plane swift worker route",
            ],
            top_k=2,
        ),
        context=None,
    )

    assert first.error.code == ""
    assert len(first.items) == 2
    assert first.items[0].score >= first.items[1].score
    assert first.items[0].index == second.items[0].index
    assert first.items[1].index == second.items[1].index
    assert first.items[0].score == second.items[0].score
    assert first.items[1].score == second.items[1].score


def test_load_model_exposes_jina_v3_rerank_metadata() -> None:
    runtime = DeterministicRerankRuntime()

    loaded = runtime.load_model(WorkerModelCatalog.dev_rerank_model())

    assert loaded["rerank_backend_id"] == "token-overlap-v1"
    assert loaded["rerank_family_id"] == "jina-v3"
    assert loaded["rerank_scoring_mode"] == "order-aware-overlap"


def test_jina_v3_rerank_prefers_exact_query_order() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_rerank_model())

    rerank = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-jina-v3"),
            model_handle=model_handle,
            query="swift runtime",
            documents=["runtime swift", "swift runtime"],
            top_k=2,
        ),
        context=None,
    )

    assert rerank.error.code == ""
    assert [item.index for item in rerank.items] == [1, 0]
    assert rerank.items[0].score > rerank.items[1].score


def test_load_model_rejects_unsupported_rerank_family() -> None:
    runtime = DeterministicRerankRuntime()
    model = WorkerModelCatalog.dev_rerank_model(
        environment={"MELIX_DEV_RERANK_FAMILY_ID": "unsupported-family"}
    )

    with pytest.raises(ValueError, match="Unsupported rerank family"):
        runtime.load_model(model)


def test_rerank_family_base_score_is_abstract() -> None:
    adapter = RerankFamilyAdapter()

    with pytest.raises(NotImplementedError):
        adapter.score(DeterministicRerankBackend(), "swift", "swift runtime")


def test_basic_rerank_family_scores_empty_and_overlap_inputs() -> None:
    adapter = BasicRerankFamilyAdapter()
    backend = DeterministicRerankBackend()

    empty_score = adapter.score(backend, "", "")
    overlap_score = adapter.score(backend, "swift", "swift runtime")

    assert empty_score >= 1.0
    assert overlap_score > 0.0


def test_jina_v3_helpers_cover_empty_and_short_inputs() -> None:
    adapter = JinaV3RerankFamilyAdapter()
    backend = DeterministicRerankBackend()

    empty_score = adapter.score(backend, "", "")

    assert empty_score >= 1.0
    assert adapter._ordered_pair_bonus(["swift"], ["swift"]) == 0.0
    assert adapter._contains_contiguous_query(["swift"], ["swift", "runtime"]) is False


def test_resolve_rerank_backend_and_family_support_basic_family() -> None:
    backend = resolve_rerank_backend("token-overlap-v1")
    family = resolve_rerank_family("basic", backend)

    assert family.metadata()["rerank_family_id"] == "basic"

    with pytest.raises(ValueError, match="Unsupported rerank backend"):
        resolve_rerank_backend("unsupported-backend")


def test_score_documents_resolves_backend_and_family_from_loaded_model_metadata() -> None:
    runtime = DeterministicRerankRuntime()

    scores = runtime.score_documents(
        {
            "rerank_backend_id": "token-overlap-v1",
            "rerank_family_id": "basic",
        },
        "swift",
        ["swift runtime"],
    )

    assert len(scores) == 1
    assert scores[0] > 0.0


def test_rerank_rejects_missing_and_wrong_model_kinds() -> None:
    runtime_service, inference_service = build_services()
    text_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    missing = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-missing"),
            model_handle="missing-handle",
            query="swift",
            documents=["swift worker"],
            top_k=1,
        ),
        context=None,
    )
    wrong_kind = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-text"),
            model_handle=text_handle,
            query="swift",
            documents=["swift worker"],
            top_k=1,
        ),
        context=None,
    )

    assert missing.error.code == "not_found"
    assert wrong_kind.error.code == "invalid_argument"
