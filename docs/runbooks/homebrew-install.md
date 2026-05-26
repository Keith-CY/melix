# Homebrew Install And Service Management

Install Melix from the checked-out repository with the repository-owned Homebrew formula:

```bash
brew install --formula ./infra/homebrew/Formula/melix.rb
```

This formula installs:

- `melix`
- `melix-control-plane`
- `melix-text-worker-swift`
- `melix-homebrew-service`

Inspect the generated Homebrew service manifest before starting the service:

```bash
melix-homebrew-service manifest --json
```

This flow maps to the `homebrew_service` packaging target while preserving the shared logical
Melix identity used by the launch-agent install and app-bundle flows.

The repository-owned Homebrew service uses the `homebrew` Melix sidecar instance and writes state
under:

- `~/.melix/sidecars/homebrew`
- `~/.melix/sidecars/homebrew/logs`

Start the service bundle through Homebrew:

```bash
brew services start melix
```

The Homebrew service wrapper supervises the same three Melix processes that the local-product
install flow manages through launch agents:

- `melix-text-worker-swift`
- `uv run --project ... python -m worker.bootstrap`
- `melix-control-plane`

Verify readiness:

```bash
curl -sS http://127.0.0.1:12436/v1/models
```

Upgrade after pulling a newer repository checkout:

```bash
brew upgrade --formula ./infra/homebrew/Formula/melix.rb
brew services restart melix
```

Stop the service bundle:

```bash
brew services stop melix
```

Remove the installed commands:

```bash
brew uninstall melix
```

If you also want to prune the Melix sidecar state created by the Homebrew service instance:

```bash
python3 scripts/uninstall_local_product.py --service-instance-name homebrew --prune
```

Repository-owned deterministic validation commands:

```bash
python3 scripts/m8_homebrew_formula_smoke.py --json
python3 scripts/m8_homebrew_service_smoke.py --json
python3 scripts/m8_packaging_target_smoke.py --json
```

## Release Distribution

The checked-in formula above remains the local checkout formula. Published
GitHub Releases distribute the self-contained `Melix.app` archive through a
Homebrew cask in a configured tap repository.

When a GitHub Release is published, the
`release-homebrew-distribution` workflow runs from the release event or from the
`melix-release-asset-published` repository dispatch emitted after the packaging
workflow attaches the archive. It:

1. downloads the existing `Melix-<version>-macos.zip` release asset,
2. computes its SHA-256 digest,
3. renders `Casks/melix.rb` for the configured tap repository,
4. commits the cask update to that tap.

Required repository configuration:

- variable `MELIX_HOMEBREW_TAP_REPOSITORY`: target tap in `owner/repo` form
- secret `MELIX_HOMEBREW_TAP_TOKEN`: token with write access to that tap

The workflow fails before checkout if either value is missing. It does not
rebuild the app archive; the GitHub Release asset remains the source of truth.
