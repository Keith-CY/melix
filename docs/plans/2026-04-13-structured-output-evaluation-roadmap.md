# Structured Output Evaluation Roadmap

## Summary

Melix should add structured-output evaluation as a first-class intelligence measurement path for
LoRA workflows that target machine-readable JSON output. The roadmap below keeps the runtime
boundary package-based, treats external corpora as source datasets rather than executable
contracts, and stages the work so the contract lands before parser or scorer implementation.

This roadmap describes future milestones only. It does not claim current implementation support.

## Milestone 1: Contract And Package Profile

### Outcome

Melix has a documented structured-output evaluation contract with a stable package shape and
profile vocabulary.

### Scope

- define the `evaluation profile` abstraction in the canonical contract
- define the structured sample shape as `system`, `input`, and `target`
- define `target` as a JSON object requirement
- define strict single-object JSON parsing semantics
- define the no-compatibility rule for legacy `prompt` and `expected` structured-output rows

### Exit Criteria

- the canonical contract describes the package boundary and structured-output profile vocabulary
- the contract explicitly separates `source dataset` from `materialized evaluation package`
- the contract explicitly states that wrapped prose, multiple JSON values, and non-object JSON are
  parse failures

### Risks

- over-documenting implementation detail before scorer design is stable
- allowing historical fixture language to look like a supported long-term compatibility path

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
branches.

### Scope

- strict single-object JSON parser
- schema validation gate
- profile-driven field comparison primitives
- default ignored-path handling
- correctness threshold handling

### Exit Criteria

- worker execution semantics are described in profile-driven terms rather than suite-specific terms
- schema validity and field score are the primary structured-output evidence model
- the design leaves room for new profiles without redefining the public evaluation surface

### Risks

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
