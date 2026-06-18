# Issue 1761 Retrieval Source Observation Receipts Plan

## Goal

Continue #1761 by attaching source-specific untrusted-context receipts to
deterministic retrieval tool observations for selected text and image search
results.

## Scope

This slice covers the Python worker deterministic agentic tool runtime:

- `text_search` selected retrieved document rows
- `image_search` selected retrieved image rows
- shared `worker.runtime.tool_observation` attachment of caller-provided
  source receipts beside the generic tool-observation receipt
- the governing unified agentic tool runtime contract

This slice does not add a live RAG store, skill entrypoint, memory entrypoint,
background-continuation link validation, or prompt wording changes.

## Architecture

The generic tool-observation prompt-boundary receipt marks an entire sanitized
tool observation payload as untrusted data. Retrieval results also need
source-specific receipts so downstream prompt assemblers can distinguish
retrieved documents and retrieved images from generic tool output without
parsing payload content.

`ToolObservationRecord` remains the only emitted observation shape. It now
accepts caller-provided source receipts and appends them outside the sanitized
payload, after the generic `tool_observation` receipt. This keeps payload
redaction, truncation, payload hashes, and replay fingerprints focused on the
sanitized tool output.

The deterministic retrieval adapters emit one source receipt per selected
result:

- `segment_id = <tool_call_id>:result-<1-based index>`
- `source_type = retrieved_document` for `text_search`
- `source_type = retrieved_image` for `image_search`
- `source_field = results[<0-based index>]`
- `source_id` from the selected corpus row id, or the existing deterministic
  fallback id
- `owner_scope_checked = true` only when an expected owner scope is configured
  for the run

Receipts must not include retrieved text, captions, media refs, query strings,
private prompt text, or tool arguments.

## Verification

1. Red focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_agentic_tools.py -k 'source_receipts_for_text_search_results or source_receipts_for_image_search_results'
```

2. Green focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_agentic_tools.py -k 'source_receipts_for_text_search_results or source_receipts_for_image_search_results'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_tool_observation.py -k 'source_receipts or untrusted_context_receipt_for_payload or replay_fingerprint'
```

3. Full touched test modules:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_agentic_tools.py services/mlx-worker-python/tests/test_tool_observation.py
```

4. Changed-scope coverage for touched Python files, with at least 95 percent
   measured coverage.

5. Full local pre-commit gate before commit:

```bash
.githooks/pre-commit
```

## Metrics

This change adds a fixed receipt dictionary per selected deterministic retrieval
result. The local PR-scoped performance report must remain `Status: ok` with
regressions `0`, context regressions `0`, and verification failures `0`.

No registered runtime probe is expected to be selected for this Python
metadata-only path.
