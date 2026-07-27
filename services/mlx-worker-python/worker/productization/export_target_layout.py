from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Iterable, Literal

from google.protobuf.json_format import MessageToDict

from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
from worker.productization.export_target_manifest import (
    EXPORT_TARGET_MANIFEST_FILENAME,
    validate_export_target_manifest_file,
)


EXPORT_LAYOUT_REPORT_SCHEMA_VERSION = "melix.export_layout_report.v1"
EXPORT_RETENTION_REPORT_SCHEMA_VERSION = "melix.export_retention_report.v1"
EXPORT_TARGET_LAYOUT_METRICS_SCHEMA_VERSION = "melix.export_target_layout.metrics.v1"

RETENTION_DECISION_RETAIN = "retain"
RETENTION_DECISION_CLEANABLE = "cleanable"
RETENTION_DECISION_DELETE_AFTER_TTL = "delete_after_ttl"

_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_TARGET_TYPE_SEGMENTS = {
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_MELIX_MANAGED: "melix_managed",
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_OLLAMA: "ollama",
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_GGUF: "gguf",
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_MLX_RUNTIME: "mlx_runtime",
}
_RETENTION_CLASS_NAMES = {
    value: export_target_manifest_pb2.ExportRetentionClass.Name(value)
    for value in (
        export_target_manifest_pb2.EXPORT_RETENTION_CLASS_REQUIRED,
        export_target_manifest_pb2.EXPORT_RETENTION_CLASS_EVIDENCE,
        export_target_manifest_pb2.EXPORT_RETENTION_CLASS_RUNTIME_LOG,
        export_target_manifest_pb2.EXPORT_RETENTION_CLASS_INTERMEDIATE,
        export_target_manifest_pb2.EXPORT_RETENTION_CLASS_CACHE,
        export_target_manifest_pb2.EXPORT_RETENTION_CLASS_TEMPORARY,
    )
}
_RETAINED_RETENTION_CLASSES = {
    export_target_manifest_pb2.EXPORT_RETENTION_CLASS_REQUIRED,
    export_target_manifest_pb2.EXPORT_RETENTION_CLASS_EVIDENCE,
}
_CLEANABLE_AFTER_SUCCESS_RETENTION_CLASSES = {
    export_target_manifest_pb2.EXPORT_RETENTION_CLASS_INTERMEDIATE,
    export_target_manifest_pb2.EXPORT_RETENTION_CLASS_CACHE,
    export_target_manifest_pb2.EXPORT_RETENTION_CLASS_TEMPORARY,
}
_CLEANABLE_VERIFICATION_STATES = {
    export_target_manifest_pb2.EXPORT_VERIFICATION_STATE_PASSED,
    export_target_manifest_pb2.EXPORT_VERIFICATION_STATE_WAIVED,
}
_CLEANUP_DELETE_DECISIONS = frozenset(
    (RETENTION_DECISION_CLEANABLE, RETENTION_DECISION_DELETE_AFTER_TTL)
)
_EVIDENCE_PATH_FIELDS = (
    "export_report_path",
    "retention_report_path",
    "smoke_receipt_path",
    "diagnostics_receipt_path",
)
_MAX_PATH_SEGMENT_LENGTH = 128


@dataclass(frozen=True, slots=True)
class ExportTargetLayout:
    workspace_root: Path
    target_root: Path
    manifest_path: Path
    export_report_path: Path
    retention_report_path: Path
    artifacts_dir: Path
    intermediates_dir: Path
    logs_dir: Path
    smoke_dir: Path
    diagnostics_dir: Path
    target_type_segment: str


@dataclass(frozen=True, slots=True)
class _FileDecision:
    section: str
    path: str
    role: str
    retention_class: int
    retention_class_name: str
    decision: str
    byte_size: int
    exists: bool
    deleted: bool
    reason: str


