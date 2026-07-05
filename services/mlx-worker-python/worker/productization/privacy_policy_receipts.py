from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit


NETWORK_FETCH_POLICY_RECEIPT_SCHEMA_VERSION = "melix.network_fetch_policy_receipt.v1"
PRIVACY_AUDIT_COUNTER_SCHEMA_VERSION = "melix.privacy_audit_counter.v1"
PRIVACY_DETECTOR_RECEIPT_SCHEMA_VERSION = "melix.privacy_detector_receipt.v1"

DEFAULT_PRIVACY_POLICY_ID = "melix.default_privacy_policy.v1"
PATTERN_PRIVACY_DETECTOR_ID = "melix.pattern_detector.v1"

_PRIVATE_IP_REDACTION = "[REDACTED_PRIVATE_IP]"
_LOCAL_PATH_REDACTION = "[LOCAL_PATH]"
_DETERMINISTIC_PATTERN_CONFIDENCE_SOURCE = "deterministic_pattern"

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\b"
)
_HF_TOKEN_PATTERN = re.compile(
    r"\bhf_[A-Za-z0-9][A-Za-z0-9_\-=]{5,}",
    flags=re.IGNORECASE,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b[A-Za-z0-9_]*(?:"
    r"HF_TOKEN|HUGGINGFACE_HUB_TOKEN|MELIX_HF_TOKEN|MELIX_HUGGINGFACE_TOKEN|"
    r"MELIX_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|"
    r"API_KEY|ACCESS_TOKEN|AUTH_TOKEN|BEARER_TOKEN|SECRET_KEY|CLIENT_SECRET|"
    r"PASSWORD"
    r")\s*=\s*(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s;]+)",
    flags=re.IGNORECASE,
)
_BEARER_TOKEN_PATTERN = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}",
    flags=re.IGNORECASE,
)
_PRIVACY_PATTERNS = (
    ("secret", "[REDACTED_SECRET]", _SECRET_ASSIGNMENT_PATTERN),
    ("secret", "[REDACTED_SECRET]", _BEARER_TOKEN_PATTERN),
    ("secret", "[REDACTED_SECRET]", _HF_TOKEN_PATTERN),
    ("email", "[REDACTED_EMAIL]", _EMAIL_PATTERN),
)

_NETWORK_FETCH_METADATA_FIELDS = {
    "melix.network_fetch.policy.surface": "surface",
    "melix.network_fetch.policy.route_scope": "route_scope",
    "melix.network_fetch.policy.action": "action",
    "melix.network_fetch.policy.url_class": "url_class",
    "melix.network_fetch.policy.url_scheme": "url_scheme",
    "melix.network_fetch.policy.host_class": "host_class",
    "melix.network_fetch.policy.resolved_ip": "resolved_ip",
    "melix.network_fetch.policy.resolved_ip_class": "resolved_ip_class",
    "melix.network_fetch.policy.redirect_hops_checked": "redirect_hops_checked",
    "melix.network_fetch.policy.blocked_reason": "blocked_reason",
    "melix.network_fetch.policy.redacted_url": "redacted_url",
    "melix.network_fetch.policy.raw_url_included": "raw_url_included",
    "melix.network_fetch.policy.fetch_attempted": "fetch_attempted",
}
_NETWORK_FETCH_REQUIRED_FIELDS = frozenset(
    (
        "surface",
        "route_scope",
        "action",
        "url_class",
        "url_scheme",
        "host_class",
        "redirect_hops_checked",
        "blocked_reason",
        "redacted_url",
        "raw_url_included",
        "fetch_attempted",
    )
)

_PRIVACY_AUDIT_METADATA_FIELDS = {
    "melix.privacy.audit.surface": "surface",
    "melix.privacy.audit.route_scope": "route_scope",
    "melix.privacy.audit.blocked_count": "blocked_count",
    "melix.privacy.audit.redacted_count": "redacted_count",
    "melix.privacy.audit.passed_count": "passed_count",
    "melix.privacy.audit.raw_sensitive_span_count": "raw_sensitive_span_count",
}
_PRIVACY_AUDIT_REQUIRED_FIELDS = frozenset(_PRIVACY_AUDIT_METADATA_FIELDS.values())

