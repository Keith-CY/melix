from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import runpy
import sys
from pathlib import Path

import pytest

from worker.productization.release_distribution import (
    ReleaseAsset,
    release_asset_from_archive,
    release_asset_from_tag,
    render_homebrew_cask,
    render_nix_flake,
    write_distribution_files,
)


def test_release_asset_from_tag_derives_existing_app_archive_url() -> None:
    asset = release_asset_from_tag(
        tag_name="v1.2.3",
        repository="Keith-CY/melix",
        sha256_hex="a" * 64,
    )

    assert asset.version == "1.2.3"
    assert asset.archive_name == "Melix-1.2.3.zip"
    assert asset.download_url == (
        "https://github.com/Keith-CY/melix/releases/download/v1.2.3/Melix-1.2.3.zip"
    )
    assert asset.sha256_hex == "a" * 64
    assert asset.nix_hash == "sha256-qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqo="


def test_release_asset_from_tag_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        release_asset_from_tag(tag_name="v1.2.3", repository="Keith-CY/melix", sha256_hex="ABC")


@pytest.mark.parametrize(
    ("tag_name", "repository", "message"),
    (
        ("", "Keith-CY/melix", "tag_name must not be empty"),
        ("v", "Keith-CY/melix", "release version must not be empty"),
        ("v1.2.3", "melix", "repository must use owner/name format"),
    ),
)
def test_release_asset_from_tag_rejects_invalid_release_metadata(
    tag_name: str,
    repository: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        release_asset_from_tag(tag_name=tag_name, repository=repository, sha256_hex="a" * 64)


def test_release_asset_from_archive_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Release archive does not exist"):
        release_asset_from_archive(
            tag_name="v1.2.3",
            repository="Keith-CY/melix",
            archive_path=tmp_path / "Melix-1.2.3.zip",
        )


def test_release_asset_from_archive_hashes_without_whole_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "Melix-1.2.3.zip"
    payload = b"melix archive" * 1024
    archive.write_bytes(payload)

    def fail_whole_file_read(self: Path) -> bytes:
        raise AssertionError("release archive hashing must stream bytes instead of read_bytes")

    monkeypatch.setattr(Path, "read_bytes", fail_whole_file_read)

    asset = release_asset_from_archive(
        tag_name="v1.2.3",
        repository="Keith-CY/melix",
        archive_path=archive,
    )

    assert asset.sha256_hex == hashlib.sha256(payload).hexdigest()


def test_render_homebrew_cask_points_to_release_asset_and_service_metadata() -> None:
    asset = ReleaseAsset(
        version="1.2.3",
        tag_name="v1.2.3",
        repository="Keith-CY/melix",
        archive_name="Melix-1.2.3.zip",
        download_url="https://github.com/Keith-CY/melix/releases/download/v1.2.3/Melix-1.2.3.zip",
        sha256_hex="b" * 64,
    )

    cask = render_homebrew_cask(asset)

    assert 'cask "melix"' in cask
    assert 'version "1.2.3"' in cask
    assert 'sha256 "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"' in cask
    assert 'url "https://github.com/Keith-CY/melix/releases/download/v1.2.3/Melix-1.2.3.zip"' in cask
    assert 'app "Melix.app"' in cask
    assert 'zap trash: ["~/.melix"]' in cask


def test_render_nix_flake_exposes_darwin_package_from_release_asset() -> None:
    asset = ReleaseAsset(
        version="1.2.3",
        tag_name="v1.2.3",
        repository="Keith-CY/melix",
        archive_name="Melix-1.2.3.zip",
        download_url="https://github.com/Keith-CY/melix/releases/download/v1.2.3/Melix-1.2.3.zip",
        sha256_hex="c" * 64,
    )

    flake = render_nix_flake(asset)

    assert 'description = "Melix local-first AI runtime for Apple Silicon";' in flake
    assert 'nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";' in flake
    assert "import <nixpkgs>" not in flake
    assert "system = \"aarch64-darwin\";" in flake
    assert 'version = "1.2.3";' in flake
    assert "pkgs.fetchurl" in flake
    assert "fetchzip" not in flake
    assert "nativeBuildInputs = [ pkgs.unzip ];" in flake
    assert 'url = "https://github.com/Keith-CY/melix/releases/download/v1.2.3/Melix-1.2.3.zip";' in flake
    assert 'hash = "sha256-zMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMw=";' in flake
    assert 'unzip -q "$src" -d "$TMPDIR/melix-app"' in flake
    assert 'cp -R "$TMPDIR/melix-app/Melix.app" "$out/Applications/Melix.app"' in flake


def test_write_distribution_files_rejects_archive_name_that_does_not_match_release_tag(tmp_path: Path) -> None:
    archive = tmp_path / "Melix-wrong.zip"
    archive.write_bytes(b"wrong release asset")

    with pytest.raises(ValueError, match="archive path name"):
        write_distribution_files(
            tag_name="v1.2.3",
            repository="Keith-CY/melix",
            archive_path=archive,
            output_root=tmp_path / "dist",
        )


def test_write_distribution_files_writes_manifest_for_ci_commit(tmp_path: Path) -> None:
    archive = tmp_path / "Melix-1.2.3.zip"
    archive.write_bytes(b"melix archive")
    sha256_hex = hashlib.sha256(b"melix archive").hexdigest()
    output_root = tmp_path / "dist"

    payload = write_distribution_files(
        tag_name="v1.2.3",
        repository="Keith-CY/melix",
        archive_path=archive,
        output_root=output_root,
    )

    assert (output_root / "homebrew/Casks/melix.rb").exists()
    assert (output_root / "nix/flake.nix").exists()
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == payload
    assert payload["version"] == "1.2.3"
    assert payload["archive_name"] == "Melix-1.2.3.zip"
    assert payload["sha256_hex"] == sha256_hex
    assert payload["nix_hash"].startswith("sha256-")
    assert payload["homebrew_cask_path"] == "homebrew/Casks/melix.rb"
    assert payload["nix_flake_path"] == "nix/flake.nix"


def test_render_release_distribution_cli_writes_distribution_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_render_release_distribution_cli()
    archive = tmp_path / "Melix-1.2.3.zip"
    archive.write_bytes(b"melix cli archive")
    output_root = tmp_path / "dist"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render_release_distribution.py",
            "--tag-name",
            "v1.2.3",
            "--repository",
            "Keith-CY/melix",
            "--archive-path",
            str(archive),
            "--output-root",
            str(output_root),
            "--json",
        ],
    )

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["archive_name"] == "Melix-1.2.3.zip"
    assert (output_root / "homebrew/Casks/melix.rb").exists()
    assert (output_root / "nix/flake.nix").exists()


