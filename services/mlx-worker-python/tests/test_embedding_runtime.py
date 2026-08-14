from collections.abc import Sequence
import hashlib
import math
from typing import overload

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from backend_identity_support import (
    WorkerInferenceService,
    WorkerRuntimeService,
    bind_backend_identity,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_embedding_runtime import (
    DeterministicEmbeddingRuntime,
    _repeated_input_cycle_length,
)
from worker.runtime.artifact_embedding_runtime import ArtifactEmbeddingError
from worker.runtime.embedding_backends import (
    BERTEmbeddingBackend,
    DeterministicEmbeddingBackend,
    DeterministicEmbeddingFamilyAdapter,
    EmbeddingBackendDescriptor,
    EmbeddingFamilyDescriptor,
)
from worker.runtime import embedding_backends as embedding_backends_module
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


class CountingEmbeddingBackend(DeterministicEmbeddingBackend):
    descriptor = EmbeddingBackendDescriptor(
        backend_id="counting-v1",
        family_id="counting",
        pooling_mode="mean",
        normalization="none",
        estimated_resident_bytes=1,
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def embed_text(self, text: str, dimensions: int) -> list[float]:
        self.calls.append((text, dimensions))
        return [float(len(self.calls))] * dimensions


class CountingEmbeddingFamilyAdapter(DeterministicEmbeddingFamilyAdapter):
    descriptor = EmbeddingFamilyDescriptor(
        family_id="counting",
        pooling_mode="mean",
        normalization="none",
        default_dimensions=4,
    )

    def embed_text(
        self,
        backend: DeterministicEmbeddingBackend,
        text: str,
        dimensions: int,
    ) -> list[float]:
        return backend.embed_text(text, dimensions)


class RecordingEmbeddingRuntime(DeterministicEmbeddingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.received_inputs_type_name = ""

    def embed_inputs(self, loaded_model, inputs):
        self.received_inputs_type_name = type(inputs).__name__
        return super().embed_inputs(loaded_model, inputs)


class FailingEmbeddingRuntime(DeterministicEmbeddingRuntime):
    def embed_inputs(self, loaded_model, inputs):
        raise RuntimeError("embedding backend unavailable")


class RefusingEmbeddingRuntime(DeterministicEmbeddingRuntime):
    def embed_inputs(self, loaded_model, inputs):
        raise ArtifactEmbeddingError(
            "embedding_fully_padded_input",
            "Embedding tokenizer produced a fully padded input row.",
        )


class LoadRefusingEmbeddingRuntime(DeterministicEmbeddingRuntime):
    def estimate_resident_bytes(self, _model_spec):
        return 0

    def load_model(self, _model_spec):
        raise ArtifactEmbeddingError(
            "embedding_media_artifact_unsupported",
            "Artifact-backed embeddings do not support media model components.",
        )


def build_services(
    model_catalog: WorkerModelCatalog | None = None,
    *,
    embedding_runtime: DeterministicEmbeddingRuntime | None = None,
):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        embedding_runtime=embedding_runtime,
        model_catalog=model_catalog or WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    return registry, runtime_service, inference_service


def load_model(
    runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec
) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def _legacy_project_digest(seed_text: str, dimensions: int) -> list[float]:
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


def test_project_digest_preserves_legacy_projection_values() -> None:
    backend = BERTEmbeddingBackend()

    for dimensions in (0, 1, 8, 9, 17, 384, 1536, 4096, 4097):
        actual = backend._project_digest("bert::projection parity", dimensions)
        expected = _legacy_project_digest("bert::projection parity", dimensions)
        assert actual == expected


def test_project_digest_zero_dimensions_skips_digest_projection() -> None:
    backend = BERTEmbeddingBackend()
    digest_calls = 0

    def counting_sha256(payload: bytes = b""):
        nonlocal digest_calls
        digest_calls += 1
        return hashlib.sha256(payload)

    assert (
        backend._project_digest("bert::zero dimensions", 0, _sha256=counting_sha256)
        == []
    )
    assert (
        backend._project_digest(
            "bert::negative dimensions", -1, _sha256=counting_sha256
        )
        == []
    )
    assert digest_calls == 0

    assert (
        len(
            backend._project_digest(
                "bert::positive dimensions", 1, _sha256=counting_sha256
            )
        )
        == 1
    )
    assert digest_calls == 1


def test_project_digest_single_dimension_skips_expanded_projection() -> None:
    backend = BERTEmbeddingBackend()

    def fail_expanded_projection(base_values: list[float], dimensions: int) -> list[float]:  # pragma: no cover
        raise AssertionError(f"unexpected expanded projection for {dimensions}: {base_values!r}")

    backend._project_digest_expanded = fail_expanded_projection  # type: ignore[method-assign]

    positive = backend._project_digest(
        "bert::single-positive",
        1,
        _sha256=lambda payload=b"": hashlib.sha256(payload),
    )
    assert positive in ([-1.0], [1.0])

    zero = backend._project_digest(
        "bert::single-zero",
        1,
        _sha256=lambda payload=b"": hashlib.sha256(payload),
        _round=round,
    )
    assert zero in ([-1.0], [1.0])


def test_project_digest_single_dimension_reads_only_first_digest_word(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = BERTEmbeddingBackend()

    class FirstWordOnlyDigest:
        first_word_reads = 0

        def __getitem__(self, index: int) -> int:
            if index != 0:  # pragma: no cover - regression guard
                raise AssertionError(f"unexpected digest word read: {index}")
            self.first_word_reads += 1
            return 0xFFFFFFFF

        def __iter__(self):  # pragma: no cover - regression guard
            raise AssertionError("single-dimension projection should not iterate all digest words")

    digest_words = FirstWordOnlyDigest()
    monkeypatch.setattr(
        embedding_backends_module,
        "_UNPACK_DIGEST_UINT32",
        lambda digest: digest_words,
    )

    assert backend._project_digest("bert::single-fast-path", 1) == [1.0]
    assert digest_words.first_word_reads == 1


def test_project_digest_single_dimension_preserves_zero_norm(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = BERTEmbeddingBackend()
    monkeypatch.setattr(embedding_backends_module, "_UNPACK_DIGEST_UINT32", lambda digest: (1,) * 8)
    monkeypatch.setattr(embedding_backends_module, "_DIGEST_UINT32_SCALE", 1.0)

    assert backend._project_digest("bert::single-zero-norm", 1) == [0.0]


def test_embed_returns_stable_vectors_for_loaded_embedding_models() -> None:
    _, runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())

    first = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-1"),
                model_handle=model_handle,
                inputs=["alpha", "beta"],
            ),
        ),
        context=None,
    )
    second = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-2"),
                model_handle=model_handle,
                inputs=["alpha", "beta"],
            ),
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


