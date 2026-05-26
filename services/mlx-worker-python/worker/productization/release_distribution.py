from __future__ import annotations

import hashlib
import json
import re
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path


_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_RELEASE_REPOSITORY = "Keith-CY/melix"
DEFAULT_HOMEBREW_CASK_RELATIVE_PATH = Path("homebrew/Casks/melix.rb")
DEFAULT_NIX_FLAKE_RELATIVE_PATH = Path("nix/flake.nix")


@dataclass(frozen=True)
class ReleaseAsset:
    version: str
    tag_name: str
    repository: str
    archive_name: str
    download_url: str
    sha256_hex: str

    @property
    def nix_hash(self) -> str:
        return "sha256-" + b64encode(bytes.fromhex(self.sha256_hex)).decode("ascii")


def release_asset_from_tag(
    *,
    tag_name: str,
    repository: str = DEFAULT_RELEASE_REPOSITORY,
    sha256_hex: str,
) -> ReleaseAsset:
    normalized_tag = tag_name.strip()
    if not normalized_tag:
        raise ValueError("tag_name must not be empty")
    version = normalized_tag[1:] if normalized_tag.startswith("v") else normalized_tag
    if not version:
        raise ValueError("release version must not be empty")
    normalized_repository = repository.strip("/")
    if "/" not in normalized_repository:
        raise ValueError("repository must use owner/name format")
    _validate_sha256_hex(sha256_hex)
    archive_name = f"Melix-{version}-macos.zip"
    download_url = f"https://github.com/{normalized_repository}/releases/download/{normalized_tag}/{archive_name}"
    return ReleaseAsset(
        version=version,
        tag_name=normalized_tag,
        repository=normalized_repository,
        archive_name=archive_name,
        download_url=download_url,
        sha256_hex=sha256_hex,
    )


def release_asset_from_archive(
    *,
    tag_name: str,
    repository: str,
    archive_path: str | Path,
) -> ReleaseAsset:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Release archive does not exist: {archive}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    asset = release_asset_from_tag(
        tag_name=tag_name,
        repository=repository,
        sha256_hex=digest,
    )
    if archive.name != asset.archive_name:
        raise ValueError(
            f"archive path name must be {asset.archive_name} for tag {asset.tag_name}: {archive.name}"
        )
    return asset


def render_homebrew_cask(asset: ReleaseAsset) -> str:
    return f"""cask "melix" do
  version "{asset.version}"
  sha256 "{asset.sha256_hex}"

  url "{asset.download_url}"
  name "Melix"
  desc "Local-first AI runtime for Apple Silicon"
  homepage "https://github.com/{asset.repository}"

  app "Melix.app"

  zap trash: ["~/.melix"]
end
"""


def render_nix_flake(asset: ReleaseAsset) -> str:
    return f"""{{
  description = "Melix local-first AI runtime for Apple Silicon";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = {{ self, nixpkgs }}:
    let
      system = "aarch64-darwin";
      pkgs = nixpkgs.legacyPackages.${{system}};
    in {{
      packages.${{system}}.melix = pkgs.stdenvNoCC.mkDerivation {{
        pname = "melix";
        version = "{asset.version}";

        src = pkgs.fetchurl {{
          url = "{asset.download_url}";
          hash = "{asset.nix_hash}";
        }};

        nativeBuildInputs = [ pkgs.unzip ];
        dontBuild = true;
        dontConfigure = true;

        installPhase = ''
          runHook preInstall
          mkdir -p "$out/Applications"
          unzip -q "$src" -d "$TMPDIR/melix-app"
          cp -R "$TMPDIR/melix-app/Melix.app" "$out/Applications/Melix.app"
          runHook postInstall
        '';

        meta = {{
          description = "Local-first AI runtime for Apple Silicon";
          homepage = "https://github.com/{asset.repository}";
          platforms = [ "aarch64-darwin" ];
        }};
      }};

      packages.${{system}}.default = self.packages.${{system}}.melix;
    }};
}}
"""


def write_distribution_files(
    *,
    tag_name: str,
    repository: str,
    archive_path: str | Path,
    output_root: str | Path,
) -> dict[str, str]:
    root = Path(output_root).expanduser().resolve()
    asset = release_asset_from_archive(
        tag_name=tag_name,
        repository=repository,
        archive_path=archive_path,
    )
    homebrew_path = root / DEFAULT_HOMEBREW_CASK_RELATIVE_PATH
    nix_path = root / DEFAULT_NIX_FLAKE_RELATIVE_PATH
    homebrew_path.parent.mkdir(parents=True, exist_ok=True)
    nix_path.parent.mkdir(parents=True, exist_ok=True)
    homebrew_path.write_text(render_homebrew_cask(asset), encoding="utf-8")
    nix_path.write_text(render_nix_flake(asset), encoding="utf-8")
    payload = {
        "version": asset.version,
        "tag_name": asset.tag_name,
        "repository": asset.repository,
        "archive_name": asset.archive_name,
        "download_url": asset.download_url,
        "sha256_hex": asset.sha256_hex,
        "nix_hash": asset.nix_hash,
        "homebrew_cask_path": DEFAULT_HOMEBREW_CASK_RELATIVE_PATH.as_posix(),
        "nix_flake_path": DEFAULT_NIX_FLAKE_RELATIVE_PATH.as_posix(),
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _validate_sha256_hex(value: str) -> None:
    if _SHA256_HEX_RE.fullmatch(value) is None:
        raise ValueError("sha256_hex must be 64 lowercase hexadecimal characters")
