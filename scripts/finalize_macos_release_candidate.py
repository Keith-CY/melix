#!/usr/bin/env python3
"""Convert a receipt-bound candidate into the pinned stable Melix release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import plistlib
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from scripts.macos_release_candidate import verify_candidate_receipt
from scripts.package_macos_menubar_app import verify_archived_macos_app_bundle
from scripts.validate_macos_release_tag import StableReleaseVersion
from worker.productization.macos_app_bundle import (
    archive_macos_app_bundle,
    normalize_codesign_certificate_sha1,
    normalize_codesign_certificate_sha256,
    normalize_sparkle_update_configuration,
    resolve_macos_minimum_system_version,
    sign_macos_app_bundle,
)
from worker.productization.packaging_targets import build_packaging_target_metadata


CANDIDATE_BUNDLE_ID = "io.melix.menubar.release-candidate"
CANDIDATE_TARGET_ID = "macos_app_bundle_github_release_candidate"
RELEASE_BUNDLE_ID = "io.melix.menubar"
RELEASE_TARGET_ID = "macos_app_bundle_github_release"
RELEASE_AUTHORITY = "Melix GitHub Release Signing"
SPARKLE_FEED_URL = (
    "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_candidate_marker(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    marker = f'MELIX_PACKAGING_TARGET_ID="{CANDIDATE_TARGET_ID}"'
    if marker not in content:
        raise ValueError("candidate environment script does not contain its isolated target")
    return content


def finalize_candidate_metadata(
    *,
    repo_root: Path,
    app_path: Path,
    tag_name: str,
    source_sha: str,
    sparkle_public_key: str,
    expected_certificate_sha256: str,
    expected_certificate_sha1: str,
    candidate_receipt: Mapping[str, object],
) -> dict[str, Any]:
    """Rewrite only the trusted release metadata before signing."""

    version = StableReleaseVersion.parse_tag(tag_name).display_version
    minimum_system_version = resolve_macos_minimum_system_version(repo_root)
    update_configuration = normalize_sparkle_update_configuration(
        feed_url=SPARKLE_FEED_URL,
        public_ed_key=sparkle_public_key,
    )
    assert update_configuration is not None
    certificate_sha256 = normalize_codesign_certificate_sha256(
        expected_certificate_sha256
    )
    certificate_sha1 = normalize_codesign_certificate_sha1(expected_certificate_sha1)

    contents = app_path / "Contents"
    plist_path = contents / "Info.plist"
    manifest_path = contents / "Resources/packaging-target-manifest.json"
    environment_path = contents / "Resources/melix-product-env.sh"
    with plist_path.open("rb") as handle:
        info_plist = plistlib.load(handle)
    if info_plist.get("CFBundleIdentifier") != CANDIDATE_BUNDLE_ID:
        raise ValueError("candidate app bundle identifier mismatch")
    if "SUFeedURL" in info_plist or "SUPublicEDKey" in info_plist:
        raise ValueError("release candidate must not contain update trust configuration")
    if info_plist.get("CFBundleShortVersionString") != version:
        raise ValueError("candidate short version does not match the validated release tag")
    if info_plist.get("CFBundleVersion") != version:
        raise ValueError("candidate bundle version does not match the validated release tag")
    if info_plist.get("LSMinimumSystemVersion") != minimum_system_version:
        raise ValueError("candidate minimum system version does not match Package.swift")

    manifest = _read_json(manifest_path)
    if manifest.get("packaging_target_id") != CANDIDATE_TARGET_ID:
        raise ValueError("candidate packaging target manifest mismatch")
    if manifest.get("bundle_id") != CANDIDATE_BUNDLE_ID:
        raise ValueError("candidate manifest bundle identifier mismatch")
    if manifest.get("product_version") != version:
        raise ValueError(
            "candidate manifest product version does not match the validated release tag"
        )
    environment = _require_candidate_marker(environment_path)

    info_plist.update(
        {
            "CFBundleIdentifier": RELEASE_BUNDLE_ID,
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "LSMinimumSystemVersion": minimum_system_version,
            "SUFeedURL": update_configuration["feed_url"],
            "SUPublicEDKey": update_configuration["public_ed_key"],
            "SUEnableAutomaticChecks": True,
            "SUAllowsAutomaticUpdates": False,
            "SUScheduledCheckInterval": 86_400,
            "SUVerifyUpdateBeforeExtraction": True,
            "SURequireSignedFeed": True,
        }
    )
    plist_path.write_bytes(plistlib.dumps(info_plist, fmt=plistlib.FMT_XML, sort_keys=False))

    release_profile = build_packaging_target_metadata(
        RELEASE_TARGET_ID,
        product_version=version,
        update_channel_path=str(manifest.get("update_channel_path", "")),
        bundle_id=RELEASE_BUNDLE_ID,
    )
    manifest.update(release_profile)
    manifest["minimum_system_version"] = minimum_system_version
    manifest["code_signing"] = {
        "mode": "stable_self_signed",
        "expected_certificate_sha256": certificate_sha256,
        "expected_certificate_sha1": certificate_sha1,
        "expected_authority": RELEASE_AUTHORITY,
    }
    existing_sparkle = manifest.get("sparkle_updates")
    sparkle_metadata = dict(existing_sparkle) if isinstance(existing_sparkle, dict) else {}
    sparkle_metadata.update(
        {
            "enabled": True,
            "feed_url": SPARKLE_FEED_URL,
            "public_key_sha256": hashlib.sha256(
                base64.b64decode(sparkle_public_key, validate=True)
            ).hexdigest(),
            "requires_user_confirmation": True,
            "automatic_downloads_enabled": False,
        }
    )
    manifest["sparkle_updates"] = sparkle_metadata
    manifest["release_candidate_provenance"] = dict(candidate_receipt)
    manifest["release_source_sha"] = source_sha
    manifest["release_tag"] = tag_name
    _write_json(manifest_path, manifest)

    environment_path.write_text(
        environment.replace(CANDIDATE_TARGET_ID, RELEASE_TARGET_ID), encoding="utf-8"
    )
    if info_plist["CFBundleIdentifier"] != RELEASE_BUNDLE_ID:  # pragma: no cover
        raise RuntimeError("final Info.plist bundle identity was not rewritten")
    if (
        info_plist["CFBundleShortVersionString"] != version
        or info_plist["CFBundleVersion"] != version
    ):  # pragma: no cover
        raise RuntimeError("final Info.plist versions were not rewritten")
    if (
        manifest["packaging_target_id"] != RELEASE_TARGET_ID
        or manifest["bundle_id"] != RELEASE_BUNDLE_ID
    ):
        raise RuntimeError("final packaging manifest identity was not rewritten")
    if CANDIDATE_TARGET_ID in environment_path.read_text(  # pragma: no cover
        encoding="utf-8"
    ):
        raise RuntimeError("candidate target remains in the final environment script")
    return manifest


def finalize_release_candidate(
    *,
    repo_root: Path,
    app_path: Path,
    candidate_archive_path: Path,
    candidate_receipt_path: Path,
    tag_name: str,
    source_sha: str,
    sparkle_public_key: str,
    codesign_identity: str,
    codesign_keychain: Path,
    expected_certificate_sha256: str,
    expected_certificate_sha1: str,
    archive_path: Path,
) -> dict[str, Any]:
    receipt = _read_json(candidate_receipt_path)
    verify_candidate_receipt(
        receipt,
        app_path=app_path,
        archive_path=candidate_archive_path,
        expected_tag_name=tag_name,
        expected_source_sha=source_sha,
    )
    manifest = finalize_candidate_metadata(
        repo_root=repo_root,
        app_path=app_path,
        tag_name=tag_name,
        source_sha=source_sha,
        sparkle_public_key=sparkle_public_key,
        expected_certificate_sha256=expected_certificate_sha256,
        expected_certificate_sha1=expected_certificate_sha1,
        candidate_receipt=receipt,
    )
    if not sign_macos_app_bundle(
        app_path,
        identity=codesign_identity,
        keychain_path=codesign_keychain,
        expected_certificate_sha256=expected_certificate_sha256,
        expected_certificate_sha1=expected_certificate_sha1,
        expected_authority=RELEASE_AUTHORITY,
    ):
        raise RuntimeError("stable release inside-out code signing failed")
    archive_macos_app_bundle(app_path, archive_path)
    verify_archived_macos_app_bundle(
        archive_path,
        expected_app_name=app_path.name,
        require_sparkle_framework=True,
        expected_signing_certificate_sha256=expected_certificate_sha256,
        expected_signing_certificate_sha1=expected_certificate_sha1,
        expected_signing_authority=RELEASE_AUTHORITY,
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--sparkle-public-key", required=True)
    parser.add_argument("--codesign-identity", required=True)
    parser.add_argument("--codesign-keychain", type=Path, required=True)
    parser.add_argument("--expected-certificate-sha256", required=True)
    parser.add_argument("--expected-certificate-sha1", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    arguments = parser.parse_args(argv)

    manifest = finalize_release_candidate(
        repo_root=arguments.repo_root.resolve(),
        app_path=arguments.app.resolve(),
        candidate_archive_path=arguments.candidate_archive.resolve(),
        candidate_receipt_path=arguments.candidate_receipt.resolve(),
        tag_name=arguments.tag,
        source_sha=arguments.source_sha.lower(),
        sparkle_public_key=arguments.sparkle_public_key,
        codesign_identity=arguments.codesign_identity,
        codesign_keychain=arguments.codesign_keychain.resolve(),
        expected_certificate_sha256=arguments.expected_certificate_sha256,
        expected_certificate_sha1=arguments.expected_certificate_sha1,
        archive_path=arguments.archive.resolve(),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
