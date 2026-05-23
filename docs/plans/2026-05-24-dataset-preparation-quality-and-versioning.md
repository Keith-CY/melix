# Dataset Preparation Quality And Versioning Plan

## Goal

Define the Melix P1.2 dataset preparation contract for issue #1494 so raw
workspace inputs can become inspected, cleaned, versioned dataset artifacts
with quality evidence before LoRA training, evaluation, export, or reports
consume them.

## Architecture

Dataset preparation is a workspace-owned path layered on top of
`workspace-manifest.json`. The Python worker owns ingest, cleaning,
segmentation, dataset package materialization, failed-segment retry, and
quality scoring because it already owns training dataset packages and synthetic
dataset generation. The Swift CLI, Desktop app, and reports consume stable JSON
receipts and version manifests; they do not reimplement cleaning logic.

P1.2 is split into two executable units:

- #1495 / U1.2.1 adds document ingest cleaning quality controls.
- #1496 / U1.2.2 adds dataset versions, failed-only retry, and quality
  summaries.

## Existing Anchors

- `docs/workspace-manifest-contract.md` defines the project identity and
  artifact roots used by dataset preparation.
- `services/mlx-worker-python/worker/model_ops/training_dataset.py` already
  reads `melix.training_dataset_package.v1` packages with `manifest.json`,
  `samples.jsonl`, and optional `valid.jsonl`.
- `services/mlx-worker-python/worker/productization/synthetic_dataset_generation.py`
  already normalizes generated rows into Melix training and evaluation dataset
  packages.
- `docs/runbooks/phase-8-lora-adapter-workflow.md` documents the current LoRA
  dataset package shape.
- `docs/benchmark-evaluation-contract.md` already reserves package-level
  quality metadata for benchmark and evaluation consumers.

## Non-Goals

- Do not add a separate untyped project database; `workspace-manifest.json`,
  dataset version manifests, and run evidence remain the source of truth.
- Do not train, evaluate, or export directly from raw documents.
- Do not make OCR, network crawling, remote document retrieval, or external
  proprietary parsing services required for the first P1.2 implementation.
- Do not rewrite successful generated samples during failed-only retry.
- Do not expose raw PII or absolute host paths in CLI, Desktop, report, or
  exported summaries.

## U1.2.1 Ingest And Cleaning Controls

The first unit introduces an ingest command and worker helper that read
workspace inputs and write cleaned segment artifacts plus an ingest receipt.
The supported first-slice source kinds are:

| Source kind | Required behavior |
|---|---|
| `text` | Read UTF-8 plain text and normalize line endings. |
| `markdown` | Preserve headings and list structure as segment hints while removing unsupported markup noise. |
| `code` | Preserve file path, language hint, and fenced block boundaries as metadata. |
| `structured_data` | Read JSONL, JSON arrays, CSV, and TSV rows into text records with row identity metadata. |
| `pdf` | Accept extracted text fixtures and a parser adapter boundary for optional real binary extraction. |
| `docx` | Accept extracted text fixtures and a parser adapter boundary for optional real binary extraction. |

Every source record receives a stable `source_id`, `source_uri`, `source_kind`,
`content_sha256`, `byte_size`, and optional `page`, `row_index`, `language`, or
`section_path` metadata.

Cleaning controls must be independently enableable and reportable:

- `pii_mask`: mask email addresses, phone-like numbers, API-token-like
  strings, and configured literal denylist values before downstream samples are
  written.
- `exact_dedup`: remove byte-identical normalized text records after masking.
- `fuzzy_dedup`: remove near-duplicate records using a deterministic local
  similarity policy and record the policy id in the receipt.
- `segmentation`: split records by source-aware strategies such as paragraph,
  heading, code block, row, token budget, and fixed character window.

The ingest receipt schema is `melix.dataset_ingest_receipt.v1` and must include:

- `workspace_project_id`
- `workspace_manifest_path`
- `dataset_preparation_id`
- `source_inventory`
- `cleaning_controls`
- `segmentation_policy`
- `segment_artifacts`
- `quality_control_summary`
- `operator_failures`
- `metrics`

The receipt metrics are:

- `ingest_latency_ms`
- `ingest_throughput_bytes_per_second`
- `source_file_count`
- `source_record_count`
- `segment_count`
- `pii_mask_count`
- `exact_dedup_count`
- `fuzzy_dedup_count`
- `fuzzy_dedup_ratio`
- `segmentation_latency_ms`

Operator failures must be typed and explainable without raw logs. Required
failure codes are:

- `DATASET_INGEST_UNSUPPORTED_SOURCE`
- `DATASET_INGEST_PARSE_FAILED`
- `DATASET_INGEST_EMPTY_SOURCE`
- `DATASET_INGEST_PII_POLICY_INVALID`
- `DATASET_INGEST_DEDUP_POLICY_INVALID`
- `DATASET_INGEST_SEGMENTATION_POLICY_INVALID`
- `DATASET_INGEST_UNSAFE_PATH`

## U1.2.2 Dataset Versions, Retry, And Quality

The second unit turns cleaned segments into versioned dataset artifacts. A
dataset version directory is rooted under the workspace dataset artifact root:

```text
datasets/
  <dataset-id>/
    versions/
      <version-id>/
        dataset-version.json
        manifest.json
        samples.jsonl
        valid.jsonl
        failed-segments.jsonl
        quality-summary.json
        ingest-receipt.json
```

`manifest.json`, `samples.jsonl`, and `valid.jsonl` keep the existing Melix
training or evaluation package contracts. `dataset-version.json` is the version
index consumed by CLI, Desktop, training, evaluation, export, and reports.

The dataset version schema is `melix.dataset_version.v1` and must include:

- `dataset_id`
- `version_id`
- `created_at`
- `workspace_project_id`
- `workspace_manifest_path`
- `source_receipt_path`
- `source_file_count`
- `source_inventory`
- `source_record_count`
- `segment_count`
- `mode`
- `generator_model`
- `output_kind`
- `output_format`
- `train_count`
- `validation_count`
- `failed_count`
- `successful_segment_ids`
- `failed_segment_ids`
- `quality_summary_path`
- `package_manifest_path`
- `samples_path`
- `validation_samples_path`
- `failed_segments_path`
- `metrics`

`quality-summary.json` uses schema `melix.dataset_quality_summary.v1` and must
include:

- `dataset_id`
- `version_id`
- `score`
- `grade`
- `success_rate`
- `failed_count`
- `train_count`
- `validation_count`
- `pii_mask_count`
- `dedup_ratio`
- `mean_output_length`
- `p95_output_length`
- `policy_id`
- `review_notes`
- `blocking_reasons`
- `metrics`

Failed-only retry consumes an existing `dataset-version.json` and
`failed-segments.jsonl`, writes a new version id, and reuses successful samples
by reference or copy without regenerating or rewriting their content. The retry
receipt must prove this with:

- `base_version_id`
- `retry_version_id`
- `input_failed_segment_count`
- `retry_success_count`
- `retry_failed_count`
- `reused_successful_sample_count`
- `rewritten_successful_sample_count` fixed at `0`
- `failed_retry_success_rate`

Required failure codes are:

- `DATASET_VERSION_MANIFEST_INVALID`
- `DATASET_VERSION_OUTPUT_EXISTS`
- `DATASET_VERSION_SOURCE_RECEIPT_MISSING`
- `DATASET_VERSION_FAILED_SEGMENTS_MISSING`
- `DATASET_RETRY_BASE_VERSION_INVALID`
- `DATASET_RETRY_WOULD_REWRITE_SUCCESS`
- `DATASET_QUALITY_SUMMARY_BLOCKED`

## Operator Surfaces

CLI and Desktop must read the same receipts and manifests. The planned CLI
shape is:

```bash
melix dataset prepare ingest \
  --workspace-project-id support-chat-workspace \
  --workspace-manifest path/to/workspace-manifest.json \
  --input path/to/raw-inputs \
  --output-dir path/to/prepared-ingest \
  --dataset-preparation-id support-chat-prep-v1 \
  --output path/to/dataset-ingest-receipt.json \
  --pii-mask true \
  --exact-dedup true \
  --fuzzy-dedup true \
  --segmentation true \
  --segmentation-strategy paragraph \
  --json
```

```bash
melix dataset prepare version \
  --workspace-manifest path/to/workspace-manifest.json \
  --ingest-receipt path/to/ingest-receipt.json \
  --dataset-id support-chat \
  --output-root path/to/datasets \
  --version-id support-chat-v1 \
  --mode chat \
  --generator-model melix.local.dataset-versioner.v1 \
  --output-kind training \
  --output-format chat_messages \
  --validation-ratio 0.2 \
  --json
```

```bash
melix dataset prepare retry-failed \
  --workspace-manifest path/to/workspace-manifest.json \
  --dataset-version path/to/dataset-version.json \
  --output-root path/to/datasets \
  --version-id support-chat-v2 \
  --generator-model melix.local.dataset-versioner.v1 \
  --json
```

