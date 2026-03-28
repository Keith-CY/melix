from __future__ import annotations

import hashlib
import re


TOKEN_RE = re.compile(r"[a-z0-9]+")


class DeterministicRerankRuntime:
    runtime_name = "deterministic-rerank"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 1792

    def score_documents(self, loaded_model, query: str, documents: list[str]) -> list[float]:
        _ = loaded_model
        query_tokens = set(self._tokenize(query))
        return [self._score(query, query_tokens, document) for document in documents]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return TOKEN_RE.findall(text.lower())

    def _score(self, query: str, query_tokens: set[str], document: str) -> float:
        document_tokens = set(self._tokenize(document))
        if not query_tokens and not document_tokens:
            overlap_score = 1.0
        else:
            union = len(query_tokens | document_tokens) or 1
            overlap_score = len(query_tokens & document_tokens) / union

        digest = hashlib.sha256(f"{query}\0{document}".encode("utf-8")).digest()
        tie_breaker = int.from_bytes(digest[:4], "little") / 0xFFFFFFFF * 0.0001
        return round(overlap_score + tie_breaker, 6)
