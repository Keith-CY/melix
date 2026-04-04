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

The repository-owned Homebrew service uses the `homebrew` Melix sidecar instance and writes state
under:

- `~/Library/Application Support/Melix/sidecars/homebrew`
- `~/Library/Logs/Melix/sidecars/homebrew`

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
curl -sS http://127.0.0.1:11434/v1/models
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
```
