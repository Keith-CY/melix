import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_services(model_catalog: WorkerModelCatalog | None = None):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=model_catalog or WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    return registry, runtime_service, inference_service


def load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_embed_returns_stable_vectors_for_loaded_embedding_models() -> None:
    _, runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())

    first = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-1"),
            model_handle=model_handle,
            inputs=["alpha", "beta"],
        ),
        context=None,
    )
    second = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-2"),
            model_handle=model_handle,
            inputs=["alpha", "beta"],
        ),
        context=None,
    )

    assert first.error.code == ""
    assert len(first.embeddings) == 2
    assert len(first.embeddings[0].values) == 8
    assert len(first.embeddings[1].values) == 8
    assert first.embeddings[0].values == second.embeddings[0].values
    assert first.embeddings[1].values == second.embeddings[1].values
    assert first.embeddings[0].values != first.embeddings[1].values


def test_embed_rejects_missing_and_wrong_model_kinds() -> None:
    _, runtime_service, inference_service = build_services()
    text_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    missing = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-missing"),
            model_handle="missing-handle",
            inputs=["alpha"],
        ),
        context=None,
    )
    wrong_kind = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-text"),
            model_handle=text_handle,
            inputs=["alpha"],
        ),
        context=None,
    )

    assert missing.error.code == "not_found"
    assert wrong_kind.error.code == "invalid_argument"


def test_load_model_exposes_embedding_backend_metadata_for_bert_and_xlmr() -> None:
    registry, runtime_service, _ = build_services()
    bert_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())
    xlmr_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_BACKEND_ID": "xlmr-v1"}
    )
    xlmr_model.model_id = "melix-dev-embed-xlmr"
    xlmr_handle = load_model(runtime_service, xlmr_model)

    bert_loaded = registry.get_loaded_model(bert_handle)
    xlmr_loaded = registry.get_loaded_model(xlmr_handle)

    assert bert_loaded is not None
    assert xlmr_loaded is not None
    assert bert_loaded.runtime_model["embedding_backend_id"] == "bert-v1"
    assert bert_loaded.runtime_model["embedding_family_id"] == "bert"
    assert xlmr_loaded.runtime_model["embedding_backend_id"] == "xlmr-v1"
    assert xlmr_loaded.runtime_model["embedding_family_id"] == "xlmr"


def test_embed_returns_distinct_vectors_for_xlmr_backend_selection() -> None:
    _, runtime_service, inference_service = build_services()
    bert_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())
    xlmr_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_BACKEND_ID": "xlmr-v1"}
    )
    xlmr_model.model_id = "melix-dev-embed-xlmr"
    xlmr_handle = load_model(runtime_service, xlmr_model)

    bert = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-bert"),
            model_handle=bert_handle,
            inputs=["Straße"],
        ),
        context=None,
    )
    xlmr = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-xlmr"),
            model_handle=xlmr_handle,
            inputs=["Straße"],
        ),
        context=None,
    )

    assert bert.error.code == ""
    assert xlmr.error.code == ""
    assert bert.embeddings[0].values != xlmr.embeddings[0].values


def test_load_model_exposes_embedding_family_metadata_for_bge_and_mxbai() -> None:
    registry, runtime_service, _ = build_services()
    bge_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "bge-m3"}
    )
    bge_model.model_id = "melix-dev-embed-bge"
    mxbai_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "mxbai-embed"}
    )
    mxbai_model.model_id = "melix-dev-embed-mxbai"

    bge_handle = load_model(runtime_service, bge_model)
    mxbai_handle = load_model(runtime_service, mxbai_model)

    bge_loaded = registry.get_loaded_model(bge_handle)
    mxbai_loaded = registry.get_loaded_model(mxbai_handle)

    assert bge_loaded is not None
    assert mxbai_loaded is not None
    assert bge_loaded.runtime_model["embedding_backend_id"] == "bert-v1"
    assert bge_loaded.runtime_model["embedding_family_id"] == "bge-m3"
    assert bge_loaded.runtime_model["embedding_pooling_mode"] == "cls"
    assert bge_loaded.runtime_model["dimensions"] == 8
    assert mxbai_loaded.runtime_model["embedding_backend_id"] == "bert-v1"
    assert mxbai_loaded.runtime_model["embedding_family_id"] == "mxbai-embed"
    assert mxbai_loaded.runtime_model["embedding_pooling_mode"] == "mean"
    assert mxbai_loaded.runtime_model["dimensions"] == 10


