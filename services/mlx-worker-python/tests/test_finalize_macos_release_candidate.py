from __future__ import annotations

import base64
import importlib.util
import json
import plistlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "finalize_macos_release_candidate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("melix_finalize_release_candidate", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate_metadata_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    package = repo / "apps/macos-menubar/Package.swift"
    package.parent.mkdir(parents=True)
    package.write_text(
        "let package = Package(platforms: [.macOS(.v15)])\n", encoding="utf-8"
    )
    app = tmp_path / "Melix.app"
    resources = app / "Contents/Resources"
    resources.mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "io.melix.menubar.release-candidate",
                "CFBundleShortVersionString": "1.2.3",
                "CFBundleVersion": "1.2.3",
                "LSMinimumSystemVersion": "15.0",
            }
        )
    )
    (resources / "packaging-target-manifest.json").write_text(
        json.dumps(
            {
                "packaging_target_id": "macos_app_bundle_github_release_candidate",
                "bundle_id": "io.melix.menubar.release-candidate",
                "product_version": "1.2.3",
                "update_channel_path": str(tmp_path / "stable.json"),
                "sparkle_updates": {"enabled": False, "framework_version": "2.9.4"},
            }
        ),
        encoding="utf-8",
    )
    (resources / "melix-product-env.sh").write_text(
        'export MELIX_PACKAGING_TARGET_ID="macos_app_bundle_github_release_candidate"\n',
        encoding="utf-8",
    )
    return repo, app


def test_finalize_candidate_metadata_injects_only_protected_release_trust(
    tmp_path: Path,
) -> None:
    module = load_module()
    repo, app = candidate_metadata_fixture(tmp_path)
    public_key = base64.b64encode(bytes(range(32))).decode("ascii")
    candidate_receipt = {
        "tag_name": "v1.2.3",
        "source_sha": "a" * 40,
        "bundle_tree_sha256": "sha256:" + "b" * 64,
        "artifact_sha256": "sha256:" + "c" * 64,
    }

    manifest = module.finalize_candidate_metadata(
        repo_root=repo,
        app_path=app,
        tag_name="v1.2.3",
        source_sha="a" * 40,
        sparkle_public_key=public_key,
        expected_certificate_sha256="d" * 64,
        expected_certificate_sha1="e" * 40,
        candidate_receipt=candidate_receipt,
    )

    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleIdentifier"] == "io.melix.menubar"
    assert info["CFBundleShortVersionString"] == "1.2.3"
    assert info["CFBundleVersion"] == "1.2.3"
    assert info["LSMinimumSystemVersion"] == "15.0"
    assert info["SUFeedURL"].endswith("/releases/latest/download/appcast.xml")
    assert info["SUPublicEDKey"] == public_key
    assert manifest["packaging_target_id"] == "macos_app_bundle_github_release"
    assert manifest["product_version"] == "1.2.3"
    assert manifest["code_signing"] == {
        "mode": "stable_self_signed",
        "expected_certificate_sha256": "d" * 64,
        "expected_certificate_sha1": "e" * 40,
        "expected_authority": "Melix GitHub Release Signing",
    }
    assert manifest["release_candidate_provenance"] == candidate_receipt
    environment = (app / "Contents/Resources/melix-product-env.sh").read_text(
        encoding="utf-8"
    )
    assert "macos_app_bundle_github_release_candidate" not in environment
    assert "macos_app_bundle_github_release" in environment


def test_finalize_candidate_rejects_candidate_with_preinjected_feed(
    tmp_path: Path,
) -> None:
    module = load_module()
    repo, app = candidate_metadata_fixture(tmp_path)
    plist_path = app / "Contents/Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    info["SUFeedURL"] = "https://attacker.invalid/appcast.xml"
    plist_path.write_bytes(plistlib.dumps(info))

    with pytest.raises(ValueError, match="must not contain update trust"):
        module.finalize_candidate_metadata(
            repo_root=repo,
            app_path=app,
            tag_name="v1.2.3",
            source_sha="a" * 40,
            sparkle_public_key=base64.b64encode(bytes(32)).decode("ascii"),
            expected_certificate_sha256="d" * 64,
            expected_certificate_sha1="e" * 40,
            candidate_receipt={},
        )


