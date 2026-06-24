from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from google.protobuf import json_format
from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
from worker.productization.export_target_layout import (
    build_export_target_layout,
    _target_relative_path,
)
from worker.productization.export_target_manifest import validate_export_target_manifest_file


EXPORT_SMOKE_RECEIPT_SCHEMA_VERSION = "melix.export_smoke_receipt.v1"
EXPORT_SMOKE_METRICS_SCHEMA_VERSION = "melix.export_smoke.metrics.v1"
DEFAULT_SMOKE_POLICY_ID = "bounded-local-v1"
_DIGEST_CHUNK_BYTES = 1024 * 1024

CHECK_STATUS_PASSED = "passed"
CHECK_STATUS_FAILED = "failed"
CHECK_STATUS_BLOCKED = "blocked"
CHECK_STATUS_WAIVED = "waived"
CHECK_STATUS_NOT_APPLICABLE = "not_applicable"


class SmokeValidationError(RuntimeError):
    failure_code = "runtime_load_failed"


class MissingSmokeFileError(SmokeValidationError):
    failure_code = "missing_required_file"


class DigestMismatchError(SmokeValidationError):
    failure_code = "digest_mismatch"


class RuntimeNotInstalledError(SmokeValidationError):
    failure_code = "runtime_not_installed"


@dataclass(frozen=True, slots=True)
class _CheckResult:
    status: str
    started_at: str
    ended_at: str
    duration_ms: float
    timeout_ms: int
    failure_code: str
    failure_message: str
    evidence_path: str
    diagnostics_receipt_path: str


def run_export_target_smoke(
    manifest_path: Path | str,
    workspace_root: Path | str,
    *,
    available_runtime_binaries: set[str] | None = None,
    operator_id: str = "melix-export-smoke",
    now: float | None = None,
) -> dict[str, object]:
    current_time = time.time() if now is None else now
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    if not validation_report.ok:
        raise ValueError(
            "export target manifest failed validation: "
            + "; ".join(validation_report.errors)
        )

    layout = build_export_target_layout(workspace_root, manifest)
    timeout_ms = int(manifest.verification_policy.timeout_ms)
    preview_limit = int(manifest.verification_policy.preview_byte_limit)
    receipt_path = _target_relative_path(layout, manifest.evidence.smoke_receipt_path)
    diagnostics_receipt_path = manifest.evidence.diagnostics_receipt_path
    preview_path = layout.smoke_dir / "generation-preview.txt"

    metadata_check = _run_measured_check(
        timeout_ms=timeout_ms,
        diagnostics_receipt_path=diagnostics_receipt_path,
        evidence_path=manifest.evidence.smoke_receipt_path,
        now=current_time,
        check=lambda: _check_manifest_files(layout, manifest),
    )
    load_check = _run_required_or_not_applicable_check(
        required=bool(manifest.verification_policy.load_check_required),
        timeout_ms=timeout_ms,
        diagnostics_receipt_path=diagnostics_receipt_path,
        evidence_path=manifest.evidence.smoke_receipt_path,
        now=current_time,
        check=lambda: _check_runtime_preflight(
            manifest,
            available_runtime_binaries=available_runtime_binaries,
        ),
    )
    waiver = _waiver_for_load_failure(
        manifest,
        load_check,
        operator_id=operator_id,
        now=current_time,
    )
    if waiver is not None:
        load_check = _CheckResult(
            status=CHECK_STATUS_WAIVED,
            started_at=load_check.started_at,
            ended_at=load_check.ended_at,
            duration_ms=load_check.duration_ms,
            timeout_ms=load_check.timeout_ms,
            failure_code=load_check.failure_code,
            failure_message=load_check.failure_message,
            evidence_path=load_check.evidence_path,
            diagnostics_receipt_path=load_check.diagnostics_receipt_path,
        )
    generation_check = _run_required_or_not_applicable_check(
        required=bool(manifest.verification_policy.generation_check_required)
        and load_check.status != CHECK_STATUS_WAIVED,
        timeout_ms=timeout_ms,
        diagnostics_receipt_path=diagnostics_receipt_path,
        evidence_path="smoke/generation-preview.txt",
        now=current_time,
        check=lambda: _write_generation_preview(
            preview_path,
            manifest,
            preview_limit=preview_limit,
        ),
    )

    checks = (metadata_check, load_check, generation_check)
    status = _terminal_status(checks)
    preview_payload = _output_preview_payload(preview_path, layout, preview_limit)
    receipt = {
        "schema_version": EXPORT_SMOKE_RECEIPT_SCHEMA_VERSION,
        "export_id": manifest.export_id,
        "target_id": manifest.target_id,
        "target_type": export_target_manifest_pb2.ExportTargetType.Name(manifest.target_type),
        "policy_id": manifest.verification_policy.policy_id or DEFAULT_SMOKE_POLICY_ID,
        "status": status,
        "metadata_check": _check_payload(metadata_check),
        "load_check": _check_payload(load_check),
        "generation_check": _check_payload(generation_check),
        "timeout_policy": {
            "timeout_ms": timeout_ms,
            "preview_byte_limit": preview_limit,
        },
        "output_preview": preview_payload,
        "diagnostics_receipt_path": diagnostics_receipt_path,
        "operator_failures": [
            payload
            for payload in (
                _operator_failure_payload("metadata_check", metadata_check),
                _operator_failure_payload("load_check", load_check),
                _operator_failure_payload("generation_check", generation_check),
            )
            if payload is not None
        ],
        "waiver": waiver or {},
        "metrics": {
            "schema_version": EXPORT_SMOKE_METRICS_SCHEMA_VERSION,
            "metadata_check_latency_ms": metadata_check.duration_ms,
            "load_smoke_latency_ms": load_check.duration_ms,
            "generation_smoke_latency_ms": generation_check.duration_ms,
            "output_preview_byte_count": preview_payload["byte_count"],
            "timeout_count": sum(
                1
                for check in checks
                if check.failure_code == "runtime_timeout"
            ),
            "waiver_count": 1 if waiver is not None else 0,
        },
    }
    _write_json(receipt_path, receipt)
    _update_export_report(layout, manifest, receipt)
    return receipt