def test_embedding_model_infers_identity_from_directory_name() -> None:
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_MODEL_PATH": "models/mxbai-embed-large-v1"}
    )

    assert model.ext["embedding_backend_id"] == "bert-v1"
    assert model.ext["embedding_family_id"] == "mxbai-embed"
    assert model.ext["embedding_pooling_mode"] == "mean"
    assert model.ext["embedding_dimensions"] == "10"
    assert model.ext["model_architecture"] == "bert"
    assert model.ext["detected_architecture"] == "bert"
    assert model.ext["detected_family_id"] == "mxbai-embed"
    assert model.ext["detected_identity_source"] == "directory_name"
    assert model.ext["identity_override"] == "false"


def test_embedding_model_preserves_detected_identity_when_override_is_applied() -> None:
    model = WorkerModelCatalog.dev_embedding_model(
        environment={
            "MELIX_DEV_EMBED_MODEL_PATH": "models/xlmr-base",
            "MELIX_DEV_EMBED_FAMILY_ID": "bge-m3",
        }
    )

    assert model.ext["embedding_backend_id"] == "bert-v1"
    assert model.ext["embedding_family_id"] == "bge-m3"
    assert model.ext["model_architecture"] == "bert"
    assert model.ext["detected_architecture"] == "xlmr"
    assert model.ext["detected_family_id"] == "xlmr"
    assert model.ext["detected_identity_source"] == "directory_name"
    assert model.ext["identity_override"] == "true"


def test_embed_returns_family_specific_dimensions_for_mxbai() -> None:
    _, runtime_service, inference_service = build_services()
    bge_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "bge-m3"}
    )
    bge_model.model_id = "melix-dev-embed-bge"
    mxbai_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "mxbai-embed"}
    )
    mxbai_model.model_id = "melix-dev-embed-mxbai"

    bge_handle = load_model(runtime_service, bge_model)
    mxbai_handle = load_model(runtime_service, mxbai_model)

    bge = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-bge"),
            model_handle=bge_handle,
            inputs=["query text"],
        ),
        context=None,
    )
    mxbai = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-mxbai"),
            model_handle=mxbai_handle,
            inputs=["query text"],
        ),
        context=None,
    )

    assert bge.error.code == ""
    assert mxbai.error.code == ""
    assert len(bge.embeddings[0].values) == 8
    assert len(mxbai.embeddings[0].values) == 10


def test_embed_runtime_resolves_backend_from_loaded_model_metadata() -> None:
    runtime = DeterministicEmbeddingRuntime()

    vectors = runtime.embed_inputs(
        {
            "model_id": "melix-dev-embed-xlmr",
            "dimensions": 8,
            "embedding_backend_id": "xlmr-v1",
        },
        ["Straße"],
    )

    assert len(vectors) == 1
    assert len(vectors[0]) == 8


def test_load_model_rejects_unsupported_embedding_backend() -> None:
    runtime = DeterministicEmbeddingRuntime()
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_BACKEND_ID": "unsupported-v1"}
    )

    with pytest.raises(ValueError, match="Unsupported embedding backend"):
        runtime.load_model(model)


def test_load_model_rejects_unsupported_embedding_family() -> None:
    runtime = DeterministicEmbeddingRuntime()
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "unsupported-family"}
    )

    with pytest.raises(ValueError, match="Unsupported embedding family"):
        runtime.load_model(model)
