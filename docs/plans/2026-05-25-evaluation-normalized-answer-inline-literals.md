# Evaluation Normalized Answer Inline Literals

## Scope

Optimize the Python evaluation answer-normalization hot path by avoiding generic extraction helpers for cases that `_normalized_answer` has already proven to be simple single-letter options or full numeric literals.

## Registered Probe

The affected path is covered by the existing PR-scoped probe `evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`.

- `test_command`: focused evaluation helper tests plus PR-scoped performance registry tests.
- `coverage_command`: focused coverage for `evaluation_core.py`, evaluation tests, and PR-scoped performance tests.
- `probe_command`: command-json probe measuring answer-normalization elapsed time plus numeric/option extractor calls.

## Implementation Plan

1. Keep `_parse_candidate_for_expected` and multi-token extraction behavior unchanged.
2. Inline single-character option normalization in `_normalized_answer` after wrapping is stripped.
3. Add a narrow numeric-literal normalizer for values that already match `_looks_like_numeric`.
4. Update the focused regression test to assert the normalized-answer fast path preserves output while skipping both extraction helpers for literal inputs.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux. CI remains the authoritative registered PR-scoped performance gate after the PR is opened.
