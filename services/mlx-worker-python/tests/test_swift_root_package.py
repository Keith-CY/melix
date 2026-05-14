from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "swift_root_package.py"
MODULE_SPEC = importlib.util.spec_from_file_location("swift_root_package", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
swift_root_package = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = swift_root_package
MODULE_SPEC.loader.exec_module(swift_root_package)


def test_swift_package_environment_drops_git_hook_variables(tmp_path: Path) -> None:
    environment = swift_root_package.swift_package_environment(
        tmp_path,
        "macos-menubar",
        base_env={
            "PATH": "/usr/bin",
            "MELIX_HOME": "/tmp/melix-home",
            "GIT_DIR": "/tmp/git-dir",
            "GIT_INDEX_FILE": "/tmp/git-index",
            "GIT_WORK_TREE": "/tmp/git-work-tree",
        },
        toolchain_slug="swift-6-3",
    )

    assert environment["PATH"] == "/usr/bin"
    assert environment["MELIX_HOME"] == "/tmp/melix-home"
    assert environment["HOME"] == str(tmp_path / ".swift-home" / "macos-menubar" / "swift-6-3")
    assert environment["CLANG_MODULE_CACHE_PATH"] == str(
        tmp_path / ".build" / "ModuleCache.noindex" / "macos-menubar" / "swift-6-3"
    )
    assert all(not key.startswith("GIT_") for key in environment)
