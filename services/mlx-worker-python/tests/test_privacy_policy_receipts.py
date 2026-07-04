from __future__ import annotations

import json

from worker.productization.privacy_policy_receipts import (
    PrivacyAuditCounter,
    network_fetch_policy_receipt_from_metadata,
    network_fetch_policy_receipt_for_url,
    privacy_audit_counter,
)


def test_network_fetch_policy_receipt_blocks_private_targets_without_raw_url_leaks() -> None:
    receipts = [
        network_fetch_policy_receipt_for_url(
            "https://user:pass@127.0.0.1/private/source.png?api_key=sk-local#frag",
            surface="local_proxy_external_media",
            route_scope="image_edit",
        ),
        network_fetch_policy_receipt_for_url(
            "https://169.254.169.254/latest/meta-data?token=hf_secret_abcdef",
            surface="local_proxy_external_media",
            route_scope="image_edit",
        ),
        network_fetch_policy_receipt_for_url(
            "https://10.0.0.5/private/source.png",
            surface="local_proxy_external_media",
            route_scope="image_edit",
        ),
        network_fetch_policy_receipt_for_url(
            "https://public.example.test/image.png?token=sk-rebind",
            surface="workspace_ingest",
            route_scope="source_import",
            resolved_ip="10.0.0.7",
        ),
    ]

    assert [receipt["action"] for receipt in receipts] == ["blocked"] * 4
    assert [receipt["url_class"] for receipt in receipts] == [
        "loopback",
        "link_local",
        "private",
        "private",
    ]
    assert receipts[-1]["host_class"] == "public"
    assert receipts[-1]["resolved_ip_class"] == "private"
    assert receipts[-1]["blocked_reason"] == "resolved_private_or_loopback_ip"
    payload = json.dumps(receipts, sort_keys=True)
    for raw_fragment in (
        "user",
        "pass",
        "api_key",
        "sk-local",
        "hf_secret",
        "latest/meta-data",
        "private/source",
        "sk-rebind",
        "10.0.0.7",
    ):
        assert raw_fragment not in payload
    assert "[REDACTED_PRIVATE_IP]" in payload


def test_network_fetch_policy_receipt_blocks_ipv4_wrapped_loopback_targets() -> None:
    host_receipt = network_fetch_policy_receipt_for_url(
        "https://[::ffff:127.0.0.1]/private/source.png?token=sk-local",
        surface="local_proxy_external_media",
        route_scope="image_edit",
    )
    resolved_receipt = network_fetch_policy_receipt_for_url(
        "https://public.example.test/private/source.png?token=sk-rebind",
        surface="workspace_ingest",
        route_scope="source_import",
        resolved_ip="::ffff:127.0.0.1",
    )
    compatible_host_receipt = network_fetch_policy_receipt_for_url(
        "https://[::127.0.0.1]/private/source.png?token=sk-compatible",
        surface="local_proxy_external_media",
        route_scope="image_edit",
    )
    compatible_resolved_receipt = network_fetch_policy_receipt_for_url(
        "https://public.example.test/private/source.png?token=sk-compatible-rebind",
        surface="workspace_ingest",
        route_scope="source_import",
        resolved_ip="::127.0.0.1",
    )

    assert host_receipt["action"] == "blocked"
    assert host_receipt["url_class"] == "loopback"
    assert host_receipt["host_class"] == "loopback"
    assert host_receipt["blocked_reason"] == "private_or_loopback_host"
    assert host_receipt["redacted_url"] == "https://[REDACTED_PRIVATE_HOST]/[redacted]"
    assert resolved_receipt["action"] == "blocked"
    assert resolved_receipt["host_class"] == "public"
    assert resolved_receipt["resolved_ip"] == "[REDACTED_PRIVATE_IP]"
    assert resolved_receipt["resolved_ip_class"] == "loopback"
    assert resolved_receipt["blocked_reason"] == "resolved_private_or_loopback_ip"
    assert compatible_host_receipt["action"] == "blocked"
    assert compatible_host_receipt["url_class"] == "loopback"
    assert compatible_host_receipt["host_class"] == "loopback"
    assert compatible_resolved_receipt["action"] == "blocked"
    assert compatible_resolved_receipt["resolved_ip"] == "[REDACTED_PRIVATE_IP]"
    assert compatible_resolved_receipt["resolved_ip_class"] == "loopback"
    payload = json.dumps(
        [
            host_receipt,
            resolved_receipt,
            compatible_host_receipt,
            compatible_resolved_receipt,
        ],
        sort_keys=True,
    )
    assert "::ffff:127.0.0.1" not in payload
    assert "::127.0.0.1" not in payload
    assert "sk-local" not in payload
    assert "sk-rebind" not in payload
    assert "sk-compatible" not in payload