@pytest.mark.parametrize(
    ("surface", "value", "message"),
    [
        ("plist_bundle", "io.melix.wrong", "bundle identifier mismatch"),
        ("plist_version", "9.9.9", "version does not match"),
        ("plist_bundle_version", "9.9.9", "bundle version does not match"),
        ("plist_minimum", "14.0", "minimum system version"),
        ("manifest_target", "wrong", "target manifest mismatch"),
        ("manifest_bundle", "io.melix.wrong", "manifest bundle identifier"),
        ("manifest_version", "9.9.9", "manifest product version does not match"),
        ("environment", "wrong", "environment script"),
    ],
)
def test_finalize_candidate_rejects_mismatched_candidate_metadata(
    tmp_path: Path, surface: str, value: str, message: str
) -> None:
    module = load_module()
    repo, app = candidate_metadata_fixture(tmp_path)
    plist_path = app / "Contents/Info.plist"
    manifest_path = app / "Contents/Resources/packaging-target-manifest.json"
    environment_path = app / "Contents/Resources/melix-product-env.sh"
    if surface.startswith("plist_"):
        with plist_path.open("rb") as handle:
            info = plistlib.load(handle)
        key = {
            "plist_bundle": "CFBundleIdentifier",
            "plist_version": "CFBundleShortVersionString",
            "plist_bundle_version": "CFBundleVersion",
            "plist_minimum": "LSMinimumSystemVersion",
        }[surface]
        info[key] = value
        plist_path.write_bytes(plistlib.dumps(info))
    elif surface.startswith("manifest_"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        key = {
            "manifest_target": "packaging_target_id",
            "manifest_bundle": "bundle_id",
            "manifest_version": "product_version",
        }[surface]
        manifest[key] = value
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        environment_path.write_text(value, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        module.finalize_candidate_metadata(
            repo_root=repo,
            app_path=app,
            tag_name="v1.2.3",
            source_sha="a" * 40,
            sparkle_public_key=base64.b64encode(bytes(32)).decode("ascii"),
            expected_certificate_sha256="d" * 64,
            expected_certificate_sha1="e" * 40,
            candidate_receipt={},
        )


def test_finalizer_rejects_nonobject_json(tmp_path: Path) -> None:
    module = load_module()
    payload = tmp_path / "payload.json"
    payload.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        module._read_json(payload)


def test_finalize_release_candidate_verifies_signs_archives_and_reverifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps({"receipt": True}), encoding="utf-8")
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        module,
        "verify_candidate_receipt",
        lambda receipt, **kwargs: calls.append(("candidate", (receipt, kwargs))),
    )
    monkeypatch.setattr(
        module,
        "finalize_candidate_metadata",
        lambda **kwargs: calls.append(("metadata", kwargs)) or {"final": True},
    )
    monkeypatch.setattr(
        module,
        "sign_macos_app_bundle",
        lambda app, **kwargs: calls.append(("sign", (app, kwargs))) or True,
    )
    monkeypatch.setattr(
        module,
        "archive_macos_app_bundle",
        lambda app, archive: calls.append(("archive", (app, archive))),
    )
    monkeypatch.setattr(
        module,
        "verify_archived_macos_app_bundle",
        lambda archive, **kwargs: calls.append(("verify_archive", (archive, kwargs))),
    )

    manifest = module.finalize_release_candidate(
        repo_root=tmp_path,
        app_path=tmp_path / "Melix.app",
        candidate_archive_path=tmp_path / "candidate.zip",
        candidate_receipt_path=receipt_path,
        tag_name="v1.2.3",
        source_sha="a" * 40,
        sparkle_public_key=base64.b64encode(bytes(32)).decode("ascii"),
        codesign_identity="e" * 40,
        codesign_keychain=tmp_path / "keychain",
        expected_certificate_sha256="d" * 64,
        expected_certificate_sha1="e" * 40,
        archive_path=tmp_path / "release.zip",
    )

    assert manifest == {"final": True}
    assert [name for name, _ in calls] == [
        "candidate",
        "metadata",
        "sign",
        "archive",
        "verify_archive",
    ]


def test_finalize_release_candidate_fails_when_inside_out_signing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(module, "verify_candidate_receipt", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "finalize_candidate_metadata", lambda **kwargs: {})
    monkeypatch.setattr(module, "sign_macos_app_bundle", lambda *args, **kwargs: False)

    with pytest.raises(RuntimeError, match="inside-out"):
        module.finalize_release_candidate(
            repo_root=tmp_path,
            app_path=tmp_path / "Melix.app",
            candidate_archive_path=tmp_path / "candidate.zip",
            candidate_receipt_path=receipt_path,
            tag_name="v1.2.3",
            source_sha="a" * 40,
            sparkle_public_key=base64.b64encode(bytes(32)).decode("ascii"),
            codesign_identity="e" * 40,
            codesign_keychain=tmp_path / "keychain",
            expected_certificate_sha256="d" * 64,
            expected_certificate_sha1="e" * 40,
            archive_path=tmp_path / "release.zip",
        )


def test_finalizer_main_forwards_resolved_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module()
    captured: dict[str, object] = {}

    def fake_finalize(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(module, "finalize_release_candidate", fake_finalize)
    arguments = [
        "--repo-root", str(tmp_path),
        "--app", str(tmp_path / "Melix.app"),
        "--candidate-archive", str(tmp_path / "candidate.zip"),
        "--candidate-receipt", str(tmp_path / "receipt.json"),
        "--tag", "v1.2.3",
        "--source-sha", "A" * 40,
        "--sparkle-public-key", base64.b64encode(bytes(32)).decode("ascii"),
        "--codesign-identity", "e" * 40,
        "--codesign-keychain", str(tmp_path / "keychain"),
        "--expected-certificate-sha256", "d" * 64,
        "--expected-certificate-sha1", "e" * 40,
        "--archive", str(tmp_path / "release.zip"),
    ]

    assert module.main(arguments) == 0
    assert captured["source_sha"] == "a" * 40
    assert json.loads(capsys.readouterr().out) == {"ok": True}
