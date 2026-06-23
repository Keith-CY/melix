# Issue 2188 Log Privacy Redactors

## Goal

Land the first privacy-policy executable slice for operator-facing logs by adding
a shared Python worker redactor and routing existing local-job remediation
receipts through it.

## Scope

- Add `worker.productization.log_privacy.LogPrivacyRedactor` with deterministic
  redaction for:
  - credential-bearing URLs: userinfo, query strings, and fragments;
  - Hugging Face-style tokens;
  - common token environment assignments;
  - email addresses.
- Replace the local redaction helper in local-job remediation with the shared
  redactor.

## Non-Goals

- No model-backed NER.
- No full route privacy policy engine.
- No proxy CORS/admin envelope changes.
- No startup failure excerpt redaction in this slice.
- No UI sink escaper in this slice.

## Verification

- Focused Python tests for the shared redactor and local-job remediation
  receipts.
- Changed-scope coverage for the touched Python files.
- Scoped performance report for the changed scope.