def build_smoke_metrics_report(
    manifest_paths: Iterable[Path],
    workspace_root: Path | str,
    *,
    now: float | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    receipts: list[dict[str, object]] = []
    errors: list[str] = []

    from worker.productization.export_target_layout import materialize_export_target_layout

    for manifest_path in manifest_paths:
        export_report = materialize_export_target_layout(
            manifest_path,
            workspace_root,
            create_placeholder_files=True,
            now=now,
        )
        if export_report.get("ok") is not True:
            errors.extend(str(error) for error in export_report.get("errors", []))
            continue
        target_root = Path(workspace_root) / str(export_report["target_root"])
        manifest, validation_report = validate_export_target_manifest_file(
            target_root / "export-target-manifest.json",
            return_manifest=True,
        )
        if not validation_report.ok:
            errors.extend(str(error) for error in validation_report.errors)
            continue
        _write_digest_fixture_files(target_root, manifest)
        try:
            receipts.append(
                run_export_target_smoke(
                    target_root / "export-target-manifest.json",
                    workspace_root,
                    available_runtime_binaries=_fixture_runtime_binaries(manifest),
                    now=now,
                )
            )
        except Exception as exc:  # pragma: no cover - caller needs aggregate errors
            errors.append(str(exc))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    metrics = [receipt["metrics"] for receipt in receipts if isinstance(receipt.get("metrics"), dict)]
    return {
        "schema_version": EXPORT_SMOKE_METRICS_SCHEMA_VERSION,
        "ok": not errors and all(receipt.get("status") in {"passed", "waived"} for receipt in receipts),
        "target_count": len(receipts),
        "smoke_policy_latency_ms": elapsed_ms,
        "metadata_check_latency_ms": sum(float(metric.get("metadata_check_latency_ms", 0)) for metric in metrics),
        "load_smoke_latency_ms": sum(float(metric.get("load_smoke_latency_ms", 0)) for metric in metrics),
        "generation_smoke_latency_ms": sum(float(metric.get("generation_smoke_latency_ms", 0)) for metric in metrics),
        "output_preview_byte_count": sum(int(metric.get("output_preview_byte_count", 0)) for metric in metrics),
        "timeout_count": sum(int(metric.get("timeout_count", 0)) for metric in metrics),
        "waiver_count": sum(int(metric.get("waiver_count", 0)) for metric in metrics),
        "errors": errors,
        "receipts": receipts,
    }


def _run_required_or_not_applicable_check(
    *,
    required: bool,
    timeout_ms: int,
    diagnostics_receipt_path: str,
    evidence_path: str,
    now: float,
    check: Callable[[], None],
) -> _CheckResult:
    if not required:
        timestamp = _timestamp(now)
        return _CheckResult(
            status=CHECK_STATUS_NOT_APPLICABLE,
            started_at=timestamp,
            ended_at=timestamp,
            duration_ms=0.0,
            timeout_ms=timeout_ms,
            failure_code="",
            failure_message="",
            evidence_path="",
            diagnostics_receipt_path="",
        )
    return _run_measured_check(
        timeout_ms=timeout_ms,
        diagnostics_receipt_path=diagnostics_receipt_path,
        evidence_path=evidence_path,
        now=now,
        check=check,
    )


def _run_measured_check(
    *,
    timeout_ms: int,
    diagnostics_receipt_path: str,
    evidence_path: str,
    now: float,
    check: Callable[[], None],
) -> _CheckResult:
    started_monotonic = time.perf_counter()
    started_at = _timestamp(now)
    try:
        check()
    except Exception as exc:
        duration_ms = (time.perf_counter() - started_monotonic) * 1000.0
        return _CheckResult(
            status=CHECK_STATUS_FAILED,
            started_at=started_at,
            ended_at=_timestamp(now + duration_ms / 1000.0),
            duration_ms=duration_ms,
            timeout_ms=timeout_ms,
            failure_code=_failure_code(exc),
            failure_message=_redact_message(str(exc)),
            evidence_path=evidence_path,
            diagnostics_receipt_path=diagnostics_receipt_path,
        )
    duration_ms = (time.perf_counter() - started_monotonic) * 1000.0
    if timeout_ms > 0 and duration_ms > timeout_ms:
        return _CheckResult(
            status=CHECK_STATUS_FAILED,
            started_at=started_at,
            ended_at=_timestamp(now + duration_ms / 1000.0),
            duration_ms=duration_ms,
            timeout_ms=timeout_ms,
            failure_code="runtime_timeout",
            failure_message=f"smoke check exceeded timeout_ms={timeout_ms}",
            evidence_path=evidence_path,
            diagnostics_receipt_path=diagnostics_receipt_path,
        )
    return _CheckResult(
        status=CHECK_STATUS_PASSED,
        started_at=started_at,
        ended_at=_timestamp(now + duration_ms / 1000.0),
        duration_ms=duration_ms,
        timeout_ms=timeout_ms,
        failure_code="",
        failure_message="",
        evidence_path=evidence_path,
        diagnostics_receipt_path="",
    )


def _check_manifest_files(
    layout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> None:
    missing: list[str] = []
    mismatched: list[str] = []
    for row in (*manifest.generated_files, *manifest.required_files):
        if row.path == "export-target-manifest.json":
            continue
        path = _target_relative_path(layout, row.path)
        if not path.is_file():
            missing.append(row.path)
            continue
        digest = _file_sha256(path)
        if digest != row.sha256:
            mismatched.append(row.path)
    if missing:
        raise MissingSmokeFileError(f"missing required smoke files: {', '.join(missing)}")
    if mismatched:
        raise DigestMismatchError(f"digest mismatch for smoke files: {', '.join(mismatched)}")


def _check_runtime_preflight(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    *,
    available_runtime_binaries: set[str] | None,
) -> None:
    if not manifest.runtime_requirements.runtime_name:
        raise RuntimeError("runtime requirement is missing runtime_name")
    if manifest.runtime_requirements.runtime_binary_required:
        binary_name = manifest.runtime_requirements.runtime_binary_name
        if not binary_name:
            raise RuntimeError("runtime binary is required but runtime_binary_name is empty")
        if available_runtime_binaries is not None and binary_name not in available_runtime_binaries:
            raise RuntimeNotInstalledError(f"runtime binary not installed: {binary_name}")


def _waiver_for_load_failure(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    load_check: _CheckResult,
    *,
    operator_id: str,
    now: float,
) -> dict[str, object] | None:
    if load_check.status != CHECK_STATUS_FAILED:
        return None
    if load_check.failure_code != "runtime_not_installed":
        return None
    allowed = set(manifest.verification_policy.allowed_waiver_reasons)
    if (
        not manifest.verification_policy.waiver_allowed
        or export_target_manifest_pb2.EXPORT_WAIVER_REASON_RUNTIME_NOT_INSTALLED not in allowed
    ):
        return None
    reason = "EXPORT_WAIVER_REASON_RUNTIME_NOT_INSTALLED"
    waiver_id = hashlib.sha256(
        f"{manifest.export_id}:{manifest.target_id}:{reason}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "waiver_id": f"waiver-{waiver_id}",
        "target_id": manifest.target_id,
        "target_type": export_target_manifest_pb2.ExportTargetType.Name(manifest.target_type),
        "waived_checks": ["load_check", "generation_check"],
        "reason": reason,
        "operator_id": operator_id,
        "created_at": _timestamp(now),
        "expires_at": "",
        "risk_level": "medium",
        "replacement_evidence": load_check.evidence_path,
        "follow_up_issue": "",
    }


def _write_generation_preview(
    preview_path: Path,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    *,
    preview_limit: int,
) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if preview_limit <= 0:
        preview_path.write_text("", encoding="utf-8")
        return
    text = (
        "Melix export smoke preview\n"
        f"target_id={manifest.target_id}\n"
        f"target_type={export_target_manifest_pb2.ExportTargetType.Name(manifest.target_type)}\n"
        "prompt_fixture=synthetic\n"
    )
    preview_path.write_bytes(text.encode("utf-8")[:preview_limit])


def _output_preview_payload(
    preview_path: Path,
    layout,
    preview_limit: int,
) -> dict[str, object]:
    if not preview_path.exists():
        return {
            "path": "",
            "byte_count": 0,
            "content_type": "text/plain",
            "truncated": False,
            "sha256": "",
        }
    payload = preview_path.read_bytes()
    return {
        "path": preview_path.relative_to(layout.target_root).as_posix(),
        "byte_count": len(payload),
        "content_type": "text/plain",
        "truncated": preview_limit > 0 and len(payload) >= preview_limit,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _terminal_status(checks: Iterable[_CheckResult]) -> str:
    statuses = {check.status for check in checks}
    if CHECK_STATUS_FAILED in statuses:
        return CHECK_STATUS_FAILED
    if CHECK_STATUS_BLOCKED in statuses:
        return CHECK_STATUS_BLOCKED
    if CHECK_STATUS_WAIVED in statuses:
        return CHECK_STATUS_WAIVED
    return CHECK_STATUS_PASSED


def _check_payload(result: _CheckResult) -> dict[str, object]:
    return {
        "status": result.status,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "duration_ms": result.duration_ms,
        "timeout_ms": result.timeout_ms,
        "failure_code": result.failure_code,
        "failure_message": result.failure_message,
        "evidence_path": result.evidence_path,
        "diagnostics_receipt_path": result.diagnostics_receipt_path,
    }


def _operator_failure_payload(
    check_name: str,
    result: _CheckResult,
) -> dict[str, object] | None:
    if result.status != CHECK_STATUS_FAILED:
        return None
    return {
        "check": check_name,
        "failure_code": result.failure_code,
        "failure_message": result.failure_message,
        "diagnostics_receipt_path": result.diagnostics_receipt_path,
    }


def _update_export_report(
    layout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    receipt: dict[str, object],
) -> None:
    report_path = _target_relative_path(layout, manifest.evidence.export_report_path)
    report = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    status = str(receipt.get("status", "failed"))
    terminal_state = {
        CHECK_STATUS_PASSED: "verified",
        CHECK_STATUS_WAIVED: "waived",
        CHECK_STATUS_FAILED: "blocked",
        CHECK_STATUS_BLOCKED: "blocked",
    }.get(status, "blocked")
    report.update(
        {
            "smoke_receipt_path": manifest.evidence.smoke_receipt_path,
            "diagnostics_receipt_path": manifest.evidence.diagnostics_receipt_path
            if status in {CHECK_STATUS_FAILED, CHECK_STATUS_BLOCKED}
            else "",
            "verification_terminal_state": terminal_state,
            "verification_blocker_code": _first_failure_code(receipt),
            "waiver_id": _waiver_id(receipt),
            "ok": terminal_state in {"verified", "waived"},
        }
    )
    _write_json(report_path, report)


def _first_failure_code(receipt: dict[str, object]) -> str:
    failures = receipt.get("operator_failures", [])
    if isinstance(failures, list) and failures:
        first = failures[0]
        if isinstance(first, dict):
            return str(first.get("failure_code", ""))
    return ""


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, SmokeValidationError):
        return exc.failure_code
    return "runtime_load_failed"


def _redact_message(message: str) -> str:
    return message.replace(str(Path.home()), "~")


def _timestamp(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_digest_fixture_files(
    target_root: Path,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> None:
    for row in (*manifest.generated_files, *manifest.required_files):
        if row.path == "export-target-manifest.json":
            continue
        path = target_root / row.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"smoke fixture payload for {row.path}\n".encode("utf-8")
        path.write_bytes(payload)
        row.sha256 = hashlib.sha256(payload).hexdigest()
    (target_root / "export-target-manifest.json").write_text(
        json_format.MessageToJson(
            manifest,
            preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True,
        ),
        encoding="utf-8",
    )


def _fixture_runtime_binaries(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> set[str]:
    if manifest.runtime_requirements.runtime_binary_name:
        return {manifest.runtime_requirements.runtime_binary_name}
    return set()


def _waiver_id(receipt: dict[str, object]) -> str:
    waiver = receipt.get("waiver")
    if isinstance(waiver, dict):
        return str(waiver.get("waiver_id", ""))
    return ""


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
