from __future__ import annotations

from pathlib import Path

import pytest

from worker.runtime.workspace_file_tools import WorkspaceFileTools


def test_workspace_file_tools_read_write_and_edit_allowed_paths_emit_receipts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = WorkspaceFileTools(workspace)

    write_result = tools.write_text("notes/today.md", "alpha\n", create_parent_dirs=True)
    read_result = tools.read_text("notes/today.md")
    edit_result = tools.edit_text("notes/today.md", old_text="alpha", new_text="beta", expected_replacements=1)

    assert tools.workspace_root == workspace.resolve()
    assert (workspace / "notes" / "today.md").read_text(encoding="utf-8") == "beta\n"
    assert write_result.status == "completed"
    assert write_result.bytes_written == len("alpha\n".encode("utf-8"))
    assert read_result.status == "completed"
    assert read_result.content == "alpha\n"
    assert read_result.bytes_read == len("alpha\n".encode("utf-8"))
    assert edit_result.status == "completed"
    assert edit_result.replacement_count == 1
    assert edit_result.bytes_read == len("alpha\n".encode("utf-8"))
    assert edit_result.bytes_written == len("beta\n".encode("utf-8"))
    assert read_result.receipt == {
        "schema_version": "melix.workspace_file_tool_receipt.v1",
        "tool_name": "workspace_file.read",
        "status": "completed",
        "operation": "read",
        "workspace_root": str(workspace.resolve()),
        "requested_path": "notes/today.md",
        "resolved_path": str(workspace.resolve() / "notes" / "today.md"),
        "allowed": True,
        "refusal_reason": "",
        "bytes_read": len("alpha\n".encode("utf-8")),
        "bytes_written": 0,
        "replacement_count": 0,
    }


