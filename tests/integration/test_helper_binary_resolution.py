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
    assert helpers._newest_executable_swift_product_binary(build_root, "melix") is None


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


def test_resolve_swift_product_binary_streams_candidates_without_candidate_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "control-plane-swift" / ".build"
    flat = build_root / "debug" / "melix-control-plane"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-control-plane"
    _write_executable(flat)
    _write_executable(preferred)
    os.utime(flat, (3, 3))
    os.utime(preferred, (3, 3))

    def fail_candidate_list(build_root: Path, product_name: str):
        raise AssertionError("binary resolution should not allocate the candidate list")

    monkeypatch.setattr(helpers, "_swift_product_binary_candidates", fail_candidate_list)
    with pytest.raises(AssertionError, match="candidate list"):
        helpers._swift_product_binary_candidates(build_root, "melix-control-plane")

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/control-plane-swift"),
        product_name="melix-control-plane",
    )

    assert resolved == preferred


def test_resolve_swift_product_binary_preserves_tie_breaker_without_path_parts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "control-plane-swift" / ".build"
    flat = build_root / "debug" / "melix-control-plane"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-control-plane"
    _write_executable(flat)
    _write_executable(preferred)
    os.utime(flat, (5, 5))
    os.utime(preferred, (5, 5))

    def fail_parts(self: Path):
        raise AssertionError("binary resolution should not allocate Path.parts per candidate")

    monkeypatch.setattr(Path, "parts", property(fail_parts))

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/control-plane-swift"),
        product_name="melix-control-plane",
    )

    assert resolved == preferred


def test_resolve_swift_product_binary_stats_each_candidate_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "mlx-text-worker-swift" / ".build"
    flat = build_root / "debug" / "melix-text-worker-swift"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-text-worker-swift"
    _write_executable(flat)
    _write_executable(preferred)
    os.utime(flat, (1, 1))
    os.utime(preferred, (2, 2))

    original_stat = helpers.os.stat
    product_stats = 0

    def counting_stat(path: str, *args: object, **kwargs: object):
        nonlocal product_stats
        if os.path.basename(path) == "melix-text-worker-swift":
            product_stats += 1
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(helpers.os, "stat", counting_stat)

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/mlx-text-worker-swift"),
        product_name="melix-text-worker-swift",
    )

    assert resolved == preferred
    assert product_stats == 2