def test_embed_passes_request_inputs_without_list_materialization() -> None:
    recording_runtime = RecordingEmbeddingRuntime()
    _, runtime_service, inference_service = build_services(
        embedding_runtime=recording_runtime
    )
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())

    response = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-no-input-list-copy"),
                model_handle=model_handle,
                inputs=["alpha", "beta", "alpha"],
            ),
        ),
        context=None,
    )

    assert response.error.code == ""
    assert [list(embedding.values) for embedding in response.embeddings] == [
        [*response.embeddings[0].values],
        [*response.embeddings[1].values],
        [*response.embeddings[0].values],
    ]
    assert recording_runtime.received_inputs_type_name != "list"


def test_embed_rejects_missing_and_wrong_model_kinds() -> None:
    _, runtime_service, inference_service = build_services()
    text_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    missing = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-missing"),
                model_handle="missing-handle",
                inputs=["alpha"],
            ),
            source_handle=text_handle,
        ),
        context=None,
    )
    wrong_kind = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-text"),
                model_handle=text_handle,
                inputs=["alpha"],
            ),
        ),
        context=None,
    )

    assert missing.error.code == "model_identity_mismatch"
    assert wrong_kind.error.code == "invalid_argument"


def test_embed_returns_runtime_error_when_backend_raises() -> None:
    _, runtime_service, inference_service = build_services(
        embedding_runtime=FailingEmbeddingRuntime()
    )
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())

    response = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-runtime-error"),
                model_handle=model_handle,
                inputs=["alpha"],
            ),
        ),
        context=None,
    )

    assert response.error.code == "runtime_error"
    assert response.error.message == "embedding backend unavailable"


def test_embed_preserves_typed_artifact_runtime_refusal() -> None:
    _, runtime_service, inference_service = build_services(
        embedding_runtime=RefusingEmbeddingRuntime()
    )
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())

    response = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-typed-refusal"),
                model_handle=model_handle,
                inputs=["fully padded"],
            ),
        ),
        context=None,
    )

    assert response.error.code == "embedding_fully_padded_input"
    assert response.error.message == "Embedding tokenizer produced a fully padded input row."


def test_load_model_preserves_typed_artifact_runtime_refusal() -> None:
    _, runtime_service, _ = build_services(
        embedding_runtime=LoadRefusingEmbeddingRuntime()
    )

    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_embedding_model()),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "embedding_media_artifact_unsupported"
    assert response.error.message == (
        "Artifact-backed embeddings do not support media model components."
    )


