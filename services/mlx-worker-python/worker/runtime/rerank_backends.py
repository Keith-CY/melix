from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import re


TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RerankBackendDescriptor:
    backend_id: str
    default_family_id: str
    estimated_resident_bytes: int


class DeterministicRerankBackend:
    descriptor = RerankBackendDescriptor(
        backend_id="token-overlap-v1",
        default_family_id="jina-v3",
        estimated_resident_bytes=1792,
    )

    def metadata(self) -> dict[str, object]:
        return {
            "rerank_backend_id": self.descriptor.backend_id,
            "rerank_backend": self,
        }

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return TOKEN_RE.findall(text.lower())

    @staticmethod
    def build_tie_breaker_seed(query: str):
        return hashlib.sha256(f"{query}\0".encode("utf-8"))

    @staticmethod
    def tie_breaker_from_seed(seed, document: str) -> float:
        digest_builder = seed.copy()
        digest_builder.update(document.encode("utf-8"))
        digest = digest_builder.digest()
        return int.from_bytes(digest[:4], "little") / 0xFFFFFFFF * 0.0001

    @staticmethod
    def tie_breaker_from_prefix(query_prefix: bytes, document: str) -> float:
        digest = hashlib.sha256(query_prefix + document.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little") / 0xFFFFFFFF * 0.0001

    @staticmethod
    def tie_breaker(query: str, document: str) -> float:
        return DeterministicRerankBackend.tie_breaker_from_seed(
            DeterministicRerankBackend.build_tie_breaker_seed(query),
            document,
        )


@dataclass(frozen=True)
class RerankFamilyDescriptor:
    family_id: str
    scoring_mode: str


@dataclass(frozen=True)
class RerankQueryContext:
    query: str
    query_tokens: tuple[str, ...]
    query_token_set: frozenset[str]
    ordered_pairs: frozenset[tuple[str, str]]
    tie_breaker_seed: object


class RerankFamilyAdapter:
    descriptor: RerankFamilyDescriptor

    def metadata(self) -> dict[str, object]:
        return {
            "rerank_family_id": self.descriptor.family_id,
            "rerank_scoring_mode": self.descriptor.scoring_mode,
            "rerank_family_adapter": self,
        }

    def build_query_context(
        self,
        backend: DeterministicRerankBackend,
        query: str,
        *,
        query_tokens: list[str] | None = None,
        query_token_set: set[str] | None = None,
    ) -> RerankQueryContext:
        if query_tokens is None:
            query_tokens = backend.tokenize(query)
        if query_token_set is None:
            query_token_set = set(query_tokens)
        normalized_query_tokens = tuple(query_tokens)
        return RerankQueryContext(
            query=query,
            query_tokens=normalized_query_tokens,
            query_token_set=frozenset(query_token_set),
            ordered_pairs=frozenset(_build_adjacent_pairs(normalized_query_tokens)),
            tie_breaker_seed=backend.build_tie_breaker_seed(query),
        )

    def score(
        self,
        backend: DeterministicRerankBackend,
        query: str,
        document: str,
        *,
        query_context: RerankQueryContext | None = None,
        query_tokens: list[str] | None = None,
        query_token_set: set[str] | None = None,
    ) -> float:
        raise NotImplementedError


def _build_adjacent_pairs(tokens: Sequence[str]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (tokens[index], tokens[index + 1])
        for index in range(len(tokens) - 1)
    )


def _sequence_matches_at(
    haystack: Sequence[str],
    needle: Sequence[str],
    start: int,
) -> bool:
    return all(haystack[start + offset] == token for offset, token in enumerate(needle))


class BasicRerankFamilyAdapter(RerankFamilyAdapter):
    descriptor = RerankFamilyDescriptor(
        family_id="basic",
        scoring_mode="set-overlap",
    )

    def score(
        self,
        backend: DeterministicRerankBackend,
        query: str,
        document: str,
        *,
        query_context: RerankQueryContext | None = None,
        query_tokens: list[str] | None = None,
        query_token_set: set[str] | None = None,
    ) -> float:
        if query_context is None:
            query_context = self.build_query_context(
                backend,
                query,
                query_tokens=query_tokens,
                query_token_set=query_token_set,
            )
        reusable_query_token_set = query_token_set
        if reusable_query_token_set is None:
            reusable_query_token_set = query_context.query_token_set
        document_tokens = set(backend.tokenize(document))
        if not reusable_query_token_set and not document_tokens:
            overlap_score = 1.0
        else:
            overlap_count = len(reusable_query_token_set & document_tokens)
            union = (len(reusable_query_token_set) + len(document_tokens) - overlap_count) or 1
            overlap_score = overlap_count / union
        return round(
            overlap_score + backend.tie_breaker_from_seed(query_context.tie_breaker_seed, document),
            6,
        )


class JinaV3RerankFamilyAdapter(RerankFamilyAdapter):
    descriptor = RerankFamilyDescriptor(
        family_id="jina-v3",
        scoring_mode="order-aware-overlap",
    )

    def score(
        self,
        backend: DeterministicRerankBackend,
        query: str,
        document: str,
        *,
        query_context: RerankQueryContext | None = None,
        query_tokens: list[str] | None = None,
        query_token_set: set[str] | None = None,
    ) -> float:
        if query_context is None:
            query_context = self.build_query_context(
                backend,
                query,
                query_tokens=query_tokens,
                query_token_set=query_token_set,
            )
        reusable_query_tokens = query_tokens
        if reusable_query_tokens is None:
            reusable_query_tokens = query_context.query_tokens
        reusable_query_token_set = query_token_set
        if reusable_query_token_set is None:
            reusable_query_token_set = query_context.query_token_set
        document_tokens = backend.tokenize(document)
        document_token_set = set(document_tokens)

        if not reusable_query_token_set and not document_token_set:
            overlap_count = 0
            overlap_score = 1.0
        else:
            overlap_count = len(reusable_query_token_set & document_token_set)
            union = (len(reusable_query_token_set) + len(document_token_set) - overlap_count) or 1
            overlap_score = overlap_count / union

        if overlap_count == 0:
            pair_bonus = 0.0
        else:
            pair_bonus = self._ordered_pair_bonus(
                reusable_query_tokens,
                document_tokens,
                query_pairs=query_context.ordered_pairs,
            )
        has_all_query_terms = overlap_count >= len(reusable_query_token_set)
        if has_all_query_terms:
            exact_order, prefix_match = self._query_order_matches(document_tokens, reusable_query_tokens)
        else:
            exact_order = False
            prefix_match = False
        exact_order_bonus = 0.1 if exact_order else 0.0
        prefix_bonus = 0.05 if prefix_match else 0.0

        return round(
            overlap_score
            + pair_bonus
            + exact_order_bonus
            + prefix_bonus
            + backend.tie_breaker_from_seed(query_context.tie_breaker_seed, document),
            6,
        )

    @staticmethod
    def _ordered_pair_bonus(
        query_tokens: Sequence[str],
        document_tokens: Sequence[str],
        *,
        query_pairs: frozenset[tuple[str, str]] | None = None,
    ) -> float:
        if len(query_tokens) < 2 or len(document_tokens) < 2:
            return 0.0

        if query_pairs is None:
            query_pairs = frozenset(_build_adjacent_pairs(query_tokens))
        matched_pairs: set[tuple[str, str]] = set()
        query_pair_count = len(query_pairs)
        for index in range(len(document_tokens) - 1):
            pair = (document_tokens[index], document_tokens[index + 1])
            if pair not in query_pairs:
                continue
            matched_pairs.add(pair)
            if len(matched_pairs) == query_pair_count:
                break
        return (len(matched_pairs) / query_pair_count) * 0.15

    @staticmethod
    def _has_query_prefix(document_tokens: Sequence[str], query_tokens: Sequence[str]) -> bool:
        if not query_tokens or len(query_tokens) > len(document_tokens):
            return False
        return _sequence_matches_at(document_tokens, query_tokens, 0)

    @staticmethod
    def _contains_contiguous_query(document_tokens: Sequence[str], query_tokens: Sequence[str]) -> bool:
        if not query_tokens or len(query_tokens) > len(document_tokens):
            return False
        query_length = len(query_tokens)
        last_start = len(document_tokens) - query_length
        for start in range(last_start + 1):
            if _sequence_matches_at(document_tokens, query_tokens, start):
                return True
        return False

    @staticmethod
    def _query_order_matches(
        document_tokens: Sequence[str],
        query_tokens: Sequence[str],
    ) -> tuple[bool, bool]:
        prefix_match = JinaV3RerankFamilyAdapter._has_query_prefix(document_tokens, query_tokens)
        if prefix_match:
            return True, True
        return JinaV3RerankFamilyAdapter._contains_contiguous_query(document_tokens, query_tokens), False


class CausalLMRerankFamilyAdapter(RerankFamilyAdapter):
    descriptor = RerankFamilyDescriptor(
        family_id="causal-lm",
        scoring_mode="yes-no-logits",
    )

    def metadata(self) -> dict[str, object]:
        metadata = super().metadata()
        metadata["rerank_yes_no_labels"] = "yes,no"
        return metadata

    def score(
        self,
        backend: DeterministicRerankBackend,
        query: str,
        document: str,
        *,
        query_context: RerankQueryContext | None = None,
        query_tokens: list[str] | None = None,
        query_token_set: set[str] | None = None,
    ) -> float:
        if query_context is None:
            query_context = self.build_query_context(
                backend,
                query,
                query_tokens=query_tokens,
                query_token_set=query_token_set,
            )
        reusable_query_tokens = query_tokens
        if reusable_query_tokens is None:
            reusable_query_tokens = query_context.query_tokens
        reusable_query_token_set = query_token_set
        if reusable_query_token_set is None:
            reusable_query_token_set = query_context.query_token_set
        document_tokens = backend.tokenize(document)
        document_token_set = set(document_tokens)
        overlap_count = len(reusable_query_token_set & document_token_set)
        overlap = overlap_count / (len(reusable_query_token_set) or 1)
        if overlap_count == 0:
            pair_bonus = 0.0
        else:
            pair_bonus = JinaV3RerankFamilyAdapter._ordered_pair_bonus(
                reusable_query_tokens,
                document_tokens,
                query_pairs=query_context.ordered_pairs,
            )
        if overlap_count >= len(reusable_query_token_set):
            exact_order, prefix_match = JinaV3RerankFamilyAdapter._query_order_matches(
                document_tokens,
                reusable_query_tokens,
            )
        else:
            exact_order = False
            prefix_match = False

        yes_logit = overlap * 6.0
        yes_logit += pair_bonus * 3.0
        yes_logit += 0.75 if exact_order else 0.0
        yes_logit += 0.5 if prefix_match else 0.0

        no_logit = 1.5
        no_logit -= overlap * 3.0
        if overlap_count == 0:
            no_logit += 0.3

        return round(
            yes_logit - no_logit + backend.tie_breaker_from_seed(query_context.tie_breaker_seed, document),
            6,
        )


def resolve_rerank_backend(backend_id: str) -> DeterministicRerankBackend:
    normalized = backend_id.strip() or "token-overlap-v1"
    if normalized == "token-overlap-v1":
        return DeterministicRerankBackend()
    raise ValueError(f"Unsupported rerank backend: {backend_id}")


def resolve_rerank_family(
    family_id: str,
    backend: DeterministicRerankBackend,
) -> RerankFamilyAdapter:
    normalized = family_id.strip() or backend.descriptor.default_family_id
    if normalized == backend.descriptor.default_family_id:
        return JinaV3RerankFamilyAdapter()
    if normalized == "basic":
        return BasicRerankFamilyAdapter()
    if normalized == "causal-lm":
        return CausalLMRerankFamilyAdapter()
    raise ValueError(f"Unsupported rerank family: {family_id}")
