# Issue 2188 Workspace Ingest Privacy Detector

## Goal

Land the next executable privacy-policy slice for workspace ingestion by applying
the shared deterministic privacy detector to dataset source records before
deduplication and segmentation, while emitting machine-readable privacy detector
evidence without scanning content inside diagnostics bundle writers.

## Scope

- Add an explicit workspace ingest detector mode with `off`, `redact`, and
  `block` behavior.
- Wire the detector into `prepare_dataset_ingest(...)` after source records are
  read and before PII masking, deduplication, and segmentation.
- Emit an aggregate `melix.privacy_detector_receipt.v1` object and a matching
  `melix.privacy_audit_counter.v1` counter in the dataset ingest receipt.
- Keep raw sensitive spans, raw source text, and raw secret values out of
  receipts, operator failures, diagnostics metadata, and CLI output.
- Align the Python pattern detector with the Swift detector for quoted secret
  assignments, optional whitespace around `=`, unquoted token punctuation, and
  case-insensitive Hugging Face token prefixes. Unquoted assignment detection
  preserves semicolon statement separators instead of redacting into the next
  statement.
- Extend the dataset ingest CLI with the same detector mode control.

## Non-Goals

- No model-backed detector, NER detector, or external classifier.
- No default-on policy change for all workspace ingest flows.
- No diagnostics bundle content scanning; diagnostics may only surface receipts
  or complete namespaced metadata supplied by callers.
- No protobuf schema change.
- No remote document fetching or OCR/parser change.

## Architecture

`worker.productization.privacy_policy_receipts` owns the canonical receipt
shape and deterministic pattern detector. This slice keeps that ownership and
adds an aggregate helper so dataset ingest can summarize many source-record
decisions into one stable receipt.

`worker.productization.dataset_preparation.prepare_dataset_ingest(...)` remains
the source-reading boundary. After `_iter_source_records(...)` returns records,
ingest applies the detector when the request mode is `redact` or `block`.
Redact mode replaces sensitive spans in each record before existing PII masking,
deduplication, and segmentation run. Block mode stops before segment artifacts
are written, records a typed operator failure, cleans up partial output if
needed, and returns a blocked ingest receipt.

The dataset ingest receipt gains:

- `privacy_detector_receipts`: a list containing the aggregate detector receipt.
- `privacy_audit_counters`: a list containing the aggregate detector audit
  counter.

When the detector is off, the receipt still includes a passed aggregate receipt
with `policy_mode: off`, zero matches, and a passed counter. This keeps the
receipt contract stable for CLI, Desktop, reports, and future diagnostics
consumers. Off mode must not scan source records or enter the detector
aggregation helper, and reports zero detector latency because no detector pass
ran.

## Operator Controls

The Python request object adds `privacy_detector_mode`, defaulting to `off`.
The CLI adds `--privacy-detector-mode off|redact|block`. Unknown programmatic
values normalize to `off`; the CLI rejects unknown values through argparse.

## Failure Behavior

In `block` mode, any detector match produces a typed operator failure:

- `code`: `DATASET_INGEST_PRIVACY_DETECTOR_BLOCKED`
- `reason`: `privacy_detector_blocked`
- `detail`: count and category summary only; no raw source text or raw matched
  span.

The returned receipt keeps `source_inventory` populated from the records already
read, reports zero segments, and leaves `segments.jsonl` absent.

## Performance Probes And Metrics

Measurement points:

- source record detector pass latency inside ingest;
- aggregate match and category counts;
- existing ingest throughput and segmentation latency metrics;
- import overhead on default/off and unrelated dataset listing/source scan
  paths, which must not eager-load privacy detector regex or workspace preflight
  modules before they are needed.
- source-record scan probe stability, with garbage collection isolated from
  the timed source enumeration loop so Path-heavy sample cleanup does not
  dominate p95 measurements.

Success metrics:

- changed-scope automated coverage at least 95 percent before commit;
- no raw sensitive spans in receipts, operator failures, or CLI JSON;
- block mode avoids writing `segments.jsonl`;
- repository pre-commit scoped performance report shows no in-scope regression,
  or explicitly reports no matching probes.

## Verification

- Focused Python tests for detector regex parity.
- Focused Swift tests for the shared pattern detector statement-separator
  behavior and Hugging Face token casing.
- Focused Python tests for dataset ingest redact mode, block mode, off mode,
  stable receipt fields, and CLI mode propagation.
- Focused Python import test proving `dataset_preparation` does not eager-load
  the privacy detector module for default/off and unrelated listing paths.
- Focused source-record probe tests proving the probe restores the caller's GC
  state and still rejects changed source count, ordering, source-kind
  classification, and byte accounting.
- Focused diagnostics tests remain unchanged because bundle writers must not
  scan content.
- Full pre-commit gate before opening the PR.
