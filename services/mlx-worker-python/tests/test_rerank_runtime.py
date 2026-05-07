import builtins
from unittest.mock import Mock, patch

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.engine.rerank_core import RerankCore
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime import rerank_backends
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.rerank_backends import (
    BasicRerankFamilyAdapter,
    CausalLMRerankFamilyAdapter,
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


def test_rerank_rank_scores_preserves_sort_contract_for_bounded_top_k() -> None:
    scores = [0.4, 0.9, 0.9, -0.2, 0.7, 0.9]

    ranked = RerankCore._rank_scores(scores, top_k=3)

    assert ranked == [(1, 0.9), (2, 0.9), (5, 0.9)]


def test_rerank_rank_scores_uses_single_scan_for_top_k_one(monkeypatch) -> None:
    nsmallest = Mock()
    monkeypatch.setattr("worker.engine.rerank_core.heapq.nsmallest", nsmallest)

    ranked = RerankCore._rank_scores([0.1, 0.8, 0.8, -0.2, 0.7], top_k=1)

    assert ranked == [(1, 0.8)]
    nsmallest.assert_not_called()


def test_rerank_rank_scores_uses_heap_for_bounded_top_k(monkeypatch) -> None:
    nsmallest = Mock(return_value=[(-0.8, 2, 0.8), (-0.7, 4, 0.7)])
    monkeypatch.setattr("worker.engine.rerank_core.heapq.nsmallest", nsmallest)

    ranked = RerankCore._rank_scores([0.1, 0.2, 0.8, 0.3, 0.7], top_k=2)

    assert ranked == [(2, 0.8), (4, 0.7)]
    nsmallest.assert_called_once()
    assert nsmallest.call_args.args[0] == 2
    assert "key" not in nsmallest.call_args.kwargs


def test_rerank_rank_scores_keeps_full_sort_when_unbounded(monkeypatch) -> None:
    nsmallest = Mock()
    monkeypatch.setattr("worker.engine.rerank_core.heapq.nsmallest", nsmallest)

    ranked = RerankCore._rank_scores([0.2, 0.5, 0.5], top_k=None)
    oversized = RerankCore._rank_scores([0.2, 0.5, 0.5], top_k=5)

    assert ranked == [(1, 0.5), (2, 0.5), (0, 0.2)]
    assert oversized == ranked
    nsmallest.assert_not_called()


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


def test_load_model_exposes_causal_lm_yes_no_metadata() -> None:
    runtime = DeterministicRerankRuntime()

    loaded = runtime.load_model(
        WorkerModelCatalog.dev_rerank_model(
            environment={"MELIX_DEV_RERANK_FAMILY_ID": "causal-lm"}
        )
    )

    assert loaded["rerank_family_id"] == "causal-lm"
    assert loaded["rerank_scoring_mode"] == "yes-no-logits"
    assert loaded["rerank_yes_no_labels"] == "yes,no"


def test_rerank_model_infers_identity_from_directory_name() -> None:
    model = WorkerModelCatalog.dev_rerank_model(
        environment={"MELIX_DEV_RERANK_MODEL_PATH": "models/causal-lm-reranker"}
    )

    assert model.ext["rerank_family_id"] == "causal-lm"
    assert model.ext["rerank_scoring_mode"] == "yes-no-logits"
    assert model.ext["rerank_yes_no_labels"] == "yes,no"
    assert model.ext["model_architecture"] == "causal-lm"
    assert model.ext["detected_architecture"] == "causal-lm"
    assert model.ext["detected_family_id"] == "causal-lm"
    assert model.ext["detected_identity_source"] == "directory_name"
    assert model.ext["identity_override"] == "false"


def test_rerank_model_preserves_detected_identity_when_override_is_applied() -> None:
    model = WorkerModelCatalog.dev_rerank_model(
        environment={
            "MELIX_DEV_RERANK_MODEL_PATH": "models/jina-v3-reranker",
            "MELIX_DEV_RERANK_FAMILY_ID": "causal-lm",
        }
    )

    assert model.ext["rerank_family_id"] == "causal-lm"
    assert model.ext["rerank_scoring_mode"] == "yes-no-logits"
    assert model.ext["model_architecture"] == "causal-lm"
    assert model.ext["detected_architecture"] == "cross-encoder"
    assert model.ext["detected_family_id"] == "jina-v3"
    assert model.ext["detected_identity_source"] == "directory_name"
    assert model.ext["identity_override"] == "true"


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


def test_causal_lm_rerank_produces_positive_and_negative_logits() -> None:
    runtime_service, inference_service = build_services(
        environment={"MELIX_DEV_RERANK_FAMILY_ID": "causal-lm"}
    )
    model_handle = load_model(
        runtime_service,
        WorkerModelCatalog.dev_rerank_model(
            environment={"MELIX_DEV_RERANK_FAMILY_ID": "causal-lm"}
        ),
    )

    rerank = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-causal-lm"),
            model_handle=model_handle,
            query="swift runtime",
            documents=["swift runtime is available", "python packaging release"],
            top_k=2,
        ),
        context=None,
    )

    assert rerank.error.code == ""
    assert [item.index for item in rerank.items] == [0, 1]
    assert rerank.items[0].score > 0
    assert rerank.items[1].score < 0


