# Issue #1761: Agentic Trace Receipt Summary

## Scope

Expose scalar untrusted-context receipt summary fields on normalized
`agentic_tool_trace` samples when the Python worker replays sample-level tool
calls through the deterministic agentic tool runtime.

The trace already preserves full `agentic_tool_observations`, including each
observation's `untrusted_context_receipts`. This slice adds sample-level summary
metadata so downstream training-package and snapshot readers can verify that
tool-output boundary evidence exists without parsing full observation payloads.

## Non-Goals

- No changes to tool execution, observation payloads, or replay turns.
- No copying receipt bodies, retrieved text, page content, media references,
  prompts, or tool payload values into scalar fields.
- No changes to manually authored traces that do not execute replayed tool
  calls.
- No new training formatter behavior.

## Plan

1. Add a failing normalization test for a replayed `agentic_tool_trace` sample
   that expects `agentic_tool_untrusted_context_receipt_schema` and
   `agentic_tool_untrusted_context_receipt_count`.
2. Implement a small receipt-summary helper in `training_dataset.py` that
   counts mapping-shaped receipts across `AgenticToolRun.observations` and
   records the first string `schema_version`.
3. Attach the scalar fields to replay evidence only when at least one receipt
   exists.
4. Update the unified agentic tool runtime contract to document the normalized
   training-trace summary fields.

## Performance Probes

- Focused pytest for `test_training_dataset_builder.py`.
- Changed-scope Python coverage for the touched training dataset code and test.
- Repository pre-commit scoped performance report before PR creation.

## Success Criteria

- Replayed `agentic_tool_trace` samples expose
  `agentic_tool_untrusted_context_receipt_schema =
  melix.untrusted_context_receipt.v1`.
- Replayed samples expose the total count of mapping-shaped receipts across all
  replayed tool observations.
- Scalar fields do not copy tool payloads, retrieved text, prompt text, or
  receipt JSON bodies.
- Existing observation, turn, and training formatter behavior remains
  unchanged.
