# MCP Tooling

## Purpose

Load repository-owned MCP tool configuration into the Melix control plane and verify that enabled tool namespaces are auto-injected into supported structured-tool request paths.

## Configuration Shape

Point `MELIX_MCP_CONFIG_PATH` at a JSON file with this structure:

```json
{
  "default_parser_mode": "json",
  "sources": [
    {
      "source_id": "filesystem",
      "enabled": true,
      "namespaces": ["tools.fs.read", "tools.fs.write"]
    }
  ]
}
```

Rules:

- `default_parser_mode` is used when no request-level or model-level parser selection is already present.
- Only enabled sources contribute namespaces to auto-injection.
- Namespaces are deduplicated in source order after disabled sources are removed.

## Runtime Behavior

- The control-plane handshake advertises the `mcp-tools` feature when MCP configuration is present.
- The effective MCP catalog appears in the typed server snapshot under `mcp_tools`.
- Structured text requests record `melix.mcp.source_ids` when MCP namespaces are auto-injected.
- Control-plane metrics record `mcp.tool_injection_count`, `mcp.configured_tool_count`, and `mcp.tool_injection_success_rate`.

## Deterministic Smoke

Run the repository-owned smoke command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/m9_mcp_smoke.py --json
```

The smoke command:

- writes a temporary MCP config fixture
- boots the deterministic local Melix stack with `MELIX_MCP_CONFIG_PATH`
- sends one `/v1/responses` request
- verifies that MCP injection metrics were recorded

## Troubleshooting

- If the handshake does not advertise `mcp-tools`, confirm `MELIX_MCP_CONFIG_PATH` points at a readable file.
- If `mcp.tool_injection_count` stays at `0`, confirm the request path is a structured-tool-capable text endpoint and not an unsupported route.
- If the control plane starts but no namespaces are injected, inspect the source `enabled` flags and make sure each namespace string is non-empty.
