#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
from scripts.dev_up import (
    SWIFT_MLX_METALLIB_PATH_ENV,
    compatible_mlx_metal_versions_for_swift_mlx,
    read_mlx_metal_dist_info_version,
    resolve_local_mlx_metallib,
)


_RELEASE_BUILD_CONFIGURATION = "release"
_DEBUG_BUILD_CONFIGURATION = "debug"


def _resolve_built_product(build_root: Path, product_name: str) -> Path | None:
    is_dir = os.path.isdir
    is_file = os.path.isfile
    join = os.path.join
    path_type = Path

    build_root_path = os.fspath(build_root)
    direct_release_candidate = join(build_root_path, _RELEASE_BUILD_CONFIGURATION, product_name)
    if is_file(direct_release_candidate):
        return path_type(direct_release_candidate)

    direct_debug_candidate = join(build_root_path, _DEBUG_BUILD_CONFIGURATION, product_name)
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
                triple_name = entry.name
                triple_names.append(triple_name)
                if lex_first_triple_name is None or triple_name < lex_first_triple_name:
                    lex_first_triple_name = triple_name
    except OSError:
        if is_file(direct_debug_candidate):
            return path_type(direct_debug_candidate)
        return None

    if lex_first_triple_name is None:
        return None

    lex_first_triple_path = join(build_root_path, lex_first_triple_name)
    lex_first_release_dir = join(lex_first_triple_path, _RELEASE_BUILD_CONFIGURATION)
    if is_dir(lex_first_release_dir):
        lex_first_release_candidate = join(lex_first_release_dir, product_name)
        if is_file(lex_first_release_candidate):
            return path_type(lex_first_release_candidate)

    if is_file(direct_debug_candidate):
        return path_type(direct_debug_candidate)

    lex_first_debug_candidate = join(
        lex_first_triple_path,
        _DEBUG_BUILD_CONFIGURATION,
        product_name,
    )
    if is_file(lex_first_debug_candidate):
        return path_type(lex_first_debug_candidate)

    remaining_triple_names = sorted(name for name in triple_names if name != lex_first_triple_name)
    remaining_debug_candidate: str | None = None
    build_root_prefix = build_root_path + os.sep
    release_candidate_suffix = os.sep + _RELEASE_BUILD_CONFIGURATION + os.sep + product_name
    debug_candidate_suffix = os.sep + _DEBUG_BUILD_CONFIGURATION + os.sep + product_name
    for triple_name in remaining_triple_names:
        triple_candidate_prefix = build_root_prefix + triple_name
        candidate = triple_candidate_prefix + release_candidate_suffix
        if is_file(candidate):
            return path_type(candidate)
        if remaining_debug_candidate is None:
            candidate = triple_candidate_prefix + debug_candidate_suffix
            if is_file(candidate):
                remaining_debug_candidate = candidate

    if remaining_debug_candidate is not None:
        return path_type(remaining_debug_candidate)
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


def resolve_built_control_plane_binary(repo_root: Path) -> Path:
    candidate = _resolve_built_product(
        repo_root / "services/control-plane-swift/.build",
        "melix-control-plane",
    )
    if candidate is not None:
        return candidate
    raise FileNotFoundError(
        "Unable to find built `melix-control-plane`. Run `swift build -c release "
        "--package-path services/control-plane-swift --product melix-control-plane` first."
    )


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


def resolve_swift_mlx_metallib(
    repo_root: Path,
    configured_path: str | Path | None = None,
) -> tuple[Path, str]:
    if configured_path is not None and str(configured_path).strip():
        metallib_path = Path(configured_path).expanduser().resolve()
        if not metallib_path.is_file():
            raise FileNotFoundError(f"{SWIFT_MLX_METALLIB_PATH_ENV} does not point to a file: {metallib_path}")
    else:
        metallib_path = resolve_local_mlx_metallib(
            repo_root,
            uv_cache_dir=repo_root / ".uv-cache",
        )
        if metallib_path is None:
            raise FileNotFoundError(
                "No compatible Swift MLX metallib was found for the packaged text worker. "
                f"Set {SWIFT_MLX_METALLIB_PATH_ENV} or pass --swift-mlx-metallib-path."
            )

    metallib_version = read_mlx_metal_dist_info_version(metallib_path)
    if metallib_version is None:
        raise RuntimeError(
            "Unable to determine the mlx_metal version for the packaged Swift MLX metallib: "
            f"{metallib_path}"
        )

    compatible_versions = compatible_mlx_metal_versions_for_swift_mlx(repo_root)
    if not compatible_versions:
        raise RuntimeError(
            "Unable to prove Swift MLX metallib compatibility from the vendored Swift MLX core "
            f"for {repo_root}."
        )
    if metallib_version not in compatible_versions:
        compatible_display = " or ".join(compatible_versions)
        raise RuntimeError(
            f"Incompatible Swift MLX metallib {metallib_version} at {metallib_path}; "
            f"the packaged Swift worker requires mlx_metal {compatible_display}."
        )
    return metallib_path, metallib_version


def _manifest_timings(manifest: dict[str, Any]) -> dict[str, float]:
    """Return mutable manifest timings for tests that stub bundle writing."""
    timings = manifest.get("timings")
    if isinstance(timings, dict):
        return timings
    timings = {}
    manifest["timings"] = timings
    return timings