```bash
melix dataset prepare list-versions \
  --workspace-manifest path/to/workspace-manifest.json \
  --dataset-id support-chat \
  --output-root path/to/datasets \
  --json
```

Desktop should display source counts, segment counts, PII mask count, dedup
counts, version history, failed retry status, and quality grade from these
machine-readable artifacts. It must not parse raw worker logs for normal
operator explanations.

Reports should attach `ingest-receipt.json`, `dataset-version.json`, and
`quality-summary.json` by path in run evidence when a dataset version feeds
training, evaluation, export, or release evidence.

## Unit Issue Coverage

#1495 is complete when:

- fixtures cover text, PDF text fixture, DOCX text fixture, markdown, code,
  JSONL, JSON array, CSV, and TSV inputs;
- each cleaning control can be enabled and inspected independently;
- the ingest receipt records source counts, segment counts, mask counts, dedup
  counts, strategy labels, typed failures, and metrics;
- CLI and Desktop decode the same receipt schema.

The #1495 implementation slice adds `scripts/dataset_preparation_ingest.py`,
`worker.productization.dataset_preparation.prepare_dataset_ingest(...)`,
`melix dataset prepare ingest`, and a Desktop receipt decoder/runner method.
The first slice supports UTF-8 local files, extracted `.pdf.txt` and
`.docx.txt` fixtures, JSONL, JSON arrays, CSV, and TSV. It records typed
unsupported-source and empty-source failures in `operator_failures` while
keeping parse and policy-specific failure codes reserved for deeper parser and
policy validation follow-ups.

The #1496 implementation slice adds an offline deterministic dataset versioner
on top of the #1495 ingest receipt. `prepare_dataset_version(...)` reads
`segments.jsonl`, writes `datasets/<dataset-id>/versions/<version-id>/`, and
materializes `dataset-version.json`, `manifest.json`, `samples.jsonl`,
`valid.jsonl`, `failed-segments.jsonl`, `quality-summary.json`, and a local
copy of `ingest-receipt.json`. First-slice generation is local and
schema-backed: every successful segment becomes a deterministic
`prompt_completion` or `chat_messages` training row, while explicit
`fail_segment_ids` provide a reproducible failure path for tests and operator
retry. `retry_failed_dataset_version(...)` reads the base version manifest and
failed-segment file, copies successful sample rows unchanged into a new version,
regenerates only failed segment ids, and writes `dataset-retry-receipt.json`
with `rewritten_successful_sample_count` fixed at `0`. `list_dataset_versions(...)`
reads version manifests from the dataset root, sorts by `created_at` and
`version_id`, and records listing latency. The matching operator surface adds
`melix dataset prepare version`, `retry-failed`, and `list-versions`, plus
Desktop decoders for dataset version, retry receipt, and quality summary states.
Report evidence consumes the same schema-backed paths by rendering
`dataset_version_path`, `dataset_quality_summary_path`, and
`dataset_ingest_receipt_path` artifact rows when they appear in run evidence.

#1496 is complete when:

- dataset version directories and `dataset-version.json` are deterministic;
- quality summaries are schema-backed and reportable;
- failed-only retry creates a new version while proving successful samples were
  not rewritten;
- dataset version listing is sorted by version metadata and has a latency
  metric;
- CLI, Desktop, and reports consume the same schema-backed artifacts.

## Verification Plan

U1.2.1 verification should include:

- Python fixture tests for source parsing, PII masking, exact dedup, fuzzy
  dedup, segmentation, and typed failures.
- Swift CLI parser and runner tests for `dataset prepare ingest`.
- Desktop decoding tests for the ingest receipt and typed failures.
- Changed-line coverage for touched Python and Swift paths.
- A metrics report containing ingest throughput, segment count, PII mask count,
  exact dedup count, fuzzy dedup ratio, and segmentation latency.

U1.2.2 verification should include:

- Python fixture tests for dataset version creation, deterministic listing,
  quality summary, failed-segment files, and failed-only retry.
- Swift CLI parser and runner tests for `dataset prepare version` and
  `dataset prepare retry-failed`.
- Desktop decoding tests for dataset version rows, retry receipts, and quality
  summary states.
- Report/export fixture tests that attach dataset artifacts to run evidence.
- A metrics report containing dataset version listing latency, failed retry
  success rate, quality scoring latency, generated sample count, and failed
  sample count.

## Metrics Report For This Planning Slice

This issue is documentation-only. Runtime metrics are `N/A` for this commit
because no executable ingest, retry, or quality-scoring path changes in #1494.
The required measurement points are defined above and must be implemented by
#1495 and #1496 before their runtime changes are complete.
