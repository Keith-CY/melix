# Cross-Runtime Model Inventory Plan

## Goal

Define the Melix P4.1 cross-runtime inventory contract for issue #1512 so
Melix can inspect Melix-managed model roots and compatible external runtime
caches through one descriptor, scan receipt, classification, and metrics model
before source-specific implementation work begins.

## Architecture

The Python worker continues to own filesystem discovery because it already
owns `WorkerModelCatalog`, Hugging Face cache inspection, model metadata
parsing, and model-ops jobs. The Swift control plane remains the authority for
operator-visible catalog state, registry snapshot synchronization, Desktop and
CLI presentation, and metrics aggregation. Desktop and CLI must consume the
same machine-readable scan receipts; they must not infer source status from
ad hoc paths or perform their own source-specific parsing.

P4.1 is split into one plan issue and two executable unit issues:

- #1512 / P4.1 defines the source descriptor, scan receipt,
  classification, browse-to-admit, cancellable pull, and metrics contracts.
- #1513 / U4.1.1 adds external runtime source descriptors and fixture
  coverage.
- #1514 / U4.1.2 adds shared scan receipts and usability classification.

The first implementation slice should prototype the descriptor contract on the
existing Hugging Face cache and Hub discovery paths because Melix already owns
`HubCatalog`, Hugging Face cache-root resolution, cache snapshot scanning, and
download receipts. Other source kinds must still be represented by contract
fixtures before #1513 is closed.

## Existing Anchors

- `docs/reference-scans/m-courtyard-lessons.md` identifies cross-runtime local
  model discovery as the M4 improvement direction.
- `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md` maps #1511
  through #1517 into the M4 milestone, plan, and unit hierarchy.
- `docs/runbooks/phase-8-local-install.md` defines current Hugging Face cache
  root resolution, registry root scanning, missing-cache behavior, and private
  token redaction expectations.
- `docs/runbooks/phase-8-lora-adapter-workflow.md` defines current backend
  Hugging Face Hub discovery surfaces and keeps remote discovery separate from
  local registry metadata until a download or install flow completes.
- `services/mlx-worker-python/worker/model_registry/catalog.py` currently
  scans configured registry roots, Melix-managed roots, Hugging Face cache
  snapshots, and plain local MLX directories into `RegistrySnapshot`.
- `services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift`
  currently requests registry snapshots from the Python model-ops worker,
  parses the returned JSON, syncs discovered models into `ModelCatalog`, and
  records `registry.reload_latency_ms` plus `registry.discovered_model_count`.
- `services/control-plane-swift/Sources/ModelCatalog/ModelCatalogPresentation.swift`
  owns public registry metadata filtering for `/v1/models`, CLI, and Desktop
  presentation.

## Non-Goals

- Do not copy code, assets, layouts, or implementation structure from external
  projects.
- Do not introduce a second catalog database or make external runtime stores a
  source of truth over the Swift control plane.
- Do not mutate, delete, or repair external runtime caches in P4.1. Cleanup
  semantics belong to #1517 after inventory receipts exist.
- Do not expose tokens, proxy credentials, private repository URLs with embedded
  credentials, or raw host-specific secrets in logs, `/v1/models`, Desktop, CLI,
  or evidence artifacts.
- Do not show unsupported or ambiguous external models as usable Melix models
  until the shared classification marks them usable.
- Do not add a sixth source kind without updating this plan and its fixture
  matrix first.

## Source Descriptor Contract

Every inventory source is represented by a source descriptor with schema
`melix.model_inventory_source_descriptor.v1`. A descriptor is a contract row,
not a discovered model row.

Required fields:

- `schema_version`
- `descriptor_id`
- `source_kind`
- `display_name`
- `ownership`
- `requested_roots`
- `effective_roots`
- `path_policy`
- `discovery_policy`
- `receipt_policy`
- `redaction_policy`
- `failure_modes`
- `catalog_policy`
- `pull_policy`
- `metrics_policy`

