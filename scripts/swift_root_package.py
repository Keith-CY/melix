from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class SwiftPackageLayout:
    home: Path
    module_cache_path: Path
    scratch_path: Path


RootPackageSwiftLayout = SwiftPackageLayout


def _slugify_toolchain_version(version_output: str) -> str:
    first_line = next((line.strip() for line in version_output.splitlines() if line.strip()), "")
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", first_line).strip("-").lower()
    return normalized or "swift-unknown"


@lru_cache(maxsize=1)
def current_swift_toolchain_slug() -> str:
    completed = subprocess.run(
        ["xcrun", "swift", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    return _slugify_toolchain_version(completed.stdout or completed.stderr)


def _slugify_scope(scope: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", scope).strip("-").lower()
    return normalized or "swift-package"


def swift_package_layout(
    repo_root: Path,
    scope: str,
    *,
    toolchain_slug: str | None = None,
) -> SwiftPackageLayout:
    safe_scope = _slugify_scope(scope)
    slug = toolchain_slug or current_swift_toolchain_slug()
    return SwiftPackageLayout(
        home=repo_root / ".swift-home" / safe_scope / slug,
        module_cache_path=repo_root / ".build" / "ModuleCache.noindex" / safe_scope / slug,
        scratch_path=repo_root / ".build" / safe_scope / slug,
    )


def root_package_swift_layout(
    repo_root: Path,
    *,
    toolchain_slug: str | None = None,
) -> RootPackageSwiftLayout:
    return swift_package_layout(
        repo_root,
        "root-package",
        toolchain_slug=toolchain_slug,
    )


def swift_package_environment(
    repo_root: Path,
    scope: str,
    *,
    base_env: dict[str, str] | None = None,
    toolchain_slug: str | None = None,
) -> dict[str, str]:
    layout = swift_package_layout(
        repo_root,
        scope,
        toolchain_slug=toolchain_slug,
    )
    layout.home.mkdir(parents=True, exist_ok=True)
    layout.module_cache_path.mkdir(parents=True, exist_ok=True)
    layout.scratch_path.mkdir(parents=True, exist_ok=True)

    environment = dict(base_env or os.environ.copy())
    environment["HOME"] = str(layout.home)
    environment["CLANG_MODULE_CACHE_PATH"] = str(layout.module_cache_path)
    return environment


def root_package_swift_environment(
    repo_root: Path,
    *,
    base_env: dict[str, str] | None = None,
    toolchain_slug: str | None = None,
) -> dict[str, str]:
    return swift_package_environment(
        repo_root,
        "root-package",
        base_env=base_env,
        toolchain_slug=toolchain_slug,
    )


def swift_package_command(
    package_root: Path,
    repo_root: Path,
    scope: str,
    subcommand: str,
    arguments: list[str],
    *,
    toolchain_slug: str | None = None,
) -> list[str]:
    layout = swift_package_layout(
        repo_root,
        scope,
        toolchain_slug=toolchain_slug,
    )
    return [
        "xcrun",
        "swift",
        subcommand,
        "--package-path",
        str(package_root),
        "--scratch-path",
        str(layout.scratch_path),
        *arguments,
    ]


def root_package_swift_command(
    repo_root: Path,
    subcommand: str,
    arguments: list[str],
    *,
    toolchain_slug: str | None = None,
) -> list[str]:
    return swift_package_command(
        repo_root,
        repo_root,
        "root-package",
        subcommand,
        arguments,
        toolchain_slug=toolchain_slug,
    )
