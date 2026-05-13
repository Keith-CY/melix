from __future__ import annotations

from pathlib import Path

import pytest

import tests.integration.helpers as helpers


def _stack() -> helpers.LiveMelixStack:
    return helpers.LiveMelixStack.__new__(helpers.LiveMelixStack)


def test_remove_tree_uses_os_walk_without_rglob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-state"
    nested = root / "state" / "sessions"
    nested.mkdir(parents=True)
    (root / "gateway.json").write_text("{}", encoding="utf-8")
    (nested / "session.json").write_text("{}", encoding="utf-8")

    def fail_rglob(self: Path, pattern: str):
        raise AssertionError(f"Path.rglob should not be used for runtime cleanup: {pattern}")

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    _stack()._remove_tree(root)

    assert not root.exists()


def test_remove_tree_removes_directory_symlink_without_following_target(tmp_path: Path) -> None:
    root = tmp_path / "runtime-state"
    target = tmp_path / "shared-target"
    target.mkdir()
    (target / "preserved.txt").write_text("preserve", encoding="utf-8")
    root.mkdir()
    (root / "linked-dir").symlink_to(target, target_is_directory=True)

    _stack()._remove_tree(root)

    assert not root.exists()
    assert (target / "preserved.txt").read_text(encoding="utf-8") == "preserve"


def test_remove_tree_tolerates_missing_root(tmp_path: Path) -> None:
    _stack()._remove_tree(tmp_path / "missing")


def test_remove_tree_ignores_disappearing_file_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-state"
    root.mkdir()
    disappearing = root / "stale.json"
    disappearing.write_text("{}", encoding="utf-8")
    original_unlink = helpers.os.unlink

    def tracked_unlink(path: str) -> None:
        if Path(path).name == "stale.json":
            original_unlink(path)
            raise FileNotFoundError(path)
        original_unlink(path)

    monkeypatch.setattr(helpers.os, "unlink", tracked_unlink)

    _stack()._remove_tree(root)

    assert not root.exists()


def test_remove_tree_ignores_disappearing_directory_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-state"
    target = tmp_path / "shared-target"
    target.mkdir()
    root.mkdir()
    link = root / "linked-dir"
    link.symlink_to(target, target_is_directory=True)
    original_unlink = helpers.os.unlink

    def tracked_unlink(path: str) -> None:
        if Path(path).name == "linked-dir":
            original_unlink(path)
            raise FileNotFoundError(path)
        original_unlink(path)

    monkeypatch.setattr(helpers.os, "unlink", tracked_unlink)

    _stack()._remove_tree(root)

    assert not root.exists()
    assert target.exists()
