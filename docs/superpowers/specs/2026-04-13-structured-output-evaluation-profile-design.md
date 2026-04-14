# Final Result Evaluation Profile Design

## Summary

Melix needs a future evaluation contract for LoRA workflows that score only the final result, even
when the model emits CoT or other wrapper text. The current `eval` path is good enough for shipped
text-style suites with simple `prompt` and `expected` rows, but it does not define a durable
contract for final-result extraction, typed validation, or typed scoring.

This design defines one future-facing evaluation profile, `final_result`. It does not claim current
implementation support.

## Problem

Using task-specific scorers or scoring the entire raw response creates the wrong incentives:

- the runtime ends up coupled to task names such as `extraction`, `relationship`, and
  `summarization`
- CoT or wrapper prose can change the score even when the final answer is unchanged
- JSON-specific extraction rules do not solve the general problem of evaluating final text answers
- no-target or format-only ideas can distract the first implementation from the real LoRA compare
  path, which is ground-truth evaluation of the final result

Melix needs one reusable abstraction that answers three questions:

- what is the final artifact being evaluated
- how is that final artifact extracted from the raw response
- how is the extracted artifact validated and scored against ground truth

## Current State

Current `eval` execution is already package-based. The worker reads `manifest.json` and
`samples.jsonl` from a local `dataset_root`, and the checked-in fixtures for current suites are
repository-owned package directories.

Current `eval` execution is not runtime-dependent on Hugging Face datasets. By contrast, LoRA
training already supports direct Hugging Face dataset materialization through the training dataset
pipeline.

That means the current Melix boundary is:

- evaluation runs execute against Melix-defined local packages
- external corpora such as Hugging Face datasets are reusable source datasets rather than runtime
  contracts
- current evaluation fixtures still largely use `prompt` and `expected` sample rows

This design keeps the package boundary and replaces the future evaluation abstraction.

## Design Goals

- define one future-facing `evaluation profile` that scores only the extracted final result
- keep external datasets reusable as source corpora without making their raw schemas part of the
  Melix runtime contract
- make final-result extraction a runtime-owned, deterministic contract rather than a best-effort
  prompt convention
- support both JSON and text final results in v1
- make validation and scoring typed by `result_kind` rather than task name
- keep v1 ground-truth oriented so base-model versus LoRA comparison is the primary path

## Non-Goals

- implementing the profile in the current transaction
- changing the shipped CLI, protocol, or export surface now
- defining task-specific scorer branches for individual downstream tasks
- adding no-target or format-only evaluation to v1
- expanding v1 text scoring to open-ended semantic similarity or subjective quality measures

## Core Terms

These terms are the authoritative vocabulary for the future final-result path:

- `source dataset`: an external or local corpus used as the origin of evaluation content
- `materialized evaluation package`: the repository-owned package Melix executes against
- `evaluation profile`: the manifest-declared extraction, validation, and scoring contract for one
  package
- `profile_type`: the top-level profile selector declared in `manifest.json`; v1 uses
  `final_result`
- `result_kind`: the type of final artifact being scored; v1 supports `json` and `text`
- `extraction_mode`: the rule for isolating the final artifact from `raw_response`
- `raw_response`: the full model response captured for debugging
- `extracted_result`: the final artifact selected by the runtime and passed to validation and
  scoring

## Recommended Contract

### Source And Execution Boundary

Melix should continue to separate dataset origin from runtime execution:

- source datasets may come from Hugging Face, local annotation sets, or repository fixtures
- execution must always consume a Melix evaluation dataset package
- Hugging Face remains reusable as a source, but not as the direct runtime contract

This keeps the runtime boundary deterministic and lets Melix evolve one package format without
importing the variability of external schemas into the worker core.

### Future Profile Shape

Each future-oriented evaluation package should declare a single `final_result` profile in its
manifest. The planned core fields are:

- `profile_type: final_result`
- `result_kind: json | text`
- `extraction_mode: strict_full_response | heuristic_final`
- `scoring_mode`
- `threshold`