_PRIVACY_DETECTOR_METADATA_FIELDS = {
    "melix.privacy.detector.surface": "surface",
    "melix.privacy.detector.route_scope": "route_scope",
    "melix.privacy.detector.detector_id": "detector_id",
    "melix.privacy.detector.policy_id": "policy_id",
    "melix.privacy.detector.policy_mode": "policy_mode",
    "melix.privacy.detector.action": "action",
    "melix.privacy.detector.categories": "categories",
    "melix.privacy.detector.match_count": "match_count",
    "melix.privacy.detector.redacted_span_count": "redacted_span_count",
    "melix.privacy.detector.blocked_reason": "blocked_reason",
    "melix.privacy.detector.confidence_source": "confidence_source",
    "melix.privacy.detector.raw_sensitive_span_count": "raw_sensitive_span_count",
    "melix.privacy.detector.raw_text_included": "raw_text_included",
}
_PRIVACY_DETECTOR_REQUIRED_FIELDS = frozenset(_PRIVACY_DETECTOR_METADATA_FIELDS.values())


@dataclass(frozen=True, slots=True)
class _PrivacyPatternMatch:
    start: int
    end: int
    category: str
    placeholder: str

@dataclass(frozen=True, slots=True)
class NetworkFetchPolicyReceipt:
    surface: str
    route_scope: str
    action: str
    url_class: str
    url_scheme: str
    host_class: str
    resolved_ip: str = ""
    resolved_ip_class: str = ""
    redirect_hops_checked: int = 0
    blocked_reason: str = ""
    redacted_url: str = ""
    raw_url_included: bool = False
    fetch_attempted: bool = False
    schema_version: str = NETWORK_FETCH_POLICY_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "route_scope": self.route_scope,
            "action": self.action,
            "url_class": self.url_class,
            "url_scheme": self.url_scheme,
            "host_class": self.host_class,
            "resolved_ip": self.resolved_ip,
            "resolved_ip_class": self.resolved_ip_class,
            "redirect_hops_checked": int(self.redirect_hops_checked),
            "blocked_reason": self.blocked_reason,
            "redacted_url": self.redacted_url,
            "raw_url_included": bool(self.raw_url_included),
            "fetch_attempted": bool(self.fetch_attempted),
        }


@dataclass(frozen=True, slots=True)
class PrivacyAuditCounter:
    surface: str
    route_scope: str
    blocked_count: int = 0
    redacted_count: int = 0
    passed_count: int = 0
    raw_sensitive_span_count: int = 0
    schema_version: str = PRIVACY_AUDIT_COUNTER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "route_scope": self.route_scope,
            "blocked_count": int(self.blocked_count),
            "redacted_count": int(self.redacted_count),
            "passed_count": int(self.passed_count),
            "raw_sensitive_span_count": int(self.raw_sensitive_span_count),
        }


@dataclass(frozen=True, slots=True)
class PrivacyDetectorReceipt:
    surface: str
    route_scope: str
    detector_id: str
    policy_id: str
    policy_mode: str
    action: str
    categories: tuple[str, ...] = ()
    match_count: int = 0
    redacted_span_count: int = 0
    blocked_reason: str = ""
    confidence_source: str = _DETERMINISTIC_PATTERN_CONFIDENCE_SOURCE
    raw_sensitive_span_count: int = 0
    raw_text_included: bool = False
    schema_version: str = PRIVACY_DETECTOR_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "route_scope": self.route_scope,
            "detector_id": self.detector_id,
            "policy_id": self.policy_id,
            "policy_mode": self.policy_mode,
            "action": self.action,
            "categories": list(self.categories),
            "match_count": int(self.match_count),
            "redacted_span_count": int(self.redacted_span_count),
            "blocked_reason": self.blocked_reason,
            "confidence_source": self.confidence_source,
            "raw_sensitive_span_count": int(self.raw_sensitive_span_count),
            "raw_text_included": bool(self.raw_text_included),
        }


@dataclass(frozen=True, slots=True)
class PrivacyDetectionResult:
    redacted_text: str
    receipt_object: PrivacyDetectorReceipt
    audit_counter_object: PrivacyAuditCounter

    @property
    def receipt(self) -> dict[str, object]:
        return self.receipt_object.to_dict()

    @property
    def audit_counter(self) -> dict[str, object]:
        return self.audit_counter_object.to_dict()


def network_fetch_policy_receipt_for_url(
    raw_url: str,
    *,
    surface: str,
    route_scope: str,
    resolved_ip: str = "",
    redirect_hops_checked: int = 0,
) -> dict[str, object]:
    """Build a redacted network-fetch policy receipt without dereferencing URLs."""

    receipt = _network_fetch_policy_receipt(
        raw_url,
        surface=surface,
        route_scope=route_scope,
        resolved_ip=resolved_ip,
        redirect_hops_checked=redirect_hops_checked,
    )
    return receipt.to_dict()


