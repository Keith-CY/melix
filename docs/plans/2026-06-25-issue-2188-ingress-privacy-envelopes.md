# Issue 2188 Ingress Privacy Envelopes

## Goal

Land a focused privacy-policy receipt slice for malformed OpenAI-compatible
request ingress by ensuring JSON decode and schema validation failures expose a
stable sanitized envelope instead of raw submitted payload content.

## Scope

- Add a shared ingress privacy receipt to OpenAI handler validation errors.
- Apply the receipt to JSON decode/schema validation failures for:
  - `POST /v1/chat/completions`;
  - `POST /v1/completions`;
  - `POST /v1/responses`;
  - `POST /v1/messages`;
  - `POST /v1/embeddings`.
- Keep status codes, existing error codes, and worker-dispatch boundaries
  unchanged.
- Report only the request-target path in privacy receipts; query strings and
  fragments are treated as sensitive ingress material and omitted.
- Add sentinel tests proving error bodies do not contain submitted email, token,
  path, query, fragment, or local implementation fingerprints.

## Non-Goals

- No full privacy policy engine.
- No model-backed entity detector.
- No raw HTTP parser privacy receipt changes in this slice.
- No workspace-ingest mutation receipts in this slice.
- No ingress timeout receipt changes in this slice.

## Architecture

The Swift control plane owns local-proxy request admission and OpenAI-compatible
payload decoding. This slice keeps validation decisions in the existing handler
paths, derives route identity from the request-target path, and attaches a typed
`privacy_receipt` to client-visible validation errors. The receipt reports
route, phase, field, and redaction policy while omitting raw payload fragments
and request-target query or fragment material.

## Performance Probes And Metrics

- Measurement point: handler-level pre-dispatch validation path.
- Target metric: malformed ingress requests return before worker dispatch.
- Probe overhead: `N/A`; the receipt is built only on 4xx validation errors and
  does not add runtime-path instrumentation.
- Changed-scope coverage target: at least 95 percent for touched Swift lines.

## Verification

- Focused Swift tests for `OpenAIHandlerTests` ingress privacy envelopes.
- Changed-scope Swift coverage for touched files.
- Full repository gate through the pre-commit hook before PR merge.
