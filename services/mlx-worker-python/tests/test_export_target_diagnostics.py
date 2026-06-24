from __future__ import annotations

import json
from pathlib import Path

import pytest
from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
from worker.productization.export_target_diagnostics import (
    CODE_DUPLICATE_TENSOR_NAME,
    CODE_INSUFFICIENT_MEMORY,
    CODE_INVALID_RUNTIME_PATH,
    CODE_MISSING_BINARY,
    CODE_MISSING_BLOB,
    CODE_PERMISSION_DENIED,
    CODE_RUNTIME_LOAD_FAILED,
    CODE_RUNTIME_TIMEOUT,
    CODE_UNKNOWN_FAILURE,
    CODE_UNSUPPORTED_ARCHITECTURE,
    EXPORT_DIAGNOSTICS_RECEIPT_SCHEMA_VERSION,
    build_diagnostic_metrics_report,
    build_export_diagnostics_receipt,
    write_export_diagnostics_receipt,
)
from worker.productization.export_target_layout import (
    build_export_target_layout,
    materialize_export_target_layout,
)
from worker.productization.export_target_manifest import validate_export_target_manifest_file


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/runtime-export/target-manifests.dev.v1"
)


@pytest.mark.parametrize(
    ("expected_code", "log_line"),
    [
        (CODE_RUNTIME_LOAD_FAILED, "runtime load failed while opening model"),
        (CODE_UNSUPPORTED_ARCHITECTURE, "unsupported architecture arm64 required"),
        (CODE_DUPLICATE_TENSOR_NAME, "duplicate tensor name decoder.layers.0"),
        (CODE_MISSING_BLOB, "missing blob sha256-777777 not found"),
        (CODE_MISSING_BINARY, "runtime binary not installed: ollama"),
        (CODE_INVALID_RUNTIME_PATH, "invalid runtime path /tmp/melix/bad-target"),
        (CODE_RUNTIME_TIMEOUT, "generation smoke timed out after deadline exceeded"),
        (CODE_PERMISSION_DENIED, "permission denied opening model weights"),
        (CODE_INSUFFICIENT_MEMORY, "Metal out of memory during load"),
    ],
)
def test_export_target_diagnostics_parser_matches_common_runtime_failures(
    tmp_path: Path,
    expected_code: str,
    log_line: str,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    (target_root / "logs/ollama-create.log").write_text(log_line + "\n", encoding="utf-8")

    receipt = write_export_diagnostics_receipt(layout, manifest)

    receipt_path = target_root / "diagnostics/diagnostics-receipt.json"
    excerpt_path = target_root / "diagnostics/redacted-log-excerpt.txt"
    assert receipt["schema_version"] == EXPORT_DIAGNOSTICS_RECEIPT_SCHEMA_VERSION
    assert receipt["status"] == "matched"
    assert receipt["diagnoses"][0]["code"] == expected_code
    assert receipt["diagnoses"][0]["evidence_path"].startswith(
        "diagnostics/redacted-log-excerpt.txt#line-"
    )
    assert receipt["operator_remedies"][0]["code"] == expected_code
    assert receipt["metrics"]["parsed_failure_count"] >= 1
    assert receipt_path.is_file()
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert excerpt_path.read_text(encoding="utf-8").startswith("[logs/ollama-create.log]")


def test_export_target_diagnostics_redacts_paths_secrets_private_text_and_identity(
    tmp_path: Path,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    log_text = "\n".join(
        [
            f"failed to load model from {target_root / 'artifacts/blobs/sha256-777777'}",
            "Authorization: Bearer sk-testsecret123456",
            "api_key=super-secret-value",
            "proxy=http://user:secret-proxy-pass@example.test",
            "prompt: private customer prompt that must not leave the log",
            "operator_id=chenyu",
        ]
    )
    (target_root / "logs/ollama-create.log").write_text(log_text + "\n", encoding="utf-8")

    receipt = write_export_diagnostics_receipt(layout, manifest)

    excerpt = (target_root / "diagnostics/redacted-log-excerpt.txt").read_text(
        encoding="utf-8"
    )
    encoded_receipt = json.dumps(receipt, sort_keys=True)
    assert str(target_root) not in excerpt
    assert str(target_root) not in encoded_receipt
    assert "<target>/artifacts/blobs/sha256-777777" in excerpt
    assert "sk-testsecret" not in excerpt
    assert "super-secret-value" not in excerpt
    assert "secret-proxy-pass" not in excerpt
    assert "private customer prompt" not in excerpt
    assert "chenyu" not in excerpt
    assert receipt["redaction_summary"]["redacted_absolute_path_count"] >= 1
    assert receipt["redaction_summary"]["redacted_secret_count"] >= 3
    assert receipt["redaction_summary"]["redacted_prompt_or_response_count"] == 1
    assert receipt["redaction_summary"]["redacted_identity_count"] >= 1


def test_export_target_diagnostics_preserves_bounded_unknown_failure_excerpt(
    tmp_path: Path,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "melix_managed/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    manifest.diagnostic_policy.bounded_log_excerpt_bytes = 160

    receipt = write_export_diagnostics_receipt(
        layout,
        manifest,
        failure_checks=[
            {
                "check": "load_check",
                "status": "failed",
                "failure_code": "opaque_runtime_failure",
                "failure_message": "unclassified runtime symptom " + ("detail " * 80),
                "evidence_path": "smoke/smoke-receipt.json",
            }
        ],
    )

    excerpt = (target_root / "diagnostics/redacted-log-excerpt.txt").read_text(
        encoding="utf-8"
    )
    assert receipt["status"] == "unknown"
    assert receipt["diagnoses"][0]["code"] == CODE_UNKNOWN_FAILURE
    assert receipt["bounded_log_excerpt_path"] == "diagnostics/redacted-log-excerpt.txt"
    assert receipt["redaction_summary"]["truncated"] is True
    assert receipt["redaction_summary"]["excerpt_byte_count"] <= 160
    assert excerpt


def test_export_target_diagnostics_not_applicable_without_logs_or_failures(
    tmp_path: Path,
) -> None:
    _target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "mlx_runtime/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)

    receipt = build_export_diagnostics_receipt(layout, manifest)

    assert receipt["status"] == "not_applicable"
    assert receipt["diagnoses"] == []
    assert receipt["operator_remedies"] == []
    assert receipt["bounded_log_excerpt_path"] == ""
    assert receipt["metrics"]["parsed_failure_count"] == 0


def test_export_target_diagnostics_metrics_report_covers_supported_codes(
    tmp_path: Path,
) -> None:
    payload = build_diagnostic_metrics_report(
        sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json")),
        tmp_path,
    )

    assert payload["ok"] is True
    assert payload["target_count"] == 4
    assert payload["diagnostic_parser_coverage"] == 1.0
    assert payload["diagnosis_code_count"] == 9
    assert payload["parsed_failure_count"] >= 9
    assert payload["unknown_failure_count"] == 1
    assert payload["redaction_count"] >= 2
    assert payload["diagnostic_latency_ms"] >= 0


def _materialized_manifest(
    workspace_root: Path,
    manifest_path: Path,
) -> tuple[Path, export_target_manifest_pb2.ExportTargetManifest]:
    export_report = materialize_export_target_layout(
        manifest_path,
        workspace_root,
        create_placeholder_files=True,
    )
    target_root = workspace_root / str(export_report["target_root"])
    manifest, validation_report = validate_export_target_manifest_file(
        target_root / "export-target-manifest.json",
        return_manifest=True,
    )
    assert validation_report.ok is True
    return target_root, manifest