def privacy_audit_counter(
    *,
    surface: str,
    route_scope: str,
    decisions: tuple[str, ...] = (),
    raw_sensitive_span_count: int = 0,
) -> PrivacyAuditCounter:
    return PrivacyAuditCounter(
        surface=surface,
        route_scope=route_scope,
        blocked_count=sum(1 for decision in decisions if decision == "blocked"),
        redacted_count=sum(1 for decision in decisions if decision == "redacted"),
        passed_count=sum(1 for decision in decisions if decision == "passed"),
        raw_sensitive_span_count=raw_sensitive_span_count,
    )


def detect_privacy_patterns(
    value: str,
    *,
    surface: str,
    route_scope: str,
    policy_mode: str = "redact",
    policy_id: str = DEFAULT_PRIVACY_POLICY_ID,
    detector_id: str = PATTERN_PRIVACY_DETECTOR_ID,
) -> PrivacyDetectionResult:
    text = value if isinstance(value, str) else ""
    normalized_mode = str(policy_mode).strip().lower() or "redact"
    if normalized_mode not in {"redact", "block"}:
        normalized_mode = "redact"

    matches = _privacy_pattern_matches(text)
    categories = tuple(sorted({match.category for match in matches}))
    match_count = len(matches)

    action = "passed"
    blocked_reason = ""
    redacted_span_count = 0
    redacted_text = text
    if match_count and normalized_mode == "block":
        action = "blocked"
        blocked_reason = "pattern_match_blocked"
        redacted_text = ""
    elif match_count:
        action = "redacted"
        redacted_span_count = match_count
        redacted_text = _redacted_text_for_matches(text, matches)

    receipt = PrivacyDetectorReceipt(
        surface=surface,
        route_scope=route_scope,
        detector_id=detector_id,
        policy_id=policy_id,
        policy_mode=normalized_mode,
        action=action,
        categories=categories,
        match_count=match_count,
        redacted_span_count=redacted_span_count,
        blocked_reason=blocked_reason,
        confidence_source=_DETERMINISTIC_PATTERN_CONFIDENCE_SOURCE,
        raw_sensitive_span_count=0,
        raw_text_included=False,
    )
    return PrivacyDetectionResult(
        redacted_text=redacted_text,
        receipt_object=receipt,
        audit_counter_object=privacy_audit_counter(
            surface=surface,
            route_scope=route_scope,
            decisions=(action,),
            raw_sensitive_span_count=0,
        ),
    )


def aggregate_privacy_detection_results(
    results: Iterable[PrivacyDetectionResult],
    *,
    surface: str,
    route_scope: str,
    policy_mode: str,
    policy_id: str = DEFAULT_PRIVACY_POLICY_ID,
    detector_id: str = PATTERN_PRIVACY_DETECTOR_ID,
) -> PrivacyDetectionResult:
    result_tuple = tuple(results)
    actions = tuple(result.receipt_object.action for result in result_tuple) or ("passed",)
    action = "passed"
    blocked_reason = ""
    if any(decision == "blocked" for decision in actions):
        action = "blocked"
        blocked_reason = "pattern_match_blocked"
    elif any(decision == "redacted" for decision in actions):
        action = "redacted"

    categories = tuple(sorted({
        category
        for result in result_tuple
        for category in result.receipt_object.categories
    }))
    match_count = sum(result.receipt_object.match_count for result in result_tuple)
    redacted_span_count = sum(
        result.receipt_object.redacted_span_count for result in result_tuple
    )
    normalized_mode = str(policy_mode).strip().lower() or "off"
    if normalized_mode not in {"off", "redact", "block"}:
        normalized_mode = "off"
    receipt = PrivacyDetectorReceipt(
        surface=surface,
        route_scope=route_scope,
        detector_id=detector_id,
        policy_id=policy_id,
        policy_mode=normalized_mode,
        action=action,
        categories=categories,
        match_count=match_count,
        redacted_span_count=redacted_span_count,
        blocked_reason=blocked_reason,
        confidence_source=_DETERMINISTIC_PATTERN_CONFIDENCE_SOURCE,
        raw_sensitive_span_count=0,
        raw_text_included=False,
    )
    return PrivacyDetectionResult(
        redacted_text="",
        receipt_object=receipt,
        audit_counter_object=privacy_audit_counter(
            surface=surface,
            route_scope=route_scope,
            decisions=actions,
            raw_sensitive_span_count=0,
        ),
    )


