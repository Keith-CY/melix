from __future__ import annotations

import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import overload

from google.protobuf import json_format

from packages.protocol.python.workspace.v1 import workspace_manifest_pb2


WORKSPACE_MANIFEST_SCHEMA_VERSION = "melix.workspace_manifest.v1"

REQUIRED_WORKSPACE_ARTIFACT_TYPES = (
    "WORKSPACE_ARTIFACT_TYPE_RAW_INPUTS",
    "WORKSPACE_ARTIFACT_TYPE_CLEANED_DATA",
    "WORKSPACE_ARTIFACT_TYPE_DATASET_VERSION",
    "WORKSPACE_ARTIFACT_TYPE_ADAPTER",
    "WORKSPACE_ARTIFACT_TYPE_LOG",
    "WORKSPACE_ARTIFACT_TYPE_EXPORT",
    "WORKSPACE_ARTIFACT_TYPE_REPORT",
    "WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE",
)

_REQUIRED_WORKSPACE_ARTIFACT_TYPE_VALUES = {
    workspace_manifest_pb2.WorkspaceArtifactType.Value(name)
    for name in REQUIRED_WORKSPACE_ARTIFACT_TYPES
}


@overload
def validate_workspace_manifest_file(
    path: Path | str,
    *,
    fixture_count: int = 1,
    return_manifest: bool = False,
) -> workspace_manifest_pb2.WorkspaceManifestValidationReport: ...


@overload
def validate_workspace_manifest_file(
    path: Path | str,
    *,
    fixture_count: int = 1,
    return_manifest: bool = True,
) -> tuple[
    workspace_manifest_pb2.WorkspaceManifest,
    workspace_manifest_pb2.WorkspaceManifestValidationReport,
]: ...


def validate_workspace_manifest_file(
    path: Path | str,
    *,
    fixture_count: int = 1,
    return_manifest: bool = False,
) -> (
    workspace_manifest_pb2.WorkspaceManifestValidationReport
    | tuple[
        workspace_manifest_pb2.WorkspaceManifest,
        workspace_manifest_pb2.WorkspaceManifestValidationReport,
    ]
):
    manifest_path = Path(path)
    started = time.perf_counter()
    payload = manifest_path.read_text(encoding="utf-8")
    manifest = workspace_manifest_pb2.WorkspaceManifest()
    errors: list[str] = []

    try:
        json_format.Parse(payload, manifest)
    except json_format.ParseError as exc:
        errors.append(f"parse_error: {exc}")

    if not errors:
        errors.extend(_validate_manifest(manifest))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    report = workspace_manifest_pb2.WorkspaceManifestValidationReport(
        ok=not errors,
        schema_version=manifest.schema_version,
        project_id=manifest.project.project_id,
        redaction_policy_id=manifest.redaction_policy.policy_id,
        redaction_mode=manifest.redaction_policy.mode,
        fixture_count=fixture_count,
        schema_error_count=len(errors),
        manifest_byte_size=manifest_path.stat().st_size,
        manifest_validation_latency_ms=elapsed_ms,
        errors=errors,
    )

    if return_manifest:
        return manifest, report
    return report


