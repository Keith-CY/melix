# MCP Tooling

## Purpose

Load operator-owned MCP configuration into the Melix control plane. A source
may be a legacy catalog-only namespace source or a live MCP source with an
explicit stdio or Streamable HTTP transport.

## Configuration Shape

Point `MELIX_MCP_CONFIG_PATH` at a JSON file with this structure:

```json
{
  "default_parser_mode": "json",
  "sources": [
    {
      "source_id": "filesystem",
      "enabled": true,
      "transport": {
        "kind": "stdio",
        "command": "/absolute/path/to/mcp-server",
        "arguments": ["--stdio"],
        "working_directory": "/absolute/path/to/workspace",
        "environment_references": {
          "SERVICE_TOKEN": "MELIX_FILESYSTEM_MCP_TOKEN"
        }
      },
      "request_timeout_ms": 30000,
      "connect_timeout_ms": 15000,
      "max_result_bytes": 262144,
      "configuration_revision": "filesystem-v1"
    },
    {
      "source_id": "search",
      "enabled": true,
      "transport": {
        "kind": "streamable_http",
        "url": "https://mcp.example.com/rpc",
        "headers": {
          "X-Client": "melix"
        },
        "header_environment_references": {
          "Authorization": "MELIX_SEARCH_MCP_AUTHORIZATION"
        }
      }
    },
    {
      "source_id": "legacy-catalog",
      "enabled": true,
      "namespaces": ["tools.read"]
    }
  ]
}
```

Rules:

- Discovery order is `MELIX_MCP_CONFIG_PATH`, then
  `$MELIX_HOME/config/mcp-tools.json`, then no MCP config.
- Melix does not discover `./mcp-tools.json` or any other process current
  working directory file during packaged/default local launch.
- `default_parser_mode` is used when no request-level or model-level parser selection is already present.
- A live source requires exactly one explicit `transport` object. Stdio
  commands are passed as command and argument vectors; they are not evaluated
  by a shell. Streamable HTTP requires HTTPS except for loopback development
  endpoints. Streamable HTTP URLs must not contain userinfo or fragments.
- Credential values are never stored in the MCP catalog. The values in
  `environment_references` and `header_environment_references` are names of
  environment variables that the worker resolves at connection time. Static
  HTTP headers are limited to non-credential metadata; credential-bearing
  headers such as `Authorization`, `Cookie`, and API-key headers must use
  `header_environment_references`. Resolved credential header values are
  mandatory result-redaction terms.
- Only environment values referenced by the active configuration at worker
  startup are exposed to the Python tool worker. Introducing a new credential
  source key after startup is restart-required and fails closed; unrelated
  parent credentials are never escrowed by the worker.
  Development and packaged launchers build every other child environment from
  a reserved minimal allowlist, so a config change cannot turn an already
  inherited arbitrary value into a newly exposed credential. The resolver
  accepts only bounded JSON and environment names matching
  `^[A-Z_][A-Z0-9_]*$`; invalid or unreadable active configuration stops App
  launch without printing credential values. Source keys, stdio child names,
  and HTTP header names are limited to 255 UTF-8 bytes each. The config accepts
  at most 1,024 credential references across stdio and HTTP; the raw reference
  target-name list and deduplicated comma-separated source-key list are each
  limited to 32,768 bytes. Separately, all raw static and referenced HTTP
  header-name entries across the config share a 1,024-entry and 32,768-byte
  budget; an HTTP reference counts against both budgets. HTTP static and
  referenced names must use RFC token-compatible header-name characters and
  must be unique case-insensitively within one transport. The active file must
  be a regular file no larger than 1 MiB. Launcher, App, and direct-daemon
  readers open the resolved final path with no-follow and non-blocking flags,
  then classify, size-check, and bounded-read the same file descriptor; FIFO,
  device, directory, and final-component symlink replacements fail closed before
  any bytes are consumed. Duplicate JSON object keys,
  non-standard numeric constants, non-integer numeric lexical tokens, explicit
  null for known fields, nesting beyond 128, more than 16,384 value tokens, or
  more than 8,192 object members
  are refused. A config may contain at most 256 sources. Source IDs normalize
  to the worker contract
  `^[a-z0-9][a-z0-9_-]{0,63}$` and must remain unique after normalization.
  Launcher and App preflight also reject unsupported transport kinds, missing
  required command or URL fields, and malformed transport field types before
  the stack is forked. The control plane repeats these file, source, transport,
  reference, and identifier checks even when started directly without an App or
  development launcher.
  The initial active snapshot is deduplicated, bounded, and frozen before any
  child is forked. A post-start refresh may only remove keys from that snapshot;
  adding a credential key fails closed and requires a stack restart. The Python
  tool worker receives values only for the frozen snapshot, while the App
  sentinel receives that same key list solely to sanitize descendant processes.
  After trimming,
  `MELIX_MCP_CONFIG_PATH` must be absolute or use current-user `~` / `~/...`
  syntax; relative paths, `~otheruser`, NUL, and paths over 4096 UTF-8 bytes are
  refused. `HOME` participates in tilde expansion only when it is absolute;
  otherwise Melix uses the platform current-user home. Credential references
  must not reuse launcher-owned names such as `MELIX_MCP_CONFIG_PATH`, `MELIX_HOME`,
  `HOME`, `PATH`, private socket/key names, or Swift probe overrides.
