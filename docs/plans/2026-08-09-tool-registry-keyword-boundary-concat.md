# Tool Registry Keyword Boundary Concatenation

## Scope

This Python-only performance slice keeps tool-selection behavior unchanged while
using direct string concatenation for keyword-boundary text construction.

## Registered Probe

The affected path is already covered by the PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `scripts/tool_registry_select_probe.py`

## Implementation Plan

1. Reuse the existing focused tool-registry behavior tests for keyword routing
   and schema-consistency receipts.
2. Replace the boundary helper f-string with direct string concatenation around
   the translated text.
3. Verify with focused pytest, changed-scope coverage, and the registered local
   probe on Linux.

## Metrics

The registered probe reports selector and no-keyword fallback timings that call
`_keyword_boundary_text()` repeatedly. This slice expects neutral-to-positive
movement on those selector metrics while preserving exact selected-tool output.