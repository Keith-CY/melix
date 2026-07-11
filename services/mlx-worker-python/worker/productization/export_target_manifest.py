from __future__ import annotations

import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import overload

from google.protobuf import json_format

from packages.protocol.python.workspace.v1 import export_target_manifest_pb2


EXPORT_TARGET_MANIFEST_SCHEMA_VERSION = "melix.export_target_manifest.v1"
EXPORT_TARGET_MANIFEST_FILENAME = "export-target-manifest.json"

REQUIRED_EXPORT_TARGET_TYPES = (
    "EXPORT_TARGET_TYPE_MELIX_MANAGED",
    "EXPORT_TARGET_TYPE_OLLAMA",
    "EXPORT_TARGET_TYPE_GGUF",
    "EXPORT_TARGET_TYPE_MLX_RUNTIME",
)

_TARGET_RUNTIME_BY_TYPE = {
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_MELIX_MANAGED: {"melix"},
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_OLLAMA: {"ollama"},
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_GGUF: {"gguf"},
    export_target_manifest_pb2.EXPORT_TARGET_TYPE_MLX_RUNTIME: {"mlx-lm", "melix-mlx"},
}

_TARGET_NAME_BY_TYPE = {
    value: export_target_manifest_pb2.ExportTargetType.Name(value)
    for value in _TARGET_RUNTIME_BY_TYPE
}
_DERIVED_MODEL_ACTIVATION_MODES = frozenset(
    {
        export_target_manifest_pb2.EXPORT_ACTIVATION_MODE_FUSED_DERIVED_MODEL,
        export_target_manifest_pb2.EXPORT_ACTIVATION_MODE_ADAPTER_BACKED_RUNTIME,
    }
)
_RUNTIME_BINARY_REQUIRED_TARGET_TYPES = frozenset(
    {
        export_target_manifest_pb2.EXPORT_TARGET_TYPE_OLLAMA,
        export_target_manifest_pb2.EXPORT_TARGET_TYPE_MLX_RUNTIME,
    }
)
_LOAD_CHECK_REQUIRED_TARGET_TYPES = frozenset(
    {
        export_target_manifest_pb2.EXPORT_TARGET_TYPE_MELIX_MANAGED,
        export_target_manifest_pb2.EXPORT_TARGET_TYPE_OLLAMA,
        export_target_manifest_pb2.EXPORT_TARGET_TYPE_MLX_RUNTIME,
    }
)
_RUNTIME_NOT_INSTALLED_WAIVER = (
    export_target_manifest_pb2.EXPORT_WAIVER_REASON_RUNTIME_NOT_INSTALLED
)
_RETENTION_DECISION_RETAIN = export_target_manifest_pb2.EXPORT_RETENTION_DECISION_RETAIN
_RETENTION_DECISION_CLEANABLE = export_target_manifest_pb2.EXPORT_RETENTION_DECISION_CLEANABLE
_RETENTION_DECISION_DELETE_AFTER_TTL = (
    export_target_manifest_pb2.EXPORT_RETENTION_DECISION_DELETE_AFTER_TTL
)
_RETENTION_DECISION_DELETE_AFTER_SUCCESS = (
    export_target_manifest_pb2.EXPORT_RETENTION_DECISION_DELETE_AFTER_SUCCESS
)
_RETENTION_DECISION_NAME = export_target_manifest_pb2.ExportRetentionDecision.Name


@overload
def validate_export_target_manifest_file(
    path: Path | str,
    *,
    fixture_count: int = 1,
    return_manifest: bool = False,
) -> export_target_manifest_pb2.ExportTargetManifestValidationReport: ...


@overload
def validate_export_target_manifest_file(
    path: Path | str,
    *,
    fixture_count: int = 1,
    return_manifest: bool = True,
) -> tuple[
    export_target_manifest_pb2.ExportTargetManifest,
    export_target_manifest_pb2.ExportTargetManifestValidationReport,
]: ...


