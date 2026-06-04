# Config-Derived Long-Context Admission

## Problem

Gemma E4B MLX checkpoints can declare a 128k text context window through
`config.json` (`text_config.max_position_embeddings`), but Melix registry
discovery currently publishes raw local and Hugging Face cache models with an
8192-token `max_context`. The OpenAI-compatible gateway uses the catalog
`ModelSummary.maxContext` for prompt-budget admission before worker dispatch, so
long-context requests are rejected before the Swift text runtime can apply its
own config-derived context.

## Goal

Make text request admission use model-artifact context evidence instead of a
hard-coded discovery default, while preserving pre-worker budget protection for
clearly over-budget requests.

## Scope

- Infer discovered model `max_context` from model config files when available.
- Support top-level and nested text config fields used by local MLX, VLM, and
  MoE-style checkpoints.
- Preserve the existing 8192 fallback only when no usable context declaration is
  present.
- Keep prompt-budget admission typed and pre-worker for clearly excessive
  prompts.
- Record prompt estimate source in rejection metadata so near-boundary
  admission decisions remain auditable.

## Out Of Scope

- Changing Swift text KV-cache strategy, chunking, or decode throughput.
- Adding a cross-process tokenizer-count RPC.
- Claiming 128k runtime performance parity; this slice only removes the
  incorrect admission/catalog cap.

## Verification

- Python registry tests prove raw discovered models publish config-derived
  `max_context`, including nested `text_config.max_position_embeddings`.
- Swift gateway tests prove a 128k-capable text companion can reach worker
  dispatch instead of being rejected under the old 8192 catalog cap.
- Focused Swift prompt-budget tests continue to reject clearly over-budget
  requests before worker generation.
