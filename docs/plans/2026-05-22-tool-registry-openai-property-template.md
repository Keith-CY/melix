# Tool Registry OpenAI Property Template

Date: 2026-05-22

## Scope

This Python performance slice is limited to `ToolRegistry.as_openai_tools()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Problem

The OpenAI tool schema path must return fresh mutable dictionaries on every call,
but the cached registry template previously stored small per-argument schema
dictionaries and copied each one while building the returned payload. The hot
path only needs the stable argument name, JSON type, and description values to
reconstruct isolated response dictionaries.

## Optimization slice

Store each cached OpenAI tool property template as `(name, json_type,
description)` strings when the registry is initialized. `as_openai_tools()` then
constructs the required fresh nested dictionaries directly from those immutable
strings instead of copying cached dictionaries.

Behavior remains unchanged:

- `ToolDescriptor.as_openai_tool()` is still bypassed by registry-level cached
  templates.
- Returned OpenAI tool payloads remain independently mutable.
- Tool names, descriptions, kinds, observation kinds, and schema fields are
  unchanged.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-openai-tools-template-cache` in
`infra/perf/pr_scoped_probes.json`. The probe entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for this source
file, the focused tool-registry tests, the PR-scoped probe tests, and
`scripts/tool_registry_openai_tools_probe.py`.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command and require at least 95%
  changed-line coverage for touched scope.
- Run `scripts/tool_registry_openai_tools_probe.py` before and after the change
  and compare `elapsed_ms_mean` while preserving checksum,
  `descriptor_as_openai_tool_calls_mean == 0`, and mutation isolation.
- Use GitHub Actions PR-scoped performance as the merge gate after pushing.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claims are made.