def test_jina_v3_skips_pair_and_contiguous_query_checks_when_document_misses_query_terms(monkeypatch) -> None:
    adapter = JinaV3RerankFamilyAdapter()
    backend = DeterministicRerankBackend()
    ordered_pair_bonus = Mock(return_value=0.0)
    contains = Mock(return_value=False)

    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_ordered_pair_bonus",
        staticmethod(ordered_pair_bonus),
    )
    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_contains_contiguous_query",
        staticmethod(contains),
    )

    score = adapter.score(
        backend,
        "swift control plane runtime",
        "python worker packaging",
    )

    assert score >= 0.0
    ordered_pair_bonus.assert_not_called()
    contains.assert_not_called()


def test_causal_lm_skips_pair_and_contiguous_query_checks_when_document_misses_query_terms(monkeypatch) -> None:
    adapter = CausalLMRerankFamilyAdapter()
    backend = DeterministicRerankBackend()
    ordered_pair_bonus = Mock(return_value=0.0)
    contains = Mock(return_value=False)

    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_ordered_pair_bonus",
        staticmethod(ordered_pair_bonus),
    )
    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_contains_contiguous_query",
        staticmethod(contains),
    )

    score = adapter.score(
        backend,
        "swift control plane runtime",
        "python worker packaging",
    )

    assert score < 0.0
    ordered_pair_bonus.assert_not_called()
    contains.assert_not_called()


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


def test_score_documents_tokenizes_the_query_once_for_multiple_documents() -> None:
    class CountingBackend(DeterministicRerankBackend):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def tokenize(self, text: str) -> list[str]:
            self.calls.append(text)
            return super().tokenize(text)

    runtime = DeterministicRerankRuntime()
    backend = CountingBackend()

    scores = runtime.score_documents(
        {
            "rerank_backend": backend,
            "rerank_family_adapter": JinaV3RerankFamilyAdapter(),
        },
        "swift runtime",
        [
            "swift runtime is available",
            "runtime swift uses reversed order",
            "python packaging release",
        ],
    )

    assert len(scores) == 3
    assert backend.calls.count("swift runtime") == 1
    assert backend.calls == [
        "swift runtime",
        "swift runtime is available",
        "runtime swift uses reversed order",
        "python packaging release",
    ]


def test_score_documents_builds_query_context_once_for_multiple_documents() -> None:
    class TrackingFamilyAdapter(JinaV3RerankFamilyAdapter):
        def __init__(self) -> None:
            self.query_contexts: list[object] = []
            self.query_context_builds = 0

        def build_query_context(self, backend: DeterministicRerankBackend, query: str, **kwargs: object):
            self.query_context_builds += 1
            return super().build_query_context(backend, query, **kwargs)

        def score(self, backend: DeterministicRerankBackend, query: str, document: str, **kwargs: object) -> float:
            self.query_contexts.append(kwargs["query_context"])
            return super().score(backend, query, document, **kwargs)

    runtime = DeterministicRerankRuntime()
    backend = DeterministicRerankBackend()
    family = TrackingFamilyAdapter()

    scores = runtime.score_documents(
        {
            "rerank_backend": backend,
            "rerank_family_adapter": family,
        },
        "swift runtime",
        [
            "swift runtime is available",
            "runtime swift uses reversed order",
            "python packaging release",
        ],
    )

    assert len(scores) == 3
    assert family.query_context_builds == 1
    assert len(family.query_contexts) == 3
    assert family.query_contexts[0] is family.query_contexts[1] is family.query_contexts[2]


def test_basic_rerank_family_reuses_query_context_token_set_without_copying() -> None:
    adapter = BasicRerankFamilyAdapter()
    backend = DeterministicRerankBackend()
    query_context = adapter.build_query_context(backend, "swift runtime")
    original_set = builtins.set
    copied_query_token_sets = 0

    def tracking_set(values=()):
        nonlocal copied_query_token_sets
        copied_query_token_sets += int(values is query_context.query_token_set)
        return original_set(values)

    with patch("builtins.set", tracking_set):
        score = adapter.score(
            backend,
            query_context.query,
            "swift runtime is available",
            query_context=query_context,
        )

    assert score > 0.0
    assert copied_query_token_sets == 0


