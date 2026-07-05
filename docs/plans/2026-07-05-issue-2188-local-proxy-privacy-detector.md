# Issue 2188 Local Proxy Privacy Detector Integration

## Goal

Land the next executable privacy-policy slice by applying the deterministic
pattern privacy detector to local proxy text-generation requests before they
reach worker execution, while keeping the policy explicitly opt-in.

## Scope

- Add a Swift detector receipt shape equivalent to
  `melix.privacy_detector_receipt.v1`.
- Add a deterministic Swift pattern detector for common email and secret-like
  spans, matching the Python helper's receipt contract.
- Gate local proxy prompt scanning behind `MELIX_PRIVACY_DETECTOR_MODE`.
- Support `redact` mode by replacing matched text in worker request message
  text parts before dispatch.
- Support `block` mode by returning a sanitized 400 response before worker
  dispatch.
- Attach `melix.privacy.detector.*` and `melix.privacy.audit.*` metadata to
  dispatched worker requests when the opt-in detector runs.
- Keep raw matched values, raw prompt text, and raw sensitive spans out of
  detector receipts, audit counters, and block responses.

## Non-Goals

- No protobuf schema changes.
- No default-on privacy mutation.
- No model-backed NER detector.
- No workspace document-ingest integration in this slice.
- No diagnostics bundle content scanning.
- No streaming framing changes beyond using the already translated worker
  request with redacted message text.

## Operator Setting

`MELIX_PRIVACY_DETECTOR_MODE` is the explicit opt-in switch for this slice:

- unset, empty, `off`, or `disabled`: detector is not run and request behavior is
  unchanged;
- `redact`: matched sensitive text is replaced with stable placeholders before
  the worker request is dispatched;
- `block`: matched sensitive text blocks the local proxy request before worker
  dispatch and returns a sanitized error response.

Other values fail closed to disabled for this slice.

## Receipt Metadata

When the detector runs, local proxy text requests attach:

- `melix.privacy.detector.schema_version`
- `melix.privacy.detector.surface`
- `melix.privacy.detector.route_scope`
- `melix.privacy.detector.detector_id`
- `melix.privacy.detector.policy_id`
- `melix.privacy.detector.policy_mode`
- `melix.privacy.detector.action`
- `melix.privacy.detector.categories`
- `melix.privacy.detector.match_count`
- `melix.privacy.detector.redacted_span_count`
- `melix.privacy.detector.blocked_reason`
- `melix.privacy.detector.confidence_source`
- `melix.privacy.detector.raw_sensitive_span_count`
- `melix.privacy.detector.raw_text_included`
- `melix.privacy.audit.*`

The metadata is category/count evidence only. It must not contain raw matched
values or prompt snippets.

## Performance Probes And Metrics

- Measurement points:
  - detector execution over already-materialized local proxy message text;
  - worker request metadata enrichment;
  - block response construction.
- Success metrics:
  - changed-scope coverage at least 95 percent;
  - zero raw sensitive spans in metadata and block responses;
  - no worker dispatch in block mode;
  - no behavior change while the opt-in setting is unset.
- Probe overhead:
  - bounded regular-expression scans over request-local text parts;
  - small metadata dictionary writes.
- PR-scoped performance:
  - use the repository pre-commit scoped performance report. If no registered
    probe matches the changed files, report the no-probe result explicitly.

## Verification

- Swift red test proving an enabled detector redacts a local proxy worker
  request and emits metadata without leaking raw matched values.
- Swift tests for block mode, disabled mode, and clean pass-through metadata.
- Focused Swift test package run for `OpenAIHandlerTests`.
- Relevant Python receipt parser tests to prove metadata remains compatible with
  diagnostics enrichment.
- Full repository pre-commit gate before PR update.
