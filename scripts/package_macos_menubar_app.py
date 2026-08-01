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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

import worker.productization.macos_app_bundle as macos_app_bundle_module
from worker.productization.macos_app_bundle import (
    archive_macos_app_bundle,
    elapsed_seconds,
    normalize_codesign_certificate_sha1,
    normalize_codesign_certificate_sha256,
    resolve_macos_minimum_system_version,
    resolve_python_runtime_root,
    resolve_site_packages_root,
    sign_macos_app_bundle,
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
_PREVIEW_BUNDLE_ID = "io.melix.menubar.preview"
_PREVIEW_PACKAGING_TARGET_ID = "macos_app_bundle_preview"
_RELEASE_BUNDLE_ID = "io.melix.menubar"
_RELEASE_PACKAGING_TARGET_ID = "macos_app_bundle_github_release"
_RELEASE_SIGNING_AUTHORITY = "Melix GitHub Release Signing"
_MINIMUM_SYSTEM_VERSION = resolve_macos_minimum_system_version(ROOT)


@dataclass(frozen=True)
class AppCodeSigningConfiguration:
    identity: str
    keychain_path: Path | None
    expected_certificate_sha256: str | None
    expected_certificate_sha1: str | None
    expected_authority: str | None
    mode: str


def resolve_app_code_signing_configuration(
    *,
    sparkle_feed_url: str,
    sparkle_public_ed_key: str,
    bundle_id: str,
    packaging_target_id: str,
    codesign_identity: str,
    codesign_keychain: str,
    codesign_certificate_sha256: str = "",
) -> AppCodeSigningConfiguration:
    has_feed = bool(sparkle_feed_url.strip())
    has_public_key = bool(sparkle_public_ed_key.strip())
    if has_feed != has_public_key:
        raise ValueError("Sparkle feed URL and EdDSA public key must be provided together")
    updates_enabled = has_feed and has_public_key
    release_metadata = (
        bundle_id == _RELEASE_BUNDLE_ID
        and packaging_target_id == _RELEASE_PACKAGING_TARGET_ID
    )
    partial_release_metadata = (
        bundle_id == _RELEASE_BUNDLE_ID
        or packaging_target_id == _RELEASE_PACKAGING_TARGET_ID
    )
    if updates_enabled and not release_metadata:
        raise ValueError(
            "Signed updates require the stable Melix release bundle ID and packaging target"
        )
    if not updates_enabled and partial_release_metadata:
        raise ValueError(
            "The Melix release bundle identity must not be used without signed updates"
        )

    normalized_identity = codesign_identity.strip() or "-"
    normalized_keychain = codesign_keychain.strip()
    stable_identity_requested = normalized_identity != "-"
    if updates_enabled and not stable_identity_requested:
        raise ValueError(
            "Signed updates require the stable self-signed Melix code-signing identity"
        )
    if stable_identity_requested and not updates_enabled:
        raise ValueError(
            "The stable Melix release signing identity must not be used without signed updates"
        )
    if not stable_identity_requested:
        if normalized_keychain:
            raise ValueError("An ad-hoc signature must not receive a release signing keychain")
        return AppCodeSigningConfiguration(
            identity="-",
            keychain_path=None,
            expected_certificate_sha256=None,
            expected_certificate_sha1=None,
            expected_authority=None,
            mode="adhoc",
        )

    certificate_sha1 = normalize_codesign_certificate_sha1(normalized_identity)
    certificate_sha256 = normalize_codesign_certificate_sha256(
        codesign_certificate_sha256
    )
    if not normalized_keychain:
        raise ValueError("Stable release signing requires an explicit ephemeral keychain")
    keychain_path = Path(normalized_keychain).expanduser().resolve()
    if not keychain_path.is_file():
        raise FileNotFoundError(f"Release signing keychain is missing: {keychain_path}")
    return AppCodeSigningConfiguration(
        identity=certificate_sha1,
        keychain_path=keychain_path,
        expected_certificate_sha256=certificate_sha256,
        expected_certificate_sha1=certificate_sha1,
        expected_authority=_RELEASE_SIGNING_AUTHORITY,
        mode="stable_self_signed",
    )


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


def resolve_sparkle_framework(
    repo_root: Path,
    configured_path: str | Path | None = None,
) -> Path:
    if configured_path is not None and str(configured_path).strip():
        framework_path = Path(configured_path).expanduser().resolve()
    else:
        framework_path = (
            repo_root
            / "apps/macos-menubar/.build/artifacts/sparkle/Sparkle/Sparkle.xcframework"
            / "macos-arm64_x86_64/Sparkle.framework"
        ).resolve()
    if not framework_path.is_dir():
        raise FileNotFoundError(
            "Unable to find the complete Sparkle framework. Resolve and build "
            "apps/macos-menubar before packaging, or pass --sparkle-framework-path: "
            f"{framework_path}"
        )
    required_paths = [
        framework_path / "Versions/B/Sparkle",
        framework_path / "Versions/B/Autoupdate",
        framework_path / "Versions/B/Updater.app",
        framework_path / "Versions/B/XPCServices/Downloader.xpc",
        framework_path / "Versions/B/XPCServices/Installer.xpc",
    ]
    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        raise FileNotFoundError(
            "Sparkle framework is incomplete: "
            + ", ".join(str(path) for path in missing_paths)
        )
    return framework_path


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
    require_sparkle_framework: bool = False,
    expected_signing_certificate_sha256: str | None = None,
    expected_signing_certificate_sha1: str | None = None,
    expected_signing_authority: str | None = None,
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
    identity_expectations = (
        expected_signing_certificate_sha256,
        expected_signing_certificate_sha1,
        expected_signing_authority,
    )
    if any(value is not None for value in identity_expectations) and not all(
        value is not None for value in identity_expectations
    ):
        raise ValueError(
            "Expected code-signing certificate SHA-256, SHA-1, and authority must be provided together"
        )
    normalized_expected_certificate_sha256 = (
        macos_app_bundle_module.normalize_codesign_certificate_sha256(
            expected_signing_certificate_sha256
        )
        if expected_signing_certificate_sha256 is not None
        else None
    )
    normalized_expected_certificate_sha1 = (
        normalize_codesign_certificate_sha1(expected_signing_certificate_sha1)
        if expected_signing_certificate_sha1 is not None
        else None
    )
    normalized_expected_authority = (
        expected_signing_authority.strip()
        if expected_signing_authority is not None
        else None
    )
    if expected_signing_authority is not None and not normalized_expected_authority:
        raise ValueError("Expected code-signing authority must not be empty")

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

        if require_sparkle_framework:
            sparkle_framework = extracted_app / "Contents/Frameworks/Sparkle.framework"
            required_sparkle_paths = [
                sparkle_framework / "Versions/B/Sparkle",
                sparkle_framework / "Versions/B/Autoupdate",
                sparkle_framework / "Versions/B/Updater.app",
                sparkle_framework / "Versions/B/XPCServices/Downloader.xpc",
                sparkle_framework / "Versions/B/XPCServices/Installer.xpc",
            ]
            missing_sparkle_paths = [
                path for path in required_sparkle_paths if not path.exists()
            ]
            if missing_sparkle_paths:
                raise RuntimeError(
                    "Archived Sparkle framework is incomplete: "
                    + ", ".join(str(path) for path in missing_sparkle_paths)
                )

            app_binary = extracted_app / "Contents/Resources/melix-menubar"
            otool = shutil.which("otool")
            if otool is None:
                raise RuntimeError("otool is required to verify packaged Sparkle linkage")
            linked_libraries = subprocess.run(
                [otool, "-L", os.fspath(app_binary)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            load_commands = subprocess.run(
                [otool, "-l", os.fspath(app_binary)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            if "@rpath/Sparkle.framework/Versions/B/Sparkle" not in linked_libraries:
                raise RuntimeError("Packaged menu-bar executable is not linked to Sparkle")
            if "@loader_path/../Frameworks" not in load_commands:
                raise RuntimeError(
                    "Packaged menu-bar executable cannot resolve Contents/Frameworks"
                )

        try:
            for target in macos_app_bundle_module.macos_code_signing_plan(extracted_app):
                subprocess.run(
                    [
                        codesign,
                        "--verify",
                        "--strict",
                        "--verbose=4",
                        os.fspath(target.path),
                    ],
                    check=True,
                )
                if "runtime" not in macos_app_bundle_module._codesign_details(
                    codesign, target.path
                ):
                    raise RuntimeError(
                        f"Archived code is missing hardened runtime: {target.path}"
                    )
                if normalized_expected_certificate_sha1 is not None:
                    assert normalized_expected_certificate_sha256 is not None
                    assert normalized_expected_authority is not None
                    if target.preserve_entitlements:
                        macos_app_bundle_module._canonical_codesign_entitlements(
                            codesign, target.path
                        )
                    macos_app_bundle_module._verify_codesign_identity_evidence(
                        codesign,
                        target.path,
                        expected_certificate_sha256=normalized_expected_certificate_sha256,
                        expected_certificate_sha1=normalized_expected_certificate_sha1,
                        expected_authority=normalized_expected_authority,
                    )
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            raise RuntimeError(
                f"Archived macOS app signature verification failed: {extracted_app}"
            ) from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-path", default="/tmp/Melix.app")
    parser.add_argument("--home-dir", default=str(Path.home()))
    parser.add_argument("--app-name", default="Melix")
    parser.add_argument("--bundle-id", default=_PREVIEW_BUNDLE_ID)
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--packaging-target-id", default=_PREVIEW_PACKAGING_TARGET_ID)
    parser.add_argument("--update-channel-path", default="")
    parser.add_argument("--archive-path", default="")
    parser.add_argument("--python-runtime-root", default="")
    parser.add_argument("--python-site-packages-path", default="")
    parser.add_argument("--sparkle-framework-path", default="")
    parser.add_argument("--sparkle-feed-url", default="")
    parser.add_argument("--sparkle-public-ed-key", default="")
    parser.add_argument("--codesign-identity", default="-")
    parser.add_argument("--codesign-keychain", default="")
    parser.add_argument("--codesign-certificate-sha256", default="")
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

    code_signing = resolve_app_code_signing_configuration(
        sparkle_feed_url=args.sparkle_feed_url,
        sparkle_public_ed_key=args.sparkle_public_ed_key,
        bundle_id=args.bundle_id,
        packaging_target_id=args.packaging_target_id,
        codesign_identity=args.codesign_identity,
        codesign_keychain=args.codesign_keychain,
        codesign_certificate_sha256=args.codesign_certificate_sha256,
    )
    if code_signing.mode == "stable_self_signed" and not args.archive_path.strip():
        raise ValueError("Signed update releases require an archive path")

    repo_root = Path(args.repo_root).expanduser().resolve()
    menubar_binary = resolve_built_binary(repo_root)
    cli_binary = resolve_built_cli_binary(repo_root)
    control_plane_binary = resolve_built_control_plane_binary(repo_root)
    swift_worker_binary = resolve_built_swift_text_worker_binary(repo_root)
    swift_mlx_metallib, swift_mlx_metallib_version = resolve_swift_mlx_metallib(
        repo_root,
        args.swift_mlx_metallib_path or None,
    )
    sparkle_framework = resolve_sparkle_framework(
        repo_root,
        args.sparkle_framework_path or None,
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
        sparkle_framework_path=sparkle_framework,
        sparkle_feed_url=args.sparkle_feed_url or None,
        sparkle_public_ed_key=args.sparkle_public_ed_key or None,
        code_signing_mode=code_signing.mode,
        code_signing_certificate_sha256=code_signing.expected_certificate_sha256,
        code_signing_certificate_sha1=code_signing.expected_certificate_sha1,
        code_signing_authority=code_signing.expected_authority,
        minimum_system_version=_MINIMUM_SYSTEM_VERSION,
    )
    if args.archive_path:
        timings = _manifest_timings(manifest)
        write_seconds = timings.get("write_total_seconds")
        if write_seconds is None:
            raise KeyError("write_total_seconds missing from bundle manifest timings")

        started_at = time.perf_counter()
        manifest["code_signed"] = sign_macos_app_bundle(
            manifest["app_path"],
            identity=code_signing.identity,
            keychain_path=code_signing.keychain_path,
            expected_certificate_sha256=code_signing.expected_certificate_sha256,
            expected_certificate_sha1=code_signing.expected_certificate_sha1,
            expected_authority=code_signing.expected_authority,
        )
        timings["code_sign_seconds"] = elapsed_seconds(started_at)
        if code_signing.mode == "adhoc":
            timings["adhoc_sign_seconds"] = timings["code_sign_seconds"]
        manifest["code_signing_mode"] = code_signing.mode
        manifest["code_signing_certificate_sha256"] = (
            code_signing.expected_certificate_sha256
        )
        manifest["code_signing_certificate_sha1"] = (
            code_signing.expected_certificate_sha1
        )
        manifest["code_signing_authority"] = code_signing.expected_authority
        manifest["adhoc_signed"] = (
            manifest["code_signed"] and code_signing.mode == "adhoc"
        )
        if not manifest["code_signed"]:
            raise RuntimeError(
                "Code signing or signature verification failed; refusing to create the app archive"
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
            require_sparkle_framework=True,
            expected_signing_certificate_sha256=(
                code_signing.expected_certificate_sha256
            ),
            expected_signing_certificate_sha1=(
                code_signing.expected_certificate_sha1
            ),
            expected_signing_authority=code_signing.expected_authority,
        )
        timings["archive_verify_seconds"] = elapsed_seconds(started_at)
        manifest["archive_verified"] = True
        timings["total_seconds"] = round(
            float(write_seconds)
            + timings["code_sign_seconds"]
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
