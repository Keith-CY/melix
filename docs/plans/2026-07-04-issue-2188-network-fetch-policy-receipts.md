# Issue 2188 Network Fetch Policy Receipts

## Goal

Land the next executable privacy-policy slice for local proxy and workspace
ingest safety evidence by defining stable network-fetch and aggregate privacy
audit receipt shapes, then wiring those shapes into existing diagnostics
surfaces without adding network I/O.

## Scope

- Add `NetworkFetchPolicyReceipt` and `PrivacyAuditCounter` helpers for Python
  workspace and diagnostics code.
- Classify URL candidates as public, loopback, link-local, private, local, or
  invalid without performing DNS or HTTP fetches.
- Accept an already-resolved IP from the caller so DNS-rebinding-style host
  changes can be recorded as blocked private-network targets.
- Add a local workspace-ingest preflight network-fetch receipt that proves the
  current ingest path is local-only and does not dereference remote URLs.
- Add namespaced diagnostics metadata support so proxy or worker surfaces can
  emit network-fetch and privacy-audit receipts into
  `effective-config.json`.
- Extend the Swift local proxy external-media URL admission path to expose the
  same receipt and audit-counter schema for blocked unsafe URLs and to forward
  accepted remote-media decisions through worker request metadata.
- Keep raw URLs, query strings, fragments, userinfo, and private-network
  targets out of exported diagnostics and client-visible error bodies.

## Non-Goals

- No new protobuf schema.
- No DNS resolver, HTTP client, redirect follower, or remote URL fetch.
- No change to local proxy Host/Origin security policy behavior.
- No change to remote provider base-URL storage or provider health probes.
- No model-backed privacy detector or NER.

## Receipt Shapes

`NetworkFetchPolicyReceipt` uses schema version
`melix.network_fetch_policy_receipt.v1` and records:

- `surface`
- `route_scope`
- `action` (`passed` or `blocked`)
- `url_class`
- `url_scheme`
- `host_class`
- `resolved_ip`
- `resolved_ip_class`
- `redirect_hops_checked`
- `blocked_reason`
- `redacted_url`
- `raw_url_included`
- `fetch_attempted`

`PrivacyAuditCounter` uses schema version `melix.privacy_audit_counter.v1` and
records:

- `surface`
- `route_scope`
- `blocked_count`
- `redacted_count`
- `passed_count`
- `raw_sensitive_span_count`

## Architecture

The Python helper owns the canonical JSON shape used by workspace preflight and
serving diagnostics bundle writing. The helper performs deterministic parsing
and IP classification only; any caller that performs DNS resolution must pass the
resolved address into the helper. Private, loopback, link-local, and invalid
targets are blocked before fetch, and their receipts carry only classified or
redacted target evidence.

Workspace preflight emits a local-only `network_fetch_policy` receipt and a
`privacy_audit_counters` list because dataset ingest embeds the preflight receipt
before reading sources. This gives the workspace-ingest path a machine-readable
privacy receipt without changing ingest execution.

Serving diagnostics preserves explicit receipt payloads and can synthesize them
from complete namespaced metadata. Incomplete metadata remains nested in the
original effective config so bundle writing does not fabricate partial privacy
evidence.

The Swift local proxy external-media URL admission path keeps its existing
admission behavior. It adds the shared network-fetch receipt shape to blocked
image-edit URL errors and forwards accepted URL-admission metadata into worker
request `ext`, making downstream diagnostics able to surface the proxy decision.

## Performance Probes And Metrics

- Measurement points:
  - workspace preflight receipt construction;
  - serving diagnostics effective-config enrichment;
  - local proxy external-media URL admission.
- Target metrics:
  - no network I/O during receipt construction;
  - no raw sensitive spans in exported receipts;
  - changed-scope coverage at least 95 percent.
- Probe overhead:
  - workspace and diagnostics overhead is small JSON construction on existing
    receipt paths;
  - local proxy overhead is only on external-media URL admission or 4xx refusal
    paths.
- PR-scoped performance:
  - use the repository pre-commit scoped performance report. If no registered
    probe matches all touched files, report the no-probe result explicitly.

## Verification

- Focused Python tests for network-fetch classification, redaction, privacy
  counters, workspace preflight receipt shape, dataset ingest embedding, and
  serving diagnostics metadata derivation.
- Focused Swift tests for external-media local proxy receipts and metadata.
- Full repository pre-commit gate before PR update.
