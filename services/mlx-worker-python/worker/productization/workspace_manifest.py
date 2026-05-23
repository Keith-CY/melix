from __future__ import annotations

import os
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, overload

from google.protobuf import json_format

from packages.protocol.python.workspace.v1 import workspace_manifest_pb2


WORKSPACE_MANIFEST_SCHEMA_VERSION = "melix.workspace_manifest.v1"
WORKSPACE_PREFLIGHT_RECEIPT_SCHEMA_VERSION = "melix.workspace_preflight_receipt.v1"
WORKSPACE_MANIFEST_FILENAME = "workspace-manifest.json"
WORKSPACE_PREFLIGHT_RECEIPT_FILENAME = "workspace-preflight-receipt.json"

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


def preflight_workspace(
    manifest_path: Path | str,
    *,
    receipt_output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build an operator-facing workspace preflight receipt."""

    started = time.perf_counter()
    manifest_path = Path(manifest_path)
    workspace_root = manifest_path.parent
    manifest, validation_report = validate_workspace_manifest_file(
        manifest_path,
        return_manifest=True,
    )

    root_ids = {root.root_id for root in manifest.artifact_roots if root.root_id}
    stale_schema_items = _stale_schema_items(manifest)
    unknown_root_items = _unknown_artifact_root_items(manifest, root_ids)
    unsafe_path_items = _unsafe_path_items(manifest)
    resolved_roots = _resolved_safe_roots(workspace_root, manifest, unsafe_path_items)
    missing_root_items = _missing_root_items(manifest, resolved_roots)
    unmanaged_artifact_items = _unmanaged_artifact_items(
        workspace_root=workspace_root,
        manifest_path=manifest_path,
        manifest=manifest,
        resolved_roots=resolved_roots,
        receipt_output_path=Path(receipt_output_path) if receipt_output_path else None,
    )

    migration_started = time.perf_counter()
    migration_check = _migration_check(stale_schema_items)
    migration_validation_latency_ms = (time.perf_counter() - migration_started) * 1000.0

    checks = [
        _check(
            code="WORKSPACE_SCHEMA_STALE",
            status="blocked",
            title="Workspace manifest schema is stale",
            detail=(
                "Workspace manifest schema version "
                f"{manifest.schema_version!r} is not supported by this Melix build. "
                f"Expected {WORKSPACE_MANIFEST_SCHEMA_VERSION!r}."
            ),
            recovery_hint=(
                "Open the workspace with a compatible Melix build or run a future "
                "explicit workspace migration command before starting dataset "
                "preparation or training."
            ),
            items=stale_schema_items,
        )
        if stale_schema_items
        else _check(
            code="WORKSPACE_SCHEMA_CURRENT",
            status="ready",
            title="Workspace manifest schema is current",
            detail=f"Workspace manifest uses {WORKSPACE_MANIFEST_SCHEMA_VERSION}.",
            recovery_hint="No action required.",
        ),
        _check(
            code="WORKSPACE_ROOT_MISSING",
            status="blocked",
            title="Workspace artifact root is missing",
            detail="One or more manifest artifact roots do not exist on disk.",
            recovery_hint=(
                "Create or restore the missing root before starting dataset "
                "preparation or training."
            ),
            items=missing_root_items,
        )
        if missing_root_items
        else _check(
            code="WORKSPACE_ROOT_EXISTS",
            status="ready",
            title="Workspace artifact roots exist",
            detail="All path-backed manifest artifact roots exist on disk.",
            recovery_hint="No action required.",
        ),
        _check(
            code="WORKSPACE_ARTIFACT_ROOT_UNKNOWN",
            status="blocked",
            title="Workspace artifact references an unknown root",
            detail="One or more artifacts reference root ids missing from artifact_roots.",
            recovery_hint=(
                "Add the missing artifact root to workspace-manifest.json or update "
                "the artifact root_id to an existing root."
            ),
            items=unknown_root_items,
        )
        if unknown_root_items
        else _check(
            code="WORKSPACE_ARTIFACT_ROOTS_KNOWN",
            status="ready",
            title="Workspace artifact root references are known",
            detail="All artifacts reference declared artifact roots.",
            recovery_hint="No action required.",
        ),
        _check(
            code="WORKSPACE_PATH_UNSAFE",
            status="blocked",
            title="Workspace manifest contains unsafe paths",
            detail="One or more root or artifact paths escape the workspace contract.",
            recovery_hint=(
                "Rewrite manifest paths as normalized relative paths without parent "
                "directory segments, absolute paths, Windows drives, or backslashes."
            ),
            items=unsafe_path_items,
        )
        if unsafe_path_items
        else _check(
            code="WORKSPACE_PATHS_SAFE",
            status="ready",
            title="Workspace manifest paths are safe",
            detail="All root and artifact paths are safe relative paths.",
            recovery_hint="No action required.",
        ),
        _check(
            code="WORKSPACE_UNMANAGED_ARTIFACT",
            status="blocked",
            title="Workspace contains unmanaged artifacts",
            detail="One or more files under the workspace root are not listed in the manifest.",
            recovery_hint=(
                "Add the artifact to workspace-manifest.json, move it outside the "
                "workspace root, or remove it before starting dataset preparation or "
                "training."
            ),
            items=unmanaged_artifact_items,
        )
        if unmanaged_artifact_items
        else _check(
            code="WORKSPACE_ARTIFACTS_MANAGED",
            status="ready",
            title="Workspace artifacts are managed",
            detail="All files under the workspace root are listed in the manifest.",
            recovery_hint="No action required.",
        ),
        migration_check,
    ]

    unclassified_schema_errors = _unclassified_schema_errors(
        validation_report.errors,
        stale_schema_items=stale_schema_items,
        unsafe_path_items=unsafe_path_items,
        unknown_root_items=unknown_root_items,
    )
    if unclassified_schema_errors:
        checks.append(
            _check(
                code="WORKSPACE_MANIFEST_INVALID",
                status="blocked",
                title="Workspace manifest failed schema validation",
                detail="The manifest has schema errors not covered by workspace preflight checks.",
                recovery_hint=(
                    "Repair workspace-manifest.json so it validates against "
                    f"{WORKSPACE_MANIFEST_SCHEMA_VERSION}."
                ),
                items=[{"error": error} for error in unclassified_schema_errors],
            )
        )

    status = "blocked" if any(check["status"] == "blocked" for check in checks) else "ready"
    metrics = {
        "preflight_latency_ms": (time.perf_counter() - started) * 1000.0,
        "missing_root_count": len(missing_root_items),
        "stale_schema_count": len(stale_schema_items),
        "unsafe_path_count": len(unsafe_path_items),
        "unmanaged_artifact_count": len(unmanaged_artifact_items),
        "migration_validation_latency_ms": migration_validation_latency_ms,
    }

    return {
        "schema_version": WORKSPACE_PREFLIGHT_RECEIPT_SCHEMA_VERSION,
        "status": status,
        "workspace_manifest_schema_version": manifest.schema_version,
        "project_id": manifest.project.project_id,
        "manifest_path": manifest_path.name,
        "checks": checks,
        "metrics": metrics,
    }


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


def _check(
    *,
    code: str,
    status: str,
    title: str,
    detail: str,
    recovery_hint: str,
    items: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "title": title,
        "detail": detail,
        "recovery_hint": recovery_hint,
        "items": items or [],
    }


def _stale_schema_items(
    manifest: workspace_manifest_pb2.WorkspaceManifest,
) -> list[dict[str, str]]:
    if manifest.schema_version == WORKSPACE_MANIFEST_SCHEMA_VERSION:
        return []
    return [
        {
            "found": manifest.schema_version,
            "expected": WORKSPACE_MANIFEST_SCHEMA_VERSION,
        }
    ]


def _unknown_artifact_root_items(
    manifest: workspace_manifest_pb2.WorkspaceManifest,
    root_ids: set[str],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for artifact in manifest.artifacts:
        if artifact.root_id not in root_ids:
            items.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "root_id": artifact.root_id,
                }
            )
    return items


def _unsafe_path_items(
    manifest: workspace_manifest_pb2.WorkspaceManifest,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for root in manifest.artifact_roots:
        if root.path:
            error = _safe_relative_path_error(root.path, allow_current_dir=True)
            if error:
                items.append(
                    {
                        "kind": "artifact_root",
                        "root_id": root.root_id,
                        "path": root.path,
                        "reason": error,
                    }
                )
    for artifact in manifest.artifacts:
        if artifact.relative_path:
            error = _safe_relative_path_error(
                artifact.relative_path,
                allow_current_dir=False,
            )
            if error:
                items.append(
                    {
                        "kind": "artifact",
                        "artifact_id": artifact.artifact_id,
                        "path": artifact.relative_path,
                        "reason": error,
                    }
                )
    return items


def _resolved_safe_roots(
    workspace_root: Path,
    manifest: workspace_manifest_pb2.WorkspaceManifest,
    unsafe_path_items: list[dict[str, str]],
) -> dict[str, Path]:
    unsafe_root_ids = {
        item["root_id"]
        for item in unsafe_path_items
        if item.get("kind") == "artifact_root" and item.get("root_id")
    }
    resolved_roots: dict[str, Path] = {}
    for root in manifest.artifact_roots:
        if not root.root_id or not root.path or root.root_id in unsafe_root_ids:
            continue
        resolved_roots[root.root_id] = (workspace_root / root.path).resolve(strict=False)
    return resolved_roots


def _missing_root_items(
    manifest: workspace_manifest_pb2.WorkspaceManifest,
    resolved_roots: dict[str, Path],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    root_paths = {root.root_id: root.path for root in manifest.artifact_roots}
    for root_id, root_path in sorted(resolved_roots.items()):
        if not root_path.exists():
            items.append(
                {
                    "root_id": root_id,
                    "path": root_paths.get(root_id, ""),
                }
            )
    return items


def _unmanaged_artifact_items(
    *,
    workspace_root: Path,
    manifest_path: Path,
    manifest: workspace_manifest_pb2.WorkspaceManifest,
    resolved_roots: dict[str, Path],
    receipt_output_path: Path | None,
) -> list[dict[str, str]]:
    workspace_roots = [
        resolved_roots[root.root_id]
        for root in manifest.artifact_roots
        if (
            root.kind == workspace_manifest_pb2.ARTIFACT_ROOT_KIND_WORKSPACE
            and root.root_id in resolved_roots
            and resolved_roots[root.root_id].exists()
        )
    ]
    if not workspace_roots:
        return []

    managed_paths = _managed_artifact_paths(manifest, resolved_roots)
    ignored_paths = {
        manifest_path.resolve(strict=False),
        (workspace_root / WORKSPACE_MANIFEST_FILENAME).resolve(strict=False),
        (workspace_root / WORKSPACE_PREFLIGHT_RECEIPT_FILENAME).resolve(strict=False),
    }
    if receipt_output_path is not None:
        ignored_paths.add(receipt_output_path.resolve(strict=False))

    unmanaged: list[dict[str, str]] = []
    for workspace_root_path in sorted(set(workspace_roots)):
        for candidate in _iter_files(workspace_root_path):
            resolved_candidate = candidate.resolve(strict=False)
            if resolved_candidate in ignored_paths or resolved_candidate in managed_paths:
                continue
            unmanaged.append(
                {
                    "path": _relative_posix_path(resolved_candidate, workspace_root_path),
                }
            )
    return sorted(unmanaged, key=lambda item: item["path"])


def _managed_artifact_paths(
    manifest: workspace_manifest_pb2.WorkspaceManifest,
    resolved_roots: dict[str, Path],
) -> set[Path]:
    managed_paths: set[Path] = set()
    for artifact in manifest.artifacts:
        root_path = resolved_roots.get(artifact.root_id)
        if root_path is None or not artifact.relative_path:
            continue
        if _safe_relative_path_error(artifact.relative_path, allow_current_dir=False):
            continue
        managed_paths.add((root_path / artifact.relative_path).resolve(strict=False))
    return managed_paths


def _iter_files(root_path: Path) -> list[Path]:
    files: list[Path] = []
    stack = [root_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scandir:
                entries = sorted(scandir, key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            entry_path = Path(entry.path)
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry_path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry_path)
            except OSError:
                continue
    return files


def _migration_check(stale_schema_items: list[dict[str, str]]) -> dict[str, Any]:
    if not stale_schema_items:
        return _check(
            code="WORKSPACE_MIGRATION_VALIDATED",
            status="ready",
            title="Workspace migration validation passed",
            detail="The workspace manifest does not require migration.",
            recovery_hint="No action required.",
        )
    return _check(
        code="WORKSPACE_MIGRATION_REQUIRED",
        status="blocked",
        title="Workspace requires explicit migration",
        detail=(
            "This Melix build does not migrate workspaces automatically during "
            "preflight."
        ),
        recovery_hint=(
            "Open the workspace with a compatible Melix build or run a future "
            "explicit workspace migration command before proceeding."
        ),
        items=stale_schema_items,
    )


def _unclassified_schema_errors(
    errors: list[str],
    *,
    stale_schema_items: list[dict[str, str]],
    unsafe_path_items: list[dict[str, str]],
    unknown_root_items: list[dict[str, str]],
) -> list[str]:
    ignored_fragments: list[str] = []
    if stale_schema_items:
        ignored_fragments.append("schema_version must be")
    if unsafe_path_items:
        ignored_fragments.append("safe relative path")
    if unknown_root_items:
        ignored_fragments.append("references unknown root_id")
    return [
        error
        for error in errors
        if not any(fragment in error for fragment in ignored_fragments)
    ]


def _relative_posix_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


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