def workspace_ingest_network_fetch_policy_receipt() -> dict[str, object]:
    return network_fetch_policy_receipt_for_url(
        ".",
        surface="workspace_ingest",
        route_scope="workspace_preflight",
    )


def workspace_ingest_privacy_audit_counters() -> list[dict[str, object]]:
    return [
        privacy_audit_counter(
            surface="workspace_ingest",
            route_scope="workspace_preflight",
            decisions=("passed",),
        ).to_dict()
    ]


def network_fetch_policy_receipt_from_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt = {
        receipt_key: metadata.get(audit_key)
        for audit_key, receipt_key in _NETWORK_FETCH_METADATA_FIELDS.items()
        if metadata.get(audit_key) is not None
    }
    if not _NETWORK_FETCH_REQUIRED_FIELDS.issubset(receipt):
        return {}
    schema_version = str(
        metadata.get(
            "melix.network_fetch.policy.schema_version",
            NETWORK_FETCH_POLICY_RECEIPT_SCHEMA_VERSION,
        )
    )
    if schema_version != NETWORK_FETCH_POLICY_RECEIPT_SCHEMA_VERSION:
        return {}
    parsed_redirect_hops = _int_value(receipt["redirect_hops_checked"])
    raw_url_included = _bool_value(receipt["raw_url_included"])
    fetch_attempted = _bool_value(receipt["fetch_attempted"])
    if parsed_redirect_hops is None or raw_url_included is None or fetch_attempted is None:
        return {}
    return NetworkFetchPolicyReceipt(
        surface=str(receipt["surface"]),
        route_scope=str(receipt["route_scope"]),
        action=str(receipt["action"]),
        url_class=str(receipt["url_class"]),
        url_scheme=str(receipt["url_scheme"]),
        host_class=str(receipt["host_class"]),
        resolved_ip=str(receipt.get("resolved_ip", "")),
        resolved_ip_class=str(receipt.get("resolved_ip_class", "")),
        redirect_hops_checked=parsed_redirect_hops,
        blocked_reason=str(receipt["blocked_reason"]),
        redacted_url=str(receipt["redacted_url"]),
        raw_url_included=raw_url_included,
        fetch_attempted=fetch_attempted,
    ).to_dict()


def privacy_audit_counter_from_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    counter = {
        receipt_key: metadata.get(audit_key)
        for audit_key, receipt_key in _PRIVACY_AUDIT_METADATA_FIELDS.items()
        if metadata.get(audit_key) is not None
    }
    if not _PRIVACY_AUDIT_REQUIRED_FIELDS.issubset(counter):
        return {}
    schema_version = str(
        metadata.get(
            "melix.privacy.audit.schema_version",
            PRIVACY_AUDIT_COUNTER_SCHEMA_VERSION,
        )
    )
    if schema_version != PRIVACY_AUDIT_COUNTER_SCHEMA_VERSION:
        return {}
    parsed_counts = {
        key: _int_value(counter[key])
        for key in (
            "blocked_count",
            "redacted_count",
            "passed_count",
            "raw_sensitive_span_count",
        )
    }
    if any(value is None for value in parsed_counts.values()):
        return {}
    return PrivacyAuditCounter(
        surface=str(counter["surface"]),
        route_scope=str(counter["route_scope"]),
        blocked_count=parsed_counts["blocked_count"] or 0,
        redacted_count=parsed_counts["redacted_count"] or 0,
        passed_count=parsed_counts["passed_count"] or 0,
        raw_sensitive_span_count=parsed_counts["raw_sensitive_span_count"] or 0,
    ).to_dict()


