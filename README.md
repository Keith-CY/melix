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

When you need the installer to avoid an occupied default port while preserving the requested port
as packaging intent:

```bash
python3 scripts/install_local_product.py \
  --http-port 11434 \
  --prefer-available-http-port \
  --json
```

Validate the generated install assets without running `launchctl`:

```bash
make phase8-install-smoke
```

The installer writes:

- launch agents under `~/Library/LaunchAgents`
- an install manifest under `~/Library/Application Support/Melix/install-manifest.json`
- an environment export file under `~/Library/Application Support/Melix/melix-product-env.sh`

The install manifest now records product version, update-channel path, requested and selected HTTP
ports, ready-probe URL, and worker or control-plane log locations. The environment export file also
surfaces `MELIX_PRODUCT_VERSION` and `MELIX_UPDATE_CHANNEL_PATH`.

Run the deterministic packaged-startup smoke to verify update detection and startup-failure
classification without bootstrapping launch agents:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx \
python scripts/m8_startup_failure_smoke.py --json
```

The full operator flow, including bootstrap and uninstall commands, is documented in
`docs/runbooks/phase-8-local-install.md`.

For same-host service reuse, generate a named sidecar layout instead of reusing the default
product instance:

```bash
python3 scripts/install_local_product.py \
  --service-instance-name team-a \
  --http-port 12434 \
  --json
```

This creates isolated launch agents, runtime roots, managed model roots, and tooling jobs
roots for that consumer.

## Homebrew Install

Install Melix from the checked-out repository with the repository-owned Homebrew formula:

```bash
brew install --formula ./infra/homebrew/Formula/melix.rb
melix-homebrew-service manifest --json
brew services start melix
```

This flow installs the CLI plus the control-plane and text-worker binaries, then supervises the
three-process Melix bundle through the `homebrew` sidecar instance. Detailed install, upgrade,
stop, and prune guidance lives in `docs/runbooks/homebrew-install.md`.

## Packaging Targets

Melix now ships a repository-owned packaging target matrix for Apple Silicon delivery paths. The
current supported targets are:

- `launch_agents_checkout`
- `homebrew_service`
- `macos_app_bundle_preview`

Each target keeps the same logical Melix identity while differentiating packaging metadata, runtime
layout, and update strategy. Build the preview app bundle with:

```bash
python3 scripts/package_macos_menubar_app.py --output-path /tmp/Melix.app --json
```

Validate the shared target matrix with:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx \
python scripts/m8_packaging_target_smoke.py --json
```

Detailed guidance lives in `docs/runbooks/platform-packaging-targets.md`.

## LoRA And Benchmark Operator Flows

The same local control-plane truth now powers both the native operator window and the public
`melix` CLI.

Use the native operator window when you need:

- guided model, dataset, and parameter selection for LoRA training
- adapter activation into a derived text model for local inference
- benchmark suite multi-select, history inspection, charting, and CSV export

Use the CLI when you need reproducible automation or shell integration:

```bash
swift run melix lora list

swift run melix lora train \
  --model-id melix-dev-text::1 \
  --dataset-uri /absolute/path/to/dataset-package \
  --adapter-name melix-dev-adapter \
  --target-repo melix/adapters/melix-dev-adapter

swift run melix lora train \
  --model-id melix-dev-text::1 \
  --hf-dataset-path HuggingFaceH4/ultrachat_200k \
  --hf-train-split train_sft \
  --chat-feature messages \
  --adapter-name melix-ultrachat \
  --target-repo melix/adapters/melix-ultrachat

swift run melix lora activate \
  --model-id melix-dev-text::1 \
  --adapter-path /absolute/path/to/train_lora.adapter.json \
  --alias melix-dev-text-lora

swift run melix bench run \
  --model-id melix-dev-text::1 \
  --suite smoke \
  --suite latency \
  --sample-size 2 \
  --batch-factor 1

swift run melix bench list --json

swift run melix bench export-csv \
  --job-id <benchmark-job-id> \
  --output /tmp/melix-benchmark.csv
```

Detailed operator guidance lives in:

- `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`
- `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`

## External Agent Integrations

Melix can render reproducible setup fragments for external coding-agent clients from the
currently selected desktop server session. The current target set includes:

- `OpenAI-Compatible`
- `OpenClaw`
- `Hermes Agent`
- `OpenCode`
- `Codex`

Run the deterministic smoke command for the export layer:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/m9_agent_export_smoke.py --json
```

Operator guidance for the desktop export picker, target-specific fragment formats, and
placeholder auth behavior lives in `docs/runbooks/external-agent-integrations.md`.

## Shared Access

Melix can switch from implicit local trust to an explicit gateway keyring for shared local
client access. Run the deterministic shared-access smoke with:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/m9_shared_access_smoke.py --json
```

This smoke verifies:

- shared-enabled multi-key acceptance
- missing and unknown key rejection
- configured-but-disabled local-trust compatibility
- shared-access gateway metrics export

Environment examples, operator guidance, and desktop-state expectations live in
`docs/runbooks/shared-access.md`.

## Service-First Reuse

Melix remains an `app + cli` product first. For team reuse, prefer calling Melix as a
same-host sidecar service rather than extracting the inference core into a library.

The stable v1 local reuse surface is:

- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `POST /v1/rerank`
- `GET /v1/models`
- `GET /health`

For repository-local development, a named sidecar instance uses an isolated runtime root:

```bash
MELIX_SERVICE_INSTANCE_NAME=team-a \
MELIX_HTTP_PORT=12434 \
bash scripts/dev_up.sh
```

This defaults the runtime directory to `.runtime/sidecars/team-a` and exports isolated
paths for models, runtime packs, and tooling jobs.

Operator guidance for service-first reuse and same-host sidecars lives in
`docs/runbooks/service-first-reuse.md`.

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
- `docs/runbooks/service-first-reuse.md`
- `docs/runbooks/phase-8-release-gates.md`
- `docs/runbooks/phase-8-product-acceptance.md`

## License

Melix is licensed under the Apache License, Version 2.0. See `LICENSE` for the full text.
