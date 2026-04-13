# Structured Output Evaluation Profile Design

## Summary

Melix needs real evaluation paths for LoRA workflows that cover three distinct scenarios: models
tuned to emit schema-constrained structured output, models evaluated against reference answers, and
early-stage models where only format adherence can be measured.

The current `eval` path is good enough for text-style suites with simple `prompt` and `expected`
rows, but it does not define a durable contract for format adherence, JSON parsing semantics,
schema validity, or field-level extraction quality. It also does not formally name the existing
text-generation path as a permanent long-term contract.

This design defines three evaluation profiles: `structured_output`, `text_generation`, and
`format_compliance`. It does not claim current implementation support for the new profiles.

## Problem

Using `multiple_choice_accuracy` or `exact_match` as a proxy for structured-output quality creates
the wrong incentives:

- multiple-choice scoring changes the task rather than evaluating the intended output format
- exact-match scoring is too brittle for structured JSON unless the runtime also owns full
  canonicalization
- task-specific scorer branches for `extraction`, `relationship`, or `summarization` would turn
  each new use case into a product-surface change

A second problem is that the current eval path has no formal contract designation. Packages using
`prompt` and `expected` rows are implicitly treated as a legacy or transitional format, which
creates pressure to migrate working evaluation datasets without a clear benefit.

A third problem is that early-stage LoRA experiments often cannot produce ground-truth target data.
Without a format-only evaluation path, operators have no automated way to measure whether a newly
trained model is emitting valid structured output at all.

Melix needs three reusable abstractions: one for schema-constrained output evaluation, one that
formally names the existing text-generation path as permanent, and one for format-compliance
measurement without ground truth.

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
- existing evaluation fixtures use `prompt` and `expected` rows

This design keeps the package boundary but replaces the long-term structured-output row shape and
scoring semantics.

## Design Goals

- define three `evaluation profile` types that cover the full range of current LoRA evaluation
  scenarios without making the eval core depend on task names
- keep external datasets reusable as source corpora without making their raw schemas part of the
  Melix runtime contract
- support both strict bare-JSON parsing and prose-tolerant JSON extraction through a declared
  `parser_mode`, so the eval path matches the training format
- let the declared `output_schema` root type determine what JSON shapes are valid targets, rather
  than hardcoding object-only acceptance
- make schema validity and field-level quality the target evidence for structured-output LoRA
  comparison
- formally designate the `prompt`/`expected` path as a permanent long-term profile so that
  non-structured LoRA has a stable evaluation home
- provide a format-compliance profile for early-stage evaluation without ground-truth targets

## Non-Goals

- implementing the new profiles in the current transaction
- adding new CLI, protocol, or export fields now
- making Hugging Face raw dataset schemas executable without materialization
- evaluating subjective quality such as creativity or conversational naturalness without a
  reference answer

## Core Terms

These terms are the authoritative vocabulary for the future evaluation profile path:

- `source dataset`: an external or local corpus used as the origin of evaluation content
- `materialized evaluation package`: the repository-owned package Melix executes against
- `evaluation profile`: the manifest-declared parsing, schema, and scoring contract for one package
- `profile_type`: the top-level profile selector declared in `manifest.json`; one of
  `structured_output`, `text_generation`, or `format_compliance`
- `parser_mode`: a `structured_output` profile attribute that controls whether prose surrounding
  the JSON value is a parse failure (`strict`) or is tolerated (`extract`)
- `strict parsing`: the `strict` parser mode; accepts exactly one JSON value and no surrounding
  prose
- `extract parsing`: the `extract` parser mode; extracts the last valid JSON value from the
  response; permits surrounding prose

## Recommended Contract

### Source And Execution Boundary

Melix should continue to separate dataset origin from runtime execution:

- source datasets may come from Hugging Face, local annotation sets, or repository fixtures
- execution must always consume a Melix evaluation dataset package
- Hugging Face remains reusable as a source, but not as the direct runtime contract

This keeps the runtime boundary deterministic and lets Melix evolve one package format without
importing the variability of external schemas into the worker core.

### Profile Type Selection

Each evaluation package must declare a `profile_type` in its manifest. The declared type
determines the sample shape, parsing rules, and scoring semantics for that package.

