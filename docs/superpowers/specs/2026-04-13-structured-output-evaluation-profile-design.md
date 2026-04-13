# Structured Output Evaluation Profile Design

## Summary

Melix needs a real evaluation path for LoRA workflows that tune models to emit schema-constrained
structured output. The current `eval` path is good enough for text-style suites with simple
`prompt` and `expected` rows, but it does not define a durable contract for format adherence,
single-object JSON parsing, schema validity, or field-level extraction quality.

This design defines the target documentation contract for a future structured-output evaluation
profile. It does not claim current implementation support.

## Problem

Using `multiple_choice_accuracy` or `exact_match` as a proxy for structured-output quality creates
the wrong incentives:

- multiple-choice scoring changes the task rather than evaluating the intended output format
- exact-match scoring is too brittle for structured JSON unless the runtime also owns full
  canonicalization
- task-specific scorer branches for `extraction`, `relationship`, or `summarization` would turn
  each new use case into a product-surface change

Melix needs one reusable abstraction that can evaluate format adherence and extraction quality
across multiple structured tasks without making the evaluation core depend on task names.

## Current State

Current `eval` execution is already package-based. The worker reads `manifest.json` and
`samples.jsonl` from a local `dataset_root`, and the checked-in fixtures for current suites are
repository-owned package directories.

Current `eval` execution is not runtime-dependent on Hugging Face datasets. By contrast, LoRA
training already supports direct Hugging Face dataset materialization through the training dataset
pipeline.

That means the current Melix boundary is:

- evaluation runs execute against Melix-defined local packages
- training can materialize external Hugging Face datasets
- existing evaluation fixtures use historical `prompt` and `expected` rows

This design keeps the package boundary but replaces the long-term structured-output row shape and
scoring semantics.

## Design Goals

- define one reusable `evaluation profile` abstraction for structured-output evaluation
- keep external datasets reusable as source corpora without making their raw schemas part of the
  Melix runtime contract
- require strict single-object JSON parsing so format failures are visible and machine-readable
- make schema validity and field-level quality the target evidence for LoRA comparison
- avoid tying scorer behavior to task names or suite-specific hardcoded branches

## Non-Goals

- implementing the profile in the current transaction
- redefining the current non-structured suite contracts
- adding new CLI, protocol, or export fields now
- making Hugging Face raw dataset schemas executable without materialization

## Core Terms

These terms are the authoritative vocabulary for the future structured-output path:

- `source dataset`: an external or local corpus used as the origin of evaluation content
- `materialized evaluation package`: the repository-owned package Melix executes against
- `evaluation profile`: the manifest-declared parsing, schema, and scoring contract for one package
- `strict single-object JSON parsing`: the parsing rule that accepts exactly one JSON object and
  rejects wrapped prose, multiple JSON values, and non-object JSON payloads

## Recommended Contract

### Source And Execution Boundary

Melix should continue to separate dataset origin from runtime execution:

- source datasets may come from Hugging Face, local annotation sets, or repository fixtures
- execution must always consume a Melix evaluation dataset package
- Hugging Face remains reusable as a source, but not as the direct runtime contract

This keeps the runtime boundary deterministic and lets Melix evolve one package format without
importing the variability of external schemas into the worker core.

### Evaluation Profile

Each structured-output package should declare an `evaluation profile` in its manifest. The profile
defines:

- the expected output schema
- the parser mode
- the field-level comparison policy
- the threshold used for correctness decisions
- the ignored paths that do not contribute to scoring

The evaluation profile is the abstraction layer. Task names such as `extraction`,
`relationship`, and `summarization` may still appear as suite labels or dataset metadata, but they
must not be the primary hook for scorer implementation.

### Structured Sample Shape

The planned structured-output sample shape is:

- `system`
- `input`
- `target`

`target` must be a JSON object. The long-term structured-output contract does not preserve a
compatibility path for legacy `prompt` and `expected` rows.

### Strict Single-Object Parsing

Structured-output parsing must be intentionally narrow:

- exactly one JSON object is accepted
- any wrapped prose before or after the JSON object is rejected
- multiple JSON values are rejected
- JSON arrays, strings, numbers, booleans, and `null` are rejected

This is stricter than some current LLM-evaluation conventions, but it matches the LoRA tuning goal:
the model should emit a schema-constrained machine-readable object, not a loosely parseable answer.

### Schema And Field Scoring

Structured-output evaluation should use schema validation as a gate and field-level comparison as
the score:

- parse success is required before validation
- schema success is required before field scoring
- default ignored fields are `evidence`, `confidence`, `closeness_logits`, and `closeness_probs`
- the primary score should be a field-level precision or recall or F1 style measure rather than
  plain string equality

This gives Melix a truthful way to compare base models and LoRA-derived models on both format
adherence and extraction quality.

## Why This Is Better Than Task-Specific Scorers

The structured-output profile is the reusable layer because it:

- avoids one-off scorer branches per task name
- keeps new structured tasks primarily data- and manifest-driven
- leaves room for a future importer or materializer from Hugging Face without changing worker
  execution semantics
- creates one stable place to document and test parsing and schema rules

The remaining task differences belong in profile configuration, not in the public evaluation
surface.

## Migration Boundary

The repository should treat existing `prompt` and `expected` evaluation fixtures as historical
formats. They remain part of current implementation history, but they are not the desired contract
for future structured-output evaluation.

That migration should happen through new package profiles and new materialized packages rather than
by widening the structured-output contract to support both historical and future row shapes.
