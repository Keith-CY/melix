# Source-Anchored Data Construction

## Objective

Define the Melix data-construction contract for small agentic multimodal
datasets whose answers require source evidence, visual grounding, and multi-hop
reasoning rather than memorized prompt patterns.

This plan covers the first OpenSearch-VL alignment slice for data construction
and leakage controls. It is a planning and contract slice; implementation of
pipeline metadata, validators, and sample-selection reports is intentionally
reserved for follow-up issues.

## Context

Melix already has three relevant data contracts:

- training packages with `manifest.json`, `samples.jsonl`, and optional
  `valid.jsonl`
- evaluation packages with `manifest.json`, `samples.jsonl`, and package-local
  media or document assets
- synthetic dataset generation through DataDesigner-normalized Melix packages

The source-anchored construction flow must feed those package contracts instead
of introducing a fourth execution format. The output of this flow is still a
Melix training or evaluation package; the construction metadata explains where
rows came from, how questions were rewritten, and why a sample requires tool use
or multimodal evidence.

## Goals

- Define a repeatable image, entity, and source selection process for small
  agentic multimodal datasets.
- Define fuzzy rewrite and multi-hop question construction rules that avoid
  copying source answers into prompts.
- Define minimum construction metadata needed by later leakage validators and
  sample-quality selectors.
- Keep the first implementation path compatible with existing Melix dataset
  packages, evaluation fixtures, and DataDesigner-generated packages.
- Define performance measurement points before broad implementation.

## Non-Goals

- No new public CLI command in this slice.
- No protobuf, Swift control-plane, or worker runtime schema change in this
  slice.
- No remote web crawling or live search dependency in the construction
  contract. Source material may be curated from local files, cached dataset
  snapshots, or checked-in fixture assets.
- No training, RL, or release-gate behavior change in this slice.
- No automatic leakage blocking yet; validators are a follow-up slice.

## Construction Pipeline

The source-anchored pipeline has five stages.

### 1. Source Inventory

Start from a stable local source bundle. Each source record must have a stable
`source_id` and may reference text, image, document, or metadata assets. A
source bundle may come from:

- a checked-in fixture package
- a local JSONL or CSV file
- a managed Hugging Face dataset snapshot already readable by the dataset
  registry
- a DataDesigner seed source that is materialized into local rows before use

The inventory stage records:

- `source_id`
- `source_kind`
- `source_uri` or package-relative asset path
- `source_revision` when available
- content digest for local files or rows
- license or usage note when known
- candidate split label

### 2. Image And Entity Selection

For visual or multimodal samples, select source images and entity anchors before
writing questions. A selected construction row should identify:

- the primary `image_id` or document asset
- visible entities or regions the question depends on
- source text spans, captions, table cells, or document sections used as
  evidence
- any negative entities that should not be accepted as equivalent answers

The selection process should prefer rows where the answer cannot be inferred
from a generic class label alone. For example, an image-only category question is
weaker than a question that links an object, a visible attribute, and a separate
source fact.

### 3. Fuzzy Rewrites

Fuzzy rewrites convert source facts into natural task prompts while preserving
the answer target. They must not copy the final answer verbatim into the prompt,
the observation text, or few-shot demonstrations.

Each rewrite records:

- `rewrite_id`
- source fields used by the rewrite
- prompt template or generator id
- answer-preserving transformation labels, such as paraphrase, entity alias,
  attribute substitution, temporal framing, or distractor insertion
- excluded leakage fields whose raw values must not appear in the prompt or
  tool observations

Rewrites should produce at least one prompt form that differs lexically from the
source answer and any direct source caption. The exact lexical threshold belongs
to the validator slice, but construction metadata must preserve enough source
and transformation context for that validator to run later.

### 4. Multi-Hop Question Assembly

Multi-hop samples combine at least two evidence steps. The sample metadata must
state the intended hop graph rather than relying on prose alone.

Supported first-hop shapes:

- image region or visible entity to source entity
- document section to entity
- search result or local index hit to source document

Supported second-hop shapes:

- source entity to answer fact
- source fact to comparison target
- document attribute to final answer

The row should identify:

- `hop_count`
- ordered `evidence_chain`
- required tool families, such as image inspection, search, or document lookup
- answer type and accepted aliases
- ambiguity notes when multiple answers could be valid

### 5. Package Materialization

The final materialized package remains a Melix package:

- training output uses `melix.training_dataset_package.v1`
- evaluation output uses `melix.evaluation_dataset_package.v2`
- media and documents remain package-local assets referenced from sample rows

Generated packages may include a source-anchored construction summary in the
package manifest and per-sample construction metadata in rows created by this
pipeline. DataDesigner-backed generation accepts this metadata through the
`source_construction` request contract and preserves per-row
`source_construction` objects in generated training and final-result evaluation
packages.

## Minimum Metadata Contract

Generated packages use a `source_construction` object for manifest-level
construction metadata and a per-sample `source_construction` object for rows
that were created by this pipeline.

Manifest-level fields:

- `schema_version`
- `construction_method`
- `source_bundle_id`
- `source_bundle_revision`
- `source_count`
- `sample_count`
- `transformation_kinds`
- `excluded_leakage_field_kinds`
- `split_policy`

Sample-level fields:

- `source_ids`
- `source_asset_paths`
- `image_ids`
- `entity_ids`
- `rewrite_id`
- `transformation_kinds`
- `excluded_leakage_fields`
- `evidence_chain`
- `required_tool_families`
- `hop_count`
- `answer_aliases`
- `ambiguity_notes`

The metadata must use package-relative paths for local assets and must not store
raw secrets, API keys, or live provider credentials.

## Leakage Controls Planned From This Contract

The validator slice consumes the metadata above to check source-anchored rows
before package materialization:

- prompt or example overlap with excluded source fields by resolving
  `excluded_leakage_fields` against the generated row and scanning
  prompt/example text that is visible before the target answer
- answer-in-observation leakage by scanning tool observation payloads for the
  same excluded raw values
- train/eval source collision by comparing per-row `source_ids` across the
  materialized training and validation splits
- duplicate source ids across incompatible splits
- exact or near-exact prompt duplication

The initial lexical leakage checks ignore excluded raw values shorter than
three characters because single-character labels and very short aliases create
high-noise substring matches in normal prompt text.

The first validator implementation blocks invalid generated packages when these
checks fail. Follow-up slices should add machine-readable summaries in dataset
manifests and evaluation artifacts before any release-facing claim uses the
generated data.

Successful source-anchored package materialization must write a
`source_leakage_validation` summary in the package `manifest.json`. The summary
must be machine-readable and safe to publish with release evidence. It must not
include raw excluded field values, prompts, observations, source text spans, or
secrets.

The summary fields are:

- `schema_version`
- `status`
- `output_kind`
- `validators`
- `source_row_count`
- `excluded_field_reference_count`
- `checked_prompt_segment_count`
- `checked_observation_segment_count`
- `minimum_value_length`

Training packages with a validation split also record:

- `train_row_count`
- `validation_row_count`
- `train_source_id_count`
- `validation_source_id_count`
- `shared_source_id_count`

Evaluation final-result packages record the same summary under their existing
evaluation package manifest contract. The sample rows keep their per-row
`source_construction` metadata, but they do not duplicate package-level
validation totals.

## Quality Metrics Planned From This Contract

The sample-selection slice should compute:

- tool necessity
- multi-hop depth
- evidence coverage
- answer ambiguity
- source diversity
- transformation diversity

Successful source-anchored package materialization must write a
`source_quality_metrics` summary in the package `manifest.json` when at least
one row carries `source_construction` metadata. The summary is descriptive
evidence for downstream selection and release review; it does not accept or
reject samples by itself.

The summary fields are:

- `schema_version`
- `output_kind`
- `source_row_count`
- `tool_required_row_count`
- `tool_required_rate`
- `multi_hop_row_count`
- `max_hop_count`
- `average_hop_count`
- `evidence_chain_row_count`
- `evidence_coverage_rate`
- `ambiguous_row_count`
- `ambiguity_rate`
- `unique_source_id_count`
- `unique_transformation_kind_count`

The metrics are computed from sanitized per-row `source_construction` metadata
only. They must not persist raw prompts, observations, source text, answer
values, or provider secrets. Selection reports that explain accepted and
rejected samples are a follow-up slice and should consume this summary rather
than redefining the metric names.

Selection reports should explain why each accepted sample was kept and why each
rejected sample was rejected.

Successful source-anchored package materialization must also write a
package-local `source_selection_report.jsonl` when at least one row carries
`source_construction` metadata. Each report row must be publishable with release
evidence and must not include prompt, answer, observation, source text, or
secret values.

Report row fields:

- `schema_version`
- `row_index`
- `row_id`
- `status`
- `reason_codes`
- `summary`
- `source_ids`
- `required_tool_families`
- `hop_count`
- `evidence_chain_count`
- `ambiguity_flag`

The initial deterministic selection policy accepts rows that declare at least
one required tool family, `hop_count >= 2`, and a non-empty `evidence_chain`.
Rows missing one or more of those signals are reported as `rejected` with
stable reason codes. Rows with `ambiguity_notes` keep the accepted or rejected
status derived from the hard signals and add `answer_ambiguity_review` as a
review reason. The package manifest records the relative report path plus
accepted and rejected row counts.

## Performance And Measurement Points

Construction must be measurable before implementation. The first implementation
slice should record:

- `source_inventory_ms`
- `source_rows_scanned`
- `candidate_rows_selected`
- `rewrite_ms`
- `package_write_ms`
- `manifest_write_ms`
- `peak_bytes`

Success metrics:

- source inventory scans rows in streaming order where the source format allows
  it
- package materialization writes JSONL rows incrementally
- peak memory is proportional to one input row, one constructed sample, and
  bounded metadata buffers, not the full source corpus
- every generated sample has at least one `source_id`
- every multi-hop sample has `hop_count >= 2` and a non-empty `evidence_chain`

## Verification Plan

For the initial documentation slice:

- `git diff --check`
- PR evidence validation
- metrics report: `N/A`, documentation-only contract slice

For this metadata implementation slice:

- focused Python tests for manifest and sample metadata serialization
- changed-scope coverage for modified Python files

For remaining implementation slices:

- focused Python tests for leakage validator edge cases
- a synthetic construction probe that records the measurement points above

## Follow-Up Issues

- Record leakage validation summaries in dataset manifests and evaluation
  artifacts.
- Add quality metrics for tool necessity, multi-hop depth, evidence coverage,
  and answer ambiguity.
- Add selection reports that explain why samples were accepted or rejected.