def build_export_target_layout(
    workspace_root: Path | str,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> ExportTargetLayout:
    root = Path(workspace_root)
    target_type_segment = _target_type_segment(manifest.target_type)
    target_root = (
        root
        / "exports"
        / "adapters"
        / _path_segment(manifest.adapter_id)
        / _path_segment(manifest.adapter_snapshot)
        / _path_segment(manifest.export_id)
        / "targets"
        / target_type_segment
        / _path_segment(manifest.target_id)
    )
    return ExportTargetLayout(
        workspace_root=root,
        target_root=target_root,
        manifest_path=target_root / EXPORT_TARGET_MANIFEST_FILENAME,
        export_report_path=target_root / manifest.evidence.export_report_path,
        retention_report_path=target_root / manifest.evidence.retention_report_path,
        artifacts_dir=target_root / "artifacts",
        intermediates_dir=target_root / "intermediates",
        logs_dir=target_root / "logs",
        smoke_dir=target_root / "smoke",
        diagnostics_dir=target_root / "diagnostics",
        target_type_segment=target_type_segment,
    )


def materialize_export_target_layout(
    manifest_path: Path | str,
    workspace_root: Path | str,
    *,
    create_placeholder_files: bool = False,
    now: float | None = None,
) -> dict[str, object]:
    export_report, _retention_report = _materialize_export_target_layout_reports(
        manifest_path,
        workspace_root,
        create_placeholder_files=create_placeholder_files,
        now=now,
    )
    return export_report


def _materialize_export_target_layout_reports(
    manifest_path: Path | str,
    workspace_root: Path | str,
    *,
    create_placeholder_files: bool,
    now: float | None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    if not validation_report.ok:
        return {
            "schema_version": EXPORT_LAYOUT_REPORT_SCHEMA_VERSION,
            "ok": False,
            "errors": list(validation_report.errors),
        }, None

    layout = build_export_target_layout(workspace_root, manifest)
    _create_layout_directories(layout)
    source_manifest_path = Path(manifest_path)
    if source_manifest_path.resolve() != layout.manifest_path.resolve():
        shutil.copyfile(source_manifest_path, layout.manifest_path)
    if create_placeholder_files:
        _materialize_placeholder_files(layout, manifest)

    retention_report = build_export_retention_report(
        layout,
        manifest,
        apply_cleanup=False,
        now=now,
    )
    export_report = _build_export_report(
        manifest,
        layout,
        validation_report,
        retention_report,
    )
    _write_json(layout.export_report_path, export_report)
    _write_json(layout.retention_report_path, retention_report)
    return export_report, retention_report


def build_export_retention_report(
    layout: ExportTargetLayout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    *,
    apply_cleanup: bool,
    now: float | None = None,
) -> dict[str, object]:
    current_time = time.time() if now is None else now
    resolved_target_root = layout.target_root.resolve()
    retained_byte_size = 0
    cleanable_byte_size = 0
    deleted_byte_size = 0
    retained_file_count = 0
    cleanable_file_count = 0
    deleted_file_count = 0
    missing_file_count = 0
    retention_decision_count = 0
    decision_payloads: list[dict[str, object]] = []
    for section, rows in _file_sections(manifest):
        for row in rows:
            decision = _decide_file(
                layout,
                manifest,
                section,
                row,
                resolved_target_root=resolved_target_root,
                apply_cleanup=apply_cleanup,
                now=current_time,
            )
            retention_decision_count += 1
            if decision.decision == RETENTION_DECISION_RETAIN:
                retained_byte_size += decision.byte_size
                retained_file_count += 1
            elif decision.decision in _CLEANUP_DELETE_DECISIONS:
                cleanable_byte_size += decision.byte_size
                cleanable_file_count += 1
            if decision.deleted:
                deleted_byte_size += decision.byte_size
                deleted_file_count += 1
            if not decision.exists:
                missing_file_count += 1
            decision_payloads.append(_decision_payload(decision))

    payload = {
        "schema_version": EXPORT_RETENTION_REPORT_SCHEMA_VERSION,
        "export_id": manifest.export_id,
        "target_id": manifest.target_id,
        "target_type": layout.target_type_segment,
        "target_root": _relative_to_workspace(layout, layout.target_root),
        "mode": "apply" if apply_cleanup else "dry_run",
        "retained_byte_size": retained_byte_size,
        "cleanable_byte_size": cleanable_byte_size,
        "deleted_byte_size": deleted_byte_size,
        "retention_decision_count": retention_decision_count,
        "retained_file_count": retained_file_count,
        "cleanable_file_count": cleanable_file_count,
        "deleted_file_count": deleted_file_count,
        "missing_file_count": missing_file_count,
        "decisions": decision_payloads,
    }
    return payload


def cleanup_export_target(
    manifest_path: Path | str,
    workspace_root: Path | str,
    *,
    apply_cleanup: bool = False,
    now: float | None = None,
    output_path: Path | str | None = None,
) -> dict[str, object]:
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    if not validation_report.ok:
        return {
            "schema_version": EXPORT_RETENTION_REPORT_SCHEMA_VERSION,
            "ok": False,
            "errors": list(validation_report.errors),
        }

    layout = build_export_target_layout(workspace_root, manifest)
    report = build_export_retention_report(
        layout,
        manifest,
        apply_cleanup=apply_cleanup,
        now=now,
    )
    report["ok"] = True
    destination = Path(output_path) if output_path is not None else layout.retention_report_path
    _write_json(destination, report)
    return report


def build_layout_metrics_report(
    manifest_paths: Iterable[Path],
    workspace_root: Path | str,
    *,
    create_placeholder_files: bool = True,
    cleanup: Literal["none", "dry-run", "apply"] = "dry-run",
    now: float | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    root = Path(workspace_root)
    export_reports: list[dict[str, object]] = []
    retention_reports: list[dict[str, object]] = []
    errors: list[str] = []
    reports_ok = True
    target_count = 0

    for manifest_path in manifest_paths:
        export_report, retention_report = _materialize_export_target_layout_reports(
            manifest_path,
            root,
            create_placeholder_files=create_placeholder_files,
            now=now,
        )
        target_count += 1
        export_reports.append(export_report)
        if export_report.get("ok") is not True:
            reports_ok = False
            errors.extend(str(error) for error in export_report.get("errors", []))
            continue
        if cleanup == "apply":
            retention_reports.append(
                cleanup_export_target(
                    root / str(export_report["target_root"]) / EXPORT_TARGET_MANIFEST_FILENAME,
                    root,
                    apply_cleanup=True,
                    now=now,
                )
            )
        elif retention_report is not None:
            retention_reports.append(retention_report)
        else:
            retention_report_path = root / str(export_report["retention_report_path"])
            if retention_report_path.is_file():
                retention_reports.append(json.loads(retention_report_path.read_text(encoding="utf-8")))

    retained_byte_size = 0
    cleanable_byte_size = 0
    deleted_byte_size = 0
    retention_decision_count = 0
    deleted_file_count = 0
    missing_file_count = 0
    for report in retention_reports:
        retained_byte_size += int(report.get("retained_byte_size", 0))  # type: ignore[arg-type]
        cleanable_byte_size += int(report.get("cleanable_byte_size", 0))  # type: ignore[arg-type]
        deleted_byte_size += int(report.get("deleted_byte_size", 0))  # type: ignore[arg-type]
        retention_decision_count += int(report.get("retention_decision_count", 0))  # type: ignore[arg-type]
        deleted_file_count += int(report.get("deleted_file_count", 0))  # type: ignore[arg-type]
        missing_file_count += int(report.get("missing_file_count", 0))  # type: ignore[arg-type]

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "schema_version": EXPORT_TARGET_LAYOUT_METRICS_SCHEMA_VERSION,
        "ok": not errors and reports_ok,
        "target_count": target_count,
        "layout_materialization_latency_ms": elapsed_ms,
        "retained_byte_size": retained_byte_size,
        "cleanable_byte_size": cleanable_byte_size,
        "deleted_byte_size": deleted_byte_size,
        "retention_decision_count": retention_decision_count,
        "deleted_file_count": deleted_file_count,
        "missing_file_count": missing_file_count,
        "errors": errors,
        "reports": export_reports,
    }


def _build_export_report(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    layout: ExportTargetLayout,
    validation_report: export_target_manifest_pb2.ExportTargetManifestValidationReport,
    retention_report: dict[str, object],
) -> dict[str, object]:
    manifest_payload = MessageToDict(
        validation_report,
        always_print_fields_with_no_presence=True,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
    )
    declared_file_count = int(
        retention_report.get("retention_decision_count", 0)  # type: ignore[arg-type]
    )
    return {
        "schema_version": EXPORT_LAYOUT_REPORT_SCHEMA_VERSION,
        "ok": True,
        "export_id": manifest.export_id,
        "target_id": manifest.target_id,
        "target_type": layout.target_type_segment,
        "target_root": _relative_to_workspace(layout, layout.target_root),
        "manifest_path": _relative_to_workspace(layout, layout.manifest_path),
        "export_report_path": _relative_to_workspace(layout, layout.export_report_path),
        "retention_report_path": _relative_to_workspace(layout, layout.retention_report_path),
        "artifact_byte_size": int(manifest.metrics.artifact_byte_size),
        "required_byte_size": int(manifest.metrics.required_byte_size),
        "evidence_byte_size": int(manifest.metrics.evidence_byte_size),
        "retained_byte_size": int(retention_report.get("retained_byte_size", 0)),
        "cleanable_byte_size": int(retention_report.get("cleanable_byte_size", 0)),
        "retention_decision_count": int(retention_report.get("retention_decision_count", 0)),
        "retained_file_count": int(retention_report.get("retained_file_count", 0)),
        "cleanable_file_count": int(retention_report.get("cleanable_file_count", 0)),
        "declared_file_count": declared_file_count,
        "layout_directories": {
            "artifacts": _relative_to_workspace(layout, layout.artifacts_dir),
            "intermediates": _relative_to_workspace(layout, layout.intermediates_dir),
            "logs": _relative_to_workspace(layout, layout.logs_dir),
            "smoke": _relative_to_workspace(layout, layout.smoke_dir),
            "diagnostics": _relative_to_workspace(layout, layout.diagnostics_dir),
            "retention": _relative_to_workspace(layout, layout.retention_report_path.parent),
        },
        "manifest_validation": manifest_payload,
    }


def _create_layout_directories(layout: ExportTargetLayout) -> None:
    for directory in (
        layout.target_root,
        layout.artifacts_dir,
        layout.intermediates_dir,
        layout.logs_dir,
        layout.smoke_dir,
        layout.diagnostics_dir,
        layout.retention_report_path.parent,
        layout.export_report_path.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def _materialize_placeholder_files(
    layout: ExportTargetLayout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> None:
    resolved_target_root = layout.target_root.resolve()
    for _section, rows in _file_sections(manifest):
        for row in rows:
            path = _target_relative_path(layout, row.path, resolved_root=resolved_target_root)
            if path == layout.manifest_path:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(_placeholder_bytes(manifest, row))
    for field_name in _EVIDENCE_PATH_FIELDS:
        evidence_path = _target_relative_path(
            layout,
            getattr(manifest.evidence, field_name),
            resolved_root=resolved_target_root,
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        if not evidence_path.exists():
            _write_json(
                evidence_path,
                {
                    "schema_version": "melix.export_placeholder_evidence.v1",
                    "export_id": manifest.export_id,
                    "target_id": manifest.target_id,
                    "field": field_name,
                },
            )


def _placeholder_bytes(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    row: export_target_manifest_pb2.ExportTargetFile,
) -> bytes:
    digest = hashlib.sha256(
        f"{manifest.export_id}:{manifest.target_id}:{row.path}".encode("utf-8")
    ).hexdigest()
    return f"melix export placeholder\n{digest}\n".encode("utf-8")


def _decide_file(
    layout: ExportTargetLayout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    section: str,
    row: export_target_manifest_pb2.ExportTargetFile,
    *,
    resolved_target_root: Path | None = None,
    apply_cleanup: bool,
    now: float,
) -> _FileDecision:
    path = _target_relative_path(layout, row.path, resolved_root=resolved_target_root)
    try:
        path_stat = path.stat()
        exists = True
    except OSError:
        path_stat = None
        exists = False
    decision, reason = _retention_decision(
        manifest,
        row,
        path,
        exists,
        now,
        path_stat=path_stat,
    )
    deleted = False
    if (
        apply_cleanup
        and exists
        and decision in _CLEANUP_DELETE_DECISIONS
    ):
        path.unlink(missing_ok=True)
        deleted = True
        exists = False
    return _FileDecision(
        section=section,
        path=row.path,
        role=export_target_manifest_pb2.ExportTargetFileRole.Name(row.role),
        retention_class=row.retention_class,
        retention_class_name=_RETENTION_CLASS_NAMES.get(row.retention_class, "UNKNOWN"),
        decision=decision,
        byte_size=int(row.byte_size),
        exists=exists,
        deleted=deleted,
        reason=reason,
    )


def _retention_decision(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    row: export_target_manifest_pb2.ExportTargetFile,
    path: Path,
    exists: bool,
    now: float,
    *,
    path_stat: os.stat_result | None = None,
) -> tuple[str, str]:
    if row.retention_class in _RETAINED_RETENTION_CLASSES:
        return RETENTION_DECISION_RETAIN, "required_or_evidence_artifact"
    if row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_RUNTIME_LOG:
        if _runtime_log_ttl_expired(manifest, path, exists, now, path_stat=path_stat):
            return RETENTION_DECISION_DELETE_AFTER_TTL, "runtime_log_ttl_expired"
        return RETENTION_DECISION_RETAIN, "runtime_log_ttl_active"
    if row.retention_class in _CLEANABLE_AFTER_SUCCESS_RETENTION_CLASSES:
        if manifest.verification_status.state in _CLEANABLE_VERIFICATION_STATES:
            return RETENTION_DECISION_CLEANABLE, "verification_complete_or_waived"
        return RETENTION_DECISION_RETAIN, "verification_not_complete"
    return RETENTION_DECISION_RETAIN, "unknown_retention_class_retained"


def _runtime_log_ttl_expired(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    path: Path,
    exists: bool,
    now: float,
    *,
    path_stat: os.stat_result | None = None,
) -> bool:
    ttl_seconds = int(manifest.retention_policy.runtime_log_ttl_seconds)
    if ttl_seconds <= 0:
        return False
    if not exists:
        return False
    try:
        stat_result = path.stat() if path_stat is None else path_stat
        return now - stat_result.st_mtime >= ttl_seconds
    except FileNotFoundError:
        return False


def _decision_payload(decision: _FileDecision) -> dict[str, object]:
    return {
        "section": decision.section,
        "path": decision.path,
        "role": decision.role,
        "retention_class": decision.retention_class_name,
        "decision": decision.decision,
        "byte_size": decision.byte_size,
        "exists": decision.exists,
        "deleted": decision.deleted,
        "reason": decision.reason,
    }


def _file_sections(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> tuple[
    tuple[str, Iterable[export_target_manifest_pb2.ExportTargetFile]],
    tuple[str, Iterable[export_target_manifest_pb2.ExportTargetFile]],
    tuple[str, Iterable[export_target_manifest_pb2.ExportTargetFile]],
]:
    return (
        ("generated_files", manifest.generated_files),
        ("required_files", manifest.required_files),
        ("intermediate_files", manifest.intermediate_files),
    )


def _target_type_segment(target_type: int) -> str:
    try:
        return _TARGET_TYPE_SEGMENTS[target_type]
    except KeyError as exc:  # pragma: no cover - validator guards callers
        raise ValueError(f"unsupported export target type: {target_type}") from exc


def _path_segment(value: str) -> str:
    stripped = value.strip()
    segment = _SEGMENT_PATTERN.sub("-", stripped).strip(".-_")[:_MAX_PATH_SEGMENT_LENGTH]
    return segment or "unnamed"


def _target_relative_path(
    layout: ExportTargetLayout,
    relative_path: str,
    *,
    resolved_root: Path | None = None,
) -> Path:
    if not relative_path:
        raise ValueError("export target file path is empty")
    target_root = layout.target_root.resolve() if resolved_root is None else resolved_root
    path = (target_root / relative_path).resolve()
    if not path.is_relative_to(target_root):
        raise ValueError(f"export target file path escapes target root: {relative_path}")
    return path


def _relative_to_workspace(layout: ExportTargetLayout, path: Path) -> str:
    try:
        return path.relative_to(layout.workspace_root).as_posix()
    except ValueError:  # pragma: no cover - defensive for absolute custom roots
        return path.as_posix()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
