from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worker.runtime.workspace_paths import WorkspacePathResolution, WorkspacePathResolver


RECEIPT_SCHEMA_VERSION = "melix.workspace_file_tool_receipt.v1"


@dataclass(frozen=True, slots=True)
class WorkspaceFileToolResult:
    tool_name: str
    status: str
    resolution: WorkspacePathResolution
    content: str = ""
    bytes_read: int = 0
    bytes_written: int = 0
    replacement_count: int = 0
    error: str = ""

    @property
    def receipt(self) -> dict[str, object]:
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "tool_name": self.tool_name,
            "status": self.status,
            **self.resolution.receipt_fields(),
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "replacement_count": self.replacement_count,
        }
        if self.error:
            receipt["error"] = self.error
        return receipt


class WorkspaceFileTools:
    def __init__(self, workspace_root: str | Path, *, resolver: WorkspacePathResolver | None = None) -> None:
        self._resolver = resolver or WorkspacePathResolver(workspace_root)

    @property
    def workspace_root(self) -> Path:
        return self._resolver.workspace_root

    def read_text(self, requested_path: str | Path, *, encoding: str = "utf-8") -> WorkspaceFileToolResult:
        resolution = self._resolver.resolve(requested_path, operation="read")
        if not resolution.allowed:
            return _refused_result(tool_name="workspace_file.read", resolution=resolution)

        content = resolution.resolved_path.read_text(encoding=encoding)
        return WorkspaceFileToolResult(
            tool_name="workspace_file.read",
            status="completed",
            resolution=resolution,
            content=content,
            bytes_read=len(content.encode(encoding)),
        )

    def write_text(
        self,
        requested_path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
        create_parent_dirs: bool = False,
    ) -> WorkspaceFileToolResult:
        resolution = self._resolver.resolve(requested_path, operation="write")
        if not resolution.allowed:
            return _refused_result(tool_name="workspace_file.write", resolution=resolution)

        if create_parent_dirs:
            resolution.resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolution.resolved_path.write_text(content, encoding=encoding)
        return WorkspaceFileToolResult(
            tool_name="workspace_file.write",
            status="completed",
            resolution=resolution,
            bytes_written=len(content.encode(encoding)),
        )

    def edit_text(
        self,
        requested_path: str | Path,
        *,
        old_text: str,
        new_text: str,
        expected_replacements: int | None = None,
        encoding: str = "utf-8",
    ) -> WorkspaceFileToolResult:
        resolution = self._resolver.resolve(requested_path, operation="edit")
        if not resolution.allowed:
            return _refused_result(tool_name="workspace_file.edit", resolution=resolution)
        if not old_text:
            return WorkspaceFileToolResult(
                tool_name="workspace_file.edit",
                status="failed",
                resolution=resolution,
                error="workspace edit requires non-empty old_text",
            )

        original = resolution.resolved_path.read_text(encoding=encoding)
        replacement_count = original.count(old_text)
        if expected_replacements is not None and replacement_count != expected_replacements:
            return WorkspaceFileToolResult(
                tool_name="workspace_file.edit",
                status="failed",
                resolution=resolution,
                error=(
                    "workspace edit replacement count mismatch: "
                    f"expected {expected_replacements}, found {replacement_count}"
                ),
            )
        updated = original.replace(old_text, new_text)
        resolution.resolved_path.write_text(updated, encoding=encoding)
        return WorkspaceFileToolResult(
            tool_name="workspace_file.edit",
            status="completed",
            resolution=resolution,
            bytes_read=len(original.encode(encoding)),
            bytes_written=len(updated.encode(encoding)),
            replacement_count=replacement_count,
        )


def _refused_result(*, tool_name: str, resolution: WorkspacePathResolution) -> WorkspaceFileToolResult:
    return WorkspaceFileToolResult(
        tool_name=tool_name,
        status="failed",
        resolution=resolution,
    )
