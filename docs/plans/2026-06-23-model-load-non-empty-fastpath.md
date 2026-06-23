# Model load trust non-empty source fast path

## Goal

Avoid allocating stripped copies while resolving model-load trust policy source
fields on the hot path.

## Slice

- Keep model-load trust behavior unchanged for non-empty, empty, and
  whitespace-only policy sources.
- Replace the helper-level `strip()` truthiness check with an allocation-free
  non-empty/`isspace()` guard.
- Validate through the registered `model-load-config-json-bytes` PR-scoped
  performance probe because the affected helper is exercised by
  `resolve_model_load_trust_policy`.

## Verification

- Focused model-load trust tests, including the helper fallback behavior.
- Changed-scope coverage for `model_load_trust.py` and related tests.
- Local Linux registered probe before/after comparison.
