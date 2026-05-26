# Release Homebrew And Nix Distribution CI

## Goal

Publish Melix release artifacts to Homebrew and Nix distribution repositories when a GitHub Release
is published and the packaged app archive is attached.

## Non-Goals

- Do not replace the existing `package-self-contained-app` workflow that builds and attaches `Melix-<version>-macos.zip`.
- Do not make local checkout Homebrew development installs depend on a published tap.

## Context

- The existing `.github/workflows/package-self-contained-app.yml` workflow attaches the self-contained macOS app archive to GitHub Releases for `v*` tags.
- Release updates made with the repository `GITHUB_TOKEN` do not reliably fan out through a second
  `release` event workflow. After uploading the archive, the packaging workflow therefore emits a
  `repository_dispatch` event with the release tag and archive name so distribution workflows can
  run after the asset exists.
- `infra/homebrew/Formula/melix.rb` remains a repository-local source formula for development and service validation.
- There is no current Nix distribution artifact in the repository.
- Release distribution must be reproducible from the GitHub Release asset URL and the measured SHA-256 digest of the downloaded archive.

## Assumptions

- Release assets follow the existing package metadata convention: tag `v1.2.3` produces `Melix-1.2.3-macos.zip`.
- Homebrew distribution uses a cask because the release asset is a self-contained `Melix.app` archive.
- Nix distribution uses a Darwin-only flake that fetches the same release archive with `fetchurl`, unzips it, and exposes `packages.aarch64-darwin.melix`.
- Target repositories are configured through repository variables and tokens:
  - `MELIX_HOMEBREW_TAP_REPOSITORY` plus `MELIX_HOMEBREW_TAP_TOKEN`
  - `MELIX_NIX_REPOSITORY` plus `MELIX_NIX_REPOSITORY_TOKEN`

## Work Plan

1. Add a release-distribution renderer for Homebrew cask and Nix flake content.
2. Add focused tests that prove the generated Homebrew and Nix files point at the release archive URL, version, and hashes.
3. Add two GitHub Actions workflows:
   - `release-homebrew-distribution.yml`
   - `release-nix-distribution.yml`
4. Each workflow waits for or downloads the existing release archive, computes SHA-256 locally, renders the distribution file, checks out the configured target repository, commits the rendered update, and pushes it.
5. Bridge the existing release packaging workflow to the distribution workflows with a
   `melix-release-asset-published` `repository_dispatch` event after the archive upload succeeds.
6. Update runbooks to document release-time distribution configuration and failure modes.

## Verification

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_release_distribution.py
python3 -m py_compile scripts/render_release_distribution.py services/mlx-worker-python/worker/productization/release_distribution.py
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/package-self-contained-app.yml"); YAML.load_file(".github/workflows/release-homebrew-distribution.yml"); YAML.load_file(".github/workflows/release-nix-distribution.yml")'
```

Expected evidence:

- The pytest target passes and validates rendered Homebrew and Nix distribution files.
- Python compilation succeeds for the release-distribution renderer and CLI.
- Ruby YAML parsing succeeds for the packaging workflow and both new workflows.

## Acceptance Criteria

- Publishing a GitHub Release can trigger a Homebrew distribution workflow.
- Publishing a GitHub Release can trigger a Nix distribution workflow.
- Uploading the packaged release archive from the existing packaging workflow dispatches both
  distribution workflows after the release asset exists.
- Both workflows derive the version, asset name, release URL, and digest from the release event and downloaded asset.
- Both workflows fail with an explicit configuration error if the target repository variable or token is missing.
- Documentation tells operators which variables and secrets are required.

## Rollback or Safe Exit

- Disable either release workflow from the GitHub Actions UI if an external distribution repository is misconfigured.
- Revert the generated commit in the external Homebrew tap or Nix repository if a published formula or flake points to the wrong release asset.
- The existing GitHub Release artifact remains the source of truth and is not modified by either distribution workflow.
