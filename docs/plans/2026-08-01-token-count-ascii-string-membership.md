# Token Count ASCII String Membership Fast Path

## Scope

This Python-only performance slice is limited to
`worker.runtime.token_counting.whitespace_token_count()` and its deterministic
vision callers.

## Registered Probes

The affected helper is covered by registered PR-scoped probes in
`infra/perf/pr_scoped_probes.json` with focused `test_command`,
`coverage_command`, and `probe_command` entries:

- `deterministic-ocr-token-count-scan`
- `deterministic-vlm-completion-token-scan`

The OCR probe is the primary local Linux metric for this slice, and GitHub
Actions PR-scoped performance remains the merge gate.

## Optimization Slice

The existing ASCII fast path already avoids `str.isspace()` per character. This
slice narrows only the ASCII whitespace container from a `frozenset[str]` to the
six-character ASCII whitespace string used by the same membership test. For
single-character membership in the hot loop this removes hash lookup overhead
while preserving the exact ASCII whitespace set and keeping the Unicode fallback
path unchanged.

## Verification Plan

Run the focused deterministic vision token-count tests, changed-scope coverage,
and both registered probes locally on Linux before opening the PR. Hosted
PR-scoped performance must complete successfully before merge.

## Linux Verification Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