def privacy_detector_receipt_from_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt = {
        receipt_key: metadata.get(audit_key)
        for audit_key, receipt_key in _PRIVACY_DETECTOR_METADATA_FIELDS.items()
        if metadata.get(audit_key) is not None
    }
    if not _PRIVACY_DETECTOR_REQUIRED_FIELDS.issubset(receipt):
        return {}
    schema_version = str(
        metadata.get(
            "melix.privacy.detector.schema_version",
            PRIVACY_DETECTOR_RECEIPT_SCHEMA_VERSION,
        )
    )
    if schema_version != PRIVACY_DETECTOR_RECEIPT_SCHEMA_VERSION:
        return {}
    action = str(receipt["action"])
    if action not in {"passed", "redacted", "blocked"}:
        return {}
    categories = _category_values(receipt["categories"])
    if categories is None:
        return {}
    parsed_match_count = _int_value(receipt["match_count"])
    parsed_redacted_span_count = _int_value(receipt["redacted_span_count"])
    parsed_raw_sensitive_span_count = _int_value(receipt["raw_sensitive_span_count"])
    raw_text_included = _bool_value(receipt["raw_text_included"])
    if (
        parsed_match_count is None
        or parsed_redacted_span_count is None
        or parsed_raw_sensitive_span_count is None
        or raw_text_included is None
    ):
        return {}
    if raw_text_included or parsed_raw_sensitive_span_count > 0:
        return {}
    if parsed_redacted_span_count > parsed_match_count:
        return {}
    return PrivacyDetectorReceipt(
        surface=str(receipt["surface"]),
        route_scope=str(receipt["route_scope"]),
        detector_id=str(receipt["detector_id"]),
        policy_id=str(receipt["policy_id"]),
        policy_mode=str(receipt["policy_mode"]),
        action=action,
        categories=tuple(categories),
        match_count=parsed_match_count,
        redacted_span_count=parsed_redacted_span_count,
        blocked_reason=str(receipt["blocked_reason"]),
        confidence_source=str(receipt["confidence_source"]),
        raw_sensitive_span_count=parsed_raw_sensitive_span_count,
        raw_text_included=raw_text_included,
    ).to_dict()


