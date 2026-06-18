# Status Override Tool Output Receipt Plan

## Issue

GitHub issue #1761 tracks untrusted-context boundaries for retrieved docs,
skills, memories, and tool output.

## Goal

Attach source-specific `tool_output` untrusted-context receipts to deterministic
tool observations produced by fixture status overrides so timeout, failed, and
cancelled status-control output is visible as untrusted prompt data without
copying status messages or error text into receipt metadata.

## Architecture

`DeterministicAgenticToolRuntime.execute` already accepts
`_untrusted_context_receipts` from adapter payload helpers and attaches them
beside the generic tool-observation receipt. This slice keeps that flow and adds
one helper for `_status_override_payload`.

The helper emits a `tool_output` receipt through
`worker.runtime.prompt_context.admit_prompt_context_source_evidence` with:

- `segment_id = <tool_call_id>:status-output`
- `source_type = tool_output`
- `source_field = status`
- `source_id = <tool_call_id>`
- `owner_scope_checked = false`

The receipt value is the status-control payload so the shared admission boundary
knows what prompt data is represented, but receipt JSON must not include the
override message, error text, failure stage, tool arguments, or private prompt
content.

## Scope

- Add focused regression coverage for timeout, failed, and cancelled status
  overrides.
- Add the status-output receipt helper and attach it from
  `_status_override_payload`.
- Update the unified agentic tool runtime contract.

## Out of Scope

- Changing normal adapter failure semantics for validation, owner-scope, or
  workspace-path refusals.
- Changing sanitized observation payloads, replay hashes, byte metrics, or
  status counters.
- Adding receipts to missing-result observations such as `visit` not found.

## Verification

- Focused red/green test:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agentic_tools.py -k status_override`
- Related Python worker tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agentic_tools.py services/mlx-worker-python/tests/test_tool_observation.py`
- Changed-scope coverage with at least 95 percent coverage.
- Local scoped performance report with `Status: ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.
- Full local pre-commit gate before PR.

## Performance Probe

Status overrides are fixture/test-control paths, not hot runtime retrieval.
This slice adds one constant-size receipt admission for each overridden tool
call. Expected overhead is negligible; the local and remote PR-scoped
performance reports must stay green.
