# Tool registry worker config template copy slice

## Scope

This Python-only performance slice targets `services/mlx-worker-python/worker/runtime/tool_registry.py` and is limited to `ToolRegistry.as_worker_tool_config()` cache reuse.

The affected path is covered by the registered PR-scoped probes in `infra/perf/pr_scoped_probes.json` for `services/mlx-worker-python/worker/runtime/tool_registry.py`. The primary local metric for this slice comes from `tool-registry-schema-bytes-cache`, whose focused `test_command`, `coverage_command`, and `probe_command` include the built-in and partial worker tool config paths. The registry also selects the related tool registry probes for name selection, names snapshot, and OpenAI tool template behavior when this source path changes.

## Optimization

Before this slice, repeated `as_worker_tool_config()` calls cached serialized protobuf bytes and reparsed them on every call. The new path caches a protobuf template object and returns isolated `CopyFrom` copies from that template. Local micro-measurement showed template `CopyFrom` is faster than reparsing the serialized bytes for this small hot config, while still preserving mutation isolation for every returned `ToolConfig`.

## Verification plan

- Add focused regression coverage proving the cached path avoids descriptor rebuilds and serialized-byte reparsing.
- Verify the first returned `ToolConfig` is also isolated from the cached template.
- Run the registered tool registry focused test command.
- Run changed-scope coverage for the modified source, tests, registry, and probe script.
- Run the registered `tool-registry-schema-bytes-cache` PR-scoped probe locally on Linux against `origin/main` vs this worktree.

## Boundaries

This slice is Python-only and locally verifiable on Linux. No Swift runtime performance claim is made.
