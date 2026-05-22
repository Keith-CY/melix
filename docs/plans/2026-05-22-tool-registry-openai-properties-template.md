# Tool registry OpenAI properties template reuse

## Scope

This Python-only performance slice targets `ToolRegistry.as_openai_tools()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-openai-tools-template-cache` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries covering the
runtime source, focused tool-registry tests, PR-scoped performance selection,
and `scripts/tool_registry_openai_tools_probe.py`.

## Change

`ToolRegistry.__init__()` previously converted each descriptor's cached schema
property dictionaries into `(name, type, description)` tuples, then
`as_openai_tools()` rebuilt the tiny `{"type": ..., "description": ...}`
dictionaries on every call. This slice keeps the descriptor's cached property
templates in the OpenAI tool template and uses `schema.copy()` per emitted tool
payload.

Behavior remains unchanged: callers still receive fresh mutable payloads, and
mutating a returned `properties` entry or `required` list does not alter the next
`as_openai_tools()` result. The slice only removes repeated literal-dict
reconstruction in the hot path.

## Validation plan

1. Run the focused tool-registry tests and PR-scoped performance registry tests.
2. Run changed-scope coverage for the changed source path, focused tests, probe
   tests, and probe script.
3. Run the registered local Linux probe against `origin/main` and this branch.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local result

Local Linux registered probe (`tool-registry-openai-tools-template-cache`,
`MELIX_TOOL_REGISTRY_OPENAI_TOOLS_ITERATIONS=50000`, default samples=5):

- base (`origin/main`): `elapsed_ms_mean=467.417690`
- head: `elapsed_ms_mean=458.931321`
- delta: `-8.486369 ms` (`-1.82%`)
- guard rails unchanged: `descriptor_as_openai_tool_calls_mean=0.0`,
  `isolated_payload_calls_mean=50000.0`, `checksum=1500000.0`
