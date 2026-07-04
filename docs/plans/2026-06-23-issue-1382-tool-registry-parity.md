# Issue 1382 Tool Registry Parity Slice

## Goal

Add a focused agent tool availability guardrail that keeps Melix worker tool
schemas, index metadata, and deterministic routing in sync for selectable
agentic tools.

## Governing Documents

- `AGENTS.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/plans/2026-03-30-m3-6-tool-parser-registry.md`
- `docs/plans/2026-06-08-issue-1761-workspace-file-tools.md`
- `docs/plans/2026-05-24-issue-1384-openai-conformance-suite.md`

The OpenAI conformance plan keeps required tool-choice and compatibility work
inside the Swift control-plane boundary. This slice stays in the Python worker
tool registry and does not change OpenAI request handling.

## Scope

This slice covers:

- a lightweight parity fixture for selectable agentic tool schemas, index
  metadata, and keyword routing metadata;
- one non-default local integration tool schema for workspace file operations;
- deterministic routing for workspace file intent prompts;
- focused Python tests and changed-scope coverage for the touched worker
  registry path.

This slice does not implement the full issue #1382 guardrail product, response
rescue, required tool-choice conformance, MCP registration policy, or live shell
command execution.

## Architecture

The best end state is a single registry-owned source of truth for model-visible
tool schemas and prompt/index affordances. Every selectable schema must have
index metadata with a retrieval description. Tools that are not always
available must also provide keyword hints so deterministic routing can include
the intended schema before generation.

This PR implements that as a small worker-only slice:

- `ToolIndexMetadata` describes prompt/index-facing metadata for each selectable
  tool.
- `_BUILTIN_TOOL_INDEX_METADATA` owns retrieval descriptions and keyword hints.
- `_BUILTIN_TOOL_KEYWORD_HINTS` is derived from index metadata so schema and
  index fixtures cannot drift silently.
- `workspace_file` is added as a non-default selectable local integration tool
  over the existing workspace file operator primitive.

## Performance Probes And Metrics

The changed path only adds constant-size metadata and one additional selectable
tool. Existing registered probes for `tool_registry.py` cover schema bytes,
name selection, and selector planning:

- `tool-registry-schema-bytes-cache`
- `tool-registry-select-name-index-cache`
- `tool-registry-names-snapshot-cache`
- `tool-registry-openai-tools-template-cache`

The local metrics report for this slice is:

- selectable tool parity: all selectable schema names have index metadata;
- routing precision: a workspace-file prompt includes `workspace_file`;
- unrelated greeting precision: a greeting only includes always-available
  `local_compute`;
- changed-scope coverage for `tool_registry.py`, `agentic_tools.py`, and
  their focused tests, plus `workspace_file_tools.py` when review fixes touch
  workspace-file result semantics.

## TDD Plan

1. Add failing tests to `services/mlx-worker-python/tests/test_tool_registry.py`
   for schema/index metadata parity and workspace-file integration-intent
   routing.
2. Run the focused tests and confirm they fail because index metadata and
   `workspace_file` schema/routing are absent.
3. Implement `ToolIndexMetadata`, index metadata parity helpers, and the
   `workspace_file` selectable schema and routing hints in
   `services/mlx-worker-python/worker/runtime/tool_registry.py`.
4. Update `docs/unified-agentic-tool-runtime-contract.md` so `workspace_file`
   is listed as a selectable non-default tool and the registry contract requires
   index metadata parity.
5. Run focused tests, changed-scope coverage, the relevant registered probe, and
   `git diff --check` before committing.

## Verification Commands

Focused red/green:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_tool_registry.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_agentic_tools.py
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_agentic_tools.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
UV_PYTHON=3.12 uv run python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/worker/runtime/agentic_tools.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_agentic_tools.py
```

Metrics/probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python3 scripts/tool_registry_select_probe.py
```

General checks:

```bash
git diff --check
```
