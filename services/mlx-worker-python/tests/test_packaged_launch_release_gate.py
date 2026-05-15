from __future__ import annotations

from pathlib import Path

from worker.productization.release_gates import (
    build_packaged_launch_evidence,
    collect_install_evidence,
    evaluate_release_gate,
    load_release_gate_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _packaged_launch_policy() -> dict[str, object]:
    policy = load_release_gate_policy(REPO_ROOT / "infra" / "release" / "phase8-release-gate-policy.json")
    return policy["packaged_launch"]


def _passing_packaged_launch_evidence() -> dict[str, object]:
    return {
        "runtime_source": {
            "packaging_target_id": "launch_agents_checkout",
            "packaging_kind": "launch_agents",
            "runtime_layout": "repo_checkout",
        },
        "connect_host_resolution": {
            "bind_host": "0.0.0.0",
            "connect_host": "127.0.0.1",
            "expected_connect_host": "127.0.0.1",
            "service_base_url": "http://127.0.0.1:12436/v1",
            "connect_host_loopback": 1.0,
        },
        "health_probe_reuse": {
            "health_probe_url": "http://127.0.0.1:12436/health",
            "health_probe_url_matches_connect_host": 1.0,
            "reused_client_count": 1.0,
            "time_wait_socket_count": 0.0,
        },
        "installed_app_audit": {
            "audit_schema_version": "melix.packaged_launch.installed_app_audit.v1",
            "install_manifest_path": "/tmp/melix/install-manifest.json",
            "expected_logical_product_identity": "io.melix",
            "logical_product_identity": "io.melix",
            "logical_product_identity_matches": 1.0,
            "audit_passed": 1.0,
        },
    }


def test_collect_install_evidence_records_packaged_launch_audit(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    evidence = collect_install_evidence(repo_root)

    packaged_launch = evidence["packaged_launch"]
    assert packaged_launch["connect_host_resolution"]["bind_host"] == "0.0.0.0"
    assert packaged_launch["connect_host_resolution"]["connect_host"] == "127.0.0.1"
    assert packaged_launch["connect_host_resolution"]["connect_host_loopback"] == 1.0
    assert packaged_launch["health_probe_reuse"]["reused_client_count"] == 1.0
    assert packaged_launch["health_probe_reuse"]["time_wait_socket_count"] == 0.0
    assert packaged_launch["installed_app_audit"]["audit_passed"] == 1.0


def test_build_packaged_launch_evidence_records_loopback_health_and_installed_audit() -> None:
    evidence = build_packaged_launch_evidence(
        {
            "packaging_target_id": "launch_agents_checkout",
            "packaging_kind": "launch_agents",
            "logical_product_identity": "io.melix",
            "runtime_layout": "repo_checkout",
            "http_bind_host": "0.0.0.0",
            "http_connect_host": "127.0.0.1",
            "http_port": 12436,
            "health_probe_url": "http://127.0.0.1:12436/health",
            "service_base_url": "http://127.0.0.1:12436/v1",
            "install_manifest_path": "/tmp/melix/install-manifest.json",
        }
    )

    assert evidence["runtime_source"]["runtime_layout"] == "repo_checkout"
    assert evidence["connect_host_resolution"]["connect_host_loopback"] == 1.0
    assert evidence["health_probe_reuse"]["health_probe_url_matches_connect_host"] == 1.0
    assert evidence["health_probe_reuse"]["reused_client_count"] == 1.0
    assert evidence["health_probe_reuse"]["time_wait_socket_count"] == 0.0
    assert evidence["installed_app_audit"]["audit_passed"] == 1.0


def test_build_packaged_launch_evidence_accepts_ipv6_loopback_urls() -> None:
    evidence = build_packaged_launch_evidence(
        {
            "packaging_target_id": "launch_agents_checkout",
            "packaging_kind": "launch_agents",
            "logical_product_identity": "io.melix",
            "runtime_layout": "repo_checkout",
            "http_bind_host": "::",
            "http_connect_host": "::1",
            "http_port": 12436,
            "health_probe_url": "http://[::1]:12436/health",
            "service_base_url": "http://[::1]:12436/v1",
            "install_manifest_path": "/tmp/melix/install-manifest.json",
        }
    )

    assert evidence["connect_host_resolution"]["expected_connect_host"] == "::1"
    assert evidence["connect_host_resolution"]["connect_host_loopback"] == 1.0
    assert evidence["health_probe_reuse"]["health_probe_url_matches_connect_host"] == 1.0
    assert evidence["installed_app_audit"]["logical_product_identity_matches"] == 1.0
    assert evidence["installed_app_audit"]["audit_passed"] == 1.0


def test_build_packaged_launch_evidence_fails_identity_mismatch_explicitly() -> None:
    evidence = build_packaged_launch_evidence(
        {
            "packaging_target_id": "launch_agents_checkout",
            "packaging_kind": "launch_agents",
            "logical_product_identity": "io.other",
            "runtime_layout": "repo_checkout",
            "http_bind_host": "0.0.0.0",
            "http_connect_host": "127.0.0.1",
            "http_port": 12436,
            "health_probe_url": "http://127.0.0.1:12436/health",
            "service_base_url": "http://127.0.0.1:12436/v1",
            "install_manifest_path": "/tmp/melix/install-manifest.json",
        }
    )

    assert evidence["installed_app_audit"]["expected_logical_product_identity"] == "io.melix"
    assert evidence["installed_app_audit"]["logical_product_identity"] == "io.other"
    assert evidence["installed_app_audit"]["logical_product_identity_matches"] == 0.0
    assert evidence["installed_app_audit"]["audit_passed"] == 0.0


def test_evaluate_release_gate_fails_closed_for_missing_packaged_launch_evidence() -> None:
    failures = evaluate_release_gate(
        {"install": {"checks": {}}},
        {"packaged_launch": _packaged_launch_policy()},
    )

    assert "packaged_launch evidence is missing" in failures


def test_evaluate_release_gate_accepts_top_level_packaged_launch_evidence() -> None:
    failures = evaluate_release_gate(
        {"packaged_launch": _passing_packaged_launch_evidence()},
        {"packaged_launch": _packaged_launch_policy()},
    )

    assert not [failure for failure in failures if "packaged_launch" in failure]


def test_evaluate_release_gate_reports_malformed_packaged_launch_sections() -> None:
    failures = evaluate_release_gate(
        {
            "packaged_launch": {
                "runtime_source": {
                    "packaging_target_id": "",
                    "runtime_layout": "",
                },
                "connect_host_resolution": None,
                "health_probe_reuse": _passing_packaged_launch_evidence()["health_probe_reuse"],
            }
        },
        {"packaged_launch": _packaged_launch_policy()},
    )

    assert "packaged_launch.connect_host_resolution is missing" in failures
    assert "packaged_launch.installed_app_audit is missing" in failures
    assert "packaged_launch.runtime_source.packaging_target_id is missing" in failures
    assert "packaged_launch.runtime_source.runtime_layout is missing" in failures
    assert "connect_host_resolution.connect_host_loopback is missing" in failures
    assert "installed_app_audit.audit_passed is missing" in failures


def test_evaluate_release_gate_reports_packaged_launch_metric_regressions() -> None:
    report = {
        "install": {
            "packaged_launch": {
                **_passing_packaged_launch_evidence(),
                "connect_host_resolution": {
                    **_passing_packaged_launch_evidence()["connect_host_resolution"],
                    "connect_host_loopback": 0.0,
                },
                "health_probe_reuse": {
                    **_passing_packaged_launch_evidence()["health_probe_reuse"],
                    "reused_client_count": 0.0,
                    "time_wait_socket_count": 6.0,
                },
                "installed_app_audit": {
                    **_passing_packaged_launch_evidence()["installed_app_audit"],
                    "audit_passed": 0.0,
                },
            }
        }
    }

    failures = evaluate_release_gate(
        report,
        {"packaged_launch": _packaged_launch_policy()},
    )

    assert "connect_host_resolution.connect_host_loopback=0.00 fell below minimum 1.00" in failures
    assert "health_probe_reuse.reused_client_count=0.00 fell below minimum 1.00" in failures
    assert "health_probe_reuse.time_wait_socket_count=6.00 exceeded maximum 4.00" in failures
    assert "installed_app_audit.audit_passed=0.00 fell below minimum 1.00" in failures
