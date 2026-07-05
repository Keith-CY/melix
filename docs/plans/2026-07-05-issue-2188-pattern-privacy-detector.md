# Issue 2188 Pattern Privacy Detector Receipts

## Goal

Land the next executable privacy-policy slice by adding a deterministic pattern
detector receipt that can redact or block common sensitive spans before local
proxy, workspace-ingest, and diagnostics surfaces export evidence.

## Scope

- Add a Python `PrivacyDetectorReceipt` shape with schema version
  `melix.privacy_detector_receipt.v1`.
- Add a deterministic pattern detector for common contact and secret-like spans.
- Return redacted text, a detector receipt, and a compatible
  `PrivacyAuditCounter` from one helper.
- Support policy modes for `redact` and `block`, with clean text passing
  through unchanged.
- Add namespaced diagnostics metadata support so callers that already performed
  detection can preserve the detector receipt in `effective-config.json`.
- Keep raw sensitive text, matched substrings, and raw input text out of
  receipts and exported diagnostics.

## Non-Goals

- No new protobuf schema.
- No model-backed NER or cloud moderation service.
- No live route integration for OpenAI-compatible proxy requests, workspace
  source import, streaming, or document ingest.
- No scanning of diagnostics bundle content during bundle writing.
- No mutation of user files or persisted workspace artifacts.

## Receipt Shape

`PrivacyDetectorReceipt` records:

- `schema_version`
- `surface`
- `route_scope`
- `detector_id`
- `policy_id`
- `policy_mode`
- `action` (`passed`, `redacted`, or `blocked`)
- `categories`
- `match_count`
- `redacted_span_count`
- `blocked_reason`
- `confidence_source`
- `raw_sensitive_span_count`
- `raw_text_included`

The receipt is evidence-only: it reports categories and counts, not raw matched
values or snippets.

## Architecture

The Python worker keeps the canonical helper beside the existing
`NetworkFetchPolicyReceipt` and `PrivacyAuditCounter` helpers. The detector is
pure and deterministic: it receives caller-provided text, applies a fixed set of
patterns, and returns sanitized output plus machine-readable evidence. Clean
inputs emit a passed receipt with zero spans. Redaction mode replaces matched
spans with stable category placeholders. Block mode returns an empty text body
and records a typed blocked reason.

Serving diagnostics can synthesize a `privacy_detector_receipts` list from
complete namespaced metadata in the same way it already preserves
network-fetch receipts. Bundle writing must not inspect prompt, completion,
document, or artifact content to create detector receipts; callers must attach
complete metadata after they have already evaluated policy.

## Performance Probes And Metrics

- Measurement points:
  - detector helper execution on caller-provided text;
  - diagnostics effective-config enrichment from metadata.
- Target metrics:
  - no network I/O, filesystem scans, model inference, or bundle-content scans;
  - zero raw sensitive spans in exported receipts;
  - changed-scope coverage at least 95 percent.
- Probe overhead:
  - bounded regex scans over already-materialized text;
  - small JSON construction for receipt and counter payloads.
- PR-scoped performance:
  - use the repository pre-commit scoped performance report. If no registered
    probe matches the changed files, report the no-probe result explicitly.

## Verification

- Focused Python tests for redaction, block mode, clean pass-through, metadata
  derivation, incomplete metadata rejection, and diagnostics enrichment.
- Adjacent Python tests for privacy receipts and serving diagnostics.
- Full repository pre-commit gate before PR update.