def test_render_release_distribution_cli_writes_compact_json_without_pretty_flag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_render_release_distribution_cli()
    archive = tmp_path / "Melix-1.2.3.zip"
    archive.write_bytes(b"melix compact cli archive")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render_release_distribution.py",
            "--tag-name",
            "v1.2.3",
            "--repository",
            "Keith-CY/melix",
            "--archive-path",
            str(archive),
            "--output-root",
            str(tmp_path / "dist"),
        ],
    )

    assert module.main() == 0
    output = capsys.readouterr().out
    assert "\n  " not in output
    assert json.loads(output)["archive_name"] == "Melix-1.2.3.zip"


def test_render_release_distribution_cli_main_guard_exits_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts/render_release_distribution.py"
    archive = tmp_path / "Melix-1.2.3.zip"
    archive.write_bytes(b"melix main guard archive")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render_release_distribution.py",
            "--tag-name",
            "v1.2.3",
            "--repository",
            "Keith-CY/melix",
            "--archive-path",
            str(archive),
            "--output-root",
            str(tmp_path / "dist"),
        ],
    )

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(module_path), run_name="__main__")

    assert error.value.code == 0
    assert json.loads(capsys.readouterr().out)["archive_name"] == "Melix-1.2.3.zip"


def _load_render_release_distribution_cli():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts/render_release_distribution.py"
    spec = importlib.util.spec_from_file_location("render_release_distribution_cli", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_step(workflow: str, name: str) -> str:
    match = re.search(
        rf"^[ \t]*-[ \t]+name:[ \t]+{re.escape(name)}[ \t]*\n"
        r"(?P<body>.*?)(?=^[ \t]*-[ \t]+name:|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Workflow step not found: {name}"
    return match.group("body")


def test_release_homebrew_distribution_workflow_publishes_configured_tap() -> None:
    workflow = (
        Path(__file__).resolve().parents[3]
        / ".github/workflows/release-homebrew-distribution.yml"
    ).read_text(encoding="utf-8")

    assert "types: [published]" in workflow
    assert "repository_dispatch:" in workflow
    assert "types: [melix-release-asset-published]" in workflow
    assert "github.event.client_payload.tag_name" in workflow
    assert "github.event.release.prerelease" not in workflow
    assert "environment:" in workflow
    assert "name: release" in workflow
    assert "MELIX_HOMEBREW_TAP_REPOSITORY" in workflow
    assert "MELIX_HOMEBREW_TAP_TOKEN" in workflow
    assert "scripts/render_release_distribution.py" in workflow
    assert "Casks/melix.rb" in workflow
    assert 'archive_name="${RELEASE_ARCHIVE_NAME:-Melix-${version}.zip}"' in workflow
    assert "-macos.zip" not in workflow
    assert "EndBug/add-and-commit@v10" in workflow
    assert 'message: "chore: update melix Homebrew cask ${{ steps.archive.outputs.version }}"' in workflow
    download_step = _workflow_step(workflow, "Download release archive")
    assert "gh release download" in download_step
    assert "&& test -s" in download_step
    assert "Validate Homebrew distribution configuration" in workflow


def test_release_nix_distribution_workflow_publishes_configured_repo() -> None:
    workflow = (
        Path(__file__).resolve().parents[3]
        / ".github/workflows/release-nix-distribution.yml"
    ).read_text(encoding="utf-8")

    assert "types: [published]" in workflow
    assert "repository_dispatch:" in workflow
    assert "types: [melix-release-asset-published]" in workflow
    assert "github.event.client_payload.tag_name" in workflow
    assert "github.event.release.prerelease" not in workflow
    assert "environment:" in workflow
    assert "name: release" in workflow
    assert "MELIX_NIX_REPOSITORY" in workflow
    assert "MELIX_NIX_REPOSITORY_TOKEN" in workflow
    assert "scripts/render_release_distribution.py" in workflow
    assert "nix/flake.nix" in workflow
    assert 'archive_name="${RELEASE_ARCHIVE_NAME:-Melix-${version}.zip}"' in workflow
    assert "-macos.zip" not in workflow
    assert "command -v nix" in workflow
    assert 'nix --extra-experimental-features "nix-command flakes" flake check "./nix-distribution" --no-build' in workflow
    assert "EndBug/add-and-commit@v10" in workflow
    assert 'message: "chore: update melix Nix package ${{ steps.archive.outputs.version }}"' in workflow
    download_step = _workflow_step(workflow, "Download release archive")
    assert "gh release download" in download_step
    assert "&& test -s" in download_step
    assert "Validate Nix distribution configuration" in workflow


def test_package_workflow_dispatches_distribution_after_release_asset_upload() -> None:
    workflow = (
        Path(__file__).resolve().parents[3]
        / ".github/workflows/package-self-contained-app.yml"
    ).read_text(encoding="utf-8")

    assert "softprops/action-gh-release" in workflow
    assert "Trigger release distribution workflows" in workflow
    assert '--field "event_type=melix-release-asset-published"' in workflow
    assert '--field "client_payload[tag_name]=$RELEASE_TAG"' in workflow
    assert '--field "client_payload[repository]=$RELEASE_REPOSITORY"' in workflow
    assert '--field "client_payload[archive_name]=$RELEASE_ARCHIVE_NAME"' in workflow
    assert "RELEASE_ARCHIVE_NAME" in workflow


def test_packaging_targets_document_release_environment_secret_scope() -> None:
    runbook = (
        Path(__file__).resolve().parents[3]
        / "docs/runbooks/platform-packaging-targets.md"
    ).read_text(encoding="utf-8")

    assert "`release` GitHub Actions environment" in runbook
    assert "`MELIX_HOMEBREW_TAP_TOKEN`" in runbook
    assert "`MELIX_NIX_REPOSITORY_TOKEN`" in runbook
    assert "repository variables" in runbook
    assert "environment secrets" in runbook
