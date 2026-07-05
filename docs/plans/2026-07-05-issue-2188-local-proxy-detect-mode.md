# Issue 2188 Local Proxy Detect Mode

## Goal

Add an explicit audit-only local proxy privacy detector mode so operators can
collect privacy receipts for text requests before choosing redact or block
enforcement.

## Architecture

`MELIX_PRIVACY_DETECTOR_MODE=detect` enables the same deterministic local proxy
text detector used by `redact` and `block`, but does not mutate the worker
request and does not reject the request. Matched text produces a sanitized
`melix.privacy_detector_receipt.v1` metadata receipt with `policy_mode=detect`
and `action=detected`. The paired `melix.privacy_audit_counter.v1` records the
request as passed because model-visible content was allowed through unchanged.

The detector remains local, deterministic, and opt-in. The default remains off,
unsupported environment values still disable the detector, and raw matched text
must not appear in metadata, metrics, or diagnostics-derived receipts.

## Scope

- Accept `MELIX_PRIVACY_DETECTOR_MODE=detect` for OpenAI-compatible local proxy
  text requests.
- Extend the Swift `PatternPrivacyDetector` mode normalization and receipt
  action mapping.
- Keep `redact`, `block`, disabled, and clean-text opt-in behavior unchanged.
- Document the audit-only mode in the serving diagnostics evidence runbook.

## Non-Goals

- No workspace-ingest CLI mode change.
- No model-backed or NER detector.
- No default-on policy change.
- No diagnostics bundle content scanning.
- No new protobuf schema.

## Verification

1. Add a RED Swift test proving `detect` leaves raw request text unchanged while
   emitting sanitized receipt/counter metadata.
2. Run the focused Swift test before implementation and confirm it fails.
3. Implement mode support in the detector and local proxy environment gate.
4. Re-run the focused Swift tests for local proxy privacy detection.
5. Run `git diff --check`.
6. Run the versioned pre-commit hook before commit and record the scoped
   performance/coverage report path.

## Metrics

This slice does not change hot-path request parsing or worker dispatch. The
request-time detector still runs only when the explicit environment mode is set.
The scoped performance report should select any registered Swift gateway probes
for the touched files and report `Status: ok`, zero regressions, and zero
verification failures. Changed-line coverage for the touched Swift scope must be
at least 95 percent before commit.