`requested_roots` records what the operator, CLI, Desktop, environment, or
configuration asked Melix to inspect. `effective_roots` records the normalized
roots Melix actually inspected, including defaults and environment-derived
fallbacks. Both must be visible to CLI and Desktop through the same receipt
shape, with redaction applied before public logs or HTTP responses are written.

`ownership` is one of:

- `melix_owned`: Melix may create and later clean paths under this root when a
  governing cleanup plan allows it.
- `external_read_only`: Melix may inspect metadata but must not mutate paths.
- `external_admitted`: a model was imported or downloaded into a Melix-owned
  or Melix-managed location after a browse-to-admit flow.

`path_policy` must define:

- default candidate roots
- environment variables or config keys that can set roots
- whether missing requested roots produce a source receipt
- whether the scanner descends recursively
- prune directory names
- symlink policy
- maximum traversal depth when the layout supports it
- whether absolute paths can appear in operator-private receipts
- public redaction behavior for absolute paths

`receipt_policy` must define the per-source fields emitted during every scan.
Unreadable, missing, unsupported, and invalid sources produce source receipts
without preventing valid sources from being scanned.

## Source Descriptor Matrix

### Melix-Managed Roots

- `source_kind`: `melix_managed_root`
- Requested roots: `MELIX_MODEL_ROOTS`, `MELIX_MANAGED_MODEL_ROOT`,
  Desktop model-root settings, and explicit CLI scan roots.
- Effective roots: configured roots plus the default
  `$MELIX_HOME/models/default-managed` when it exists.
- Layout policy: Melix registry manifest directories, imported local model
  directories, and derived-model artifacts that are already represented in the
  registry snapshot.
- Ownership: `melix_owned`.
- Failure modes: `not_found`, `permission_denied`, `invalid_manifest`,
  `unsafe_path`, `unsupported_layout`.
- Redaction: public surfaces may show stable source labels and model ids; full
  absolute root paths stay in operator-private receipts or are replaced by a
  redacted path plus digest.

### Hugging Face Cache Snapshots

- `source_kind`: `huggingface_cache`
- Requested roots: `HUGGINGFACE_HUB_CACHE`, `<HF_HOME>/hub`, explicit CLI or
  Desktop roots, and worker request metadata roots.
- Effective roots: the requested roots plus the default
  `~/.cache/huggingface/hub` only when no explicit cache root was requested and
  the default exists.
- Layout policy: `models--<org>--<repo>/snapshots/<snapshot-id>` directories
  with `config.json` and model weights. `blobs`, refs, and incomplete snapshot
  payloads are not standalone usable models.
- Ownership: `external_read_only` unless a later download flow admits the model
  into a Melix-owned root.
- Failure modes: `not_found`, `permission_denied`, `missing_config`,
  `missing_weights`, `unsupported_transformers_layout`, `ambiguous_mlx_signal`,
  `invalid_json`, `incomplete_snapshot`.
- Redaction: tokens and credential-bearing URLs are never stored. Public
  surfaces may show `repo_id`, revision, and compatibility state, but not raw
  private token material.
- Catalog policy: Hub search and card metadata can populate search result
  receipts, but local registry rows are created only after a local snapshot is
  discovered or a download/install flow admits a model.

### ModelScope Cache Snapshots

- `source_kind`: `modelscope_cache`
- Requested roots: explicit CLI or Desktop roots and supported environment or
  config roots defined by the implementation unit.
- Effective roots: normalized existing roots from the descriptor; default roots
  may be added only when the implementation unit verifies them and records the
  fallback in the descriptor.
- Layout policy: model snapshot directories must expose a stable repository
  identity, `config.json`, tokenizer metadata when required by the runtime, and
  model weights. Layout variants that cannot produce stable identity are
  classified as `ambiguous`.
