# Worker Receipt Source ID Redaction Plan

## Issue

GitHub issue #1761 tracks untrusted-context boundaries for retrieved docs,
skills, memories, and tool output.

## Goal

Prevent Python worker untrusted-context receipts from exposing private,
path-like, URL-like, non-ASCII, or overly long `source_id` values while
preserving short public symbolic IDs.

## Architecture

The shared Python worker receipt builder in
`worker.runtime.untrusted_context.untrusted_context_receipt` is the narrowest
boundary because every admitted and refused prompt-context receipt flows through
it. This slice adds source-ID normalization there instead of duplicating
redaction across retrieval, skill, memory, background-continuation, and tool
output callers.

Public source IDs remain unchanged when they are short ASCII identifiers made
from letters, numbers, `.`, `_`, `-`, and `:`. Other IDs are replaced with a
stable `source:<sha256-prefix>` token. `segment_id` values that are derived from
the raw source ID are rewritten to the same redacted prefix plus the original
suffix. Receipts still omit `source_id` when callers pass an empty source ID.

## Scope

- Add focused prompt-context tests for private path-like source IDs.
- Update the Python receipt helper to redact non-public source IDs.
- Update the unified runtime contract to describe worker receipt source-ID
  redaction.

## Out of Scope

- Changing payload redaction or tool-observation payload serialization.
- Redacting execution metadata that is not part of prompt-boundary receipt JSON.
- Changing Swift receipt redaction, which is covered by PR #2122.

## Verification

- Focused red/green tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_prompt_context.py -k source_id`
- Changed-scope coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_prompt_context.py services/mlx-worker-python/tests/test_agentic_tools.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/untrusted_context.py services/mlx-worker-python/tests/test_prompt_context.py services/mlx-worker-python/tests/test_agentic_tools.py`
- Agentic judge snapshot coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_evaluation_core.py -k agentic_judge_prompt_snapshot_and_audit -q`
- Full gate before PR:
  `make swift-test`
  `make py-test`
  `make integration-test`
- Scoped performance report through the versioned pre-commit hook or the
  repository performance command selected by the hook.

## Performance Probe

The change adds constant-time checks plus at most one SHA-256 calculation per
receipt when the source ID is non-public. Expected impact is negligible. The
PR-scoped performance report must remain `Status: ok` with zero regressions.