@pytest.mark.parametrize(
    ("family", "query", "document"),
    [
        (JinaV3RerankFamilyAdapter(), "swift runtime", "swift runtime is available"),
        (CausalLMRerankFamilyAdapter(), "swift runtime", "swift runtime is available"),
    ],
)
def test_order_aware_rerank_families_reuse_query_context_sequences_without_copying(
    family: RerankFamilyAdapter,
    query: str,
    document: str,
) -> None:
    backend = DeterministicRerankBackend()
    query_context = family.build_query_context(backend, query)
    original_list = builtins.list
    original_set = builtins.set
    copied_query_tokens = 0
    copied_query_token_sets = 0

    def tracking_list(values=()):
        nonlocal copied_query_tokens
        copied_query_tokens += int(values is query_context.query_tokens)
        return original_list(values)

    def tracking_set(values=()):
        nonlocal copied_query_token_sets
        copied_query_token_sets += int(values is query_context.query_token_set)
        return original_set(values)

    with patch("builtins.list", tracking_list), patch("builtins.set", tracking_set):
        score = family.score(
            backend,
            query,
            document,
            query_context=query_context,
        )

    assert score > 0.0
    assert copied_query_tokens == 0
    assert copied_query_token_sets == 0


@pytest.mark.parametrize(
    ("family", "query", "document"),
    [
        (BasicRerankFamilyAdapter(), "swift runtime", "swift runtime is available"),
        (JinaV3RerankFamilyAdapter(), "swift runtime", "swift runtime is available"),
        (CausalLMRerankFamilyAdapter(), "swift runtime", "swift runtime is available"),
    ],
)
def test_rerank_family_query_context_preserves_scoring_semantics(
    family: RerankFamilyAdapter,
    query: str,
    document: str,
) -> None:
    backend = DeterministicRerankBackend()

    baseline_score = family.score(backend, query, document)
    query_context = family.build_query_context(backend, query)
    optimized_score = family.score(backend, query, document, query_context=query_context)

    assert optimized_score == baseline_score


def test_rerank_context_tuple_and_frozenset_collections_are_scored_directly() -> None:
    backend = DeterministicRerankBackend()
    family = JinaV3RerankFamilyAdapter()
    query_context = family.build_query_context(backend, "swift runtime")

    assert isinstance(query_context.query_tokens, tuple)
    assert isinstance(query_context.query_token_set, frozenset)
    assert backend.tie_breaker_from_seed(
        query_context.tie_breaker_seed,
        "control swift runtime",
    ) == backend.tie_breaker("swift runtime", "control swift runtime")
    assert family._ordered_pair_bonus(query_context.query_tokens, ("swift", "runtime")) > 0.0
    assert family._contains_contiguous_query(
        ("control", "swift", "runtime"),
        query_context.query_tokens,
    )
    assert family.score(
        backend,
        "swift runtime",
        "control swift runtime",
        query_context=query_context,
    ) == family.score(backend, "swift runtime", "control swift runtime")


def test_ordered_pair_bonus_stops_after_matching_all_query_pairs() -> None:
    class CountingTokens:
        def __init__(self, tokens: tuple[str, ...]) -> None:
            self.tokens = tokens
            self.access_count = 0

        def __len__(self) -> int:
            return len(self.tokens)

        def __getitem__(self, index: int) -> str:
            self.access_count += 1
            return self.tokens[index]

    document_tokens = CountingTokens(
        (
            "swift",
            "runtime",
            "padding-1",
            "padding-2",
            "padding-3",
            "padding-4",
            "padding-5",
        )
    )

    assert (
        JinaV3RerankFamilyAdapter._ordered_pair_bonus(("swift", "runtime"), document_tokens)
        == 0.15
    )
    assert document_tokens.access_count <= 2


def test_contiguous_query_scan_does_not_allocate_document_slices() -> None:
    class NoSliceTokens:
        def __init__(self, tokens: tuple[str, ...]) -> None:
            self.tokens = tokens

        def __len__(self) -> int:
            return len(self.tokens)

        def __getitem__(self, index):
            if isinstance(index, slice):
                raise AssertionError("contiguous query scan should compare tokens without slicing")
            return self.tokens[index]

    family = JinaV3RerankFamilyAdapter()

    assert family._contains_contiguous_query(
        NoSliceTokens(("control", "swift", "runtime", "worker")),
        ("swift", "runtime"),
    )
    assert not family._contains_contiguous_query(
        NoSliceTokens(("control", "runtime", "swift", "worker")),
        ("swift", "runtime"),
    )
    assert family._contains_contiguous_query(
        NoSliceTokens(("control", "swift")),
        ("swift",),
    )
    assert not family._contains_contiguous_query(
        NoSliceTokens(("control", "runtime")),
        ("swift",),
    )
    with pytest.raises(AssertionError, match="without slicing"):
        NoSliceTokens(("swift", "runtime"))[0:1]


