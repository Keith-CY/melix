# Phase 8 Local Product Install

## Purpose

Install the Melix local product assets for a user-scoped operator flow and verify that the generated launchd assets are consistent before bootstrapping the services.

## Prerequisites

- Apple Silicon macOS host
- `swift`
- `python3`
- `uv`
- repository checkout on the target machine

## Install Assets

Generate the local product assets:

```bash
python3 scripts/install_local_product.py --json
```

This writes:

- user launch agents under `~/Library/LaunchAgents`
- an install manifest under `~/Library/Application Support/Melix/install-manifest.json`
- an environment export file under `~/Library/Application Support/Melix/melix-product-env.sh`

## Bootstrap

Load the generated launch agents:

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.swift-text-worker.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.python-worker.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.control-plane.plist"
```

## Verify Ready State

Probe the local control plane:

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

For deterministic install smoke without `launchctl`, validate asset generation only:

```bash
python3 scripts/phase8_install_smoke.py --json
```

## Uninstall

Remove the generated assets and print the matching bootout commands:

```bash
python3 scripts/uninstall_local_product.py
```

To also prune the generated runtime and log directories:

```bash
python3 scripts/uninstall_local_product.py --prune
```