Future `final_result` sample rows use:

- `system`
- `input`
- `target`

Task names such as `extraction`, `relationship`, and `summarization` may still appear as suite
labels or dataset metadata, but they must not be the primary hook for scorer implementation.

### Extraction And Scoring Pipeline

The planned runtime pipeline is:

- capture `raw_response`
- extract `extracted_result`
- validate the extracted result for its declared `result_kind`
- normalize as required by `scoring_mode`
- score only `extracted_result` against `target`

CoT or wrapper text may appear in `raw_response`, but it is not itself evaluation evidence.
Correctness is computed only from `extracted_result`.

### `result_kind: json`

For JSON final results:

- `target` must be valid JSON with root type `object` or `array`
- `output_schema` defines the accepted JSON root type and schema rules
- schema validation is required before scoring begins
- JSON object roots are expected to support field-level comparison in v1
- JSON array roots are expected to use conservative scoring in v1 rather than broad task-specific
  logic

The default ignored field set for JSON object scoring is:

- `evidence`
- `confidence`
- `closeness_logits`
- `closeness_probs`

Manifest-declared `ignored_paths` extend the default ignored field set. They do not override it.

### `result_kind: text`

For text final results:

- `target` is the expected final text after normalization
- v1 text scoring is intentionally narrow:
  - `normalized_exact_match`
  - `label_match`
  - `regex_match`
- task-specific text scorers are out of scope for v1
- open-ended semantic scoring is deferred until a later design pass

### Extraction Modes

The runtime owns final-result extraction. Package-specific custom extractors are not part of the v1
contract.

`extraction_mode` defines how Melix isolates the final result from `raw_response`:

- `strict_full_response`: the full response must be the final result payload; wrapper prose causes
  extraction failure
- `heuristic_final`: Melix applies a shared runtime extractor ladder to locate the final result in a
  response that may include CoT or other wrapper text

`heuristic_final` must be deterministic and reproducible. Ambiguous extraction is a failure rather
than a guess.

For `result_kind: json`, the planned shared extractor ladder is:

- prefer the last contentful fenced `json` block
- otherwise use the last contentful fenced block whose contents parse as JSON
- otherwise use the last terminal balanced JSON suffix
- if multiple same-priority candidates remain, record `ambiguous_extraction`

For `result_kind: text`, the planned shared extractor ladder is:

- prefer the last terminal `Final answer:` or `Answer:` span
- otherwise use the last contentful fenced text block
- otherwise use the last terminal non-empty line or paragraph
- if multiple same-priority candidates remain, record `ambiguous_extraction`

The current PR direction of describing extraction as "last valid JSON value" is not stable enough
for the long-term contract because it is JSON-specific and under-specifies ambiguity handling.

### Validation And Scoring

Validation and scoring are typed by `result_kind`, not by task name.

For `json`:

- parse success is required before schema validation
- schema validation success is required before scoring
- object roots should use field-level comparison in v1
- array roots should use conservative comparison in v1

For `text`:

- normalization happens before scoring
- v1 text scoring remains deterministic and reference-based
- normalization and scoring should not inspect CoT or wrapper text outside `extracted_result`

### Reporting Direction

The current shipped export contract remains current-state behavior. The future `final_result` path
should extend reporting with extraction- and validation-oriented evidence so LoRA compare can see:

- extraction success rate
- validation success rate
- typed score against ground truth
- sample-level extraction or validation failure reasons

## Why This Abstraction

The `final_result` abstraction is preferred because it keeps the critical axes separate:

- `result_kind` defines what artifact is being scored
- `extraction_mode` defines how Melix isolates that artifact from `raw_response`
- `scoring_mode` defines how the extracted artifact is compared to `target`

This is cleaner than encoding result type, ground-truth presence, and extraction behavior into
separate top-level profile names.

## Migration Boundary

Current repository fixtures that use `prompt` and `expected` remain current-state implementation
formats. They are not the primary long-term abstraction for the future final-result contract.

New package creation should drive future adoption. This document does not claim that the future
contract is already implemented.
