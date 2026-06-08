from __future__ import annotations

from pathlib import Path

from worker.runtime.workspace_paths import WorkspacePathResolver


def test_workspace_path_resolver_allows_relative_and_absolute_workspace_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes").mkdir()

    resolver = WorkspacePathResolver(workspace)
    relative = resolver.resolve("notes/today.md", operation="read")
    absolute = resolver.resolve(workspace / "notes" / "today.md", operation="write")

    assert resolver.workspace_root == workspace.resolve()
    assert relative.allowed is True
    assert relative.resolved_path == workspace.resolve() / "notes" / "today.md"
    assert relative.refusal_reason == ""
    assert absolute.allowed is True
    assert absolute.resolved_path == relative.resolved_path
    assert absolute.receipt_fields() == {
        "operation": "write",
        "workspace_root": str(workspace.resolve()),
        "requested_path": str(workspace / "notes" / "today.md"),
        "resolved_path": str(workspace.resolve() / "notes" / "today.md"),
        "allowed": True,
        "refusal_reason": "",
    }


def test_workspace_path_resolver_rejects_parent_traversal_and_absolute_escapes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()

    resolver = WorkspacePathResolver(workspace)
    traversal = resolver.resolve("../outside/secret.txt", operation="read")
    absolute = resolver.resolve(outside / "secret.txt", operation="write")

    assert traversal.allowed is False
    assert traversal.refusal_reason == "path_escapes_workspace"
    assert traversal.resolved_path == outside.resolve() / "secret.txt"
    assert absolute.allowed is False
    assert absolute.refusal_reason == "path_escapes_workspace"


def test_workspace_path_resolver_rejects_symlink_escapes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "external").symlink_to(outside)

    resolution = WorkspacePathResolver(workspace).resolve("external/secret.txt", operation="write")

    assert resolution.allowed is False
    assert resolution.refusal_reason == "path_escapes_workspace"
    assert resolution.resolved_path == outside.resolve() / "secret.txt"


def test_workspace_path_resolver_rejects_sensitive_filenames_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    resolution = WorkspacePathResolver(workspace).resolve("config/.env", operation="read")

    assert resolution.allowed is False
    assert resolution.refusal_reason == "sensitive_path"
    assert resolution.receipt_fields()["workspace_root"] == str(workspace.resolve())


def test_workspace_path_resolver_extends_sensitive_filename_defaults(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    resolver = WorkspacePathResolver(workspace, extra_sensitive_filenames=["secrets.toml"])

    assert resolver.resolve("config/secrets.toml", operation="read").refusal_reason == "sensitive_path"
    assert resolver.resolve("config/.env", operation="read").refusal_reason == "sensitive_path"