def test_workspace_file_tools_rejects_symlink_escapes_before_reading_or_mutating(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
    (workspace / "external").symlink_to(outside)
    tools = WorkspaceFileTools(workspace)

    read_result = tools.read_text("external/secret.txt")
    write_result = tools.write_text("external/secret.txt", "changed\n")
    edit_result = tools.edit_text("external/secret.txt", old_text="secret", new_text="changed")

    assert (outside / "secret.txt").read_text(encoding="utf-8") == "secret\n"
    for result in (read_result, write_result, edit_result):
        assert result.status == "failed"
        assert result.content == ""
        assert result.bytes_read == 0
        assert result.bytes_written == 0
        assert result.replacement_count == 0
        assert result.receipt["allowed"] is False
        assert result.receipt["refusal_reason"] == "path_escapes_workspace"
        assert result.receipt["resolved_path"] == str(outside.resolve() / "secret.txt")


def test_workspace_file_tools_rejects_sensitive_paths_before_parent_creation_or_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = WorkspaceFileTools(workspace)

    result = tools.write_text("config/.env", "TOKEN=secret\n", create_parent_dirs=True)

    assert result.status == "failed"
    assert result.receipt["allowed"] is False
    assert result.receipt["refusal_reason"] == "sensitive_path"
    assert result.bytes_written == 0
    assert not (workspace / "config").exists()


def test_workspace_file_tools_edit_replacement_mismatch_fails_without_mutating_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.txt"
    target.write_text("alpha alpha\n", encoding="utf-8")
    tools = WorkspaceFileTools(workspace)

    result = tools.edit_text("draft.txt", old_text="alpha", new_text="beta", expected_replacements=1)

    assert target.read_text(encoding="utf-8") == "alpha alpha\n"
    assert result.status == "failed"
    assert result.bytes_read == 0
    assert result.bytes_written == 0
    assert result.replacement_count == 0
    assert result.receipt["allowed"] is True
    assert result.receipt["error"] == "workspace edit replacement count mismatch: expected 1, found 2"


def test_workspace_file_tools_edit_zero_matches_fails_without_mutating_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.txt"
    target.write_text("alpha\n", encoding="utf-8")
    tools = WorkspaceFileTools(workspace)

    result = tools.edit_text("draft.txt", old_text="gamma", new_text="delta")

    assert target.read_text(encoding="utf-8") == "alpha\n"
    assert result.status == "failed"
    assert result.bytes_read == 0
    assert result.bytes_written == 0
    assert result.replacement_count == 0
    assert result.receipt["allowed"] is True
    assert result.receipt["error"] == "workspace edit found no occurrences of old_text"


def test_workspace_file_tools_edit_rejects_empty_old_text_without_mutating_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.txt"
    target.write_text("alpha\n", encoding="utf-8")
    tools = WorkspaceFileTools(workspace)

    result = tools.edit_text("draft.txt", old_text="", new_text="beta")

    assert target.read_text(encoding="utf-8") == "alpha\n"
    assert result.status == "failed"
    assert result.receipt["allowed"] is True
    assert result.receipt["error"] == "workspace edit requires non-empty old_text"


def test_workspace_file_tools_read_missing_file_returns_failed_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = WorkspaceFileTools(workspace)

    result = tools.read_text("missing.txt")

    assert result.status == "failed"
    assert result.content == ""
    assert result.bytes_read == 0
    assert result.receipt["allowed"] is True
    assert "No such file or directory" in result.receipt["error"]


def test_workspace_file_tools_write_parent_creation_failure_returns_failed_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    blocker = workspace / "blocker"
    blocker.write_text("not a directory\n", encoding="utf-8")
    tools = WorkspaceFileTools(workspace)

    result = tools.write_text("blocker/output.txt", "content\n", create_parent_dirs=True)

    assert result.status == "failed"
    assert result.bytes_written == 0
    assert result.receipt["allowed"] is True
    assert result.receipt["error"]
    assert blocker.read_text(encoding="utf-8") == "not a directory\n"


def test_workspace_file_tools_edit_missing_file_returns_failed_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = WorkspaceFileTools(workspace)

    result = tools.edit_text("missing.txt", old_text="alpha", new_text="beta")

    assert result.status == "failed"
    assert result.bytes_read == 0
    assert result.bytes_written == 0
    assert result.replacement_count == 0
    assert result.receipt["allowed"] is True
    assert "No such file or directory" in result.receipt["error"]


def test_workspace_file_tools_read_decoding_failure_returns_failed_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "binary.txt"
    target.write_bytes(b"\xff")
    tools = WorkspaceFileTools(workspace)

    result = tools.read_text("binary.txt", encoding="utf-8")

    assert result.status == "failed"
    assert result.bytes_read == 0
    assert result.receipt["allowed"] is True
    assert "codec" in result.receipt["error"]


def test_workspace_file_tools_write_encoding_failure_returns_failed_receipt_without_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = WorkspaceFileTools(workspace)

    result = tools.write_text("latin1.txt", "snowman \u2603", encoding="latin-1")

    assert result.status == "failed"
    assert result.bytes_written == 0
    assert result.receipt["allowed"] is True
    assert "codec" in result.receipt["error"]
    assert not (workspace / "latin1.txt").exists()


def test_workspace_file_tools_write_encoding_failure_returns_failed_receipt_without_parent_dir(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = WorkspaceFileTools(workspace)

    result = tools.write_text("nested/latin1.txt", "snowman \u2603", encoding="latin-1", create_parent_dirs=True)

    assert result.status == "failed"
    assert result.bytes_written == 0
    assert result.receipt["allowed"] is True
    assert "codec" in result.receipt["error"]
    assert not (workspace / "nested").exists()


def test_workspace_file_tools_edit_write_failure_returns_failed_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.txt"
    target.write_text("alpha\n", encoding="utf-8")
    tools = WorkspaceFileTools(workspace)

    def fail_write_bytes(self: Path, data: bytes) -> int:
        if self == target:
            raise OSError("simulated write failure")
        return original_write_bytes(self, data)

    original_write_bytes = Path.write_bytes
    monkeypatch.setattr(Path, "write_bytes", fail_write_bytes)

    result = tools.edit_text("draft.txt", old_text="alpha", new_text="beta", expected_replacements=1)

    assert result.status == "failed"
    assert result.bytes_read == 0
    assert result.bytes_written == 0
    assert result.replacement_count == 0
    assert result.receipt["allowed"] is True
    assert result.receipt["error"] == "simulated write failure"
    assert target.read_text(encoding="utf-8") == "alpha\n"