def validate_export_target_manifest_file(
    path: Path | str,
    *,
    fixture_count: int = 1,
    return_manifest: bool = False,
) -> (
    export_target_manifest_pb2.ExportTargetManifestValidationReport
    | tuple[
        export_target_manifest_pb2.ExportTargetManifest,
        export_target_manifest_pb2.ExportTargetManifestValidationReport,
    ]
):
    manifest_path = Path(path)
    started = time.perf_counter()
    payload_bytes = manifest_path.read_bytes()
    payload = payload_bytes.decode("utf-8")
    manifest = export_target_manifest_pb2.ExportTargetManifest()
    errors: list[str] = []

    try:
        json_format.Parse(payload, manifest, ignore_unknown_fields=False)
    except json_format.ParseError as exc:
        errors.append(f"parse_error: {exc}")

    if not errors:
        errors.extend(_validate_manifest(manifest))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    report = export_target_manifest_pb2.ExportTargetManifestValidationReport(
        ok=not errors,
        schema_version=manifest.schema_version,
        export_id=manifest.export_id,
        target_id=manifest.target_id,
        target_type=manifest.target_type,
        fixture_count=fixture_count,
        schema_error_count=len(errors),
        manifest_byte_size=len(payload_bytes),
        manifest_validation_latency_ms=elapsed_ms,
        generated_file_count=len(manifest.generated_files),
        required_file_count=len(manifest.required_files),
        intermediate_file_count=len(manifest.intermediate_files),
        errors=errors,
    )

    if return_manifest:
        return manifest, report
    return report


def _validate_manifest(manifest: export_target_manifest_pb2.ExportTargetManifest) -> list[str]:
    errors: list[str] = []

    if manifest.schema_version != EXPORT_TARGET_MANIFEST_SCHEMA_VERSION:
        errors.append(
            "schema_version must be "
            f"{EXPORT_TARGET_MANIFEST_SCHEMA_VERSION}, got {manifest.schema_version!r}"
        )
    if not manifest.export_id:
        errors.append("export_id is required")
    if not manifest.target_id:
        errors.append("target_id is required")
    if manifest.target_type == export_target_manifest_pb2.EXPORT_TARGET_TYPE_UNSPECIFIED:
        errors.append("target_type must be specified")
    elif manifest.target_type not in _TARGET_RUNTIME_BY_TYPE:
        errors.append(
            "target_type must be one of "
            f"{', '.join(REQUIRED_EXPORT_TARGET_TYPES)}"
        )
    if not manifest.target_runtime:
        errors.append("target_runtime is required")
    elif manifest.target_type in _TARGET_RUNTIME_BY_TYPE:
        allowed_runtimes = _TARGET_RUNTIME_BY_TYPE[manifest.target_type]
        if manifest.target_runtime not in allowed_runtimes:
            errors.append(
                f"target_runtime {manifest.target_runtime!r} is not allowed for "
                f"{_TARGET_NAME_BY_TYPE[manifest.target_type]} "
                f"(expected one of {', '.join(sorted(allowed_runtimes))})"
            )
    if not manifest.workspace_project_id:
        errors.append("workspace_project_id is required")
    _append_path_error(errors, "workspace_manifest_path", manifest.workspace_manifest_path)
    _append_path_error(
        errors,
        "source_adapter_manifest_path",
        manifest.source_adapter_manifest_path,
    )
    if (
        not manifest.source_derived_model_manifest_path
        and manifest.activation_mode in _DERIVED_MODEL_ACTIVATION_MODES
    ):
        errors.append(
            "source_derived_model_manifest_path is required for derived model activation modes"
        )
    if manifest.source_derived_model_manifest_path:
        _append_path_error(
            errors,
            "source_derived_model_manifest_path",
            manifest.source_derived_model_manifest_path,
        )
    _append_path_error(
        errors,
        "source_training_dataset_manifest_path",
        manifest.source_training_dataset_manifest_path,
    )
    if not manifest.base_model_id:
        errors.append("base_model_id is required")
    if not manifest.adapter_id:
        errors.append("adapter_id is required")
    if not manifest.adapter_snapshot:
        errors.append("adapter_snapshot is required")
    if manifest.activation_mode == export_target_manifest_pb2.EXPORT_ACTIVATION_MODE_UNSPECIFIED:
        errors.append("activation_mode must be specified")

    seen_file_paths: set[str] = set()
    _append_file_row_errors(
        errors,
        "generated_files",
        manifest.generated_files,
        seen_file_paths,
    )
    _append_file_row_errors(
        errors,
        "required_files",
        manifest.required_files,
        seen_file_paths,
    )
    _append_file_row_errors(
        errors,
        "intermediate_files",
        manifest.intermediate_files,
        seen_file_paths,
    )
    if not manifest.generated_files:
        errors.append("generated_files must not be empty")
    if not manifest.required_files:
        errors.append("required_files must not be empty")

    errors.extend(_validate_runtime_requirements(manifest))
    errors.extend(_validate_verification_policy(manifest))
    errors.extend(_validate_retention_policy(manifest.retention_policy))
    errors.extend(_validate_evidence_policy(manifest))
    errors.extend(_validate_metrics(manifest))

    return errors