def verify_archived_macos_app_bundle(
    archive_path: str | Path,
    *,
    expected_app_name: str,
) -> None:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Packaged macOS app archive is missing: {archive}")

    normalized_app_name = Path(expected_app_name).name
    if normalized_app_name != expected_app_name or not normalized_app_name.endswith(".app"):
        raise ValueError(f"Expected archived app name must be a single .app name: {expected_app_name}")

    codesign = shutil.which("codesign")
    if codesign is None:
        raise RuntimeError("codesign is required to verify an archived macOS app bundle")

    environment = dict(os.environ)
    environment["COPYFILE_DISABLE"] = "1"
    with tempfile.TemporaryDirectory(prefix="melix-archive-verify-") as extraction_dir:
        extraction_root = Path(extraction_dir)
        try:
            subprocess.run(
                [
                    "/usr/bin/ditto",
                    "-x",
                    "-k",
                    os.fspath(archive),
                    os.fspath(extraction_root),
                ],
                check=True,
                env=environment,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Packaged macOS app archive extraction failed: {archive}") from error

        extracted_app = (extraction_root / normalized_app_name).resolve()
        if not extracted_app.is_dir():
            raise RuntimeError(f"Archived macOS app bundle is missing after extraction: {extracted_app}")

        metallib_link = extracted_app / "Contents/Resources/mlx.metallib"
        if not metallib_link.is_symlink():
            raise RuntimeError(
                "Archived Swift MLX metallib entry must remain a symbolic link: "
                f"{metallib_link}"
            )
        metallib_target = metallib_link.readlink()
        if metallib_target.is_absolute():
            raise RuntimeError(
                "Archived Swift MLX metallib link target must be relative: "
                f"{metallib_target}"
            )
        expected_metallib_target = Path("swift-mlx/mlx.metallib")
        if metallib_target != expected_metallib_target:
            raise RuntimeError(
                "Archived Swift MLX metallib link target is unexpected: "
                f"{metallib_target}; expected {expected_metallib_target}"
            )
        if not (metallib_link.parent / metallib_target).is_file():
            raise RuntimeError(
                "Archived Swift MLX metallib link target is missing: "
                f"{metallib_link.parent / metallib_target}"
            )

        try:
            subprocess.run(
                [
                    codesign,
                    "--verify",
                    "--deep",
                    "--strict",
                    "--verbose=4",
                    os.fspath(extracted_app),
                ],
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"Archived macOS app deep signature verification failed: {extracted_app}"
            ) from error


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
        "--swift-mlx-metallib-path",
        default=os.environ.get(SWIFT_MLX_METALLIB_PATH_ENV, ""),
    )
    parser.add_argument(
        "--icon-source-path",
        default=str(
            ROOT / "apps/macos-menubar/Sources/AppMain/Resources/Branding/MelixAppIcon.icns"
        ),
    )
    parser.add_argument(
        "--allow-insecure-http-host",
        action="append",
        default=[],
        metavar="HOST",
        help=(
            "Add an explicit App Transport Security exception for one HTTP host. "
            "Pass a host without scheme, port, or path; repeat for multiple hosts."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    menubar_binary = resolve_built_binary(repo_root)
    cli_binary = resolve_built_cli_binary(repo_root)
    control_plane_binary = resolve_built_control_plane_binary(repo_root)
    swift_worker_binary = resolve_built_swift_text_worker_binary(repo_root)
    swift_mlx_metallib, swift_mlx_metallib_version = resolve_swift_mlx_metallib(
        repo_root,
        args.swift_mlx_metallib_path or None,
    )
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
        control_plane_executable_path=control_plane_binary,
        swift_text_worker_executable_path=swift_worker_binary,
        swift_mlx_metallib_path=swift_mlx_metallib,
        swift_mlx_metallib_version=swift_mlx_metallib_version,
        python_runtime_root=python_runtime_root,
        python_site_packages_path=python_site_packages_path,
        output_path=args.output_path,
        app_name=args.app_name,
        bundle_id=args.bundle_id,
        version=args.version,
        packaging_target_id=args.packaging_target_id,
        update_channel_path=args.update_channel_path or None,
        icon_source_path=args.icon_source_path,
        insecure_http_hosts=args.allow_insecure_http_host,
    )
    if args.archive_path:
        timings = _manifest_timings(manifest)
        write_seconds = timings.get("write_total_seconds")
        if write_seconds is None:
            raise KeyError("write_total_seconds missing from bundle manifest timings")

        started_at = time.perf_counter()
        manifest["adhoc_signed"] = adhoc_sign_macos_app_bundle(manifest["app_path"])
        timings["adhoc_sign_seconds"] = elapsed_seconds(started_at)
        if not manifest["adhoc_signed"]:
            raise RuntimeError(
                "Ad-hoc signing and deep verification failed; refusing to create the app archive"
            )

        started_at = time.perf_counter()
        manifest["archive_path"] = str(
            archive_macos_app_bundle(manifest["app_path"], args.archive_path)
        )
        timings["archive_seconds"] = elapsed_seconds(started_at)

        started_at = time.perf_counter()
        verify_archived_macos_app_bundle(
            manifest["archive_path"],
            expected_app_name=Path(manifest["app_path"]).name,
        )
        timings["archive_verify_seconds"] = elapsed_seconds(started_at)
        manifest["archive_verified"] = True
        timings["total_seconds"] = round(
            float(write_seconds)
            + timings["adhoc_sign_seconds"]
            + timings["archive_seconds"]
            + timings["archive_verify_seconds"],
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