def test_contiguous_query_scan_skips_full_comparison_until_first_token_matches(monkeypatch) -> None:
    calls: list[int] = []
    original_sequence_matches_at = rerank_backends._sequence_matches_at

    def tracking_sequence_matches_at(haystack, needle, start):
        calls.append(start)
        return original_sequence_matches_at(haystack, needle, start)

    monkeypatch.setattr(rerank_backends, "_sequence_matches_at", tracking_sequence_matches_at)

    assert JinaV3RerankFamilyAdapter._contains_contiguous_query(
        ("padding", "runtime", "control", "swift", "runtime"),
        ("swift", "runtime"),
    )
    assert calls == [3]

    calls.clear()
    assert not JinaV3RerankFamilyAdapter._contains_contiguous_query(
        ("padding", "runtime", "control", "worker"),
        ("swift", "runtime"),
    )
    assert calls == []


def test_ordered_pair_bonus_skips_second_token_reads_for_noncandidate_pair_starts() -> None:
    class CountingTokens:
        def __init__(self, tokens: tuple[str, ...]) -> None:
            self.tokens = tokens
            self.accessed_indexes: list[int] = []

        def __len__(self) -> int:
            return len(self.tokens)

        def __getitem__(self, index: int) -> str:
            self.accessed_indexes.append(index)
            return self.tokens[index]

    padding = tuple(f"padding-{index}" for index in range(20))
    document_tokens = CountingTokens(padding + ("swift", "runtime"))

    assert (
        JinaV3RerankFamilyAdapter._ordered_pair_bonus(
            ("swift", "runtime"),
            document_tokens,
            query_pairs=frozenset({("swift", "runtime")}),
            query_pair_start_tokens=frozenset({"swift"}),
        )
        == 0.15
    )
    assert document_tokens.accessed_indexes == list(range(21)) + [21]


@pytest.mark.parametrize(
    ("family", "expected_exact_order_bonus", "expected_prefix_bonus", "expected_pair_bonus"),
    [
        (JinaV3RerankFamilyAdapter(), 0.1, 0.05, 0.15),
        (CausalLMRerankFamilyAdapter(), 0.75, 0.5, 0.45),
    ],
)
def test_order_aware_query_context_preserves_exact_order_and_prefix_bonuses(
    family: RerankFamilyAdapter,
    expected_exact_order_bonus: float,
    expected_prefix_bonus: float,
    expected_pair_bonus: float,
) -> None:
    backend = DeterministicRerankBackend()
    query = "swift runtime"
    prefix_document = "swift runtime adapters"
    exact_order_document = "adapters swift runtime"
    shuffled_document = "runtime swift adapters"
    query_context = family.build_query_context(backend, query)

    prefix_score = family.score(backend, query, prefix_document, query_context=query_context)
    exact_order_score = family.score(backend, query, exact_order_document, query_context=query_context)
    shuffled_score = family.score(backend, query, shuffled_document, query_context=query_context)

    normalized_prefix_score = prefix_score - backend.tie_breaker(query, prefix_document)
    normalized_exact_order_score = exact_order_score - backend.tie_breaker(query, exact_order_document)
    normalized_shuffled_score = shuffled_score - backend.tie_breaker(query, shuffled_document)

    assert normalized_prefix_score - normalized_exact_order_score == pytest.approx(expected_prefix_bonus, abs=1e-6)
    assert normalized_exact_order_score - normalized_shuffled_score == pytest.approx(
        expected_exact_order_bonus + expected_pair_bonus,
        abs=1e-6,
    )


@pytest.mark.parametrize(
    "family",
    [JinaV3RerankFamilyAdapter(), CausalLMRerankFamilyAdapter()],
)
def test_order_aware_rerank_families_use_combined_order_match_once_for_full_overlap(
    monkeypatch,
    family: RerankFamilyAdapter,
) -> None:
    backend = DeterministicRerankBackend()
    query_order_matches = Mock(return_value=(True, True))
    contains = Mock(side_effect=AssertionError("score should use the combined order matcher"))
    has_prefix = Mock(side_effect=AssertionError("score should use the combined order matcher"))

    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_query_order_matches",
        staticmethod(query_order_matches),
    )
    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_contains_contiguous_query",
        staticmethod(contains),
    )
    monkeypatch.setattr(
        JinaV3RerankFamilyAdapter,
        "_has_query_prefix",
        staticmethod(has_prefix),
    )

    score = family.score(backend, "swift runtime", "swift runtime is available")

    assert score > 0.0
    query_order_matches.assert_called_once_with(
        ["swift", "runtime", "is", "available"],
        ("swift", "runtime"),
    )
    contains.assert_not_called()
    has_prefix.assert_not_called()


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