def _append_file_row_errors(
    errors: list[str],
    field_name: str,
    rows: list[export_target_manifest_pb2.ExportTargetFile],
    seen_paths: set[str],
) -> None:
    for index, row in enumerate(rows):
        prefix = f"{field_name}[{index}]"
        if not row.path:
            errors.append(f"{prefix}.path is required")
        else:
            path_error = _safe_relative_path_error(row.path)
            if path_error:
                errors.append(f"{prefix}.path must be a safe relative path: {path_error}")
            if row.path in seen_paths:
                errors.append(f"{prefix}.path duplicates another file row: {row.path}")
            seen_paths.add(row.path)
        if row.role == export_target_manifest_pb2.EXPORT_TARGET_FILE_ROLE_UNSPECIFIED:
            errors.append(f"{prefix}.role must be specified")
        if not row.media_type:
            errors.append(f"{prefix}.media_type is required")
        if not row.sha256:
            errors.append(f"{prefix}.sha256 is required")
        if row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_UNSPECIFIED:
            errors.append(f"{prefix}.retention_class must be specified")
        if not row.source_provenance:
            errors.append(f"{prefix}.source_provenance is required")
        if row.redaction_class == export_target_manifest_pb2.EXPORT_REDACTION_CLASS_UNSPECIFIED:
            errors.append(f"{prefix}.redaction_class must be specified")