- Ownership: `external_read_only`.
- Failure modes: `not_found`, `permission_denied`, `missing_config`,
  `missing_weights`, `ambiguous_identity`, `unsupported_layout`,
  `invalid_json`.
- Redaction: local absolute roots are redacted in public surfaces; repository
  ids and non-secret revision identifiers may be displayed.
- Catalog policy: remote ModelScope search is out of scope for the first P4.1
  implementation unless a follow-up plan adds a source-specific catalog client.

### Ollama Model Stores

- `source_kind`: `ollama_store`
- Requested roots: `OLLAMA_MODELS`, explicit CLI or Desktop roots, and the
  platform default only when no explicit root was requested and it exists.
- Effective roots: normalized model-store roots that contain an Ollama-style
  manifest and blob layout.
- Layout policy: manifests identify model tags and blob digests; blob payloads
  are not parsed as arbitrary model directories. A manifest with missing blobs
  becomes an incomplete row rather than a usable Melix model.
- Ownership: `external_read_only`.
- Failure modes: `not_found`, `permission_denied`, `missing_manifest`,
  `missing_blob`, `unsupported_architecture`, `ambiguous_family`,
  `unsupported_layout`.
- Redaction: public receipts may show model name, tag, digest prefix, and
  usable state; raw absolute blob paths are redacted or digest-referenced.
- Catalog policy: Ollama store discovery does not imply Melix can serve the
  model. Usability must pass MLX compatibility or an explicit external runtime
  bridge policy added by a later plan.

### LM Studio Model Stores

- `source_kind`: `lm_studio_store`
- Requested roots: explicit CLI or Desktop roots plus platform default roots
  verified by the implementation unit.
- Effective roots: normalized model directories under each usable root.
- Layout policy: local model directories must expose stable identity,
  configuration metadata, and model weights. GGUF-only rows are classified as
  external runtime artifacts unless a Melix-compatible load path exists.
- Ownership: `external_read_only`.
- Failure modes: `not_found`, `permission_denied`, `missing_config`,
  `missing_weights`, `gguf_without_bridge`, `ambiguous_identity`,
  `unsupported_layout`.
- Redaction: public receipts may show source kind, model display name,
  compatibility, and size estimate; raw absolute roots are redacted.
- Catalog policy: remote LM Studio catalog browsing is out of scope for P4.1.

## Scan Receipt Contract

Every scan writes a receipt with schema
`melix.model_inventory_scan_receipt.v1`. The receipt may be returned in the
existing registry snapshot JSON while #1513 and #1514 prove the shape. If the
shape becomes part of a long-lived worker or control-plane API, the relevant
protobuf schema must be updated and generated artifacts committed in that same
unit.

Required top-level fields:

- `schema_version`
- `scan_id`
- `started_at_unix_ms`
- `completed_at_unix_ms`
- `requested_sources`
- `effective_sources`
- `source_receipts`
- `discovered_models`
- `summary`
- `redaction_summary`
- `metrics`

Each source receipt must include:

- `descriptor_id`
- `source_kind`
- `requested_root`
- `effective_root`
- `root_redaction`
- `root_path_digest`
- `accessible`
- `scan_status`
- `failure_code`
- `failure_message`
- `discovered_model_count`
- `usable_model_count`
- `unsupported_model_count`
- `incomplete_model_count`
- `ambiguous_model_count`
- `invalid_entry_count`
- `redaction_count`
- `scan_latency_ms`
- `payload_byte_size`

`scan_status` values:

- `completed`
- `completed_with_warnings`
- `skipped`
- `failed`

Invalid or unreadable sources never poison the whole scan. The final scan
status may be `completed_with_warnings` while valid sources still populate the
catalog.

## Usability Classification

Each discovered model row must include a classification block with schema
`melix.model_inventory_classification.v1`.

Required fields:

