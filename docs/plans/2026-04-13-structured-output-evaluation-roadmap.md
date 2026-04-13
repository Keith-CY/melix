# Structured Output Evaluation Roadmap

## Summary

Melix should add structured-output evaluation as a first-class intelligence measurement path for
LoRA workflows that target machine-readable JSON output, while also formally designating the
existing text-generation path as a permanent long-term profile and adding a format-compliance
profile for early-stage evaluation without ground truth.

The roadmap keeps the runtime boundary package-based, treats external corpora as source datasets
rather than executable contracts, and stages the work so the contract lands before parser or scorer
implementation.

This roadmap describes future milestones only. It does not claim current implementation support.

## Milestone 1: Contract And Package Profile

### Outcome

Melix has a documented evaluation profile contract that covers three profile types with stable
package shapes and vocabulary.

### Scope

- define three `profile_type` values: `structured_output`, `text_generation`, and
  `format_compliance`
- define the `structured_output` sample shape as `system`, `input`, and `target`
- define `target` as valid JSON whose root type matches the declared `output_schema` root type
- define `parser_mode` as a `structured_output` profile attribute with values `strict` and
  `extract`
- define `strict` parsing: exactly one JSON value, no surrounding prose
- define `extract` parsing: last valid JSON value extracted from response, prose tolerated
- define `text_generation` as a permanent long-term profile with `prompt` and `expected` sample
  rows and a declared `scoring_mode`
- define `format_compliance` as a profile with `system` and `input` sample rows, no `target`, and
  `parse_success_rate` and `schema_valid_rate` as output metrics
- define that `ignored_paths` in the manifest extend the default ignored set rather than override
  it
- define the no-forced-migration rule: existing `prompt` and `expected` packages belong to
  `text_generation` and are not subject to migration

### Exit Criteria

- the canonical contract describes all three profile types with their sample shapes and scoring
  semantics
- the contract explicitly separates `source dataset` from `materialized evaluation package`
- `parser_mode` vocabulary is consistent between the contract and the design spec
- `profile_type` naming is consistent across all documents

### Risks

- over-documenting implementation detail before scorer design is stable
- `extract` mode semantics may need refinement once the JSON-in-prose extractor is implemented

## Milestone 2: Dataset Materialization

### Outcome

Melix can reuse external structured corpora, including Hugging Face datasets, by materializing them
into repository-owned evaluation packages before execution.

### Scope

- define importer and materializer responsibilities
- define how profile metadata is attached to materialized packages
- define failure behavior for incompatible source schemas
- preserve the rule that worker execution consumes only Melix evaluation packages

### Exit Criteria

- the roadmap and design specify a source-to-package conversion boundary
- external datasets are documented as reusable source corpora rather than direct runtime contracts
- profile metadata is defined as part of the materialized package rather than a side channel

### Risks

- source datasets may omit fields required by structured-output scoring
- profile metadata may drift if materialization is underspecified

## Milestone 3: Structured Evaluation Core

### Outcome

Melix has one generic runtime core for structured-output evaluation rather than task-specific scorer
branches, with parser mode selection controlled by the declared profile.

### Scope

- `strict` parser: exactly one JSON value, parse failure on surrounding prose
- `extract` parser: last valid JSON value extracted from response, prose tolerated
- JSON root type validation against `output_schema` root type declaration
- schema validation gate
- profile-driven field comparison primitives
- default ignored-path handling with manifest extension support
- correctness threshold handling
- `format_compliance` profile runner: parse and optionally schema-validate, emit
  `parse_success_rate` and `schema_valid_rate`

### Exit Criteria

- worker execution semantics are described in profile-driven terms rather than suite-specific terms
- schema validity and field score are the primary `structured_output` evidence model
- `text_generation` packages continue to execute through the existing scorer without modification
- `format_compliance` packages execute and produce format metrics without requiring a `target` field
- the design leaves room for new profiles without redefining the public evaluation surface

### Risks

- `extract` mode JSON extraction heuristics may require iteration before they generalize across
  different model output styles
- generic comparison primitives may be too weak for some tasks
- too many early special cases would collapse the abstraction back into task-specific scoring

## Milestone 4: Compare And Reporting

### Outcome

Melix compare workflows can measure structured-output LoRA deltas using schema-valid and field-score
evidence instead of binary proxy scores alone.

### Scope

- compare semantics for base versus derived models
- schema-valid rate reporting
- field-score delta reporting
- regression counting for structured-output workflows
- sample-level diagnostics for parse and schema failures

### Exit Criteria

- compare is documented in terms of schema-valid and field-score evidence
- reporting semantics distinguish parsing failures from low-quality but schema-valid outputs
- LoRA comparison claims are grounded in the structured-output evidence model rather than MCQ or
  exact-match proxies

### Risks

- compare summaries may over-simplify structured-output quality if diagnostics are too thin
- operator expectations may drift if proxy metrics and structured-output metrics coexist without
  clear labeling
