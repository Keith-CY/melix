# External Agent Integrations

## Purpose

Render reproducible external coding-agent setup artifacts from the currently selected Melix provider without copying live secrets into repository-owned examples.

## Supported Targets

- `OpenAI-Compatible`
- `OpenClaw`
- `Hermes Agent`
- `OpenCode`
- `Codex`

Every target is generated from one canonical Melix provider projection:

- listener base URL: `http://<host>:<port>/v1`
- served model ID
- auth mode
- auth placeholder derived from the configured token hint or `not-required`

## Export Shapes

The desktop shell renders two canonical artifacts for every supported target:

- a config fragment shaped for that target
- a shell snippet that points the target at the selected Melix listener

Current fragment formats:

- `OpenAI-Compatible`: JSON
- `OpenClaw`: YAML
- `Hermes Agent`: TOML
- `OpenCode`: JSON
- `Codex`: environment-variable block

When the selected provider uses bearer auth, Melix renders a placeholder such as `<dev-token>` or `<smoke-token>`. When auth is disabled, Melix renders `not-required`.

## Desktop Operator Flow

1. Open the Melix menu bar app.
2. Select the provider whose listener and model should be exported.
3. Open either the `Server` inspector or the `API` workspace.
4. Choose the target integration from the shared export picker.
5. Copy the generated config fragment or shell snippet.

The exported content always rebinds to the currently selected provider. Changing host, port, model, or auth mode updates every target-specific export.

## Deterministic Smoke

Run the repository-owned smoke command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/m9_agent_export_smoke.py --json
```

The smoke command:

- runs a Swift smoke test against `AgentIntegrationExport.exports(from:)`
- validates that every supported target is rendered from the same fixture provider
- reports deterministic setup metrics for the exported target count and setup success rate

## Metrics

M9.2 records these metrics in the touched scope:

- `integration.export_generation_ms`
- `integration.export_target_count`
- `integration.setup_success_rate`

`integration.setup_success_rate` is currently derived from the deterministic smoke command because repository-local end-to-end launches of every external tool are not yet practical inside the worktree.
