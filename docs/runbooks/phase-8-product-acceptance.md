# Phase 8 Product Acceptance

## Purpose

Run the end-of-phase product acceptance flow for Melix and capture the final metrics report.

## Install Or Upgrade

Generate or refresh the local product assets:

```bash
python3 scripts/install_local_product.py --json
```

Bootstrap the generated launch agents:

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.swift-text-worker.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.python-worker.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.control-plane.plist"
```

## Roll Back

To roll back to a previous repository revision:

1. `python3 scripts/uninstall_local_product.py`
2. check out the target revision
3. rerun `python3 scripts/install_local_product.py --json`
4. bootstrap the generated launch agents again

## Diagnostics And Training

Run the deterministic release gate:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
```

This verifies:

- install evidence
- benchmark thresholds
- restart recovery
- training sanity

## Final Metrics Report

Generate the final product metrics report:

```bash
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

The report includes:

- cold boot to ready
- HTTP ready latency
- background preload latency
- first text-model warm latency
- first text-model estimated resident bytes
- first text-model resident bytes
- operator action latency
- install success rate
- benchmark regression percentage
- smoke pass rate
- training duration
- adapter publish latency
- restart-to-ready latency
- snapshot restore latency
- restart recovery latency and success

## Recovery

If the local stack needs to be reinstalled or reset:

```bash
python3 scripts/uninstall_local_product.py --prune
python3 scripts/install_local_product.py --json
```

Then rerun:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```
