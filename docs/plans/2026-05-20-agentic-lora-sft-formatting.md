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
- Split each trace into trainer rows that end at one trainable assistant span,
  so MLX-LM's single contiguous `mask_prompt` boundary trains tool-call tokens
  and final-answer tokens without training user/system/tool-observation context.
- Record response-only boundary metadata for each projected row.
- Resolve SFT training modes that consume `agentic_tool_trace` packages to the
  explicit `training_objective: agentic_sft` and
  `dataset_contract: agentic_tool_trace` contract while keeping backend
  execution on the supervised MLX-LM LoRA path.

Out of scope:

- Schema or protobuf changes.
- Network-backed tool execution.
- Claiming quality or benchmark improvement.
- A custom MLX-LM loss that trains multiple disjoint assistant spans in a
  single row.

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
5. Enable response-only masking for `agentic_tool_trace` by default after
   projecting each trainable assistant span into a separate chat row.
6. Add config validation so explicit incompatible `training_objective`
   overrides fail before training starts.
7. Add focused tests for the formatter, snapshot artifacts, and LoRA pipeline
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
- Trainer row count.
- Response-only boundary count.
- Mask-prompt boundary count.
- Focused pytest runtime for dataset builder and LoRA pipeline tests.
- Changed-scope coverage for touched Python files, target >= 95%.

Existing PR-scoped dataset probes that watch `training_dataset.py` remain
applicable. No new production metric is required because this is an offline
training data preparation path.

## Success Criteria

- `agentic_tool_trace` snapshots expose `trainer_format: chat_messages`.
- `train.jsonl` and `valid.jsonl` contain supervised `messages` rows with
  deterministic tool-call, observation, media-reference, and final-answer text.
- Each projected row ends with the one assistant span that should receive loss
  for that row, and records `response_only_boundary` metadata.
- Agentic SFT defaults to `response_only=true` and `mask_prompt=true`.
- Adapter receipts and runner configs identify the slice as
  `training_objective: agentic_sft` with
  `dataset_contract: agentic_tool_trace`.
- Explicit incompatible `training_objective` overrides fail before backend
  execution.
- Original normalized traces are preserved in sibling JSONL evidence files.
- LoRA training still reports `dataset_format: agentic_tool_trace` and records
  `trainer_dataset_format: chat_messages`.
- Focused tests and changed-scope coverage pass.
