# Final Result Evaluation Roadmap

## Summary

Melix should add final-result evaluation as the future intelligence measurement path for LoRA
workflows. The runtime should score only the extracted final result, not CoT or wrapper text.

The roadmap keeps the runtime boundary package-based, treats external corpora as source datasets
rather than executable contracts, and stages the work so the contract lands before extractor,
validator, or scorer implementation.

This roadmap describes future milestones only. It does not claim current implementation support.

## Milestone 1: Final-Result Contract

### Outcome

Melix has a documented future evaluation contract centered on `final_result` packages rather than
profile splits by task style.

### Scope

- define `profile_type: final_result`
- define `result_kind` as `json | text`
- define `extraction_mode` as `strict_full_response | heuristic_final`
- define the sample shape as `system`, `input`, and `target`
- define that only the extracted final result is scored
- define that CoT is retained only as `raw_response` for debugging
- define v1 as ground-truth only

### Exit Criteria

- the canonical contract describes the `final_result` abstraction and its core manifest fields
- the contract explicitly separates `source dataset` from `materialized evaluation package`
- the contract explicitly states that CoT and wrapper text are not correctness evidence
- the contract does not treat no-target or format-only evaluation as part of v1

### Risks

- over-documenting extraction details before scorer design is stable
- mixing current implementation formats with future contract language

## Milestone 2: Dataset Materialization

### Outcome

Melix can reuse external corpora, including Hugging Face datasets, by materializing them into
repository-owned evaluation packages before execution.

### Scope

- define importer and materializer responsibilities
- define how `final_result` profile metadata is attached to materialized packages
- define failure behavior for incompatible source schemas
- preserve the rule that worker execution consumes only Melix evaluation packages

### Exit Criteria

- the roadmap and design specify a source-to-package conversion boundary
- external datasets are documented as reusable source corpora rather than direct runtime contracts
- profile metadata is defined as part of the materialized package rather than a side channel

### Risks

- source datasets may omit fields required by typed scoring
- profile metadata may drift if materialization is underspecified

## Milestone 3: Extraction And Validation Core

### Outcome

Melix has one generic runtime core that extracts, validates, and normalizes final results before
scoring.

### Scope

- implement the shared extractor ladder for `heuristic_final`
- implement ambiguity detection and extraction failure handling
- implement `strict_full_response`
- implement JSON schema gating for `result_kind: json`
- implement text normalization gates for `result_kind: text`
- keep validation and extraction behavior runtime-owned rather than package-customized

### Exit Criteria

- worker execution semantics are described in terms of extraction and validation rather than task
  names
- JSON and text result kinds both have deterministic extraction rules
- ambiguity is treated as failure rather than guessed resolution
- validation runs before scoring for both result kinds

### Risks

- heuristic extraction may need iteration before it generalizes across model output styles
- text extraction rules may be noisier than JSON extraction rules

## Milestone 4: Typed Scoring And Compare

### Outcome

Melix compare workflows can measure LoRA deltas through extraction, validation, and typed scoring
rather than binary proxy scores alone.

### Scope

- implement JSON object field scoring
- implement conservative JSON array scoring
- implement normalized text scoring for exact, label, and regex match modes
- report extraction success, validation success, and typed score in compare outputs
- report regression counts with extraction and validation failures separated from score regressions

### Exit Criteria

- compare is documented in terms of extraction success, validation success, and typed score
- v1 does not introduce task-specific scorer branches
- v1 does not score CoT or wrapper text
- reporting semantics distinguish extraction failure, validation failure, and low-quality but valid
  outputs

### Risks

- compare summaries may over-simplify quality if extraction and validation diagnostics are too thin
- operator expectations may drift if current proxy metrics and future typed metrics coexist without
  clear labeling
