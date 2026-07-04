from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


RESEARCH_FETCH_BUDGET_RECEIPT_SCHEMA_VERSION = "melix.research_fetch_budget_receipt.v1"

_BINARY_CONTENT_TYPES = frozenset(
    (
        "application/octet-stream",
        "application/pdf",
    )
)


@dataclass(frozen=True, slots=True)
class ResearchFetchBudgetPolicy:
    default_max_bytes: int
    hard_max_bytes: int

    def __post_init__(self) -> None:
        if self.default_max_bytes <= 0:
            raise ValueError("default_max_bytes must be positive")
        if self.hard_max_bytes <= 0:
            raise ValueError("hard_max_bytes must be positive")
        if self.default_max_bytes > self.hard_max_bytes:
            raise ValueError("default_max_bytes must not exceed hard_max_bytes")


@dataclass(frozen=True, slots=True)
class ResearchFetchBudgetReceipt:
    source_id: str
    source_url_hash: str
    requested_max_bytes: int
    default_max_bytes: int
    effective_max_bytes: int
    hard_max_bytes: int
    fetched_bytes: int
    declared_total_bytes: int
    truncated: bool
    status: str
    blocked_reason: str
    content_type: str
    partial_content_notice: str
    refetch_hint: str
    cache_key: str
    raw_url_included: bool = False
    schema_version: str = RESEARCH_FETCH_BUDGET_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_url_hash": self.source_url_hash,
            "requested_max_bytes": int(self.requested_max_bytes),
            "default_max_bytes": int(self.default_max_bytes),
            "effective_max_bytes": int(self.effective_max_bytes),
            "hard_max_bytes": int(self.hard_max_bytes),
            "fetched_bytes": int(self.fetched_bytes),
            "declared_total_bytes": int(self.declared_total_bytes),
            "truncated": bool(self.truncated),
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "content_type": self.content_type,
            "partial_content_notice": self.partial_content_notice,
            "refetch_hint": self.refetch_hint,
            "cache_key": self.cache_key,
            "raw_url_included": bool(self.raw_url_included),
        }


@dataclass(frozen=True, slots=True)
class ResearchFetchResult:
    content: str
    receipt: dict[str, object]


def fetch_stream_with_budget(
    *,
    source_id: str,
    url: str,
    content_type: str,
    chunks: Iterable[bytes],
    policy: ResearchFetchBudgetPolicy,
    declared_total_bytes: int | None = None,
    requested_max_bytes: int | None = None,
) -> ResearchFetchResult:
    normalized_content_type = _normalized_content_type(content_type)
    normalized_url = _normalized_url(url)
    source_url_hash = _sha256_hex(normalized_url)
    requested = _requested_budget_value(requested_max_bytes)
    effective_max_bytes = _effective_max_bytes(requested, policy)
    declared_total = _declared_total_value(declared_total_bytes)

    if declared_total > policy.hard_max_bytes:
        receipt = _receipt(
            source_id=source_id,
            source_url_hash=source_url_hash,
            requested_max_bytes=requested,
            policy=policy,
            effective_max_bytes=effective_max_bytes,
            fetched_bytes=0,
            declared_total_bytes=declared_total,
            truncated=False,
            status="blocked",
            blocked_reason="declared_total_exceeds_hard_max",
            content_type=normalized_content_type,
            partial_content_notice="",
            refetch_hint="Lower the source size or configure a higher hard fetch ceiling.",
        )
        return ResearchFetchResult(content="", receipt=receipt.to_dict())

    collected = bytearray()
    truncated = False
    for chunk in chunks:
        if not chunk:
            continue
        remaining = effective_max_bytes - len(collected)
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            collected.extend(chunk[:remaining])
            truncated = True
            break
        collected.extend(chunk)

    fetched_bytes = len(collected)
    if (
        declared_total
        and fetched_bytes >= effective_max_bytes
        and declared_total > fetched_bytes
    ):
        truncated = True

    if truncated and normalized_content_type in _BINARY_CONTENT_TYPES:
        receipt = _receipt(
            source_id=source_id,
            source_url_hash=source_url_hash,
            requested_max_bytes=requested,
            policy=policy,
            effective_max_bytes=effective_max_bytes,
            fetched_bytes=fetched_bytes,
            declared_total_bytes=declared_total,
            truncated=True,
            status="blocked",
            blocked_reason="binary_truncation_not_parseable",
            content_type=normalized_content_type,
            partial_content_notice="",
            refetch_hint="Fetch the complete binary source before parsing it as evidence.",
        )
        return ResearchFetchResult(content="", receipt=receipt.to_dict())

    notice = ""
    status = "ok"
    if truncated:
        total_description = str(declared_total) if declared_total else "an unknown total"
        notice = (
            f"[Melix partial content: fetched {fetched_bytes} of "
            f"{total_description} bytes.]"
        )
        status = "truncated"

    body = collected.decode("utf-8", errors="replace")
    content = f"{notice}\n{body}" if notice else body
    receipt = _receipt(
        source_id=source_id,
        source_url_hash=source_url_hash,
        requested_max_bytes=requested,
        policy=policy,
        effective_max_bytes=effective_max_bytes,
        fetched_bytes=fetched_bytes,
        declared_total_bytes=declared_total,
        truncated=truncated,
        status=status,
        blocked_reason="",
        content_type=normalized_content_type,
        partial_content_notice=notice,
        refetch_hint="Increase max_bytes to fetch the complete source." if truncated else "",
    )
    return ResearchFetchResult(content=content, receipt=receipt.to_dict())