The three profile types are described below. Task names such as `extraction`, `relationship`, and
`summarization` may still appear as suite labels or dataset metadata, but they must not be the
primary hook for scorer implementation.

### `structured_output` Profile

#### Sample Shape

- `system`
- `input`
- `target`

`target` must be valid JSON whose root type matches the root type declared in the package
`output_schema`. The profile declares:

- `output_schema`: a JSON Schema reference or inline schema
- `parser_mode`: `strict` or `extract`
- `comparison_policy`: `field_f1`, `field_precision`, `field_recall`, or `exact_match`
- `threshold`: the minimum score required for a sample to be counted correct
- `ignored_paths`: paths excluded from field-level scoring (extends the default ignored set)

#### Parser Mode

`parser_mode` should match how the model was trained to emit output:

- use `strict` when the model is trained to emit bare JSON with no surrounding prose; in this mode
  any response that contains prose before or after the JSON value is a parse failure
- use `extract` when the model is trained with a reasoning prefix before the structured output; in
  this mode the parser extracts the last valid JSON value from the response and ignores surrounding
  prose

`extract` mode supports CoT-style LoRA workflows where the model reasons through the task and then
emits the structured result. It does not relax schema or field-level scoring requirements.

#### Accepted JSON Root Type

The accepted root type for `target` and for parsed model responses is determined by the
`output_schema` root type declaration, not hardcoded to object:

- schema root `{type: "object"}` requires a JSON object
- schema root `{type: "array"}` requires a JSON array

Multiple JSON values in one response are a parse failure in both `strict` and `extract` modes.
Non-JSON payloads are a parse failure in both modes.

#### Schema And Field Scoring

- parse success is required before schema validation
- schema validation success is required before field-level scoring
- default ignored fields are `evidence`, `confidence`, `closeness_logits`, and `closeness_probs`
- manifest-declared `ignored_paths` extend the default ignored set; they do not override it
- the primary score is a field-level F1, precision, or recall measure rather than plain string
  equality

### `text_generation` Profile

#### Sample Shape

- `prompt`
- `expected`

#### Scoring

The profile declares a `scoring_mode`. Supported values are:

- `multiple_choice_accuracy`
- `exact_match`
- `numeric_match`
- `code_exec`

This profile is a permanent long-term evaluation path. Existing packages using `prompt` and
`expected` rows are not subject to migration. LoRA workflows evaluated against reference answers
should use this profile regardless of whether the underlying task involves structured data.

### `format_compliance` Profile

#### Sample Shape

- `system`
- `input`

No `target` field is required. This profile measures format adherence without correctness scoring.

#### Format Declaration

The profile declares a `format` value:

- `json_object`: the response must parse as a JSON object
- `json_array`: the response must parse as a JSON array
- `json_any`: the response must parse as any valid JSON value
- `json_schema`: the response must parse and validate against the declared `output_schema`

#### Metrics

Output metrics are `parse_success_rate` and `schema_valid_rate`. There are no `correct` or
`incorrect` sample counts for this profile type.

This profile is intended for early-stage LoRA evaluation where ground-truth target data is not yet
available. It answers the question of whether the model is producing validly formatted output,
before annotation effort is invested in field-level correctness scoring.

## Why Three Profiles Instead Of One

The three-profile design avoids a false choice between structured and non-structured LoRA. Each
profile covers a distinct evaluation scenario:

- `structured_output` makes schema validity and field quality the primary evidence for LoRA
  comparison, and `parser_mode` ensures the eval contract matches the training format
- `text_generation` gives non-structured LoRA a stable long-term home without forcing a migration
  to structured packages
- `format_compliance` unblocks early-stage evaluation that would otherwise require fully annotated
  target data

Profile differences belong in manifest configuration, not in the public evaluation surface or
scorer implementation.

## Profile Boundary

Existing `prompt` and `expected` evaluation fixtures belong to the `text_generation` profile. They
are not historical formats. New structured-output packages should use the `structured_output`
profile with an appropriate `parser_mode`. New early-stage packages should use the
`format_compliance` profile.

New package creation drives profile adoption. There is no forced migration of existing packages.
