#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.macos_app_bundle import (
    adhoc_sign_macos_app_bundle,
    archive_macos_app_bundle,
    elapsed_seconds,
    resolve_python_runtime_root,
    resolve_site_packages_root,
    write_unsigned_macos_app_bundle,
)


_RELEASE_BUILD_CONFIGURATION = "release"
_DEBUG_BUILD_CONFIGURATION = "debug"


def _resolve_built_product(build_root: Path, product_name: str) -> Path | None:
    build_root_path = os.fspath(build_root)
    direct_release_candidate = os.path.join(build_root_path, _RELEASE_BUILD_CONFIGURATION, product_name)
    if os.path.isfile(direct_release_candidate):
        return Path(direct_release_candidate)

    direct_debug_candidate = os.path.join(build_root_path, _DEBUG_BUILD_CONFIGURATION, product_name)
    lex_first_triple_name: str | None = None
    triple_names: list[str] = []
    try:
        with os.scandir(build_root) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                triple_names.append(entry.name)
                if lex_first_triple_name is None or entry.name < lex_first_triple_name:
                    lex_first_triple_name = entry.name
    except OSError:
        if os.path.isfile(direct_debug_candidate):
            return Path(direct_debug_candidate)
        return None

    if lex_first_triple_name is None:
        return None

    lex_first_triple_path = os.path.join(build_root_path, lex_first_triple_name)
    lex_first_release_dir = os.path.join(lex_first_triple_path, _RELEASE_BUILD_CONFIGURATION)
    if os.path.isdir(lex_first_release_dir):
        lex_first_release_candidate = os.path.join(lex_first_release_dir, product_name)
        if os.path.isfile(lex_first_release_candidate):
            return Path(lex_first_release_candidate)

    if os.path.isfile(direct_debug_candidate):
        return Path(direct_debug_candidate)

    lex_first_debug_candidate = os.path.join(
        lex_first_triple_path,
        _DEBUG_BUILD_CONFIGURATION,
        product_name,
    )
    if os.path.isfile(lex_first_debug_candidate):
        return Path(lex_first_debug_candidate)

    remaining_triple_names = [name for name in triple_names if name != lex_first_triple_name]
    remaining_triple_names.sort()
    for triple_name in remaining_triple_names:
        candidate = os.path.join(build_root_path, triple_name, _RELEASE_BUILD_CONFIGURATION, product_name)
        if os.path.isfile(candidate):
            return Path(candidate)

    for triple_name in remaining_triple_names:
        candidate = os.path.join(build_root_path, triple_name, _DEBUG_BUILD_CONFIGURATION, product_name)
        if os.path.isfile(candidate):
            return Path(candidate)
    return None


def resolve_built_binary(repo_root: Path) -> Path:
    candidate = _resolve_built_product(
        repo_root / "apps/macos-menubar/.build",
        "melix-menubar",
    )
    if candidate is not None:
        return candidate
    raise FileNotFoundError(
        "Unable to find built `melix-menubar`. Run `swift build -c release --package-path apps/macos-menubar` first."
    )


def resolve_built_cli_binary(repo_root: Path) -> Path:
    candidate = _resolve_built_product(repo_root / ".build", "melix")
    if candidate is not None:
        return candidate
    raise FileNotFoundError("Unable to find built `melix`. Run `swift build -c release --product melix` first.")


def resolve_built_swift_text_worker_binary(repo_root: Path) -> Path:
    candidate = _resolve_built_product(
        repo_root / "services/mlx-text-worker-swift/.build",
        "melix-text-worker-swift",
    )
    if candidate is not None:
        return candidate
    raise FileNotFoundError(
        "Unable to find built `melix-text-worker-swift`. Run `swift build -c release --package-path services/mlx-text-worker-swift` first."
    )


def _manifest_timings(manifest: dict[str, Any]) -> dict[str, float]:
    """Return mutable manifest timings for tests that stub bundle writing."""
    timings = manifest.get("timings")
    if isinstance(timings, dict):
        return timings
    timings = {}
    manifest["timings"] = timings
    return timings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-path", default="/tmp/Melix.app")
    parser.add_argument("--home-dir", default=str(Path.home()))
    parser.add_argument("--app-name", default="Melix")
    parser.add_argument("--bundle-id", default="io.melix.menubar.preview")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--packaging-target-id", default="macos_app_bundle_preview")
    parser.add_argument("--update-channel-path", default="")
    parser.add_argument("--archive-path", default="")
    parser.add_argument("--python-runtime-root", default="")
    parser.add_argument("--python-site-packages-path", default="")
    parser.add_argument(
        "--icon-source-path",
        default=str(
            ROOT / "apps/macos-menubar/Sources/AppMain/Resources/Branding/MelixAppIcon.icns"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    menubar_binary = resolve_built_binary(repo_root)
    cli_binary = resolve_built_cli_binary(repo_root)
    swift_worker_binary = resolve_built_swift_text_worker_binary(repo_root)
    python_runtime_root = (
        Path(args.python_runtime_root).expanduser().resolve()
        if args.python_runtime_root
        else resolve_python_runtime_root(repo_root / ".venv/bin/python")
    )
    python_site_packages_path = (
        Path(args.python_site_packages_path).expanduser().resolve()
        if args.python_site_packages_path
        else resolve_site_packages_root(repo_root)
    )
    manifest = write_unsigned_macos_app_bundle(
        repo_root=repo_root,
        executable_path=menubar_binary,
        cli_executable_path=cli_binary,
        swift_text_worker_executable_path=swift_worker_binary,
        python_runtime_root=python_runtime_root,
        python_site_packages_path=python_site_packages_path,
        output_path=args.output_path,
        app_name=args.app_name,
        bundle_id=args.bundle_id,
        version=args.version,
        packaging_target_id=args.packaging_target_id,
        update_channel_path=args.update_channel_path or None,
        icon_source_path=args.icon_source_path,
    )
    if args.archive_path:
        started_at = time.perf_counter()
        manifest["adhoc_signed"] = adhoc_sign_macos_app_bundle(manifest["app_path"])
        timings = _manifest_timings(manifest)
        timings["adhoc_sign_seconds"] = elapsed_seconds(started_at)
        started_at = time.perf_counter()
        manifest["archive_path"] = str(
            archive_macos_app_bundle(manifest["app_path"], args.archive_path)
        )
        timings["archive_seconds"] = elapsed_seconds(started_at)
        write_seconds = timings.get("write_total_seconds")
        if write_seconds is None:
            raise KeyError("write_total_seconds missing from bundle manifest timings")
        timings["total_seconds"] = round(
            float(write_seconds)
            + timings["adhoc_sign_seconds"]
            + timings["archive_seconds"],
            6,
        )
    else:
        timings = _manifest_timings(manifest)
        if "write_total_seconds" in timings:
            timings["total_seconds"] = float(timings["write_total_seconds"])

    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(manifest["app_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