def _receipt(
    *,
    source_id: str,
    source_url_hash: str,
    requested_max_bytes: int,
    policy: ResearchFetchBudgetPolicy,
    effective_max_bytes: int,
    fetched_bytes: int,
    declared_total_bytes: int,
    truncated: bool,
    status: str,
    blocked_reason: str,
    content_type: str,
    partial_content_notice: str,
    refetch_hint: str,
) -> ResearchFetchBudgetReceipt:
    cache_key = _cache_key(
        source_url_hash=source_url_hash,
        content_type=content_type,
        effective_max_bytes=effective_max_bytes,
        declared_total_bytes=declared_total_bytes,
        truncated=truncated,
    )
    return ResearchFetchBudgetReceipt(
        source_id=source_id,
        source_url_hash=source_url_hash,
        requested_max_bytes=requested_max_bytes,
        default_max_bytes=policy.default_max_bytes,
        effective_max_bytes=effective_max_bytes,
        hard_max_bytes=policy.hard_max_bytes,
        fetched_bytes=fetched_bytes,
        declared_total_bytes=declared_total_bytes,
        truncated=truncated,
        status=status,
        blocked_reason=blocked_reason,
        content_type=content_type,
        partial_content_notice=partial_content_notice,
        refetch_hint=refetch_hint,
        cache_key=cache_key,
    )


def _effective_max_bytes(requested: int, policy: ResearchFetchBudgetPolicy) -> int:
    if requested <= 0:
        return policy.default_max_bytes
    return min(requested, policy.hard_max_bytes)


def _requested_budget_value(value: int | None) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _declared_total_value(value: int | None) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _normalized_content_type(content_type: str) -> str:
    if not isinstance(content_type, str):
        return "application/octet-stream"
    normalized = content_type.split(";", 1)[0].strip().lower()
    return normalized or "application/octet-stream"


def _normalized_url(url: str) -> str:
    if not isinstance(url, str):
        return ""
    raw = url.strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.scheme or not parts.netloc:
        return raw
    host = (parts.hostname or "").lower()
    netloc = host
    try:
        port = parts.port
    except ValueError:
        return raw
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def _cache_key(
    *,
    source_url_hash: str,
    content_type: str,
    effective_max_bytes: int,
    declared_total_bytes: int,
    truncated: bool,
) -> str:
    payload = "|".join(
        (
            source_url_hash,
            content_type,
            str(effective_max_bytes),
            str(declared_total_bytes),
            "truncated" if truncated else "full",
        )
    )
    return f"research-fetch:{_sha256_hex(payload)}"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
