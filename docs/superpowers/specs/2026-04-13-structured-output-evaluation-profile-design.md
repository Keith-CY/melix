# Final Result Evaluation Profile Design

## Summary

Melix needs an evaluation contract for LoRA workflows that scores only the final result, even
when the model emits CoT or other wrapper text. The current `eval` path is good enough for shipped
text-style suites with simple `prompt` and `expected` rows, but it does not define a durable
contract for final-result extraction, typed validation, or typed scoring.

This design now documents the implemented `final_result` profile, request-driven dataset
materialization, and the remaining follow-on limits around compare entry-point parity.

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

Current `eval` execution is package-based. The worker reads `manifest.json` and `samples.jsonl`
from a local dataset package, and the checked-in fixtures for current suites are repository-owned
package directories.

Current `RunEvaluation` requests can also materialize new evaluation packages on demand from:

- local CSV files
- local JSONL files
- Hugging Face datasets

That means the current Melix boundary is:

- evaluation runs execute against Melix-defined local packages
- external corpora such as Hugging Face datasets are reusable source datasets rather than direct
  runtime contracts
- request-driven materialization attaches profile metadata during package creation
- current fixtures may still carry legacy content, but runtime evidence is normalized to
  `final_result`

The package boundary is now implemented and is the foundation for the `final_result` abstraction.

## Design Goals

- define one durable `evaluation profile` that scores only the extracted final result
- keep external datasets reusable as source corpora without making their raw schemas part of the
  Melix runtime contract
- make final-result extraction a runtime-owned, deterministic contract rather than a best-effort
  prompt convention
- support both JSON and text final results in v1
- make validation and scoring typed by `result_kind` rather than task name
- keep v1 ground-truth oriented so base-model versus LoRA comparison is the primary path

## Non-Goals

- defining task-specific scorer branches for individual downstream tasks
- adding no-target or format-only evaluation to v1
- expanding v1 text scoring to open-ended semantic similarity or subjective quality measures
- adding compare entry-point parity for ad hoc custom dataset sources in every UI surface

## Core Terms

These terms are the authoritative vocabulary for the final-result path:

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

## Current Contract

### Source And Execution Boundary

Melix separates dataset origin from runtime execution:

- source datasets may come from Hugging Face, local annotation sets, or repository fixtures
- execution must always consume a Melix evaluation dataset package
- Hugging Face remains reusable as a source, but not as the direct runtime contract

This keeps the runtime boundary deterministic and lets Melix evolve one package format without
importing the variability of external schemas into the worker core.

### Implemented Profile Shape

Each structured evaluation package declares a single `final_result` profile in its manifest. The
core fields are:

- `profile_type: final_result`
- `result_kind: json | text`
- `extraction_mode: strict_full_response | heuristic_final`
- `scoring_mode`
- `threshold`

`final_result` sample rows use:

- `system`
- `input`
- `target`

Task names such as `extraction`, `relationship`, and `summarization` may still appear as suite
labels or dataset metadata, but they must not be the primary hook for scorer implementation.

### Extraction And Scoring Pipeline

The runtime pipeline is:

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
- JSON object roots support field-level comparison in v1
- JSON array roots use conservative scoring in v1 rather than broad task-specific
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

For `result_kind: json`, the shared extractor ladder is:

- prefer the last contentful fenced `json` block
- otherwise use the last contentful fenced block whose contents parse as JSON
- otherwise use the last terminal balanced JSON suffix
- if multiple same-priority candidates remain, record `ambiguous_extraction`

For `result_kind: text`, the shared extractor ladder is:

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
- object roots use field-level comparison in v1
- array roots use conservative comparison in v1

For `text`:

- normalization happens before scoring
- v1 text scoring remains deterministic and reference-based
- normalization and scoring should not inspect CoT or wrapper text outside `extracted_result`

### Reporting Direction

The current shipped export contract already includes extraction- and validation-oriented evidence so
LoRA evaluation and compare can see:

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

## Compatibility Boundary

Some repository fixtures may still originate from `prompt` and `expected` content, but that is a
compatibility detail rather than the contract surface.

New package creation and request-driven materialization should prefer the `final_result` fields and
profile metadata described above.

Current limitation:

- compare entry points do not yet accept ad hoc custom dataset sources from every UI workflow; the
  menubar compare path still targets existing suites or packages
