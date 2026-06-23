# Issue 2188 UI Sink Escaper

## Goal

Land the second executable privacy-policy slice for operator-facing UI sinks by
adding a shared Swift `UISinkEscaper` contract and invariant tests.

## Scope

- Add `UISinkEscaper` in `MelixControlPlaneCore` for sink-specific escaping:
  - HTML text content;
  - quoted HTML attribute values;
  - quoted CSS string values;
  - CSS `url(...)` tokens with unsafe scheme blocking;
  - URL path/query component values.
- Add repository-owned invariant tests that prove hostile user text cannot break
  out of those sinks with raw tags, quotes, controls, `url(...)`, or unsafe
  schemes.
- Document how the escaper differs from `RichOutputSanitizer`.

## Non-Goals

- No full privacy receipt schema.
- No model-backed NER.
- No broad UI call-site migration in this slice.
- No behavior changes to model context, worker truth, benchmark artifacts, or
  chat transcript storage.

## Architecture

`RichOutputSanitizer` removes unsafe rich-output fragments before operator
rendering. `UISinkEscaper` is a lower-level boundary helper for code that must
interpolate already selected text into HTML, CSS, or URL syntax. It lives in the
Swift control-plane core target so the macOS app and any future HTML/evidence
renderers can share one implementation.

The CSS URL helper returns a complete quoted `url("...")` token. It blocks
non-HTTP(S) schemes by returning `url("about:blank")`, while relative paths and
HTTP(S) URLs are escaped as CSS strings inside the quoted token.

## Verification

- Focused Swift tests for `UISinkEscaper`.
- Changed-scope coverage for the touched Swift files.
- Scoped performance report for the changed scope.
- Full local gate before commit: `make swift-test`, `make py-test`, and
  `make integration-test` through the repository pre-commit hook.
