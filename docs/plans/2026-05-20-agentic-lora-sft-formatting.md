# Agentic LoRA SFT Formatting

## Goal

Implement issue #686 by projecting `agentic_tool_trace` packages into
trainer-ready supervised rows while preserving the original trajectory evidence
needed by the OpenSearch-VL alignment family.

## Governing Specs

- `docs/agentic-trajectory-dataset-contract.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`

The upstream OpenSearch-VL SFT recipe stores agentic cold-start data as
ShareGPT-style conversations with `conversations`, `images`, `system`, and
`tools` columns. Melix keeps its repository-owned `agentic_tool_trace` contract
as the source shape and emits a local PEFT-friendly supervised projection
instead of importing the upstream Ray/full-parameter training stack.

## Scope

This slice changes only Python worker dataset normalization and LoRA training
handoff:

- Add an `agentic_tool_trace` to `chat_messages` SFT projection for normalized
  dataset snapshots.
- Format assistant tool calls, tool observations, media references, and final
  answers as deterministic supervised tokens.
- Preserve original normalized trace rows in sibling snapshot evidence files.
- Keep `dataset_format=agentic_tool_trace` in adapter receipts while passing
  the trainer the projected `chat_messages` row shape.
- Keep response-only masking disabled for `agentic_tool_trace`; issue #687 owns
  response-only and mask-prompt boundaries for tool-call tokens.

Out of scope:

- Schema or protobuf changes.
- Network-backed tool execution.
- Claiming quality or benchmark improvement.
- Enabling response-only masking for agentic traces.

## Implementation Plan

1. Add an agentic SFT formatter in
   `services/mlx-worker-python/worker/model_ops/training_dataset.py`.
2. Teach `write_normalized_dataset_snapshot(...)` to write projected
   `train.jsonl` / `valid.jsonl` rows plus original
   `agentic-traces.train.jsonl` / `agentic-traces.valid.jsonl` evidence.
3. Record formatter metadata and counts in the normalized snapshot manifest.
4. Pass the trainer-facing format from the normalized snapshot into
   `TrainingRequest` while preserving source trajectory provenance in adapter
   receipts.
5. Add focused tests for the formatter, snapshot artifacts, and LoRA pipeline
   handoff.

## Performance And Metrics

The formatter is a linear pass over already-normalized samples during snapshot
write. It does not add runtime serving overhead.

Measurement points:

- Formatter sample count.
- Formatted tool-call count.
- Formatted tool-observation count.
- Formatted media-reference count.
- Formatted final-answer count.
- Focused pytest runtime for dataset builder and LoRA pipeline tests.
- Changed-scope coverage for touched Python files, target >= 95%.

Existing PR-scoped dataset probes that watch `training_dataset.py` remain
applicable. No new production metric is required because this is an offline
training data preparation path.

## Success Criteria

- `agentic_tool_trace` snapshots expose `trainer_format: chat_messages`.
- `train.jsonl` and `valid.jsonl` contain supervised `messages` rows with
  deterministic tool-call, observation, media-reference, and final-answer text.
- Original normalized traces are preserved in sibling JSONL evidence files.
- LoRA training still reports `dataset_format: agentic_tool_trace` and records
  `trainer_dataset_format: chat_messages`.
- Focused tests and changed-scope coverage pass.