def _network_fetch_policy_receipt(
    raw_url: str,
    *,
    surface: str,
    route_scope: str,
    resolved_ip: str,
    redirect_hops_checked: int,
) -> NetworkFetchPolicyReceipt:
    value = str(raw_url).strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return NetworkFetchPolicyReceipt(
            surface=surface,
            route_scope=route_scope,
            action="blocked",
            url_class="invalid",
            url_scheme="",
            host_class="invalid",
            redirect_hops_checked=redirect_hops_checked,
            blocked_reason="malformed_url",
            redacted_url="[REDACTED_URL]",
        )

    scheme = parsed.scheme.lower()
    if not scheme:
        return NetworkFetchPolicyReceipt(
            surface=surface,
            route_scope=route_scope,
            action="passed",
            url_class="local",
            url_scheme="path",
            host_class="local",
            redirect_hops_checked=redirect_hops_checked,
            redacted_url=_LOCAL_PATH_REDACTION,
        )
    if scheme == "file":
        return NetworkFetchPolicyReceipt(
            surface=surface,
            route_scope=route_scope,
            action="passed",
            url_class="local",
            url_scheme="file",
            host_class="local",
            redirect_hops_checked=redirect_hops_checked,
            redacted_url=_LOCAL_PATH_REDACTION,
        )
    if scheme not in {"http", "https"}:
        return NetworkFetchPolicyReceipt(
            surface=surface,
            route_scope=route_scope,
            action="blocked",
            url_class="invalid",
            url_scheme=scheme,
            host_class="invalid",
            redirect_hops_checked=redirect_hops_checked,
            blocked_reason="unsupported_scheme",
            redacted_url="[REDACTED_URL]",
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return NetworkFetchPolicyReceipt(
            surface=surface,
            route_scope=route_scope,
            action="blocked",
            url_class="invalid",
            url_scheme=scheme,
            host_class="missing",
            redirect_hops_checked=redirect_hops_checked,
            blocked_reason="missing_host",
            redacted_url="[REDACTED_URL]",
        )

    host_class = _classify_host(host)
    resolved_ip_class = _classify_ip_literal(resolved_ip) if resolved_ip else ""
    url_class = _effective_url_class(host_class, resolved_ip_class)
    blocked_reason = _blocked_reason(host_class, resolved_ip_class)
    action = "blocked" if blocked_reason else "passed"
    return NetworkFetchPolicyReceipt(
        surface=surface,
        route_scope=route_scope,
        action=action,
        url_class=url_class,
        url_scheme=scheme,
        host_class=host_class,
        resolved_ip=_redacted_resolved_ip(resolved_ip, resolved_ip_class),
        resolved_ip_class=resolved_ip_class,
        redirect_hops_checked=redirect_hops_checked,
        blocked_reason=blocked_reason,
        redacted_url=_redacted_url(
            scheme=scheme,
            host=host,
            action=action,
            host_class=host_class,
            resolved_ip_class=resolved_ip_class,
        ),
    )


def _classify_host(host: str) -> str:
    normalized = host.strip("[]").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return "loopback"
    ipv4_tail = _ipv4_tail_from_ipv6_literal(normalized)
    if ipv4_tail:
        try:
            return _classify_ip(ip_address(ipv4_tail))
        except ValueError:
            pass
    try:
        return _classify_ip(ip_address(normalized))
    except ValueError:
        return "public"


def _classify_ip_literal(value: str) -> str:
    stripped = str(value).strip().strip("[]").lower()
    if not stripped:
        return ""
    ipv4_tail = _ipv4_tail_from_ipv6_literal(stripped)
    if ipv4_tail:
        try:
            return _classify_ip(ip_address(ipv4_tail))
        except ValueError:
            pass
    try:
        return _classify_ip(ip_address(stripped))
    except ValueError:
        return "invalid"


def _classify_ip(address: object) -> str:
    ipv4_mapped = getattr(address, "ipv4_mapped", None)
    if ipv4_mapped is not None:
        address = ipv4_mapped
    if getattr(address, "is_loopback", False):
        return "loopback"
    if getattr(address, "is_link_local", False):
        return "link_local"
    if getattr(address, "is_private", False):
        return "private"
    return "public"


def _ipv4_tail_from_ipv6_literal(value: str) -> str:
    if value.startswith("::ffff:"):
        tail = value.removeprefix("::ffff:")
    elif value.startswith("::"):
        tail = value.removeprefix("::")
    else:
        return ""
    if "." not in tail:
        return ""
    return tail


def _effective_url_class(host_class: str, resolved_ip_class: str) -> str:
    if resolved_ip_class in {"loopback", "link_local", "private"}:
        return resolved_ip_class
    return host_class


def _blocked_reason(host_class: str, resolved_ip_class: str) -> str:
    if resolved_ip_class in {"loopback", "link_local", "private"} and host_class == "public":
        return "resolved_private_or_loopback_ip"
    if host_class in {"loopback", "link_local", "private"}:
        return "private_or_loopback_host"
    if resolved_ip_class == "invalid":
        return "invalid_resolved_ip"
    return ""


def _redacted_resolved_ip(resolved_ip: str, resolved_ip_class: str) -> str:
    if not resolved_ip:
        return ""
    if resolved_ip_class in {"loopback", "link_local", "private"}:
        return _PRIVATE_IP_REDACTION
    if resolved_ip_class == "invalid":
        return "[REDACTED_INVALID_IP]"
    return str(resolved_ip).strip()


def _redacted_url(
    *,
    scheme: str,
    host: str,
    action: str,
    host_class: str,
    resolved_ip_class: str,
) -> str:
    if action == "blocked" and (
        host_class in {"loopback", "link_local", "private"}
        or resolved_ip_class in {"loopback", "link_local", "private"}
    ):
        return f"{scheme}://[REDACTED_PRIVATE_HOST]/[redacted]"
    return f"{scheme}://{host}/[redacted]"


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _privacy_pattern_matches(text: str) -> tuple[_PrivacyPatternMatch, ...]:
    matches: list[_PrivacyPatternMatch] = []
    for category, placeholder, pattern in _PRIVACY_PATTERNS:
        for match in pattern.finditer(text):
            if match.start() == match.end():
                continue
            matches.append(
                _PrivacyPatternMatch(
                    start=match.start(),
                    end=match.end(),
                    category=category,
                    placeholder=placeholder,
                )
            )
    matches.sort(key=lambda item: (item.start, -(item.end - item.start)))
    selected: list[_PrivacyPatternMatch] = []
    selected_end = -1
    for match in matches:
        if match.start < selected_end:
            continue
        selected.append(match)
        selected_end = match.end
    return tuple(selected)


def _redacted_text_for_matches(text: str, matches: tuple[_PrivacyPatternMatch, ...]) -> str:
    parts: list[str] = []
    cursor = 0
    for match in matches:
        parts.append(text[cursor : match.start])
        parts.append(match.placeholder)
        cursor = match.end
    parts.append(text[cursor:])
    return "".join(parts)


def _category_values(value: object) -> tuple[str, ...] | None:
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_values = list(value)
    else:
        return None
    categories = sorted({str(item).strip() for item in raw_values if str(item).strip()})
    return tuple(categories)