def test_load_model_exposes_embedding_backend_metadata_for_bert_and_xlmr() -> None:
    registry, runtime_service, _ = build_services()
    bert_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())
    xlmr_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "xlmr"}
    )
    xlmr_model.model_id = "melix-dev-embed-xlmr"
    xlmr_handle = load_model(runtime_service, xlmr_model)

    bert_loaded = registry.get_loaded_model(bert_handle)
    xlmr_loaded = registry.get_loaded_model(xlmr_handle)

    assert bert_loaded is not None
    assert xlmr_loaded is not None
    assert bert_loaded.runtime_model["embedding_backend_id"] == "deterministic-fixture-v1"
    assert bert_loaded.runtime_model["embedding_family_id"] == "bert"
    assert xlmr_loaded.runtime_model["embedding_backend_id"] == "deterministic-fixture-v1"
    assert xlmr_loaded.runtime_model["embedding_family_id"] == "xlmr"


def test_embed_returns_distinct_vectors_for_xlmr_backend_selection() -> None:
    _, runtime_service, inference_service = build_services()
    bert_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())
    xlmr_model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "xlmr"}
    )
    xlmr_model.model_id = "melix-dev-embed-xlmr"
    xlmr_handle = load_model(runtime_service, xlmr_model)

    bert = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-bert"),
                model_handle=bert_handle,
                inputs=["Straße"],
            ),
        ),
        context=None,
    )
    xlmr = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-xlmr"),
                model_handle=xlmr_handle,
                inputs=["Straße"],
            ),
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
    assert bge_loaded.runtime_model["embedding_backend_id"] == "deterministic-fixture-v1"
    assert bge_loaded.runtime_model["embedding_family_id"] == "bge-m3"
    assert bge_loaded.runtime_model["embedding_pooling_mode"] == "cls"
    assert bge_loaded.runtime_model["dimensions"] == 8
    assert mxbai_loaded.runtime_model["embedding_backend_id"] == "deterministic-fixture-v1"
    assert mxbai_loaded.runtime_model["embedding_family_id"] == "mxbai-embed"
    assert mxbai_loaded.runtime_model["embedding_pooling_mode"] == "mean"
    assert mxbai_loaded.runtime_model["dimensions"] == 10


def test_embedding_model_infers_identity_from_directory_name() -> None:
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_MODEL_PATH": "models/mxbai-embed-large-v1"}
    )

    assert model.ext["embedding_backend_id"] == "deterministic-fixture-v1"
    assert model.ext["embedding_execution_kind"] == "fixture"
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

    assert model.ext["embedding_backend_id"] == "deterministic-fixture-v1"
    assert model.ext["embedding_execution_kind"] == "fixture"
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
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-bge"),
                model_handle=bge_handle,
                inputs=["query text"],
            ),
        ),
        context=None,
    )
    mxbai = inference_service.Embed(
        bind_backend_identity(
            inference_service,
            inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id="embed-mxbai"),
                model_handle=mxbai_handle,
                inputs=["query text"],
            ),
        ),
        context=None,
    )

    assert bge.error.code == ""
    assert mxbai.error.code == ""
    assert len(bge.embeddings[0].values) == 8
    assert len(mxbai.embeddings[0].values) == 10


def test_embed_runtime_resolves_explicit_fixture_family_from_loaded_model_metadata() -> None:
    runtime = DeterministicEmbeddingRuntime()

    vectors = runtime.embed_inputs(
        {
            "model_id": "melix-dev-embed-xlmr",
            "dimensions": 8,
            "embedding_backend_id": "deterministic-fixture-v1",
            "embedding_family_id": "xlmr",
        },
        ["Straße"],
    )

    assert len(vectors) == 1
    assert len(vectors[0]) == 8


def test_embed_runtime_reuses_duplicate_inputs_within_one_request() -> None:
    runtime = DeterministicEmbeddingRuntime()
    backend = CountingEmbeddingBackend()
    family = CountingEmbeddingFamilyAdapter()

    vectors = runtime.embed_inputs(
        {
            "model_id": "melix-dev-embed-counting",
            "dimensions": 4,
            "embedding_backend": backend,
            "embedding_family_adapter": family,
        },
        ["alpha", "beta", "alpha", "gamma", "beta"],
    )

    assert backend.calls == [("alpha", 4), ("beta", 4), ("gamma", 4)]
    assert vectors == [
        [1.0, 1.0, 1.0, 1.0],
        [2.0, 2.0, 2.0, 2.0],
        [1.0, 1.0, 1.0, 1.0],
        [3.0, 3.0, 3.0, 3.0],
        [2.0, 2.0, 2.0, 2.0],
    ]
    assert vectors[0] is not vectors[2]
    vectors[0][0] = 99.0
    assert vectors[2] == [1.0, 1.0, 1.0, 1.0]