- Typed stdio and Streamable HTTP source admission in the Python worker rejects
  the same reserved names before initialization. A rejected source returns
  `mcp_source_configuration_invalid` and does not resolve or log its value.
- Only enabled catalog-only sources contribute namespaces to the legacy
  prompt-injection path. Live sources are discovered with MCP `tools/list` and
  are executed only through the agent runtime.
- Namespaces are deduplicated in source order after disabled sources are removed.
- High-risk namespaces from enabled sources are blocked by default before auto-injection. Namespace
  strings containing execution, shell, process, write-filesystem, or upload markers are refused
  unless the exact namespace is allowlisted through `MELIX_MCP_HIGH_RISK_ALLOWLIST`.

Example operator allowlist:

```bash
MELIX_MCP_HIGH_RISK_ALLOWLIST=tools.fs.write,tools.network.upload \
MELIX_MCP_CONFIG_PATH=/path/to/mcp.json \
bash scripts/dev_up.sh
```

## Runtime Behavior

- The control-plane handshake advertises the `mcp-tools` feature when MCP configuration is present.
- The effective MCP catalog appears in the typed server snapshot under `mcp_tools`.
- `mcp_tools.sources` starts with a `config-discovery` receipt. Its namespace
  records the active discovery source: `environment`, `melixHome`, `explicit`,
  or `none`.
- `mcp_tools` includes the requested policy, effective policy, operator override source, and
  refused namespaces so operator surfaces can explain why configured tools were not exposed.
- Structured text requests record `melix.mcp.source_ids` when MCP namespaces are auto-injected.
- Live source configuration is sent over the typed worker
  `ListAgentTools` RPC. The Python worker owns initialization, catalog refresh,
  `tools/call`, timeout, reconnect, result bounding, and cancellation.
- Removing or disabling a source closes its connection and removes its live
  catalog. `refresh_sources` forces a reconnect.
- If the selected configuration file cannot be read or decoded, Agent
  Operations exposes a failed `config-discovery` source with
  `config_unreadable` or `config_invalid`. Treat that receipt as a repair state;
  it is not equivalent to an intentionally empty tool catalog.
- `scripts/dev_app_up.sh` resolves credential-reference names before backend
  startup and verifies them again immediately before launching the app. The
  refreshed set must be a subset of the frozen initial snapshot; a newly added
  key fails closed, rolls back the just-started stack, and requires restart.
  The app and its CLI subprocesses sanitize the complete frozen initial
  snapshot.
- Control-plane metrics record `mcp.tool_injection_count`, `mcp.configured_tool_count`,
  `mcp.refused_tool_count`, and `mcp.tool_injection_success_rate`.

## Deterministic Smoke

Run the repository-owned smoke command:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/m9_mcp_smoke.py --json
```

The smoke command:

- writes a temporary MCP config fixture
- verifies that default policy injects safe namespaces while refusing one high-risk namespace
- boots the deterministic local Melix stack with `MELIX_MCP_CONFIG_PATH`
- sends one `/v1/responses` request
- verifies that MCP injection metrics were recorded

## Troubleshooting

- If the handshake does not advertise `mcp-tools`, confirm
  `MELIX_MCP_CONFIG_PATH` points at a readable file or
  `$MELIX_HOME/config/mcp-tools.json` exists.
- If a repo-local `mcp-tools.json` is ignored, move it under `MELIX_HOME/config`
  or pass it explicitly with `MELIX_MCP_CONFIG_PATH`.
- If a configured namespace is absent from the effective catalog, inspect `mcp_tools.refused_namespaces`
  and `mcp.refused_tool_count`.
- If `mcp.tool_injection_count` stays at `0`, confirm the request path is a structured-tool-capable text endpoint and not an unsupported route.
- If the control plane starts but no namespaces are injected, inspect the source `enabled` flags and make sure each namespace string is non-empty.