def _validate_runtime_requirements(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> list[str]:
    errors: list[str] = []
    runtime = manifest.runtime_requirements
    if not runtime.runtime_name:
        errors.append("runtime_requirements.runtime_name is required")
    elif runtime.runtime_name != manifest.target_runtime:
        errors.append("runtime_requirements.runtime_name must match target_runtime")
    if (
        manifest.target_type in _RUNTIME_BINARY_REQUIRED_TARGET_TYPES
        and not runtime.runtime_binary_required
    ):
        errors.append("runtime_requirements.runtime_binary_required is required for this target type")
    if runtime.runtime_binary_required and not runtime.runtime_binary_name:
        errors.append("runtime_requirements.runtime_binary_name is required when runtime_binary_required is true")
    if not runtime.required_capabilities:
        errors.append("runtime_requirements.required_capabilities must not be empty")
    return errors


def _validate_verification_policy(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> list[str]:
    errors: list[str] = []
    policy = manifest.verification_policy
    status = manifest.verification_status
    if not policy.policy_id:
        errors.append("verification_policy.policy_id is required")
    if not policy.metadata_check_required:
        errors.append("verification_policy.metadata_check_required must be true")
    if (
        manifest.target_type in _LOAD_CHECK_REQUIRED_TARGET_TYPES
        and not policy.load_check_required
    ):
        errors.append("verification_policy.load_check_required must be true for this target type")
    if manifest.target_type == export_target_manifest_pb2.EXPORT_TARGET_TYPE_GGUF:
        if _RUNTIME_NOT_INSTALLED_WAIVER not in policy.allowed_waiver_reasons:
            errors.append("gguf verification_policy must allow runtime_not_installed waivers")
    if status.state == export_target_manifest_pb2.EXPORT_VERIFICATION_STATE_UNSPECIFIED:
        errors.append("verification_status.state must be specified")
    if status.metadata_check == export_target_manifest_pb2.EXPORT_CHECK_STATUS_UNSPECIFIED:
        errors.append("verification_status.metadata_check must be specified")
    if status.load_check == export_target_manifest_pb2.EXPORT_CHECK_STATUS_UNSPECIFIED:
        errors.append("verification_status.load_check must be specified")
    if status.generation_check == export_target_manifest_pb2.EXPORT_CHECK_STATUS_UNSPECIFIED:
        errors.append("verification_status.generation_check must be specified")
    return errors


def _validate_retention_policy(
    policy: export_target_manifest_pb2.ExportRetentionPolicy,
) -> list[str]:
    errors: list[str] = []
    if not policy.policy_id:
        errors.append("retention_policy.policy_id is required")
    if policy.required_default_decision != _RETENTION_DECISION_RETAIN:
        errors.append(
            "retention_policy.required_default_decision must be "
            f"{_RETENTION_DECISION_NAME(_RETENTION_DECISION_RETAIN)}"
        )
    if policy.evidence_default_decision != _RETENTION_DECISION_RETAIN:
        errors.append(
            "retention_policy.evidence_default_decision must be "
            f"{_RETENTION_DECISION_NAME(_RETENTION_DECISION_RETAIN)}"
        )
    if policy.runtime_log_default_decision != _RETENTION_DECISION_DELETE_AFTER_TTL:
        errors.append(
            "retention_policy.runtime_log_default_decision must be "
            f"{_RETENTION_DECISION_NAME(_RETENTION_DECISION_DELETE_AFTER_TTL)}"
        )
    if policy.intermediate_default_decision != _RETENTION_DECISION_CLEANABLE:
        errors.append(
            "retention_policy.intermediate_default_decision must be "
            f"{_RETENTION_DECISION_NAME(_RETENTION_DECISION_CLEANABLE)}"
        )
    if policy.cache_default_decision != _RETENTION_DECISION_CLEANABLE:
        errors.append(
            "retention_policy.cache_default_decision must be "
            f"{_RETENTION_DECISION_NAME(_RETENTION_DECISION_CLEANABLE)}"
        )
    if policy.temporary_default_decision != _RETENTION_DECISION_DELETE_AFTER_SUCCESS:
        errors.append(
            "retention_policy.temporary_default_decision must be "
            f"{_RETENTION_DECISION_NAME(_RETENTION_DECISION_DELETE_AFTER_SUCCESS)}"
        )
    return errors


def _validate_evidence_policy(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> list[str]:
    errors: list[str] = []
    evidence = manifest.evidence
    for field_name, value in (
        ("export_report_path", evidence.export_report_path),
        ("retention_report_path", evidence.retention_report_path),
        ("smoke_receipt_path", evidence.smoke_receipt_path),
        ("diagnostics_receipt_path", evidence.diagnostics_receipt_path),
    ):
        _append_path_error(errors, f"evidence.{field_name}", value)
    if not evidence.redaction_policy_id:
        errors.append("evidence.redaction_policy_id is required")
    return errors


def _validate_metrics(
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> list[str]:
    metrics = manifest.metrics
    errors: list[str] = []
    evidence_bytes = 0
    if metrics.generated_file_count != len(manifest.generated_files):
        errors.append("metrics.generated_file_count must equal generated_files count")
    if metrics.required_file_count != len(manifest.required_files):
        errors.append("metrics.required_file_count must equal required_files count")
    if metrics.intermediate_file_count != len(manifest.intermediate_files):
        errors.append("metrics.intermediate_file_count must equal intermediate_files count")
    generated_bytes = 0
    for row in manifest.generated_files:
        generated_bytes += row.byte_size
        if row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_EVIDENCE:
            evidence_bytes += row.byte_size
    if metrics.artifact_byte_size != generated_bytes:
        errors.append("metrics.artifact_byte_size must equal generated_files byte_size sum")
    required_bytes = 0
    for row in manifest.required_files:
        required_bytes += row.byte_size
        if row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_EVIDENCE:
            evidence_bytes += row.byte_size
    if metrics.required_byte_size != required_bytes:
        errors.append("metrics.required_byte_size must equal required_files byte_size sum")
    for row in manifest.intermediate_files:
        if row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_EVIDENCE:
            evidence_bytes += row.byte_size
    if metrics.evidence_byte_size != evidence_bytes:
        errors.append("metrics.evidence_byte_size must equal evidence file byte_size sum")
    return errors


def _append_path_error(errors: list[str], field_name: str, path_value: str) -> None:
    if not path_value:
        errors.append(f"{field_name} is required")
        return
    path_error = _safe_relative_path_error(path_value)
    if path_error:
        errors.append(f"{field_name} must be a safe relative path: {path_error}")


def _safe_relative_path_error(path_value: str) -> str | None:
    if not path_value:
        return "path is empty"
    if path_value[0].isspace() or path_value[-1].isspace():
        return "leading or trailing whitespace is not allowed"
    if "\\" in path_value:
        return "backslashes are not allowed"

    if (
        len(path_value) >= 2
        and path_value[1] == ":"
        and path_value[0].isascii()
        and path_value[0].isalpha()
    ) or path_value.startswith("//"):
        return "Windows absolute, drive, or UNC paths are not allowed"

    if path_value[0] == "/":
        return "absolute paths are not allowed"
    if path_value == ".":
        return "current-directory paths are not allowed"
    if "//" in path_value:
        return "empty path components are not allowed"
    if _contains_parent_path_component(path_value):
        return "empty or parent-directory path components are not allowed"
    return None


def _contains_parent_path_component(path_value: str) -> bool:
    if ".." not in path_value:
        return False
    start = 0
    while True:
        index = path_value.find("..", start)
        if index < 0:
            return False
        before_component = index == 0 or path_value[index - 1] == "/"
        after_index = index + 2
        after_component = after_index == len(path_value) or path_value[after_index] == "/"
        if before_component and after_component:
            return True
        start = after_index
