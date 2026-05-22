# Tool Registry OpenAI Tools Template Cache

## Scope

This slice targets `ToolRegistry.as_openai_tools()` in the Python worker agentic tool registry. The method is called when building OpenAI-compatible tool schemas for the built-in agentic tool set.

## Current behavior

Each call returns isolated mutable OpenAI tool dictionaries so callers can mutate exported payloads without affecting future registry exports.

## Optimization

Cache the per-registry OpenAI tool templates during `ToolRegistry` construction and copy from those templates on export. This avoids re-entering each `ToolDescriptor.as_openai_tool()` on repeated exports while preserving isolated nested `parameters.properties` and `parameters.required` payloads.

The 2026-05-22 follow-up keeps the same public behavior and narrows the hot loop further by binding `dict.copy` once per `as_openai_tools()` call before copying cached schema property dictionaries. This removes one repeated method lookup per exported argument schema while preserving isolated mutable payloads.

## Probe

Registered PR-scoped probe: `tool-registry-openai-tools-template-cache`.

- `test_command` runs the focused tool registry tests and the probe smoke test.
- `coverage_command` measures changed-scope coverage for the registry, tests, and probe script; the JSON registry entry is validated by the focused PR-scoped performance tests.
- `probe_command` runs `scripts/tool_registry_openai_tools_probe.py` and records elapsed time plus descriptor export calls.

## Acceptance

- Focused behavior tests pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe reports `descriptor_as_openai_tool_calls_mean=0` after registry construction and an improved `elapsed_ms_mean` against `origin/main`.
