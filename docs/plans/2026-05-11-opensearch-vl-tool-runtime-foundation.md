# OpenSearch-VL Tool Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first unified tool runtime contract slice for the OpenSearch-VL alignment track: a deterministic Python worker tool registry contract that can later be reused by training replay, rollout, benchmark, and evaluation paths.

**Architecture:** The Python worker runtime owns the initial registry contract because current agentic trace construction, deterministic VLM tooling hooks, and evaluation/benchmark evidence are worker-side. This slice defines stable tool descriptors and schema export helpers only. It does not execute tools, redact observations, or route evaluation/rollout through tools; those remain separate executable units.

**Tech Stack:** Python 3.12, dataclasses, Melix worker protobuf `ToolConfig`, `pytest`.

---

## Scope

- Covers GitHub issue #676 under direction #674 / milestone #675.
- Defines canonical built-in tool names for image crop, layout parsing, text search, image search, visit, and local compute.
- Adds deterministic registry validation and worker `ToolConfig` export.
- Updates the architecture spec with the worker-side source-of-truth boundary for agentic tools.
- Does not implement concrete adapters, network search, browser visits, Python execution, observation redaction, replay metadata, or evaluation routing.

## Files

- Create: `services/mlx-worker-python/worker/runtime/tool_registry.py`
- Create: `services/mlx-worker-python/tests/test_tool_registry.py`
- Modify: `docs/architecture-spec.md`
- Create: `docs/plans/2026-05-11-opensearch-vl-tool-runtime-foundation.md`

## Metrics And Probes

- `tool_registry.tool_count`: number of exported built-in tools.
- `tool_registry.schema_bytes`: total serialized JSON schema bytes for the exported tool set.
- `tool_registry.required_argument_count`: total required argument names across exported tools. The first built-in registry has seven required arguments and leaves execution policy knobs such as limits, extraction mode, and purpose optional.
- Success metric: focused registry tests pass with changed-line coverage at or above 95 percent for the touched Python module.

## Implementation Tasks

### Task 1: Plan And Red Tests

- [x] Add this plan under `docs/plans/`.
- [x] Add focused tests for the built-in tool names and deterministic ordering.
- [x] Add tests that exported JSON schemas are valid object schemas with required fields.
- [x] Add tests for duplicate tool names and unknown requested names.
- [x] Add tests for worker `ToolConfig` export metadata.
- [x] Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py
```

Expected: fail until `worker.runtime.tool_registry` exists.

### Task 2: Registry Contract Implementation

- [x] Add frozen dataclass descriptors for tool arguments, tools, and registry metrics.
- [x] Define built-in descriptors for `image_crop`, `layout_parse`, `text_search`, `image_search`, `visit`, and `local_compute`.
- [x] Validate stable names, duplicate names, and requested-name filters.
- [x] Export OpenAI-compatible function tool schemas and Melix worker `ToolConfig` metadata.
- [x] Keep schema serialization deterministic with sorted keys and compact separators.

### Task 3: Documentation And Verification

- [x] Update `docs/architecture-spec.md` with the tool registry ownership boundary.
- [x] Run the focused pytest command from Task 1 and confirm it passes.
- [x] Run changed-line coverage for `worker/runtime/tool_registry.py`.
- [x] Run `git diff --check`.
- [x] Record metrics and verification output in PR evidence.

## Success Criteria

- The Python worker can export the six built-in tool contracts in a deterministic order.
- The exported schemas are valid JSON object schemas with explicit required fields.
- Duplicate registry entries and unknown requested tool names are rejected with actionable errors.
- Worker `ToolConfig` includes schema format, schema version, toolset version, parser, and parser contract version.
- Focused tests pass.
- Changed-line coverage for `tool_registry.py` is at least 95 percent.
- `git diff --check` passes.