- `source_kind`
- `source_descriptor_id`
- `source_model_id`
- `model_id`
- `model_path`
- `file_layout`
- `family_signal`
- `mlx_compatibility`
- `trainability`
- `exportability`
- `missing_file_state`
- `estimated_size_bytes`
- `artifact_state`
- `usable_state`
- `operator_message`
- `remediation`
- `metrics`

`file_layout` values:

- `melix_manifest`
- `huggingface_snapshot`
- `modelscope_snapshot`
- `ollama_manifest_blobs`
- `lm_studio_directory`
- `plain_mlx_directory`
- `gguf_file`
- `unknown`

`mlx_compatibility` values:

- `compatible`
- `incompatible`
- `unknown`

`trainability` values:

- `trainable`
- `adapter_only`
- `not_trainable`
- `unknown`

`exportability` values:

- `exportable`
- `requires_conversion`
- `not_exportable`
- `unknown`

`missing_file_state` values:

- `complete`
- `missing_config`
- `missing_weights`
- `missing_tokenizer`
- `missing_blob`
- `missing_companion`
- `unknown`

`artifact_state` values:

- `ready`
- `incomplete`
- `cancelled_pull`
- `partial_cleanup_pending`
- `partial_cleanup_done`
- `external_runtime_only`

`usable_state` values:

- `usable`
- `unsupported`
- `incomplete`
- `ambiguous`

CLI, Desktop, diagnostics, and benchmark model selection must use these
machine-readable values instead of re-parsing path names or UI strings.

## Browse-To-Admit And Pull Receipts

P4.1 source descriptors must support the later workflow where an operator
browses catalog results, chooses a compatible row, starts a pull, can cancel
the pull, and receives an admission receipt if the local artifact becomes a
usable Melix model.

The first source to implement this should be `huggingface_cache` plus the
existing Hugging Face Hub catalog client.

Catalog result receipts must include:

- `schema_version`
- `catalog_source_kind`
- `query`
- `cursor`
- `result_count`
- `compatible_result_count`
- `candidate_model_id`
- `candidate_revision`
- `candidate_family_signal`
- `candidate_mlx_compatibility`
- `selection_reason`
- `metrics`

Pull task receipts must include:

- `schema_version`
- `pull_task_id`
- `catalog_source_kind`
- `candidate_model_id`
- `requested_revision`
- `target_source_descriptor_id`
- `target_effective_root`
- `state`
- `cancel_requested`
- `transport_cancelled`
- `partial_artifacts`
- `cleanup_status`
- `admission_status`
- `terminal_reason`
- `metrics`

`state` values:

- `queued`
- `resolving`
- `downloading`
- `verifying`
- `admitted`
- `cancelled`
- `failed`

Cancelling a pull must propagate to the underlying transport when supported,
must not leave a partial artifact classified as usable, and must emit a
terminal `cancelled` receipt with cleanup evidence. If cleanup cannot remove a
partial artifact safely, the scan classification must report
`partial_cleanup_pending`.

## Unit Boundaries

### #1513 Source Descriptors

#1513 owns descriptor implementation and fixtures for:

- `melix_managed_root`
- `huggingface_cache`
- `modelscope_cache`
- `ollama_store`
- `lm_studio_store`

The unit must:

- add source descriptor data structures near the existing registry scanner
- expose requested and effective roots in the registry snapshot path
- preserve current Hugging Face cache behavior while making its source
  descriptor explicit
- add fixtures for missing, unreadable, invalid, and valid source roots
- include at least one searchable source fixture using the Hugging Face Hub
  discovery path
- define pull receipt state transitions enough for #1514 classification to
  represent cancelled and partial-cleanup rows

#1513 must not broaden Desktop UI beyond showing requested/effective source
roots from the shared receipt.

Implementation note for #1513:

- `WorkerModelCatalog.registry_snapshot_payload()` now emits
  `source_descriptors` alongside the existing `roots` and `models` fields so
  current Swift snapshot parsing remains backward-compatible while CLI and
  Desktop can consume requested and effective source roots from the shared
  receipt path.
