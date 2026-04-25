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

When the default local HTTP port might already be occupied, ask the installer to keep the requested
port as intent while selecting the next available port in the generated manifest:

```bash
python3 scripts/install_local_product.py \
  --http-port 11434 \
  --prefer-available-http-port \
  --json
```

This writes:

- user launch agents under `~/Library/LaunchAgents`
- an install manifest under `~/Library/Application Support/Melix/install-manifest.json`
- an environment export file under `~/Library/Application Support/Melix/melix-product-env.sh`

This install flow maps to the `launch_agents_checkout` packaging target. The generated manifest and
environment export now carry the shared Melix logical identity plus:

- `packaging_target_id = launch_agents_checkout`
- `packaging_kind = launch_agents`
- `distribution_channel = local_checkout`

The generated install manifest is the packaging source of truth for:

- the resolved Melix product version
- the repository-owned update-channel path
- the requested and selected HTTP port
- the ready probe URL used by startup verification
- the stdout and stderr log locations for the control plane, Swift text worker, and Python worker

The environment export file now also includes:

- `MELIX_LOGICAL_PRODUCT_ID`
- `MELIX_PACKAGING_TARGET_ID`
- `MELIX_PACKAGING_KIND`
- `MELIX_PRODUCT_VERSION`
- `MELIX_UPDATE_CHANNEL_PATH`

By default the installer resolves the version from the repository Python package metadata and points
the update feed to `infra/packaging/update-channels/stable.json`. Override either value explicitly
when packaging or testing alternate release metadata:

```bash
python3 scripts/install_local_product.py \
  --product-version 0.2.0 \
  --update-channel-path /absolute/path/to/channel.json \
  --json
```

## Registry Layout

When `MELIX_MODEL_ROOTS` is set, the Python worker scans each root in order and discovers model sidecars from one of these directory shapes:

- `<organization>/<model>/<variant>/manifest.json`
- `<provider>/<organization>/<model>/<variant>/manifest.json`

Sidecar manifests may override the path-derived identity with these optional fields:

- `provider_id`
- `organization_id`
- `model_name`
- `variant_id`

Melix preserves the actual root-relative directory in `melix.registry_relative_path`, even when one of the identity fields is overridden. Artifacts outside the supported three-level or four-level directory depth are skipped during registry scans.

## Download State

Worker-owned download jobs now persist a machine-readable state file alongside the target artifact:

- `download.artifact.partial` while bytes are still being copied or retried
- `download.state.json` for the latest operator-visible transfer state
- `download.artifact` after the terminal successful rename

The JSON state snapshot records at least these fields:

- `selected_mirror`
- `downloaded_bytes`
- `total_bytes`
- `resume_used`
- `resume_from_bytes`
- `retry_count`
- `stall_detection_count`
- `stall_reason`
- `terminal_state`

This state is intended to remain stable enough for later desktop queue recovery and release-gate automation.

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

Registry-discovered models are synchronized on demand before `/v1/models` is rendered. The response metadata includes the structured `melix.registry_*` identity fields plus `melix.model_path` for each discovered registry model.

Managed Hugging Face imports use a descriptor/cache split. The managed root contains the Melix descriptor path, for example `huggingface/mlx-community/Qwen3-0.6B-4bit/main/manifest.json`, while `melix.model_path` points to the actual Hugging Face snapshot under the standard cache (`HUGGINGFACE_HUB_CACHE`, `HF_HOME/hub`, or `~/.cache/huggingface/hub`). Use `melix.registry_descriptor_path` when debugging Melix registry metadata and `melix.model_path` when debugging runtime loading. If the cache snapshot has been removed, registry metadata includes `melix.model_path_missing=true`; Melix surfaces this as `missing-cache` / `model_runtime_missing` with the message `Hugging Face cache files are missing. Re-download this model to restore it.` The Desktop App keeps the model visible, shows a `Missing cache` badge, and changes the model action to `Restore Download`. CLI operators can confirm the state with `melix model list` or `melix model inspect --model-id <model> --json`, then restore with the reported `restore_command`, for example `melix model hub download --repo-id mlx-community/Qwen3-0.6B-4bit --revision main`, followed by `melix model roots rescan` if the app or daemon has not refreshed yet. Melix does not auto-download missing Hugging Face snapshots. Managed import `downloaded_bytes` and `total_bytes` report the runtime snapshot size, not the lightweight descriptor size. Local imports are unchanged and still copy model files into `local/<model-id>/<revision>` under the managed root.

For deterministic install smoke without `launchctl`, validate asset generation only:

```bash
python3 scripts/phase8_install_smoke.py --json
```

For deterministic update-check and startup-failure diagnostics without `launchctl`, run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
python scripts/m8_startup_failure_smoke.py --json
```

For deterministic packaging target validation across launch agents, Homebrew, and app-bundle
outputs, run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
python scripts/m8_packaging_target_smoke.py --json
```

For deterministic download resume, retry, and stall smoke without network access:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/m8_download_smoke.py --json
```

For deterministic MCP tool-loading and auto-injection smoke:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/m9_mcp_smoke.py --json
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

## Update And Startup Diagnostics

Packaged Melix installs now use a repository-owned update feed at
`infra/packaging/update-channels/stable.json`. The native operator shell reads the install manifest,
compares the installed version against the configured channel, and surfaces one of these states:

- `Update available: <version>`
- `Update: up to date`
- `Update: check failed`

When startup fails before the ready probe returns, the menu bar operator shell loads the same
install manifest and derives an actionable diagnostic from the recorded log paths. The current
classifications are:

- `host_port_conflict`
- `control_plane_crash`
- `worker_crash`
- `startup_hang`

For `host_port_conflict`, Melix points operators at the conflicting HTTP port, the authoritative
ready probe URL, and the control-plane stderr log. For crash and hang cases, the operator shell
surfaces the most relevant recorded log path and last-line excerpt without introducing a second
startup state store outside the install manifest contract.
