from __future__ import annotations

from worker.runtime.rerank_backends import (
    resolve_rerank_backend,
    resolve_rerank_family,
)


class DeterministicRerankRuntime:
    runtime_name = "deterministic-rerank"

    def load_model(self, model_spec):
        backend = resolve_rerank_backend(model_spec.ext.get("rerank_backend_id", "token-overlap-v1"))
        family = resolve_rerank_family(model_spec.ext.get("rerank_family_id", ""), backend)
        metadata = backend.metadata()
        metadata.update(family.metadata())
        return {
            "model_id": model_spec.model_id,
            **metadata,
        }

    def estimate_resident_bytes(self, model_spec):
        backend = resolve_rerank_backend(model_spec.ext.get("rerank_backend_id", "token-overlap-v1"))
        return int(backend.descriptor.estimated_resident_bytes)

    def score_documents(self, loaded_model, query: str, documents: list[str]) -> list[float]:
        backend = loaded_model.get("rerank_backend")
        if backend is None:
            backend = resolve_rerank_backend(loaded_model.get("rerank_backend_id", "token-overlap-v1"))
        family = loaded_model.get("rerank_family_adapter")
        if family is None:
            family = resolve_rerank_family(loaded_model.get("rerank_family_id", ""), backend)
        query_tokens = backend.tokenize(query)
        query_token_set = set(query_tokens)
        query_context = family.build_query_context(
            backend,
            query,
            query_tokens=query_tokens,
            query_token_set=query_token_set,
        )
        return [
            family.score(
                backend,
                query,
                document,
                query_context=query_context,
                query_tokens=query_tokens,
                query_token_set=query_token_set,
            )
            for document in documents
        ]