def test_embed_runtime_replays_repeated_cycles_without_shared_vectors() -> None:
    runtime = DeterministicEmbeddingRuntime()
    backend = CountingEmbeddingBackend()
    family = CountingEmbeddingFamilyAdapter()
    cycle = [f"document-{index}" for index in range(1024)]

    vectors = runtime.embed_inputs(
        {
            "model_id": "melix-dev-embed-counting-cycle",
            "dimensions": 2,
            "embedding_backend": backend,
            "embedding_family_adapter": family,
        },
        cycle * 3,
    )

    assert len(backend.calls) == len(cycle)
    assert len(vectors) == len(cycle) * 3
    assert vectors[0] == vectors[len(cycle)] == vectors[len(cycle) * 2]
    assert vectors[0] is not vectors[len(cycle)]
    assert vectors[len(cycle)] is not vectors[len(cycle) * 2]
    vectors[len(cycle)][0] = 99.0
    assert vectors[0] == [1.0, 1.0]
    assert vectors[len(cycle) * 2] == [1.0, 1.0]


def test_embed_runtime_replays_single_input_cycles_without_generator_reentry() -> None:
    runtime = DeterministicEmbeddingRuntime()
    backend = CountingEmbeddingBackend()
    family = CountingEmbeddingFamilyAdapter()

    vectors = runtime.embed_inputs(
        {
            "model_id": "melix-dev-embed-counting-single-cycle",
            "dimensions": 2,
            "embedding_backend": backend,
            "embedding_family_adapter": family,
        },
        ["same-document"] * 2048,
    )

    assert backend.calls == [("same-document", 2)]
    assert len(vectors) == 2048
    assert vectors[0] == vectors[-1] == [1.0, 1.0]
    assert vectors[0] is not vectors[-1]
    vectors[0][0] = 99.0
    assert vectors[-1] == [1.0, 1.0]


class SliceCountingInputs(Sequence[str]):
    def __init__(self, values: list[str]) -> None:
        self._values = values
        self.slice_count = 0

    def __len__(self) -> int:
        return len(self._values)

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> list[str]: ...

    def __getitem__(self, index: int | slice) -> str | list[str]:
        if isinstance(index, slice):
            self.slice_count += 1  # pragma: no cover - regression-only branch
        return self._values[index]


def test_repeated_input_cycle_length_rejects_partial_single_input_cycles() -> None:
    inputs = ["same-document"] * 1024 + ["different-document"]

    assert _repeated_input_cycle_length(inputs) == 0


def test_repeated_input_cycle_length_validates_multi_input_cycles_without_slices() -> (
    None
):
    cycle = [f"document-{index}" for index in range(512)]
    inputs = SliceCountingInputs(cycle * 3)

    assert _repeated_input_cycle_length(inputs) == len(cycle)
    assert inputs.slice_count == 0


def test_load_model_rejects_unsupported_embedding_backend() -> None:
    runtime = DeterministicEmbeddingRuntime()
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_BACKEND_ID": "unsupported-v1"}
    )

    with pytest.raises(ValueError, match="Unsupported embedding backend"):
        runtime.load_model(model)


def test_load_model_rejects_missing_fixture_backend() -> None:
    model = WorkerModelCatalog.dev_embedding_model()
    del model.ext["embedding_backend_id"]

    with pytest.raises(ArtifactEmbeddingError) as caught:
        DeterministicEmbeddingRuntime().load_model(model)

    assert caught.value.code == "embedding_backend_unsupported"


@pytest.mark.parametrize("backend_id", ["bert-v1", "xlmr-v1"])
def test_load_model_rejects_legacy_digest_backend_ids(backend_id: str) -> None:
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_BACKEND_ID": backend_id}
    )

    with pytest.raises(ValueError, match="Legacy embedding backend"):
        DeterministicEmbeddingRuntime().load_model(model)


def test_load_model_rejects_unsupported_embedding_family() -> None:
    runtime = DeterministicEmbeddingRuntime()
    model = WorkerModelCatalog.dev_embedding_model(
        environment={"MELIX_DEV_EMBED_FAMILY_ID": "unsupported-family"}
    )

    with pytest.raises(ValueError, match="Unsupported embedding family"):
        runtime.load_model(model)