def test_network_fetch_policy_receipt_passes_public_https_and_local_workspace_paths() -> None:
    public_receipt = network_fetch_policy_receipt_for_url(
        " HTTPS://Example.com/source.png?api_key=sk-public#frag ",
        surface="local_proxy_external_media",
        route_scope="image_edit",
        resolved_ip="93.184.216.34",
        redirect_hops_checked=1,
    )
    local_receipt = network_fetch_policy_receipt_for_url(
        "/Users/operator/private/raw-inputs/source.jsonl",
        surface="workspace_ingest",
        route_scope="workspace_preflight",
    )

    assert public_receipt == {
        "schema_version": "melix.network_fetch_policy_receipt.v1",
        "surface": "local_proxy_external_media",
        "route_scope": "image_edit",
        "action": "passed",
        "url_class": "public",
        "url_scheme": "https",
        "host_class": "public",
        "resolved_ip": "93.184.216.34",
        "resolved_ip_class": "public",
        "redirect_hops_checked": 1,
        "blocked_reason": "",
        "redacted_url": "https://example.com/[redacted]",
        "raw_url_included": False,
        "fetch_attempted": False,
    }
    assert local_receipt["action"] == "passed"
    assert local_receipt["url_class"] == "local"
    assert local_receipt["url_scheme"] == "path"
    assert local_receipt["redacted_url"] == "[LOCAL_PATH]"
    assert "/Users/operator/private" not in json.dumps(local_receipt, sort_keys=True)


def test_network_fetch_policy_receipt_metadata_accepts_numeric_boolean_values() -> None:
    receipt = network_fetch_policy_receipt_from_metadata(
        {
            "melix.network_fetch.policy.surface": "local_proxy_external_media",
            "melix.network_fetch.policy.route_scope": "image_edit",
            "melix.network_fetch.policy.action": "passed",
            "melix.network_fetch.policy.url_class": "public",
            "melix.network_fetch.policy.url_scheme": "https",
            "melix.network_fetch.policy.host_class": "public",
            "melix.network_fetch.policy.resolved_ip": "93.184.216.34",
            "melix.network_fetch.policy.resolved_ip_class": "public",
            "melix.network_fetch.policy.redirect_hops_checked": "0",
            "melix.network_fetch.policy.blocked_reason": "",
            "melix.network_fetch.policy.redacted_url": "https://example.com/[redacted]",
            "melix.network_fetch.policy.raw_url_included": 0,
            "melix.network_fetch.policy.fetch_attempted": 1,
        }
    )

    assert receipt
    assert receipt["raw_url_included"] is False
    assert receipt["fetch_attempted"] is True


def test_privacy_audit_counter_counts_blocked_redacted_and_passed_decisions() -> None:
    counter = privacy_audit_counter(
        surface="local_proxy_external_media",
        route_scope="image_edit",
        decisions=("blocked", "redacted", "passed", "redacted"),
    )

    assert isinstance(counter, PrivacyAuditCounter)
    assert counter.to_dict() == {
        "schema_version": "melix.privacy_audit_counter.v1",
        "surface": "local_proxy_external_media",
        "route_scope": "image_edit",
        "blocked_count": 1,
        "redacted_count": 2,
        "passed_count": 1,
        "raw_sensitive_span_count": 0,
    }
