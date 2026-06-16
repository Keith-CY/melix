# Tool Observation Source Receipt Normalization Plan

## Issue

GitHub issue #1761 tracks untrusted-context boundaries for retrieved docs,
skills, memories, and tool output.

## Goal

Defensively normalize source-specific untrusted-context receipts when they are
attached to Python worker tool observations so receipt metadata cannot bypass
the shared worker receipt source-ID redaction boundary.

## Architecture

Upstream source admission helpers should already create
`melix.untrusted_context_receipt.v1` receipts through the shared Python worker
receipt helper. The tool-observation normalizer is still an aggregation
boundary because it accepts caller-provided source receipts and serializes them
beside the generic tool-observation receipt.

This slice keeps non-receipt diagnostic mappings unchanged, but re-emits
well-formed `melix.untrusted_context_receipt.v1` source receipts through
`worker.runtime.untrusted_context.untrusted_context_receipt`. That preserves the
receipt schema while applying the same `source_id` and derived `segment_id`
redaction used by prompt-context receipts.

## Scope

- Add a focused tool-observation regression test for raw path-like source
  receipt metadata.
- Normalize well-formed v1 source receipts at
  `worker.runtime.tool_observation.normalize_tool_observation`.
- Update the unified runtime contract to document this aggregation boundary.

## Out of Scope

- Changing sanitized payload content, replay hashing, or observation metrics.
- Changing upstream retrieval, skill, memory, or local-compute receipt creation.
- Treating arbitrary diagnostic mappings as v1 untrusted-context receipts.

## Verification

- Focused red/green test:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_tool_observation.py -k source_receipt`
- Related Python worker tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_tool_observation.py services/mlx-worker-python/tests/test_agentic_tools.py services/mlx-worker-python/tests/test_evaluation_prompt_context.py`
- Changed-scope coverage with at least 95 percent changed-line coverage.
- Local scoped performance report with `Status: ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.
- Full local pre-commit gate before PR.

## Performance Probe

The changed path runs a constant-size schema check for each attached source
receipt and, for well-formed v1 receipts, reuses the shared receipt helper.
Private source IDs add one SHA-256 calculation per attached receipt. Expected
impact is negligible, and the PR-scoped performance report must remain green.
