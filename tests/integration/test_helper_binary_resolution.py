from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.integration.helpers as helpers


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)


def test_swift_product_binary_candidates_tolerates_missing_build_root(tmp_path: Path) -> None:
    build_root = tmp_path / "missing-build"

    assert helpers._swift_product_binary_candidates(build_root, "melix") == [
        build_root / "debug" / "melix"
    ]


def test_resolve_swift_product_binary_uses_scandir_fallback_without_path_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "mlx-text-worker-swift" / ".build"
    stale_flat = build_root / "debug" / "melix-text-worker-swift"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-text-worker-swift"
    _write_executable(stale_flat)
    _write_executable(preferred)
    os.utime(stale_flat, (1, 1))
    os.utime(preferred, (2, 2))

    def fail_glob(self: Path, pattern: str):
        raise AssertionError(f"Path.glob should not be used for Swift binary resolution: {pattern}")

    monkeypatch.setattr(Path, "glob", fail_glob)

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/mlx-text-worker-swift"),
        product_name="melix-text-worker-swift",
    )

    assert resolved == preferred


def test_resolve_scoped_swift_product_binary_uses_scandir_fallback_without_path_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / ".swiftpm" / "build" / "cli"
    preferred = build_root / "x86_64-apple-macosx" / "debug" / "melix"
    _write_executable(preferred)

    monkeypatch.setattr(
        helpers.swift_root_package,
        "swift_package_layout",
        lambda repo_root, scope: SimpleNamespace(scratch_path=build_root),
    )

    def fail_glob(self: Path, pattern: str):
        raise AssertionError(f"Path.glob should not be used for scoped Swift binary resolution: {pattern}")

    monkeypatch.setattr(Path, "glob", fail_glob)

    resolved = helpers.resolve_scoped_swift_product_binary(
        repo_root,
        scope="cli",
        product_name="melix",
    )

    assert resolved == preferred
