from __future__ import annotations

import heapq

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry


class RerankCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def rerank(self, request: inference_pb2.RerankRequest) -> inference_pb2.RerankResponse:
        registry = self._registry
        loaded_model = registry.get_loaded_model(request.model_handle)
        if loaded_model is None:
            return inference_pb2.RerankResponse(
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle.")
            )

        if loaded_model.runtime_kind != "rerank":
            return inference_pb2.RerankResponse(
                error=common_pb2.ErrorStatus(
                    code="invalid_argument",
                    message="Loaded model does not support rerank operations.",
                )
            )

        try:
            scores = registry.rerank_runtime.score_documents(
                loaded_model.runtime_model,
                request.query,
                request.documents,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            return inference_pb2.RerankResponse(
                error=common_pb2.ErrorStatus(code="runtime_error", message=str(exc))
            )

        ranked = self._rank_scores(scores, top_k=int(request.top_k) if request.top_k else None)

        response = inference_pb2.RerankResponse()
        add_item = response.items.add
        for index, score in ranked:
            item = add_item()
            item.index = index
            item.score = score
        return response

    @staticmethod
    def _rank_scores(scores: list[float], *, top_k: int | None) -> list[tuple[int, float]]:
        if top_k is not None and top_k < len(scores):
            if top_k == 1:
                best_index = 0
                best_score = scores[0]
                for index in range(1, len(scores)):
                    score = scores[index]
                    if score > best_score:
                        best_index = index
                        best_score = score
                return [(best_index, best_score)]
            return [
                (index, score)
                for _negative_score, index, score in heapq.nsmallest(
                    top_k,
                    ((-score, index, score) for index, score in enumerate(scores)),
                )
            ]
        return sorted(
            enumerate(scores),
            key=lambda item: (-item[1], item[0]),
        )