def _validate_manifest(manifest: workspace_manifest_pb2.WorkspaceManifest) -> list[str]:
    errors: list[str] = []

    if manifest.schema_version != WORKSPACE_MANIFEST_SCHEMA_VERSION:
        errors.append(
            "schema_version must be "
            f"{WORKSPACE_MANIFEST_SCHEMA_VERSION}, got {manifest.schema_version!r}"
        )
    if not manifest.project.project_id:
        errors.append("project.project_id is required")
    if not manifest.artifact_roots:
        errors.append("artifact_roots must not be empty")
    if not manifest.artifacts:
        errors.append("artifacts must not be empty")
    if not manifest.redaction_policy.policy_id:
        errors.append("redaction_policy.policy_id is required")
    if manifest.redaction_policy.mode == workspace_manifest_pb2.REDACTION_MODE_UNSPECIFIED:
        errors.append("redaction_policy.mode must be specified")

    root_ids = {root.root_id for root in manifest.artifact_roots if root.root_id}
    if len(root_ids) != len(manifest.artifact_roots):
        errors.append("artifact_roots.root_id values must be non-empty and unique")
    for root in manifest.artifact_roots:
        if root.kind == workspace_manifest_pb2.ARTIFACT_ROOT_KIND_UNSPECIFIED:
            errors.append(f"artifact root {root.root_id!r} kind must be specified")
        if not root.path and not root.uri:
            errors.append(f"artifact root {root.root_id!r} path or uri is required")
        if root.path:
            root_path_error = _safe_relative_path_error(root.path, allow_current_dir=True)
            if root_path_error:
                errors.append(
                    f"artifact root {root.root_id!r} path must be a safe relative path: "
                    f"{root_path_error}"
                )

    provenance_ids = {
        ref.provenance_ref_id for ref in manifest.provenance if ref.provenance_ref_id
    }
    if len(provenance_ids) != len(manifest.provenance):
        errors.append("provenance.provenance_ref_id values must be non-empty and unique")

    artifact_ids: set[str] = set()
    artifact_types: set[int] = set()
    for artifact in manifest.artifacts:
        if not artifact.artifact_id:
            errors.append("artifacts.artifact_id is required")
        elif artifact.artifact_id in artifact_ids:
            errors.append(f"duplicate artifact_id: {artifact.artifact_id}")
        artifact_ids.add(artifact.artifact_id)

        if artifact.artifact_type == workspace_manifest_pb2.WORKSPACE_ARTIFACT_TYPE_UNSPECIFIED:
            errors.append(f"artifact {artifact.artifact_id!r} has unspecified artifact_type")
        else:
            artifact_types.add(artifact.artifact_type)

        if artifact.root_id not in root_ids:
            errors.append(
                f"artifact {artifact.artifact_id!r} references unknown root_id "
                f"{artifact.root_id!r}"
            )
        if not artifact.relative_path:
            errors.append(f"artifact {artifact.artifact_id!r} relative_path is required")
        else:
            artifact_path_error = _safe_relative_path_error(
                artifact.relative_path,
                allow_current_dir=False,
            )
            if artifact_path_error:
                errors.append(
                    f"artifact {artifact.artifact_id!r} relative_path must be a safe "
                    f"relative path: {artifact_path_error}"
                )
        for provenance_ref_id in artifact.provenance_ref_ids:
            if provenance_ref_id not in provenance_ids:
                errors.append(
                    f"artifact {artifact.artifact_id!r} references unknown provenance "
                    f"{provenance_ref_id!r}"
                )

    missing_types = _REQUIRED_WORKSPACE_ARTIFACT_TYPE_VALUES - artifact_types
    for missing_type in sorted(missing_types):
        errors.append(
            "missing required artifact_type: "
            f"{workspace_manifest_pb2.WorkspaceArtifactType.Name(missing_type)}"
        )

    return errors


def _safe_relative_path_error(path_value: str, *, allow_current_dir: bool) -> str | None:
    if path_value != path_value.strip():
        return "leading or trailing whitespace is not allowed"
    if not path_value:
        return "path is empty"
    if "\\" in path_value:
        return "backslashes are not allowed"

    windows_path = PureWindowsPath(path_value)
    if windows_path.is_absolute() or windows_path.drive or path_value.startswith("\\\\"):
        return "Windows absolute, drive, or UNC paths are not allowed"

    posix_path = PurePosixPath(path_value)
    if posix_path.is_absolute():
        return "absolute paths are not allowed"
    if not allow_current_dir and path_value == ".":
        return "current-directory artifact paths are not allowed"
    if "//" in path_value:
        return "empty path components are not allowed"
    if any(part in ("", "..") for part in posix_path.parts):
        return "empty or parent-directory path components are not allowed"

    return None
