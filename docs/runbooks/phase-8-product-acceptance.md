# Phase 8 Product Acceptance

## Purpose

Run the end-of-phase product acceptance flow for Melix and capture the final metrics report.

## Repository Verification

Before claiming productization completion, run the repository-owned verification commands:

```bash
make proto
make py-test
make swift-test
make integration-test
```

Use these as the final repository verification gate for LoRA, benchmark, and CLI productization
in addition to the release-gate and metrics commands below.

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
- runtime-core multi-model evidence
- runtime-core memory-guard evidence
- training sanity

For the manual LoRA operator workflow, use `docs/runbooks/phase-8-lora-adapter-workflow.md`.

## Final Metrics Report

Generate the final product metrics report:

```bash
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

The report includes:

- cold boot to ready
- Swift text worker spawn-to-ready latency
- Swift text worker spawn-to-bootstrap latency
- Swift text worker registry initialization latency
- Swift text worker service wiring latency
- Swift text worker server construction latency
- Swift text worker bootstrap latency
- Python worker spawn-to-ready latency
- Python worker spawn-to-bootstrap latency
- Python worker argument parsing latency
- Python worker registry initialization latency
- Python worker server construction latency
- Python worker server start latency
- Python worker bootstrap latency
- control-plane spawn-to-ready latency
- HTTP ready latency
- background preload latency
- first text-model warm latency
- first text-model estimated resident bytes
- first text-model resident bytes
- runtime-core multi-model ready count
- runtime-core multi-model request success rate
- runtime-core prefill memory-guard rejection count
- runtime-core prefill memory-guard success rate
- operator action latency
- install success rate
- benchmark regression percentage
- smoke pass rate
- training duration
- adapter publish latency
- restart-to-ready latency
- restart Swift text worker spawn-to-ready latency
- restart Python worker spawn-to-ready latency
- restart control-plane spawn-to-ready latency
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
