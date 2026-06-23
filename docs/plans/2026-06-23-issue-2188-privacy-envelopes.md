# Issue 2188 Privacy Envelopes

## Goal

Land the next executable privacy-policy slice for local proxy error envelopes by
ensuring Host and Origin security rejections do not echo attacker-controlled
header values.

## Scope

- Keep local server Host and Origin admission behavior unchanged.
- Replace the rejected `header_value` response field with a typed
  `privacy_receipt` that records:
  - schema version;
  - privacy surface;
  - rejected header name;
  - rejection reason;
  - redaction status;
  - local server security policy receipt.
- Add regression tests with sentinel email, token, path, query, and fragment
  values in rejected Host and Origin headers.

## Non-Goals

- No full privacy policy engine.
- No model-backed detection or NER.
- No changes to accepted CORS behavior.
- No changes to auth-session state receipts.
- No workspace-ingest mutation receipts in this slice.

## Architecture

The local server security policy remains responsible for deciding whether a Host
or Origin header is admitted. The HTTP gateway owns the client-visible error
envelope. For rejected local proxy requests, the envelope should expose stable
operator evidence without returning the raw rejected header value. Diagnostics
can still report the effective local server security policy through the existing
policy receipt.

## Verification

- Focused Swift tests for `OpenAIHandlerTests` local server security rejection
  privacy envelopes.
- Changed-scope coverage for the touched Swift files.
- Scoped performance report for the changed scope.
- Full local gate before commit through the repository pre-commit hook.
