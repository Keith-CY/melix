# Melix

Melix is a local-first AI runtime for Apple Silicon. The first implementation slice in this repository focuses on:

- generated protocol artifacts from the shared protobuf schema
- a Swift control plane workspace
- a Python worker workspace
- a minimal macOS menu bar workspace

Repository-wide engineering guidance lives in:

- `AGENTS.md`
- `docs/README.md`
- `docs/engineering-standards.md`
- `docs/plans/2026-03-27-phase-0-thin-path.md`

## Prerequisites

- macOS on Apple Silicon
- `swift`
- `python3`
- `uv`
- `protoc`
- `protoc-gen-swift` for Swift protobuf generation

## First Slice Developer Flow

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
make coverage
```

## Local Operator Loop

Bring up the deterministic phase-1 stack:

```bash
bash scripts/dev_up.sh
curl -sS http://127.0.0.1:11434/v1/models
make phase1-metrics
```

Shut it down:

```bash
bash scripts/dev_down.sh
```

Optional real MLX smoke path:

```bash
MELIX_DEV_TEXT_MODEL_PATH="<local path or hf repo>" \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift \
bash scripts/dev_up.sh
```

`deterministic` remains the default integration and repeatability path.
`swift` is the real Swift MLX runtime path for the text worker and requires
`MELIX_DEV_TEXT_MODEL_PATH`.

`scripts/dev_up.sh` now starts three processes:

- the Swift text worker on a dedicated UDS socket
- the Python compatibility worker on a dedicated UDS socket
- the Swift control plane on the local HTTP port

The runtime directory defaults to `.runtime/phase1` under the repository root. After startup,
source the emitted `env.sh` file there if you need the exact socket and port values for local
debugging.

The default phase-1 metrics report compares:

- the direct Swift worker text path
- the direct Python compatibility text path
- the control-plane HTTP/SSE text path

Use JSON output when automation needs a machine-readable report:

```bash
make phase1-metrics PHASE1_METRICS_ARGS="--json"
```

## Local Product Install

Generate a user-scoped local product layout with launch agents, an install manifest, and an
environment export file:

```bash
python3 scripts/install_local_product.py --json
```

Validate the generated install assets without running `launchctl`:

```bash
make phase8-install-smoke
```

The installer writes:

- launch agents under `~/Library/LaunchAgents`
- an install manifest under `~/Library/Application Support/Melix/install-manifest.json`
- an environment export file under `~/Library/Application Support/Melix/melix-product-env.sh`

The full operator flow, including bootstrap and uninstall commands, is documented in
`docs/runbooks/phase-8-local-install.md`.

## Release Gate

Run the deterministic Phase 8 release gate before merge or release tagging:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
```

This checks install asset generation, deterministic benchmark thresholds, restart recovery,
and training sanity against the checked-in policy under
`infra/release/phase8-release-gate-policy.json`.

Generate the final Phase 8 product metrics report:

```bash
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

`make proto` currently generates:

- Swift protobuf message types into `packages/protocol/swift`
- Python protobuf and gRPC artifacts into `packages/protocol/python`

## Repository Policies

- `packages/protocol/schema` is the authoritative interface source.
- Generated protobuf outputs are committed artifacts and must be regenerated after schema changes.
- `uv.lock` is committed and Python environments should be reproduced with `uv sync --frozen`.
- Executable Swift workspaces should commit `Package.resolved` when it exists.
- `docs/product-brief.md` is intentionally ignored and untracked.
- `make coverage` is the repository entrypoint for source coverage checks before commit.

The current phase-status and implementation guidance live under:

- `docs/plans/2026-03-27-phase-0-thin-path.md`
- `docs/plans/2026-03-27-phase-1-swift-text-worker.md`
- `docs/plans/2026-03-28-p1-m6-workflow-integration-metrics.md`
- `docs/runbooks/phase-1-local-stack.md`
- `docs/plans/2026-03-29-p8-m4-packaging-startup-automation.md`
- `docs/plans/2026-03-29-p8-m5-release-gate-automation.md`
- `docs/plans/2026-03-29-p8-m6-release-runbooks-product-acceptance.md`
- `docs/runbooks/phase-8-local-install.md`
- `docs/runbooks/phase-8-release-gates.md`
- `docs/runbooks/phase-8-product-acceptance.md`

## License

Melix is licensed under the Apache License, Version 2.0. See `LICENSE` for the full text.
