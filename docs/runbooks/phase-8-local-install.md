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
  --http-port 12436 \
  --prefer-available-http-port \
  --json
```

This writes:

- user launch agents under `~/Library/LaunchAgents`
- an install manifest under `~/.melix/install/install-manifest.json`
- an environment export file under `~/.melix/install/melix-product-env.sh`
- product state, configuration, models, jobs, runtime packs, and logs under `~/.melix`

Upgrade note: sidecar installs now write instance state under
`~/.melix/sidecars/<instance-name>`. Older local installs may still have launch agents,
environment scripts, logs, and runtime state under
`~/Library/Application Support/Melix/sidecars/<instance-name>`. After upgrading, rerun
`python3 scripts/install_local_product.py --service-instance-name <instance-name> --json`
for each sidecar instance so the generated LaunchAgent environment points at the new
Melix home layout. Unload or prune old LaunchAgents with `scripts/uninstall_local_product.py`
before deleting the old App Support sidecar directory.

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
curl -sS http://127.0.0.1:12436/v1/models
```

Registry-discovered models are synchronized on demand before `/v1/models` is rendered. The response metadata includes the structured `melix.registry_*` identity fields plus `melix.model_path` for each discovered registry model.

Melix-managed Hugging Face downloads write model bytes directly to the default Hugging Face cache at `~/.cache/huggingface/hub`. Melix passes that directory as `snapshot_download(cache_dir=...)`, so `HUGGINGFACE_HUB_CACHE` and `HF_HOME` do not change the managed download destination. A Hub download receipt reports the real snapshot directory, for example `~/.cache/huggingface/hub/models--mlx-community--Qwen3-0.6B-4bit/snapshots/<snapshot-id>`, and new downloads do not create descriptor directories under `MELIX_MANAGED_MODEL_ROOT`.

Registry scanning reads user-configured model roots first and then appends `~/.cache/huggingface/hub` as the implicit default cache root when it exists. It discovers Hugging Face cache snapshots under `models--<org>--<repo>/snapshots/<snapshot-id>` and plain local MLX directories that contain `config.json` plus weights. Only models with explicit MLX compatibility signals are shown. Non-MLX Transformers repositories, ambiguous local folders, unreadable metadata, and Hugging Face `blobs` payloads are ignored. If a cache snapshot is removed and the registry is rescanned, that model disappears from `melix model list` and `/v1/models`; it does not remain as a missing-cache descriptor entry.

Private Hugging Face repositories can be downloaded with a token:

```bash
melix model hub download \
  --repo-id mlx-community/Qwen3-0.6B-4bit \
  --revision main \
  --hf-token "$HF_TOKEN"
```

The token is cached at `$MELIX_HOME/secrets/huggingface-token.json` with private permissions and reused by later `melix model hub download` commands when `--hf-token` is omitted. The Desktop App Hugging Face download form has the same behavior: a filled token field saves and uses the token, while an empty field uses the cached token if present. CLI and App surfaces only show a masked saved-token hint. Raw tokens must not appear in operation state, model metadata, `/v1/models`, logs, or evidence artifacts. Hugging Face 401/403 failures are reported as `hf_auth_failed` with `Hugging Face authentication failed. Check your token and try again.`

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

For deterministic packaged VLM artifact-cache recovery without network access or a live
VLM runtime:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python scripts/packaged_vlm_artifact_cache_smoke.py --json
```

The smoke uses a flat cache layout with `model.gguf` and `mmproj.gguf`, preserves
`model.gguf.partial` after a cancelled first pass, resumes the second pass from
the saved bytes, and emits a route receipt containing:

- `model_artifact_path`
- `companion_projector_path`
- `cache_layout`
- `cache_restore_status`
- `local_route_verified`

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
