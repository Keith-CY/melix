from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit


NETWORK_FETCH_POLICY_RECEIPT_SCHEMA_VERSION = "melix.network_fetch_policy_receipt.v1"
PRIVACY_AUDIT_COUNTER_SCHEMA_VERSION = "melix.privacy_audit_counter.v1"

_PRIVATE_IP_REDACTION = "[REDACTED_PRIVATE_IP]"
_LOCAL_PATH_REDACTION = "[LOCAL_PATH]"

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