- The first implemented descriptor set covers `melix_managed_root`,
  `huggingface_cache`, `modelscope_cache`, `ollama_store`, and
  `lm_studio_store`. Hugging Face cache descriptors mark the existing
  `HubCatalog.search_models` path as searchable and define pull states for
  cancelled and partial-cleanup follow-up receipts.
- The #1513 fixture scope verifies the five descriptor rows, Hugging Face cache
  model discovery, external requested roots, missing Hugging Face cache root
  isolation, and propagation through generated maintenance manifests.

### #1514 Scan Receipts And Classification

#1514 owns the shared scan receipt and discovered-model classification output.

The unit must:

- emit `melix.model_inventory_scan_receipt.v1` for every registry scan
- classify discovered models by source, layout, family signal, MLX
  compatibility, trainability, exportability, missing-file state, estimated
  size, artifact state, and usable state
- ensure CLI, Desktop, diagnostics, and benchmark model selection consume the
  same receipt fields
- redact token-like and secret-like values before writing logs, UI, reports, or
  public HTTP metadata
- include fixtures for usable, unsupported, incomplete, ambiguous,
  cancelled-pull, and partial-cleanup cases

#1514 must not add cleanup apply behavior. It can report cleanup state only.

## Metrics And Probes

The P4.1 implementation units must define PR-scoped probes before code changes
that alter the hot registry scan path.

Required metrics:

- `inventory_scan_latency_ms`
- `scan_payload_byte_size`
- `source_count`
- `requested_source_count`
- `effective_source_count`
- `invalid_source_count`
- `discovered_model_count`
- `usable_model_count`
- `unsupported_model_count`
- `incomplete_model_count`
- `ambiguous_model_count`
- `classification_latency_ms`
- `redaction_count`
- `catalog_scan_latency_ms`
- `catalog_result_count`
- `pull_cancel_latency_ms`
- `partial_artifact_cleanup_latency_ms`

Probe success criteria:

- existing Melix-managed and Hugging Face cache scan latency must not regress
  for the existing fixture scale
- invalid external roots must add bounded receipt rows without making valid
  source scans fail
- scan payload size must stay below the configured fixture budget
- classification must remain deterministic across repeated scans of the same
  fixture tree
- redaction count must be nonzero for fixtures with token-like or
  credential-like values
- cancelled pull fixtures must produce terminal cancelled receipts and never a
  usable model row

## Verification

This #1512 change is documentation-only. The PR that introduces this plan
should run:

```bash
git diff --check
python3 scripts/validate_pr_evidence.py --body-file .runtime/pr-body-issue-1512.md
```

The changed scope has no executable code and no measurable runtime coverage.
Metrics report: `N/A - documentation-only P4.1 plan; #1513 and #1514 define
and run the source descriptor, scan receipt, classification, and performance
probes before implementation commits.`

## Acceptance Criteria

- The plan defines external runtime source descriptors and path policies for
  Melix-managed roots, Hugging Face cache snapshots, ModelScope cache
  snapshots, Ollama model stores, and LM Studio model stores.
- The plan defines scan receipts, source receipts, usability classification,
  redaction boundaries, and invalid-source behavior.
- The plan defines browse-to-admit and cancellable pull receipt contracts for
  the first searchable source descriptor.
- The plan records implementation metrics and PR-scoped probe expectations for
  #1513 and #1514.
- The P4.1 roadmap entry links this detailed plan so child issues share one
  contract.

## Rollback Or Safe Exit

- If #1513 proves that a descriptor field is incompatible with the current
  registry snapshot path, update this plan before implementing a divergent
  field.
- If a source kind cannot be represented without a target-specific side
  channel, leave that source disabled, keep its fixture as `unsupported_layout`,
  and file a follow-up issue rather than weakening the shared receipt shape.
- If scan probes show a regression, fix the implementation before opening the
  child PR or record an explicit, reviewed performance tradeoff in that child
  PR.
