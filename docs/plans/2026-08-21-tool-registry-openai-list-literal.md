# Tool Registry OpenAI List Literal Fast Path

## Context

The PR-scoped performance probe `tool-registry-openai-tools-template-cache` covers
`ToolRegistry.as_openai_tools()`, including template reuse, returned payload
isolation, focused tests, changed-scope coverage, and the registered command JSON
probe.

## Slice

Keep the existing OpenAI tool payload semantics and template cache, but build the
per-call returned list with a single list literal/comprehension. The slice avoids
changing selection, schema validation, protobuf config generation, or tool
catalog contents.

## Verification

- Focused tool registry tests through the registered probe `test_command`.
- Changed-scope coverage through the registered probe `coverage_command`.
- Local Linux command JSON probe through the registered `probe_command`.
- GitHub PR-scoped performance workflow after pushing the PR.

## Linux Boundary

This is a Python hot-path slice and is locally verifiable on Linux. No Swift
runtime effect is claimed for this slice.
