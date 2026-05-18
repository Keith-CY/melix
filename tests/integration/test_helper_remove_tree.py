from __future__ import annotations

from pathlib import Path

import pytest

import tests.integration.helpers as helpers


def _stack() -> helpers.LiveMelixStack:
    return helpers.LiveMelixStack.__new__(helpers.LiveMelixStack)


def test_remove_tree_uses_scandir_without_tree_materialization(
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

    def fail_os_walk(*args: object, **kwargs: object):  # pragma: no cover - must never be called
        raise AssertionError(f"os.walk should not be used for runtime cleanup: {args!r} {kwargs!r}")

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    monkeypatch.setattr(helpers.os, "walk", fail_os_walk)

    _stack()._remove_tree(root)

    assert not root.exists()


def test_remove_tree_skips_initial_path_exists_stat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-state"
    nested = root / "state"
    nested.mkdir(parents=True)
    (nested / "session.json").write_text("{}", encoding="utf-8")

    def fail_exists(self: Path):  # pragma: no cover - exercised only on regression
        raise AssertionError(f"Path.exists should not be used before cleanup scan: {self}")

    monkeypatch.setattr(Path, "exists", fail_exists)

    _stack()._remove_tree(root)

    assert not root.is_dir()


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


def test_remove_tree_ignores_disappearing_directory_before_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-state"
    nested = root / "state"
    nested.mkdir(parents=True)
    (nested / "session.json").write_text("{}", encoding="utf-8")
    original_scandir = helpers.os.scandir
    original_rmdir = helpers.os.rmdir

    def tracked_scandir(path: str):
        if Path(path).name == "state":
            for child in Path(path).iterdir():
                child.unlink()
            original_rmdir(path)
            raise FileNotFoundError(path)
        return original_scandir(path)

    monkeypatch.setattr(helpers.os, "scandir", tracked_scandir)

    _stack()._remove_tree(root)

    assert not root.exists()


def test_remove_tree_ignores_disappearing_directory_before_final_rmdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime-state"
    nested = root / "state"
    nested.mkdir(parents=True)
    (nested / "session.json").write_text("{}", encoding="utf-8")
    original_rmdir = helpers.os.rmdir

    def tracked_rmdir(path: str) -> None:
        if Path(path).name == "state":
            original_rmdir(path)
            raise FileNotFoundError(path)
        original_rmdir(path)

    monkeypatch.setattr(helpers.os, "rmdir", tracked_rmdir)

    _stack()._remove_tree(root)

    assert not root.exists()


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
